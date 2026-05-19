#!/usr/bin/env python3
"""
Import Eating/ static-bitmap animations.

Each file in /home/callum/Geedo/Animation/Eating/ contains a single
PROGMEM bitmap (Adafruit row-major MSB-first, e.g. 72x61), with a comment
like:  // 'epd_bitmap_IMG', 72x61px

Convert each to a 1-frame .geedo.bin (128x64 SSD1306 page format), centered.
Add as category=eating to manifest.json.
"""
import os, re, json, hashlib

HUB = '/home/callum/Geedo-Hub'
SRC = '/home/callum/Geedo/Animation/Eating'
OUT_BIN = os.path.join(HUB, 'animations', 'bin')
os.makedirs(OUT_BIN, exist_ok=True)

def parse_bitmap(text):
    """Return (w, h, bytes) or None."""
    m = re.search(r"//\s*'[^']*',\s*(\d+)\s*x\s*(\d+)\s*px", text)
    if not m: return None
    w, h = int(m.group(1)), int(m.group(2))
    arr = re.search(r'PROGMEM\s*=\s*\{([^}]*)\}', text, re.S)
    if not arr: return None
    hex_vals = re.findall(r'0x[0-9a-fA-F]+', arr.group(1))
    bytes_ = bytes(int(h, 16) for h in hex_vals)
    expected = ((w + 7) // 8) * h
    if len(bytes_) != expected:
        print(f"  bad bytes: got {len(bytes_)} expected {expected}")
        return None
    return w, h, bytes_

def render_centered(w, h, src_bytes):
    """Row-major MSB-first bitmap -> 128x64 framebuffer.
    Source uses 1=white (the food drawings are inverse: 0xff=blank).
    Detect inverted images and flip so the food shows as ON pixels."""
    bytes_per_row = (w + 7) // 8
    # decode to bool grid
    grid = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            byte = src_bytes[y * bytes_per_row + x // 8]
            bit = (byte >> (7 - (x % 8))) & 1
            grid[y][x] = bit
    # detect inverted (majority 1 == background)
    total = sum(sum(row) for row in grid)
    if total > (w * h) // 2:
        for y in range(h):
            for x in range(w):
                grid[y][x] ^= 1
    # paint into 128x64 fb (centered)
    fb = [[0] * 128 for _ in range(64)]
    ox = (128 - w) // 2
    oy = (64 - h) // 2
    for y in range(h):
        for x in range(w):
            yy, xx = oy + y, ox + x
            if 0 <= yy < 64 and 0 <= xx < 128:
                fb[yy][xx] = grid[y][x]
    return fb

def fb_to_pages(fb):
    """128x64 fb -> 1024 bytes SSD1306 page format (8 pages * 128 cols, LSB=top)."""
    out = bytearray(1024)
    for page in range(8):
        for col in range(128):
            b = 0
            for bit in range(8):
                if fb[page * 8 + bit][col]:
                    b |= (1 << bit)
            out[page * 128 + col] = b
    return bytes(out)

def safe_name(s):
    return re.sub(r'[^A-Za-z0-9_]+', '_', s).strip('_').lower()

def sha8(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f: h.update(f.read())
    return h.hexdigest()[:8]

results = []
for fname in sorted(os.listdir(SRC)):
    path = os.path.join(SRC, fname)
    if not os.path.isfile(path): continue
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()
    parsed = parse_bitmap(text)
    if not parsed:
        print(f"  skip {fname} (not a bitmap)")
        continue
    w, h, by = parsed
    fb = render_centered(w, h, by)
    frame = fb_to_pages(fb)

    aid = "eating_" + safe_name(fname)
    out_path = os.path.join(OUT_BIN, aid + '.bin')
    # header: GDA1 + ver + frame_count + fps + flags ; then durations[fc] ; then pixels[fc*1024]
    header = b'GDA1' + bytes([1, 1, 10, 0x01])  # ver=1, frames=1, fps=10, flags=loop
    durations = bytes([1])
    with open(out_path, 'wb') as f:
        f.write(header + durations + frame)
    sz = os.path.getsize(out_path)
    hsh = sha8(out_path)
    results.append({
        "id": aid,
        "name": fname.strip(),
        "category": "eating",
        "author": "breadboard",
        "file": "bin/" + aid + ".bin",
        "size": sz,
        "hash": hsh,
        "visibility": "public",
        "frames": 1,
    })
    print(f"  {fname}: {w}x{h} -> {sz}b [{hsh}]")

# Merge into manifest
manifest_path = os.path.join(HUB, 'animations', 'manifest.json')
with open(manifest_path) as f:
    manifest = json.load(f)
ids = {a['id'] for a in results}
manifest['animations'] = [a for a in manifest['animations'] if a['id'] not in ids] + results
with open(manifest_path, 'w') as f:
    json.dump(manifest, f, indent=2)

print(f"\nImported {len(results)} eating animations")
print(f"Manifest now has {len(manifest['animations'])} total")
