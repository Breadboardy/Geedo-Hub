#!/usr/bin/env python3
"""Parse a publish-animation issue, download the attached .geedo.json,
save it into animations/examples/ and run pack.py to update bin/ + manifest.

Outputs via GITHUB_OUTPUT:
  success=true|false
  anim_id=<id>
  frames=<n>
  size=<bytes>
  hash=<sha8>
  error=<msg>
"""
import os, re, sys, json, urllib.request, hashlib, subprocess, pathlib, datetime

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / 'animations' / 'examples'
BIN_DIR  = ROOT / 'animations' / 'bin'
MANIFEST = ROOT / 'animations' / 'manifest.json'

def out(**kv):
    p = os.environ.get('GITHUB_OUTPUT')
    if not p:
        for k, v in kv.items(): print(f"::set-output name={k}::{v}")
        return
    with open(p, 'a') as f:
        for k, v in kv.items():
            f.write(f"{k}={v}\n")

def fail(msg):
    print(f"FAIL: {msg}", file=sys.stderr)
    out(success='false', error=msg)
    sys.exit(0)  # do not fail the step — let workflow comment

def safe_id(s):
    s = re.sub(r'[^A-Za-z0-9_-]+', '_', s).strip('_').lower()
    return s or 'anim'

def main():
    body   = os.environ.get('ISSUE_BODY', '') or ''
    title  = os.environ.get('ISSUE_TITLE', '') or ''
    author = (os.environ.get('ISSUE_AUTHOR', '') or '').strip()
    owner  = (os.environ.get('REPO_OWNER', '') or '').strip()

    # 1. Find a .geedo.json attachment URL in the issue body.
    # Accept any github user-attachments / repo-files / amazonaws asset URL ending with .geedo.json
    pattern = re.compile(
        r'https://[^\s\)\]]+?\.geedo\.json',
        re.IGNORECASE,
    )
    matches = pattern.findall(body)
    if not matches:
        fail('no .geedo.json attachment found in issue body — drag the file into the issue and re-label')
    url = matches[0]
    print(f"Downloading: {url}")

    # 2. Download (public attachment, no auth needed for public repos)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'geedo-bot'})
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
    except Exception as e:
        fail(f'download failed: {e}')

    # 3. Validate JSON
    try:
        data = json.loads(raw.decode('utf-8'))
    except Exception as e:
        fail(f'attachment is not valid JSON: {e}')

    if 'frames' not in data or not isinstance(data['frames'], list) or not data['frames']:
        fail('JSON has no frames[]')
    for i, f in enumerate(data['frames']):
        if 'pixels' not in f or not isinstance(f['pixels'], list):
            fail(f'frame {i} missing pixels[]')
        if len(f['pixels']) != 128 * 64:
            fail(f'frame {i} wrong pixel count: {len(f["pixels"])}')

    # 4. Pick an id from JSON name (or fall back to issue title)
    raw_name = (data.get('name') or title.replace('Publish:', '').strip() or 'anim').strip()
    aid = safe_id(raw_name)
    # Avoid clobbering reserved names
    if aid.startswith('animations_boot_'):
        aid = 'user_' + aid
    # Namespace non-owner submissions to prevent clobbering each other
    if author and owner and author.lower() != owner.lower():
        aid = 'user_' + safe_id(author) + '_' + aid

    EXAMPLES.mkdir(parents=True, exist_ok=True)
    json_path = EXAMPLES / (aid + '.geedo.json')
    with open(json_path, 'w') as f:
        json.dump(data, f)
    print(f"Wrote {json_path}")

    # 5. Run pack.py
    res = subprocess.run(
        ['python3', str(ROOT / 'tools' / 'pack.py')],
        capture_output=True, text=True
    )
    print(res.stdout)
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        fail(f'pack.py failed: {res.stderr.strip()[:200]}')

    # 6. Pull the new manifest entry to surface stats; also stamp it
    try:
        with open(MANIFEST) as f: m = json.load(f)
        entry = next((a for a in m['animations'] if a['id'] == aid), None)
    except Exception:
        entry = None
    if not entry:
        fail('pack ran but no manifest entry created')

    # Stamp published_at + author into the entry, then resave
    entry['published_at'] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    if author:
        entry['author'] = author
    with open(MANIFEST, 'w') as f: json.dump(m, f, indent=2)

    out(
        success='true',
        anim_id=aid,
        frames=str(entry.get('frames', 0)),
        size=str(entry.get('size', 0)),
        hash=str(entry.get('hash', '')),
    )
    print(f"OK: {aid} ({entry.get('frames')} frames, {entry.get('size')}b, hash {entry.get('hash')})")

if __name__ == '__main__':
    main()
