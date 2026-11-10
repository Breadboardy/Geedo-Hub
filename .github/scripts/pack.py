#!/usr/bin/env python3
"""Pack .geedo.json (from Studio) into .geedo.bin, then merge into manifest.
Preserves existing manifest entries (like imported animations).

The Hub's copy of tools/pack.py from the source repo, for the publish action:
same format, same fields. Every entry carries both hashes - the short one is
the cache's identity and what the website shows, the full one is what a robot
checks a download against. sign_manifests.py signs the result."""
import json, os, glob, hashlib, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gda      # the packed frame format, beside this file

W, H = 128, 64

def pack_frame(pixels):
    out = bytearray(1024)
    for page in range(8):
        for x in range(W):
            b = 0
            for bit in range(8):
                y = page*8 + bit
                if pixels[y*W + x]: b |= (1 << bit)
            out[page*W + x] = b
    return bytes(out)

def pack(in_path, out_path):
    """A Studio export -> the robot's file: GDA2, frames packed (gda.py)."""
    with open(in_path) as f: data = json.load(f)
    frames = data['frames']
    fps = int(data.get('fps', 8))
    loop, pp = bool(data.get('loop', True)), bool(data.get('pp', False))
    blob = gda.encode([pack_frame(f['pixels']) for f in frames], fps, loop,
                      [int(f.get('dur', 1)) for f in frames], pp=pp)
    with open(out_path, 'wb') as f: f.write(blob)
    return len(blob), len(frames)

def sha256hex(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f: h.update(f.read())
    return h.hexdigest()

def sha8(path):
    return sha256hex(path)[:8]

def main():
    # this file lives in .github/scripts/, two levels below the Hub root
    hub = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ex_dir = os.path.join(hub, 'animations', 'examples')
    out_dir = os.path.join(hub, 'animations', 'bin')
    os.makedirs(out_dir, exist_ok=True)
    mpath = os.path.join(hub, 'animations', 'manifest.json')

    try:
        with open(mpath) as f: manifest = json.load(f)
    except Exception:
        manifest = {"version": 1, "animations": []}

    try:
        with open(os.path.join(hub, 'animations', 'index.json')) as f: idx = json.load(f)
        by_id = {a['id']: a for a in idx['animations']}
    except Exception:
        by_id = {}

    # What the manifest already says about an entry outranks index.json: the
    # maker's name, the category, the date it was published, what it remixes.
    # Repacking the bytes must never wipe the record of who drew it and when.
    prev = {a['id']: a for a in manifest.get('animations', [])}

    # Handed file paths, pack only those (the publish action hands it the one
    # it just saved); handed nothing, pack every example.
    jpaths = sys.argv[1:] or sorted(glob.glob(os.path.join(ex_dir, '*.geedo.json')))

    packed = []
    for jpath in jpaths:
        name = os.path.basename(jpath).replace('.geedo.json', '')
        bin_path = os.path.join(out_dir, name + '.bin')
        size, fc = pack(jpath, bin_path)
        h = sha8(bin_path)
        meta = {**by_id.get(name, {}), **prev.get(name, {})}
        entry = {
            "id": name,
            "name": meta.get('name', name),
            "author": meta.get('author', 'Geedo'),
            "file": "bin/" + name + ".bin",
            "size": size,
            "hash": h,
            "sha256": sha256hex(bin_path),
            "visibility": meta.get('visibility', 'public'),
            "frames": fc,
            "category": meta.get('category', 'studio'),
        }
        for k in ('published_at', 'remix_of', 'issue'):
            if k in meta: entry[k] = meta[k]
        packed.append(entry)
        print(f"  {name}: {size} bytes  [{h}]")

    packed_ids = {a['id'] for a in packed}
    manifest['animations'] = [a for a in manifest['animations'] if a['id'] not in packed_ids] + packed

    with open(mpath, 'w') as f:
        json.dump(manifest, f, indent=2)
        f.write('\n')
    print(f"\nPacked {len(packed)} animations, manifest now has {len(manifest['animations'])} total")

if __name__ == '__main__':
    main()
