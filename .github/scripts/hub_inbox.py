#!/usr/bin/env python3
"""The Hub's side of publishing from the Studio.

A maker with a Geedo account presses Publish in the Studio, and the drawing
waits on the Hub's server (the address in assets/hub.json). That server can
hold a drawing but it cannot put one on a robot, and it has no way into this
repository: this script goes to it, with the GEEDO_HUB_KEY secret, from the
Hub's own workflows.

  ready                  is there a server to ask, and a key to ask it with?
  file                   collect what is waiting; check each drawing the way
                         the robot would; file it as a review issue, with a
                         preview kept for the comment; and close the issue of
                         anything its maker took back.
  comment                say what the check found on each issue just filed.
  result ID STATE [ANIM] tell the server what became of a drawing, so its
                         maker sees it in the Studio: published (and as what).
  declined               an issue was closed without being published: tell
                         the server, with the reviewer's last words as the why.

What does not change: nothing reaches a robot until a person adds the
`approved` label to the issue. That is still the only way in.
"""
import os, re, sys, json, pathlib, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gda, gif
import process_publish_issue as hub
from process_publish_issue import Refused, HubSaid, out, md

OUT = pathlib.Path('inbox_out')          # previews and reports, between the steps of one run
PER_RUN = 10                             # a flood is filed ten at a time

RULES = ("- [x] I drew this myself. It is not a character from a game, a film or a show.\n"
         "- [x] It is kind. Nothing rude, mean or scary - kids are watching these screens.\n"
         "- [x] I know a person looks at it first and might say no.")


