#!/usr/bin/env python3
"""
Import existing Geedo animations from /home/callum/Geedo/Animation/ (C source format)
and pack them into .geedo.bin files for the hub.

These C files are produced by old Geedo Animator v2 and contain:
  #define FRAME_COUNT N
  #define FRAME_DELAY ms
  const unsigned char frame_0[] PROGMEM = { 0x..., 0x..., ... };
  ...

Each frame is exactly 1024 bytes in SSD1306 page format — same as our .bin format.
"""
import os, re, json, hashlib, glob, sys

HUB = '/home/callum/Geedo-Hub'
SRC = '/home/callum/Geedo/Animation'
OUT_BIN = os.path.join(HUB, 'animations', 'bin')
OUT_JSON = os.path.join(HUB, 'animations', 'imported')
os.makedirs(OUT_BIN, exist_ok=True)
os.makedirs(OUT_JSON, exist_ok=True)

# folders to skip
SKIP = {'TESTING (animations)', 'Cloud animations', 'Kamoji'}

def parse_c(path):
    """Return (frame_count, frame_delay_ms, frames_bytes) or None if not parsable."""
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()
    m = re.search(r'#define\s+FRAME_COUNT\s+(\d+)', text)
    if not m: return None
    frame_count = int(m.group(1))
    m = re.search(r'#define\s+FRAME_DELAY\s+(\d+)', text)
    frame_delay = int(m.group(1)) if m else 100

    frames = []
    # Find all frame_N arrays in order
    pattern = re.compile(r'frame_(\d+)\s*\[\]\s*PROGMEM\s*=\s*\{([^}]*)\}', re.S)
    found = {}
    for m in pattern.finditer(text):
        idx = int(m.group(1))
        body = m.group(2)
        hex_vals = re.findall(r'0x[0-9a-fA-F]+', body)
        bytes_ = bytes(int(h, 16) for h in hex_vals)
        if len(bytes_) != 1024:
            return None  # bad frame
        found[idx] = bytes_
    if len(found) != frame_count:
        return None
    for i in range(frame_count):
        if i not in found: return None
        frames.append(found[i])
    return frame_count, frame_delay, frames

def safe_name(s):
    return re.sub(r'[^A-Za-z0-9_]+', '_', s).strip('_').lower()

def pack_bin(out_path, fps, frames, loop=True, pp=False):
    fc = len(frames)
    flags = (1 if loop else 0) | (2 if pp else 0)
    durations = bytes([1] * fc)  # 1 frame each at fps
    header = b'GDA1' + bytes([1, fc, fps, flags]) + durations
    body = b''.join(frames)
    with open(out_path, 'wb') as f:
        f.write(header + body)
    return len(header) + len(body)

def sha8(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f: h.update(f.read())
    return h.hexdigest()[:8]

results = []
for root, dirs, files in os.walk(SRC):
    # filter dirs
    dirs[:] = [d for d in dirs if d not in SKIP]
    for fname in files:
        if fname.endswith('.h') or fname.endswith('.c') or '.' not in fname:
            path = os.path.join(root, fname)
            parsed = parse_c(path)
            if not parsed:
                continue
            fc, fd, frames = parsed
            # frame delay in ms -> approximate fps
            fps = max(1, min(60, round(1000 / max(1, fd))))
            cat = os.path.basename(root)
            anim_id = safe_name(f"{cat}_{fname}")
            out_path = os.path.join(OUT_BIN, anim_id + '.bin')
            size = pack_bin(out_path, fps, frames)
            h = sha8(out_path)
            results.append({
                "id": anim_id,
                "name": fname.strip(),
                "category": cat,
                "author": "breadboard",
                "file": "bin/" + anim_id + ".bin",
                "size": size,
                "hash": h,
                "visibility": "public",
                "frames": fc,
            })
            print(f"  {cat}/{fname}: {fc} frames @ {fps}fps -> {size}b [{h}]")

# Update manifest.json (keep existing example animations too)
manifest_path = os.path.join(HUB, 'animations', 'manifest.json')
try:
    with open(manifest_path) as f:
        manifest = json.load(f)
except Exception:
    manifest = {"version": 1, "animations": []}

# Replace any with same id
ids = {a['id'] for a in results}
manifest['animations'] = [a for a in manifest['animations'] if a['id'] not in ids] + results
with open(manifest_path, 'w') as f:
    json.dump(manifest, f, indent=2)

print(f"\nImported {len(results)} animations into manifest")
print(f"Manifest now has {len(manifest['animations'])} total")
