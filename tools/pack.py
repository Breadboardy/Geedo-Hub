#!/usr/bin/env python3
"""Pack .geedo.json (from Studio) into .geedo.bin, then merge into manifest.
Preserves existing manifest entries (like imported animations)."""
import json, os, glob, hashlib

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
    with open(in_path) as f: data = json.load(f)
    frames = data['frames']
    fc = len(frames)
    fps = int(data.get('fps', 8))
    flags = (1 if data.get('loop', True) else 0) | (2 if data.get('pp', False) else 0)
    durations = bytes(min(255, int(f.get('dur', 1))) for f in frames)
    header = b'GDA1' + bytes([1, fc, fps, flags]) + durations
    body = b''.join(pack_frame(f['pixels']) for f in frames)
    with open(out_path, 'wb') as f: f.write(header + body)
    return len(header) + len(body), fc

def sha8(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f: h.update(f.read())
    return h.hexdigest()[:8]

def main():
    base = os.path.dirname(os.path.abspath(__file__))
    hub = os.path.dirname(base)
    ex_dir = os.path.join(hub, 'animations', 'examples')
    out_dir = os.path.join(hub, 'animations', 'bin')
    os.makedirs(out_dir, exist_ok=True)
    mpath = os.path.join(hub, 'animations', 'manifest.json')

    # Load existing manifest
    try:
        with open(mpath) as f: manifest = json.load(f)
    except Exception:
        manifest = {"version": 1, "animations": []}

    # Load index.json for metadata
    try:
        with open(os.path.join(hub, 'animations', 'index.json')) as f: idx = json.load(f)
        by_id = {a['id']: a for a in idx['animations']}
    except Exception:
        by_id = {}

    packed = []
    for jpath in sorted(glob.glob(os.path.join(ex_dir, '*.geedo.json'))):
        name = os.path.basename(jpath).replace('.geedo.json', '')
        bin_path = os.path.join(out_dir, name + '.bin')
        size, fc = pack(jpath, bin_path)
        h = sha8(bin_path)
        meta = by_id.get(name, {})
        packed.append({
            "id": name,
            "name": meta.get('name', name),
            "author": meta.get('author', 'breadboard'),
            "file": "bin/" + name + ".bin",
            "size": size,
            "hash": h,
            "visibility": meta.get('visibility', 'public'),
            "frames": fc,
            "category": meta.get('category', 'studio'),
        })
        print(f"  {name}: {size} bytes  [{h}]")

    # Merge: keep entries we didn't just pack, append new ones
    packed_ids = {a['id'] for a in packed}
    manifest['animations'] = [a for a in manifest['animations'] if a['id'] not in packed_ids] + packed

    with open(mpath, 'w') as f: json.dump(manifest, f, indent=2)
    print(f"\nPacked {len(packed)} animations, manifest now has {len(manifest['animations'])} total")

if __name__ == '__main__':
    main()