def github(method, path, payload=None):
    """One call to GitHub's API, as this workflow run."""
    base = os.environ.get('GITHUB_API_URL', 'https://api.github.com').rstrip('/')
    repo = os.environ['GITHUB_REPOSITORY']
    req = urllib.request.Request(
        f"{base}/repos/{repo}{path}", method=method,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'], 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'geedo-bot', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def plain(text):
    """Somebody's words on one line of an issue: as code, so nothing in them
    is markdown and no @name in them is a mention."""
    return '`' + str(text).replace('`', "'").replace('\n', ' ').strip() + '`'


def issue_body(sub, data, n_bytes):
    n = len(data['frames'])
    return (f"### Name\n\n{plain(sub['name'])}\n\n"
            f"### Maker name\n\n{plain(sub['maker'])}\n\n"
            f"### The file\n\nSent from Geedo Studio, signed in with the maker's Geedo account: "
            f"{n} frame{'s' if n != 1 else ''}, {n_bytes:,} bytes packed.\n\n"
            f"<!-- geedo-hub: {sub['id']} {sub['sha256']} -->\n\n"
            f"### The rules\n\n{RULES}\n")


def already_filed():
    """Drawings that already have an open issue: {id on the server: issue}.
    If a run stopped between filing an issue and telling the server, the
    next run finds the issue here instead of filing a second one."""
    found = {}
    for it in github('GET', '/issues?labels=submission&state=open&per_page=100') or []:
        m = hub.HUB_MARK.search(it.get('body') or '')
        if m and 'pull_request' not in it:
            found[m.group(1)] = it['number']
    return found


def cmd_ready():
    api, key = hub.hub_api(), os.environ.get('GEEDO_HUB_KEY', '')
    if not api:
        print("No server: assets/hub.json has no address, so the Studio is using the hand-in-on-GitHub steps.")
    elif not key:
        print("There is a server in assets/hub.json but this repository has no GEEDO_HUB_KEY secret to ask it with.")
    out(ready='true' if api and key else 'false')


def cmd_file():
    q = hub.hub_call('/admin/queue')
    waiting, gone = q.get('items') or [], q.get('gone') or []
    print(f"{len(waiting)} waiting, {len(gone)} taken back")
    OUT.mkdir(exist_ok=True)
    filed, previews = 0, 0
    known = already_filed() if waiting else {}

    for item in waiting[:PER_RUN]:
        sid = item['id']
        if sid in known:                      # filed by a run that did not get to say so
            hub.hub_call('/admin/filed', {'id': sid, 'issue': known[sid]})
            print(f"  {sid}: already issue #{known[sid]}")
            continue
        try:
            data, who = hub.from_hub(sid, item['sha256'])
            frames = hub.pages(data)
            durs = [int(f.get('dur', 1)) for f in data['frames']]
            fps, loop, pp = int(data['fps']), bool(data['loop']), bool(data['pp'])
            blob = gda.encode(frames, fps, loop, durs, pp=pp)
            if len(blob) > hub.MAX_PACKED:
                raise Refused(f"packed, it is {len(blob) // 1024} KB and the limit is {hub.MAX_PACKED // 1024} KB")
            worst = hub.flash_worst_second(frames, durs, fps, loop)
            if worst > hub.FLASH_MAX_PER_S:
                raise Refused(f"it flashes {worst} times in one second and Geedo refuses more than {hub.FLASH_MAX_PER_S}")
        except Refused as e:
            # The server checks the same rules before it takes a drawing, so
            # this is rare: say so to the maker rather than file it.
            if 'took this one back' in str(e):
                print(f"  {sid}: taken back before it was filed")
                continue
            print(f"  {sid}: not filed - {e}")
            try:
                hub.hub_call('/admin/result', {'id': sid, 'state': 'declined', 'note': f"The Hub's check said: {e}."})
            except HubSaid:
                pass
            continue

        sub = {'id': sid, 'sha256': item['sha256'], 'name': data['name'], 'maker': who['maker']}
        title = 'Publish: ' + data['name'].replace('@', '(at)')
        issue = github('POST', '/issues', {'title': title[:120], 'body': issue_body(sub, data, len(blob)), 'labels': ['submission']})
        n = issue['number']
        hub.hub_call('/admin/filed', {'id': sid, 'issue': n})
        filed += 1
        print(f"  {sid}: issue #{n}")

        aid = 'user_' + who['maker_key'] + '_' + hub.safe_id(data['name'])
        with open(hub.MANIFEST) as f:
            there = next((a for a in json.load(f)['animations'] if a['id'] == aid), None)
        lines = ["**Looks good.** It plays the way Geedo would play it:", "",
                 f"- **{md(data['name'])}** by **{md(who['maker'])}** · {len(frames)} frame{'s' if len(frames) != 1 else ''} at {fps} fps"
                 f"{' · loops' if loop else ' · plays once'}{' · ping-pong' if pp else ''}",
                 f"- {len(blob):,} bytes packed · busiest second has {worst} big flash{'es' if worst != 1 else ''} (limit {hub.FLASH_MAX_PER_S})"]
        if data.get('remix_of'):
            lines.append(f"- a remix of `{hub.safe_id(data['remix_of'])[:40]}`")
        lines.append("- sent from the Studio, signed in as that maker")
        if there and (there.get('author') or '') != who['maker']:
            lines.append(f"- ⚠ **`{aid}` is already an animation by {md(there.get('author') or 'somebody else')}**: "
                         "this one cannot be published under that name. Close it and say so.")
        else:
            lines.append(f"- will be published as `{aid}`" + (" — **that id already exists and would be replaced**" if there else ""))
        (OUT / f"{n}.md").write_text('\n'.join(lines))
        try:
            (OUT / f"{n}.gif").write_bytes(gif.encode(frames, fps, durs, scale=3, loop=True, pingpong=pp))
            previews += 1
        except Exception as e:                # a preview that will not draw must not lose the issue
            print(f"  {sid}: no preview ({e})")

    # A drawing taken back after it was filed: its issue is closed, kindly.
    for g in gone[:PER_RUN]:
        n = g.get('issue')
        try:
            it = github('GET', f"/issues/{n}")
            if it and it.get('state') == 'open':
                github('POST', f"/issues/{n}/comments", {'body': "Its maker took this one back, so there is nothing to look at. Closing."})
                github('PATCH', f"/issues/{n}", {'state': 'closed', 'state_reason': 'not_planned'})
            hub.hub_call('/admin/result', {'id': g['id'], 'state': 'withdrawn'})
            print(f"  {g['id']}: taken back, issue #{n} closed")
        except (urllib.error.HTTPError, HubSaid) as e:
            print(f"  {g['id']}: could not close issue #{n} ({e})")

    out(filed=str(filed), previews='true' if previews else 'false')


def cmd_comment():
    repo, run = os.environ['GITHUB_REPOSITORY'], os.environ.get('GITHUB_RUN_ID', '0')
    pushed = os.environ.get('PREVIEWS_PUSHED', 'true') == 'true'
    for report in sorted(OUT.glob('*.md'), key=lambda p: int(p.stem)):
        n = report.stem
        body = report.read_text()
        if pushed and (OUT / f"{n}.gif").exists():
            body += f"\n\n![preview](https://raw.githubusercontent.com/{repo}/previews/{n}.gif?r={run})"
        body += ("\n\n---\n*A person looks at every animation before it goes on the Hub. To publish this one, add the "
                 "**approved** label. Not this one? Say why in a comment, kindly - its maker reads your last comment "
                 "in the Studio - and close the issue.*")
        github('POST', f"/issues/{n}/comments", {'body': body})
        print(f"commented on #{n}")


def cmd_result(sid, state, anim=''):
    payload = {'id': sid, 'state': state}
    if anim:
        payload['anim'] = anim
    hub.hub_call('/admin/result', payload)
    print(f"told the server: {sid} is {state}" + (f" as {anim}" if anim else ''))


def cmd_declined():
    m = hub.HUB_MARK.search(os.environ.get('ISSUE_BODY', '') or '')
    if not m:
        print("Not a drawing from the Hub's server: nobody to tell.")
        return
    n = os.environ.get('ISSUE_NUMBER', '')
    # The why: the last thing a person (not a bot) said on the issue.
    note = ''
    try:
        for c in reversed(github('GET', f"/issues/{n}/comments?per_page=100") or []):
            who = c.get('user') or {}
            if who.get('type') != 'Bot' and not str(who.get('login', '')).endswith('[bot]'):
                note = re.sub(r'\s+', ' ', c.get('body') or '').strip()[:500]
                break
    except urllib.error.HTTPError as e:
        print(f"could not read the comments ({e})")
    try:
        hub.hub_call('/admin/result', {'id': m.group(1), 'state': 'declined', 'note': note})
        print(f"told the server: {m.group(1)} was not published" + (f" - “{note}”" if note else ''))
    except HubSaid as e:
        # 404: already settled (published, or taken back). Nothing to change.
        print(f"the server did not change it ({e})")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    try:
        if cmd == 'ready':
            cmd_ready()
        elif cmd == 'file':
            cmd_file()
        elif cmd == 'comment':
            cmd_comment()
        elif cmd == 'result' and len(sys.argv) >= 4:
            cmd_result(*sys.argv[2:5])
        elif cmd == 'declined':
            cmd_declined()
        else:
            print(__doc__)
            return 2
    except Refused as e:
        print(f"Stopped: {e}.", file=sys.stderr)
        return 1
    except HubSaid as e:
        print(f"The Hub's server said no: {e}.", file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
