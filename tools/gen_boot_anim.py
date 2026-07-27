#!/usr/bin/env python3
"""Generate Geedo's power-on animation.

Writes firmware/sketch/boot_anim_progmem.h (played from flash the instant he
powers up, before WiFi) and animations/bin/animations_boot_boot_animation.bin.

On a 1-bit panel there is no brightness - but an ordered dither fakes it. A
sparse pattern reads as a dim glow and a dense one as near-white, so ramping
dither density gives a genuine power-surge rather than a hard on/off.

The sequence ends on the idle eyes at their exact geometry from eyes.h, so
the boot hands over to the wandering face with no visible seam.
"""
import math, random, sys, zlib, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
W, H = 128, 64
FPS = 20                       # base period 50 ms; durations are multiples

# must match eyes.h
EYE_W, EYE_H, EYE_R, GAP = 30, 42, 7, 18
CXL, CXR, CY = 64 - (EYE_W + GAP) // 2, 64 + (EYE_W + GAP) // 2, 32

BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]

rnd = random.Random(20260727)


def blank():
    return [[0] * W for _ in range(H)]


def dither(fb, level, mask=None):
    """Fill with an ordered dither at `level` (0..1). `mask(x,y)->bool` limits
    it to a region. This is how brightness is faked on a 1-bit panel."""
    t = level * 17.0
    for y in range(H):
        for x in range(W):
            if mask and not mask(x, y):
                continue
            if BAYER[y & 3][x & 3] < t:
                fb[y][x] = 1


