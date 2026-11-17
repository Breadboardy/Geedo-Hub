#!/usr/bin/env python3
"""A community animation, from a GitHub issue to the Hub - in two steps.

  check    Runs when a submission is opened or edited. Gets the drawing,
           checks it the way the robot would, draws a GIF of it, and writes
           a report for the comment. Nothing is published.
  publish  Runs when a person adds the `approved` label. Does the checks
           again, packs the animation into the robot's format, adds it to
           the manifest with the maker's name and the date, and leaves the
           signing and the push to the workflow.

Why two steps: every Geedo in the world downloads whatever is on this list,
and most of the people looking at those screens are kids. So a person looks
at every animation before it goes out - the bot's job is to make that look
easy (a picture, the numbers, a clear yes/no on the technical rules), not to
skip it.

A drawing reaches an issue one of two ways:

  by hand        the maker saved a .geedo.json in the Studio and dragged it
                 into the "Publish an animation" form, with a GitHub account.
  from the Hub's server
                 the maker pressed Publish in the Studio, signed in with a
                 Geedo account. hub_inbox.py collected it and filed the issue,
                 which carries a marker - the drawing's id on the server and
                 the fingerprint of its bytes - instead of a file. The bytes
                 are fetched from the server named in assets/hub.json (the
                 repository's own file, never anything typed into an issue)
                 and must match that fingerprint, so what is published is
                 what was looked at.

Outputs, via GITHUB_OUTPUT:
  ok=true|false      the technical checks passed
  report=<markdown>  the comment body (multi-line)
  anim_id=<id>       (publish) what it was published as
  hub_id=<id>        the drawing's id on the Hub's server, if it came from there
  preview=true       (check) preview.gif was written next to this script's cwd
"""
import os, re, sys, json, base64, hashlib, urllib.request, urllib.error, urllib.parse, subprocess, pathlib, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gda, gif

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / 'animations' / 'examples'
MANIFEST = ROOT / 'animations' / 'manifest.json'
HUB_FILE = ROOT / 'assets' / 'hub.json'

MAX_FRAMES = 96          # the format holds 255, but his shelf is small
MAX_PACKED = 32 * 1024   # bytes, after packing - a full scene is 6 to 13 KB
MAX_FPS = 30             # the panel cannot draw faster anyway
MAX_DOWNLOAD = 8 << 20   # a 96-frame Studio file is under 2 MB
FLASH_MAX_PER_S = 3      # the robot's own rule (WCAG 2.3.1); he refuses more
FLASH_SWING_PX = 2048    # a quarter of the screen


def out(**kv):
    p = os.environ.get('GITHUB_OUTPUT')
    if not p:
        for k, v in kv.items():
            print(f"[output] {k}={v!r}")
        return
    with open(p, 'a') as f:
        for k, v in kv.items():
            v = str(v)
            if '\n' in v:
                f.write(f"{k}<<GEEDO_EOF\n{v}\nGEEDO_EOF\n")
            else:
                f.write(f"{k}={v}\n")


class Refused(Exception):
    """A submission the rules say no to - reported kindly, never a crash."""


def safe_id(s):
    s = re.sub(r'[^A-Za-z0-9_-]+', '_', s).strip('_').lower()
    return s[:40].strip('_') or 'anim'


def field(body, label):
    """The value under a '### Label' heading of an issue-form body."""
    m = re.search(r'^###\s+' + re.escape(label) + r'\s*\n+(.*?)(?=^###\s|\Z)', body, re.S | re.M)
    if not m:
        return ''
    v = m.group(1).strip()
    return '' if v.lower() in ('_no response_', 'no response') else v


def attachment_url(body):
    # Only files GitHub itself is hosting for this issue. An arbitrary URL
    # would have the runner fetch whatever a stranger typed.
    m = re.search(r'https://github\.com/[^\s\)\]"]+?\.geedo\.json', body, re.I)
    return m.group(0) if m else None


def download(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'geedo-bot'})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read(MAX_DOWNLOAD + 1)
    if len(raw) > MAX_DOWNLOAD:
        raise Refused(f"the file is bigger than {MAX_DOWNLOAD >> 20} MB - is it really a Studio file?")
    return raw


def parse(raw):
    try:
        data = json.loads(raw.decode('utf-8'))
    except Exception as e:
        raise Refused(f"the file is not a Studio file (not valid JSON: {e})")
    return vet(data)


