#!/usr/bin/env python3
"""A community animation, from a GitHub issue to the Hub - in two steps.

  check    Runs when a submission is opened or edited. Downloads the
           .geedo.json the maker attached, checks it the way the robot
           would, draws a GIF of it, and writes a report for the comment.
           Nothing is published.
  publish  Runs when a person adds the `approved` label. Does the checks
           again, packs the animation into the robot's format, adds it to
           the manifest with the maker's name and the date, and leaves the
           signing and the push to the workflow.

Why two steps: every Geedo in the world downloads whatever is on this list,
and most of the people looking at those screens are kids. So a person looks
at every animation before it goes out - the bot's job is to make that look
easy (a picture, the numbers, a clear yes/no on the technical rules), not to
skip it.

Outputs, via GITHUB_OUTPUT:
  ok=true|false      the technical checks passed
  report=<markdown>  the comment body (multi-line)
  anim_id=<id>       (publish) what it was published as
  preview=true       (check) preview.gif was written next to this script's cwd
"""
import os, re, sys, json, urllib.request, subprocess, pathlib, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gda, gif

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / 'animations' / 'examples'
MANIFEST = ROOT / 'animations' / 'manifest.json'

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
    frames = data.get('frames')
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
    try:
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

        # The name: the form's field first, then what the Studio saved, then
        # the title. The maker: the form's field, or the GitHub name.
        raw_name = field(body, 'Name') or data.get('name') or re.sub(r'^publish:\s*', '', title, flags=re.I) or 'anim'
        raw_name = raw_name.strip()[:40]
        maker = (field(body, 'Maker name') or author or 'someone').strip()[:32]
        maker = re.sub(r'[^\w .\-]', '', maker).strip() or (author or 'someone')
        aid = safe_id(raw_name)
        if aid.startswith('animations_boot_') or aid.startswith('animations_'):
            aid = 'user_' + aid
        if author and owner and author.lower() != owner.lower():
            aid = 'user_' + safe_id(author) + '_' + aid
        with open(MANIFEST) as f:
            manifest = json.load(f)
        exists = any(a['id'] == aid for a in manifest['animations'])
        remix_of = data.get('remix_of') or ''
        remix_of = safe_id(remix_of)[:40] if remix_of else ''

        lines.append("**Looks good.** It plays the way Geedo would play it:")
        lines.append("")
        lines.append(f"- **{raw_name}** by **{maker}** · {len(frames)} frame{'s' if len(frames) != 1 else ''} at {fps} fps"
                     f"{' · loops' if loop else ' · plays once'}{' · ping-pong' if pp else ''}")
        lines.append(f"- {len(blob):,} bytes packed · busiest second has {worst} big flash{'es' if worst != 1 else ''} (limit {FLASH_MAX_PER_S})")
        if remix_of:
            lines.append(f"- a remix of `{remix_of}`")
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
            entry['category'] = 'community'
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