def roundrect(fb, cx, cy, w, h, r, val=1):
    x0, x1 = cx - w // 2, cx - w // 2 + w - 1
    y0, y1 = cy - h // 2, cy - h // 2 + h - 1
    r = min(r, w // 2, h // 2)
    ix0, ix1, iy0, iy1 = x0 + r, x1 - r, y0 + r, y1 - r
    for y in range(max(0, y0), min(H, y1 + 1)):
        for x in range(max(0, x0), min(W, x1 + 1)):
            dx = max(ix0 - x, 0, x - ix1)
            dy = max(iy0 - y, 0, y - iy1)
            if dx * dx + dy * dy <= r * r:
                fb[y][x] = val


def eyes_frame(squash=1.0):
    fb = blank()
    h = max(2, int(EYE_H * squash))
    for cx in (CXL, CXR):
        roundrect(fb, cx, CY, EYE_W, h, EYE_R)
    return fb


def band(fb, y0, y1, level=1.0):
    for y in range(max(0, y0), min(H, y1 + 1)):
        for x in range(W):
            if level >= 1.0 or BAYER[y & 3][x & 3] < level * 17.0:
                fb[y][x] = 1


def ring(fb, cx, cy, rad, thick, level=1.0):
    lo, hi = (rad - thick) ** 2, (rad + thick) ** 2
    for y in range(H):
        dy2 = (y - cy) ** 2
        for x in range(W):
            d2 = (x - cx) ** 2 + dy2
            if lo <= d2 <= hi:
                if level >= 1.0 or BAYER[y & 3][x & 3] < level * 17.0:
                    fb[y][x] = 1


def sparks(fb, n, level=1.0):
    """Scattered electrical noise - the sound of something waking up."""
    for _ in range(n):
        x, y = rnd.randrange(W), rnd.randrange(H)
        for k in range(rnd.randrange(2, 7)):
            if 0 <= x < W and 0 <= y < H:
                fb[y][x] = 1
            x += rnd.choice((-1, 0, 1))
            y += rnd.choice((-1, 0, 1))


frames = []          # (framebuffer, duration in 50 ms units)


def add(fb, dur=1):
    frames.append((fb, dur))


# ---- ACT 1: dead, then the first twitch of power ------------------------
add(blank(), 3)
for lvl in (0.06, 0.0, 0.10, 0.0):
    f = blank(); sparks(f, int(14 * (lvl + 0.05) * 10)); add(f, 1)

# ---- ACT 2: the surge builds, brightness ramping through dither ---------
for lvl in (0.12, 0.22, 0.10, 0.34, 0.18, 0.5):
    f = blank()
    dither(f, lvl)
    sparks(f, 10)
    add(f, 1)

# ---- ACT 3: it collapses to a single charged line -----------------------
for half, lvl in ((26, 0.55), (14, 0.75), (6, 0.9), (2, 1.0)):
    f = blank()
    band(f, CY - half, CY + half, lvl)
    add(f, 1)
add(blank(), 1)                                   # beat of darkness

# ---- ACT 4: SNAP - the line fires across, full brightness ---------------
f = blank(); band(f, CY - 1, CY + 1); add(f, 4)
f = blank(); band(f, CY, CY); add(f, 1)
f = blank(); band(f, CY - 2, CY + 2); add(f, 2)

# ---- ACT 5: bloom - the line tears open into the whole screen -----------
for half in (5, 9, 15, 23, 32):
    f = blank(); band(f, CY - half, CY + half); add(f, 1)

# ---- ACT 6: total whiteout -------------------------------------------
f = blank(); band(f, 0, H - 1); add(f, 3)
add(blank(), 1)                                   # hard cut to black: impact
f = blank(); band(f, 0, H - 1); add(f, 1)

# ---- ACT 7: the whiteout blows outward as a shockwave -------------------
for rad, th, lvl in ((10, 9, 1.0), (26, 8, 1.0), (42, 7, 0.85),
                     (58, 6, 0.7), (74, 5, 0.5)):
    f = blank()
    ring(f, 64, CY, rad, th, lvl)
    add(f, 1)

# ---- ACT 8: from the dark, the eyes come up as slits and open ----------
add(blank(), 2)
for sq in (0.05, 0.05, 0.18, 0.42, 0.72, 1.0):
    add(eyes_frame(sq), 1)

# ---- ACT 9: settle - one deliberate blink, then he is awake ------------
add(eyes_frame(1.0), 5)
for sq in (0.45, 0.12, 0.45):
    add(eyes_frame(sq), 1)
add(eyes_frame(1.0), 6)

# ---------------------------------------------------------------- pack
def pack_frame(fb):
    out = bytearray(1024)
    for y in range(H):
        for x in range(W):
            if fb[y][x]:
                out[(y >> 3) * 128 + x] |= 1 << (y & 7)
    return bytes(out)


n = len(frames)
assert n <= 255, n
data = bytearray(b'GDA1')
data += bytes([1, n, FPS, 0])                     # ver, count, fps, flags(no loop)
data += bytes(min(255, d) for _, d in frames)
for fb, _ in frames:
    data += pack_frame(fb)

(ROOT / 'animations' / 'bin' / 'animations_boot_boot_animation.bin').write_bytes(bytes(data))

hdr = [f'// AUTO-GENERATED by tools/gen_boot_anim.py - do not edit',
       '#pragma once',
       '#include <Arduino.h>',
       '',
       f'// {len(data)} bytes, {n} frames, {FPS} fps',
       f'const uint8_t BOOT_ANIM_FRAME_COUNT = {n};',
       f'const uint8_t BOOT_ANIM_FPS = {FPS};',
       f'const uint8_t BOOT_ANIM_FLAGS = 0;',
       '',
       f'const uint8_t BOOT_ANIM_DATA[{len(data)}] PROGMEM = {{']
for i in range(0, len(data), 16):
    hdr.append('  ' + ', '.join(f'0x{b:02X}' for b in data[i:i + 16]) + ',')
hdr.append('};')
(ROOT / 'firmware' / 'sketch' / 'boot_anim_progmem.h').write_text('\n'.join(hdr) + '\n')

total_ms = sum(d for _, d in frames) * (1000 // FPS)
print(f"{n} frames, {len(data)} bytes of flash, runs {total_ms/1000:.1f}s")
print(f"wrote firmware/sketch/boot_anim_progmem.h")
print(f"wrote animations/bin/animations_boot_boot_animation.bin")

# ------------------------------------------------------- optional preview
if '--png' in sys.argv:
    cols, scale, pad = 8, 2, 4
    rowsn = (n + cols - 1) // cols
    tw, th = cols * (W * scale + pad) + pad, rowsn * (H * scale + pad) + pad
    px = [[40] * tw for _ in range(th)]
    for i, (fb, _) in enumerate(frames):
        ox = pad + (i % cols) * (W * scale + pad)
        oy = pad + (i // cols) * (H * scale + pad)
        for y in range(H * scale):
            for x in range(W * scale):
                px[oy + y][ox + x] = 255 if fb[y // scale][x // scale] else 0
    raw = b''.join(b'\0' + bytes(v for p in row for v in (p, p, p)) for row in px)
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', tw, th, 8, 2, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))
    out = ROOT / 'assets' / 'boot_anim_preview.png'
    out.write_bytes(png)
    print(f"wrote {out.relative_to(ROOT)}")