def vet(data):
    """The shape of a drawing, whichever way it arrived."""
    frames = data.get('frames') if isinstance(data, dict) else None
    if not isinstance(frames, list) or not frames:
        raise Refused("the file has no frames in it")
    if len(frames) > MAX_FRAMES:
        raise Refused(f"{len(frames)} frames is more than Geedo's shelf has room for - keep it to {MAX_FRAMES}")
    for i, f in enumerate(frames):
        px = f.get('pixels') if isinstance(f, dict) else None
        if not isinstance(px, list) or len(px) != 128 * 64:
            raise Refused(f"frame {i + 1} is not a 128 by 64 picture")
        d = f.get('dur', 1)
        if not isinstance(d, int) or not 1 <= d <= 255:
            raise Refused(f"frame {i + 1} has a hold of {d!r}; it must be a whole number from 1 to 255")
    fps = data.get('fps', 8)
    if not isinstance(fps, int) or not 1 <= fps <= MAX_FPS:
        raise Refused(f"{fps!r} frames per second - Geedo plays 1 to {MAX_FPS}")
    return data


# ---- a drawing that came through the Hub's server -----------------------------
# The marker hub_inbox.py leaves in the issue it files: the drawing's id on
# the server, and the SHA-256 of its bytes as they were when it was checked.
HUB_MARK = re.compile(r'<!--\s*geedo-hub:\s*([0-9a-f]{32})\s+([0-9a-f]{64})\s*-->')


def hub_api():
    """Where the Hub's server is: assets/hub.json, in this repository. Empty
    when there is none. (GEEDO_HUB_API is for the tests, which run a server on
    the same computer; the workflows never set it.)"""
    api = os.environ.get('GEEDO_HUB_API') or ''
    if not api:
        try:
            with open(HUB_FILE) as f:
                api = json.load(f).get('api') or ''
        except Exception:
            api = ''
        if not re.fullmatch(r'https://[A-Za-z0-9.-]+(?::\d+)?(?:/[A-Za-z0-9._~/-]*)?', api.strip()):
            return ''
    return api.strip().rstrip('/')


class HubSaid(Exception):
    """The server answered, with a no."""
    def __init__(self, status, error):
        super().__init__(f"{status} {error}")
        self.status, self.error = status, error


def hub_call(path, payload=None, key=True):
    """One request to the Hub's server. With `key`, as the Hub's workflow -
    and the key goes to the address in assets/hub.json and nowhere else."""
    api = hub_api()
    if not api:
        raise Refused("this drawing came through a Geedo account, and the Hub does not say where its "
                      "server is (`assets/hub.json`)")
    headers = {'User-Agent': 'geedo-bot', 'Content-Type': 'application/json'}
    if key:
        secret = os.environ.get('GEEDO_HUB_KEY', '')
        if not secret:
            raise Refused("this drawing came through a Geedo account, and the Hub has no key for its "
                          "server (the `GEEDO_HUB_KEY` secret)")
        headers['Authorization'] = 'Bearer ' + secret
    req = urllib.request.Request(api + path, headers=headers, method='GET' if payload is None else 'POST',
                                 data=None if payload is None else json.dumps(payload).encode())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read(MAX_DOWNLOAD))
    except urllib.error.HTTPError as e:
        try:
            said = json.loads(e.read() or b'{}').get('error') or ''
        except Exception:
            said = ''
        raise HubSaid(e.code, said)


def unpage(page):
    """The robot's page frame -> the Studio's list of 8192 pixels."""
    px = [0] * (128 * 64)
    for p in range(8):
        for x in range(128):
            b = page[p * 128 + x]
            for bit in range(8):
                if b >> bit & 1:
                    px[(p * 8 + bit) * 128 + x] = 1
    return px


def from_hub(sid, sha):
    """The drawing `sid` from the Hub's server, as the Studio would have saved
    it, with who sent it. Its bytes must be the ones the marker names."""
    try:
        sub = hub_call('/admin/file?id=' + urllib.parse.quote(sid))
    except HubSaid as e:
        if e.status == 410:
            raise Refused("its maker took this one back, so there is nothing to publish - close the issue")
        if e.status == 404:
            raise Refused("the Hub's server does not know this drawing")
        raise Refused(f"the Hub's server would not hand the drawing over ({e})")
    try:
        blob = base64.b64decode(sub.get('bin') or '', validate=True)
    except Exception:
        raise Refused("the Hub's server sent something that is not a drawing")
    if hashlib.sha256(blob).hexdigest() != sha:
        raise Refused("the drawing on the Hub's server is not the one that was checked when this was "
                      "handed in, so it will not be published")
    try:
        a = gda.decode(blob)
    except ValueError as e:
        raise Refused(f"the drawing is not a file Geedo can play ({e})")
    if a['fmt'] != 2:
        raise Refused("the drawing is not in the robot's packed format")
    maker, mkey = str(sub.get('maker') or '').strip(), str(sub.get('maker_key') or '')
    if not maker or len(maker) > 20 or not re.fullmatch(r'[a-z0-9_]{3,20}', mkey):
        raise Refused("the Hub's server sent a maker name the Hub does not accept")
    data = vet({'name': str(sub.get('name') or '').strip()[:40] or 'anim',
                'fps': a['fps'], 'loop': a['loop'], 'pp': a['pp'],
                'frames': [{'pixels': unpage(f), 'dur': int(d)} for f, d in zip(a['frames'], a['durs'])]})
    if sub.get('remix_of'):
        data['remix_of'] = str(sub['remix_of'])
    return data, {'id': sid, 'maker': maker, 'maker_key': mkey}


def md(text):
    """Somebody's words, safe to put in a comment: no markdown of theirs
    takes effect and no @name of theirs sends anybody a notification."""
    return re.sub(r'([\\`*_\[\]()!#<>|~])', r'\\\1', str(text)).replace('@', '@\u200b')


def account_holds(maker):
    """True if `maker` is the name of a Geedo account (so a hand-filed
    submission using it wants a second look). False if not, or if there is
    no server to ask, or it did not answer."""
    if not hub_api():
        return False
    try:
        r = hub_call('/maker?name=' + urllib.parse.quote(maker), key=False)
        return r.get('why') == 'taken'
    except Exception:
        return False


def pages(data):
    """The Studio's pixel lists -> the robot's page frames."""
    res = []
    for f in data['frames']:
        px = f['pixels']
        page = bytearray(1024)
        for p in range(8):
            for x in range(128):
                b = 0
                for bit in range(8):
                    if px[(p * 8 + bit) * 128 + x]:
                        b |= 1 << bit
                page[p * 128 + x] = b
        res.append(bytes(page))
    return res


def flash_worst_second(frames, durs, fps, loop):
    """The robot's rule, the numbers the robot uses: a large transition is a
    frame-to-frame swing of more than a quarter of the screen, and more than
    three inside any one second is refused. A loop's last frame hands to its
    first, so that step counts too."""
    base = 1000 // max(1, fps)
    seq = list(zip(frames, durs))
    if loop and len(seq) > 1:
        seq = seq + seq[:1]
    t, prev, swings = 0, None, []
    for fb, d in seq:
        n = gda.lit(fb)
        if prev is not None and abs(n - prev) > FLASH_SWING_PX:
            swings.append(t)
        prev = n
        t += base * max(1, d)
    worst = 0
    for s in swings:
        worst = max(worst, sum(1 for g in swings if s <= g < s + 1000))
    return worst


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'check'
    body = os.environ.get('ISSUE_BODY', '') or ''
    title = os.environ.get('ISSUE_TITLE', '') or ''
    author = (os.environ.get('ISSUE_AUTHOR', '') or '').strip()
    owner = (os.environ.get('REPO_OWNER', '') or '').strip()
    number = os.environ.get('ISSUE_NUMBER', '')

    lines = []
    hub = None                      # who sent it, if it came through the Hub's server
    try:
        mark = HUB_MARK.search(body)
        if mark:
            data, hub = from_hub(mark.group(1), mark.group(2))
            out(hub_id=hub['id'])
        else:
            url = attachment_url(body)
            if not url:
                raise Refused("there is no `.geedo.json` file in the issue - in Studio press **Publish**, "
                              "save the file, then drag it into the issue's text box and press Update comment")
            data = parse(download(url))

        frames = pages(data)
        durs = [int(f.get('dur', 1)) for f in data['frames']]
        fps = int(data.get('fps', 8))
        loop = bool(data.get('loop', True))
        pp = bool(data.get('pp', False))
        blob = gda.encode(frames, fps, loop, durs, pp=pp)
        if len(blob) > MAX_PACKED:
            raise Refused(f"packed, this is {len(blob) // 1024} KB; Geedo's shelf is small, so the "
                          f"limit is {MAX_PACKED // 1024} KB - fewer frames, or simpler ones")
        worst = flash_worst_second(frames, durs, fps, loop)
        if worst > FLASH_MAX_PER_S:
            raise Refused(f"it flashes {worst} times in one second. More than {FLASH_MAX_PER_S} big "
                          "flashes a second can hurt people, and Geedo refuses to play it - slow "
                          "the flashing down or make the changing part smaller")

        if hub:
            # From a Geedo account: the name is the one the maker typed in the
            # Studio, and the maker is the account - whatever the issue says.
            raw_name = data['name']
            maker, is_owner = hub['maker'], False
            aid = 'user_' + hub['maker_key'] + '_' + safe_id(raw_name)
        else:
            # The name: the form's field first, then what the Studio saved, then
            # the title. The maker: the form's field, or the GitHub name.
            raw_name = field(body, 'Name') or data.get('name') or re.sub(r'^publish:\s*', '', title, flags=re.I) or 'anim'
            raw_name = raw_name.strip()[:40]
            # The repository's owner IS the Geedo team: what they hand in is one of
            # his own, under the maker name "Geedo", unless the form says otherwise.
            is_owner = bool(author and owner and author.lower() == owner.lower())
            maker = (field(body, 'Maker name') or ('Geedo' if is_owner else author) or 'someone').strip()[:32]
            maker = re.sub(r'[^\w .\-]', '', maker).strip() or (author or 'someone')
            aid = safe_id(raw_name)
            if aid.startswith('animations_boot_') or aid.startswith('animations_'):
                aid = 'user_' + aid
            if not is_owner:
                aid = 'user_' + safe_id(author or 'someone') + '_' + aid
        with open(MANIFEST) as f:
            manifest = json.load(f)
        there = next((a for a in manifest['animations'] if a['id'] == aid), None)
        exists = there is not None
        if hub and there and (there.get('author') or '') != maker:
            raise Refused(f"`{aid}` is already an animation by {md(there.get('author') or 'somebody else')}, "
                          "so this one needs another name")
        remix_of = data.get('remix_of') or ''
        remix_of = safe_id(remix_of)[:40] if remix_of else ''

        lines.append("**Looks good.** It plays the way Geedo would play it:")
        lines.append("")
        lines.append(f"- **{md(raw_name)}** by **{md(maker)}** · {len(frames)} frame{'s' if len(frames) != 1 else ''} at {fps} fps"
                     f"{' · loops' if loop else ' · plays once'}{' · ping-pong' if pp else ''}")
        lines.append(f"- {len(blob):,} bytes packed · busiest second has {worst} big flash{'es' if worst != 1 else ''} (limit {FLASH_MAX_PER_S})")
        if remix_of:
            lines.append(f"- a remix of `{remix_of}`")
        if hub:
            lines.append("- sent from the Studio, signed in as that maker")
        elif not is_owner and account_holds(maker):
            lines.append(f"- ⚠ **“{md(maker)}” is the name of a Geedo account, and this did not come from that "
                         "account.** Ask for another maker name unless you know it is the same person.")
        lines.append(f"- will be published as `{aid}`" + (" — **that id already exists and would be replaced**" if exists else ""))

        if mode == 'check':
            with open('preview.gif', 'wb') as f:
                f.write(gif.encode(frames, fps, durs, scale=3, loop=True, pingpong=pp))
            out(ok='true', preview='true', anim_id=aid)
        else:
            EXAMPLES.mkdir(parents=True, exist_ok=True)
            json_path = EXAMPLES / (aid + '.geedo.json')
            data['name'] = raw_name
            with open(json_path, 'w') as f:
                json.dump(data, f)
            res = subprocess.run(['python3', str(ROOT / '.github' / 'scripts' / 'pack.py'), str(json_path)],
                                 capture_output=True, text=True)
            print(res.stdout)
            if res.returncode != 0:
                print(res.stderr, file=sys.stderr)
                raise Refused(f"packing failed: {res.stderr.strip()[:200]}")
            with open(MANIFEST) as f:
                manifest = json.load(f)
            entry = next((a for a in manifest['animations'] if a['id'] == aid), None)
            if not entry:
                raise Refused("packed, but the manifest did not pick it up")
            entry['name'] = raw_name
            entry['author'] = maker
            entry['category'] = 'studio' if is_owner else 'community'
            entry['published_at'] = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            entry['issue'] = int(number) if str(number).isdigit() else number
            if remix_of:
                entry['remix_of'] = remix_of
            with open(MANIFEST, 'w') as f:
                json.dump(manifest, f, indent=2)
                f.write('\n')
            out(ok='true', anim_id=aid)
        out(report='\n'.join(lines))
        print('\n'.join(lines))
    except Refused as e:
        msg = f"**Not yet:** {e}."
        print(msg, file=sys.stderr)
        out(ok='false', report=msg)
    except Exception as e:                      # a bug in here, not in the submission
        msg = f"**The bot tripped over:** `{type(e).__name__}: {e}` — that is on us, not on the animation."
        print(msg, file=sys.stderr)
        out(ok='false', report=msg)


if __name__ == '__main__':
    main()
