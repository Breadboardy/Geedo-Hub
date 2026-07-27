#!/usr/bin/env python3
"""Generate Geedo's power-on animation.

Writes firmware/sketch/boot_anim_progmem.h (played from flash the instant he
powers up, before WiFi) and animations/bin/animations_boot_boot_animation.bin.

On a 1-bit panel there is no brightness - an ordered Bayer dither fakes it, so
ramping dither density reads as a real power surge rather than a hard on/off.
Everything else is line work: Bresenham strokes, a perspective starfield and a
rotating wireframe, which stay crisp at 128x64 where shaded art turns to mud.

The sequence ends on the idle eyes at their exact geometry from eyes.h, so the
boot hands over to the wandering face with no visible seam.
"""
import math, random, sys, zlib, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
W, H = 128, 64
FPS = 20                       # base period 50 ms; durations are multiples

# must match eyes.h
EYE_W, EYE_H, EYE_R, GAP = 38, 48, 8, 22
CXL, CXR, CY = 64 - (EYE_W + GAP) // 2, 64 + (EYE_W + GAP) // 2, 32

BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
rnd = random.Random(20260727)


# ---------------------------------------------------------------- primitives
def blank():
    return [[0] * W for _ in range(H)]


def px(fb, x, y, level=1.0):
    x, y = int(x), int(y)
    if 0 <= x < W and 0 <= y < H:
        if level >= 1.0 or BAYER[y & 3][x & 3] < level * 17.0:
            fb[y][x] = 1


def line(fb, x0, y0, x1, y1, level=1.0):
    """Bresenham. Lines read far better than shading on a 1-bit panel."""
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    for _ in range(4096):
        px(fb, x0, y0, level)
        if x0 == x1 and y0 == y1:
            return
        e2 = 2 * err
        if e2 >= dy:
            err += dy; x0 += sx
        if e2 <= dx:
            err += dx; y0 += sy


def rect(fb, x, y, w, h, level=1.0):
    for j in range(int(y), int(y + h)):
        for i in range(int(x), int(x + w)):
            px(fb, i, j, level)


def disc(fb, cx, cy, r, level=1.0):
    for j in range(int(cy - r), int(cy + r) + 1):
        for i in range(int(cx - r), int(cx + r) + 1):
            if (i - cx) ** 2 + (j - cy) ** 2 <= r * r:
                px(fb, i, j, level)


def ring(fb, cx, cy, rad, thick, level=1.0):
    lo, hi = max(0, rad - thick) ** 2, (rad + thick) ** 2
    for y in range(H):
        dy2 = (y - cy) ** 2
        if dy2 > hi:
            continue
        for x in range(W):
            if lo <= (x - cx) ** 2 + dy2 <= hi:
                px(fb, x, y, level)


def dither(fb, level):
    for y in range(H):
        for x in range(W):
            if BAYER[y & 3][x & 3] < level * 17.0:
                fb[y][x] = 1


def band(fb, y0, y1, level=1.0):
    for y in range(max(0, int(y0)), min(H, int(y1) + 1)):
        for x in range(W):
            px(fb, x, y, level)


def roundrect(fb, cx, cy, w, h, r):
    x0, x1 = cx - w // 2, cx - w // 2 + w - 1
    y0, y1 = cy - h // 2, cy - h // 2 + h - 1
    r = min(r, w // 2, h // 2)
    ix0, ix1, iy0, iy1 = x0 + r, x1 - r, y0 + r, y1 - r
    for y in range(max(0, y0), min(H, y1 + 1)):
        for x in range(max(0, x0), min(W, x1 + 1)):
            dx = max(ix0 - x, 0, x - ix1)
            dy = max(iy0 - y, 0, y - iy1)
            if dx * dx + dy * dy <= r * r:
                fb[y][x] = 1


def eyes_frame(squash=1.0):
    fb = blank()
    h = max(2, int(EYE_H * squash))
    for cx in (CXL, CXR):
        roundrect(fb, cx, CY, EYE_W, h, EYE_R)
    return fb


def invert(fb):
    return [[1 - v for v in row] for row in fb]


def shift(fb, dx):
    out = blank()
    for y in range(H):
        for x in range(W):
            if fb[y][x]:
                nx = x + dx
                if 0 <= nx < W:
                    out[y][nx] = 1
    return out


# ------------------------------------------------------------- chunky letters
def L_G(fb, x, y, w, h, t):
    rect(fb, x, y, w, t); rect(fb, x, y, t, h); rect(fb, x, y + h - t, w, t)
    rect(fb, x + w - t, y + h // 2, t, h - h // 2)
    rect(fb, x + w // 2, y + h // 2 - t // 2, w - w // 2, t)


def L_E(fb, x, y, w, h, t):
    rect(fb, x, y, w, t); rect(fb, x, y, t, h); rect(fb, x, y + h - t, w, t)
    rect(fb, x, y + h // 2 - t // 2, int(w * 0.8), t)


def L_D(fb, x, y, w, h, t):
    rect(fb, x, y, w - t, t); rect(fb, x, y, t, h)
    rect(fb, x, y + h - t, w - t, t); rect(fb, x + w - t, y + t, t, h - 2 * t)


def L_O(fb, x, y, w, h, t):
    rect(fb, x, y, w, t); rect(fb, x, y + h - t, w, t)
    rect(fb, x, y, t, h); rect(fb, x + w - t, y, t, h)


WORD = [L_G, L_E, L_E, L_D, L_O]


def wordmark(fb, scale=1.0, yoff=0):
    lw, lh, t, sp = 16, 22, 4, 4
    total = len(WORD) * lw + (len(WORD) - 1) * sp
    lw2, lh2 = max(4, int(lw * scale)), max(6, int(lh * scale))
    sp2 = max(1, int(sp * scale))
    total2 = len(WORD) * lw2 + (len(WORD) - 1) * sp2
    x = (W - total2) // 2
    y = (H - lh2) // 2 + yoff
    for fn in WORD:
        fn(fb, x, y, lw2, lh2, max(2, int(t * scale)))
        x += lw2 + sp2
    return total


# ------------------------------------------------------------------ 3D bits
CUBE_V = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
          (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
CUBE_E = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
          (0, 4), (1, 5), (2, 6), (3, 7)]


def cube(fb, ang, z, scale=26, level=1.0):
    ca, sa = math.cos(ang), math.sin(ang)
    cb, sb = math.cos(ang * 0.7), math.sin(ang * 0.7)
    pts = []
    for vx, vy, vz in CUBE_V:
        x1, z1 = vx * ca - vz * sa, vx * sa + vz * ca
        y1, z2 = vy * cb - z1 * sb, vy * sb + z1 * cb
        d = z2 + z
        if d < 0.35:
            d = 0.35
        pts.append((64 + x1 * scale / d, CY + y1 * scale / d))
    for a, b in CUBE_E:
        line(fb, pts[a][0], pts[a][1], pts[b][0], pts[b][1], level)


def starfield(fb, stars, streak, level=1.0):
    for sx, sy, sz in stars:
        d = max(0.05, sz)
        x, y = 64 + sx / d, CY + sy / d
        d2 = max(0.05, sz + streak)
        x2, y2 = 64 + sx / d2, CY + sy / d2
        if streak > 0.01:
            line(fb, x2, y2, x, y, level)
        else:
            px(fb, x, y, level)



def plasma(fb, t, gain=1.0):
    """Sine-field plasma, thresholded through the Bayer matrix. Boiling
    organic mush is the one thing that reads as 'power' better than flat
    dither, and it costs nothing but sines."""
    for y in range(H):
        for x in range(W):
            v = (math.sin(x / 7.0 + t) + math.sin(y / 5.0 - t * 1.3)
                 + math.sin((x + y) / 9.0 + t * 0.7)
                 + math.sin(math.hypot(x - 64, y - 32) / 6.0 - t * 2.1))
            lvl = ((v + 4.0) / 8.0) * gain
            if BAYER[y & 3][x & 3] < lvl * 17.0:
                fb[y][x] = 1


def tunnel(fb, t, gain=1.0):
    """Polar tunnel: shade by 1/distance so it rushes at the viewer."""
    for y in range(H):
        dy = y - 32
        for x in range(W):
            dx = x - 64
            d = math.hypot(dx, dy)
            if d < 1.2:
                fb[y][x] = 1
                continue
            a = math.atan2(dy, dx)
            v = math.sin(28.0 / d + t * 4.0) * 0.5 + 0.5
            v *= 0.55 + 0.45 * math.sin(a * 6.0 + t * 2.0)
            lvl = v * gain * min(1.0, d / 26.0)
            if BAYER[y & 3][x & 3] < lvl * 17.0:
                fb[y][x] = 1


def bolt(fb, x0, y0, x1, y1, spread, depth=5):
    """Midpoint-displacement lightning, branching as it goes."""
    if depth <= 0 or spread < 1.2:
        line(fb, x0, y0, x1, y1)
        return
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    mx += rnd.uniform(-spread, spread)
    my += rnd.uniform(-spread, spread)
    bolt(fb, x0, y0, mx, my, spread / 2, depth - 1)
    bolt(fb, mx, my, x1, y1, spread / 2, depth - 1)
    if depth > 2 and rnd.random() < 0.45:
        bolt(fb, mx, my, mx + rnd.uniform(-24, 24), my + rnd.uniform(-18, 18),
             spread / 2, depth - 2)


def sphere(fb, ang, z, scale=30, level=1.0):
    """Wireframe sphere - latitude rings and longitude arcs. Reads as a far
    more complex object than a cube for the same handful of lines."""
    ca, sa = math.cos(ang), math.sin(ang)
    cb, sb = math.cos(ang * 0.6), math.sin(ang * 0.6)

    def proj(px_, py_, pz_):
        x1, z1 = px_ * ca - pz_ * sa, px_ * sa + pz_ * ca
        y1, z2 = py_ * cb - z1 * sb, py_ * sb + z1 * cb
        d = max(0.35, z2 + z)
        return 64 + x1 * scale / d, CY + y1 * scale / d

    for li in range(-2, 3):                       # latitude rings
        lat = li * 0.42
        r, yy = math.cos(lat), math.sin(lat)
        pts = [proj(r * math.cos(k * math.pi / 8), yy, r * math.sin(k * math.pi / 8))
               for k in range(17)]
        for a, b in zip(pts, pts[1:]):
            line(fb, a[0], a[1], b[0], b[1], level)
    for mi in range(6):                           # longitude arcs
        lon = mi * math.pi / 6
        pts = [proj(math.cos(k * math.pi / 8) * math.cos(lon),
                    math.sin(k * math.pi / 8),
                    math.cos(k * math.pi / 8) * math.sin(lon))
               for k in range(-8, 9)]
        for a, b in zip(pts, pts[1:]):
            line(fb, a[0], a[1], b[0], b[1], level)


frames = []


def add(fb, dur=1):
    frames.append((fb, dur))


# ===================== ACT 1: cold, dead, one dying flicker ================
add(blank(), 2)
f = blank(); band(f, 31, 32, 0.5); add(f, 1)
add(blank(), 2)

# ===================== ACT 2: the mains arcs over ==========================
for k in range(5):
    f = blank()
    bolt(f, 0, rnd.randrange(6, 58), 127, rnd.randrange(6, 58), 22)
    if k % 2:
        bolt(f, rnd.randrange(0, 40), 0, rnd.randrange(88, 128), 63, 16)
    add(f, 1)
add(blank(), 1)

# ===================== ACT 3: copper traces take the charge ================
NODES = [(64, 32), (24, 12), (104, 12), (18, 52), (110, 52), (64, 6), (64, 58),
         (40, 32), (88, 32), (24, 32), (104, 32)]
TRACES = [((64, 32), (40, 32)), ((40, 32), (24, 32)), ((24, 32), (24, 12)),
          ((64, 32), (88, 32)), ((88, 32), (104, 32)), ((104, 32), (104, 12)),
          ((24, 32), (18, 52)), ((104, 32), (110, 52)),
          ((64, 32), (64, 6)), ((64, 32), (64, 58))]
for k in range(1, 6):
    f = blank()
    grow = k / 5.0
    for (ax, ay), (bx, by) in TRACES:
        line(f, ax, ay, ax + (bx - ax) * grow, ay + (by - ay) * grow, 0.85)
    for nx, ny in NODES[:k * 2]:
        disc(f, nx, ny, 1)
    add(f, 1)
for lvl in (1.0, 0.25, 1.0):
    f = blank()
    for (ax, ay), (bx, by) in TRACES:
        line(f, ax, ay, bx, by, lvl)
    for nx, ny in NODES:
        disc(f, nx, ny, 2 if lvl > 0.5 else 1)
    add(f, 1)

# ===================== ACT 4: plasma surge, panel shaking ==================
for i, g in enumerate((0.30, 0.48, 0.36, 0.66, 0.52, 0.85, 1.0)):
    f = blank()
    plasma(f, i * 0.55, g)
    j = rnd.randrange(-3, 4)
    for (ax, ay), (bx, by) in TRACES:
        line(f, ax + j, ay, bx + j, by, 1.0)
    add(f, 1)
f = blank(); band(f, 0, H - 1); add(f, 1)

# ===================== ACT 5: down the tunnel ==============================
for i in range(8):
    f = blank()
    tunnel(f, i * 0.42, 0.55 + i * 0.06)
    add(f, 1)

# ===================== ACT 6: hyperspace ===================================
stars = [(rnd.uniform(-70, 70), rnd.uniform(-40, 40), rnd.uniform(0.25, 2.4))
         for _ in range(150)]
for adv, streak in ((0.0, 0.0), (0.18, 0.06), (0.34, 0.18), (0.50, 0.38),
                    (0.64, 0.70), (0.76, 1.20), (0.86, 1.90), (0.93, 2.80)):
    f = blank()
    starfield(f, [(sx, sy, max(0.06, sz - adv * 1.6)) for sx, sy, sz in stars],
              streak, 1.0)
    add(f, 1)

# ===================== ACT 7: a wireframe world tumbles out ================
for z, ang in ((6.0, 0.0), (3.6, 0.8), (2.4, 1.7), (1.8, 2.6),
               (1.45, 3.5), (1.2, 4.4), (1.05, 5.3)):
    f = blank()
    starfield(f, [(sx, sy, max(0.06, sz - 1.5)) for sx, sy, sz in stars], 1.3, 0.4)
    sphere(f, ang, z)
    add(f, 1)
f = blank(); sphere(f, 6.0, 0.95, 34); add(f, 2)

# it detonates: shards thrown at the viewer
for r in (7, 18, 31, 46):
    f = blank()
    for k in range(54):
        a = k * 2.39996
        d = r + rnd.uniform(-4, 4)
        x, y = 64 + math.cos(a) * d * 1.8, CY + math.sin(a) * d
        line(f, x, y, x - math.cos(a) * 6, y - math.sin(a) * 4)
    add(f, 1)

# ===================== ACT 8: GEEDO ========================================
for sc in (2.8, 1.7, 1.0):
    f = blank(); wordmark(f, sc); add(f, 1)
f = blank(); wordmark(f, 1.0); add(f, 3)
f = blank(); wordmark(f, 1.0); add(invert(f), 1)      # negative flash
f = blank(); wordmark(f, 1.0); add(f, 1)

for k in range(4):                                    # VHS tearing
    base = blank(); wordmark(base, 1.0)
    if k == 2:
        plasma(base, 3.1, 0.35)
    f = blank()
    y = 0
    while y < H:
        hgt = rnd.randrange(2, 8)
        off = rnd.choice((-14, -8, -3, 0, 4, 9, 15))
        for yy in range(y, min(H, y + hgt)):
            for x in range(W):
                if base[yy][x]:
                    nx = x + off
                    if 0 <= nx < W:
                        f[yy][nx] = 1
        y += hgt
    add(f, 1)
f = blank(); wordmark(f, 1.0); add(f, 2)

# ===================== ACT 9: strobe into whiteout =========================
for d in (1, 1, 1, 1):
    f = blank(); band(f, 0, H - 1); add(f, d)
    add(blank(), 1)
f = blank(); band(f, 0, H - 1); add(f, 3)
add(blank(), 1)

# ===================== ACT 10: shockwave ===================================
for rad, th, lvl in ((8, 9, 1.0), (24, 8, 1.0), (42, 8, 1.0),
                     (60, 7, 0.8), (78, 6, 0.55), (96, 5, 0.35)):
    f = blank(); ring(f, 64, CY, rad, th, lvl); add(f, 1)

# ===================== ACT 11: shards assemble his eyes ====================
targets = []
probe = eyes_frame(1.0)
for y in range(0, H, 3):
    for x in range(0, W, 3):
        if probe[y][x]:
            targets.append((x, y))
rnd.shuffle(targets)
starts = [(rnd.uniform(-50, 178), rnd.uniform(-40, 104)) for _ in targets]
for t in (0.0, 0.30, 0.55, 0.75, 0.89, 0.97):
    f = blank()
    for (sx, sy), (tx, ty) in zip(starts, targets):
        x, y = sx + (tx - sx) * t, sy + (ty - sy) * t
        if t < 0.92:
            line(f, x, y, x + (sx - tx) * 0.06, y + (sy - ty) * 0.06)
        else:
            disc(f, x, y, 1)
    add(f, 1)
f = blank(); band(f, 0, H - 1); add(f, 1)             # impact flash

# ===================== ACT 12: eyes open, blink, awake =====================
for sq in (0.05, 0.05, 0.22, 0.55, 0.85, 1.0):
    add(eyes_frame(sq), 1)
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
assert n <= 255, f"{n} frames exceeds the one-byte frame count"
data = bytearray(b'GDA1')
data += bytes([1, n, FPS, 0])                     # ver, count, fps, flags(no loop)
data += bytes(min(255, d) for _, d in frames)
for fb, _ in frames:
    data += pack_frame(fb)

(ROOT / 'animations' / 'bin' / 'animations_boot_boot_animation.bin').write_bytes(bytes(data))

hdr = ['// AUTO-GENERATED by tools/gen_boot_anim.py - do not edit',
       '#pragma once',
       '#include <Arduino.h>',
       '',
       f'// {len(data)} bytes, {n} frames, {FPS} fps',
       f'const uint8_t BOOT_ANIM_FRAME_COUNT = {n};',
       f'const uint8_t BOOT_ANIM_FPS = {FPS};',
       'const uint8_t BOOT_ANIM_FLAGS = 0;',
       '',
       f'const uint8_t BOOT_ANIM_DATA[{len(data)}] PROGMEM = {{']
for i in range(0, len(data), 16):
    hdr.append('  ' + ', '.join(f'0x{b:02X}' for b in data[i:i + 16]) + ',')
hdr.append('};')
(ROOT / 'firmware' / 'sketch' / 'boot_anim_progmem.h').write_text('\n'.join(hdr) + '\n')

total_ms = sum(d for _, d in frames) * (1000 // FPS)
print(f"{n} frames, {len(data)} bytes of flash, runs {total_ms/1000:.1f}s")
print("wrote firmware/sketch/boot_anim_progmem.h")
print("wrote animations/bin/animations_boot_boot_animation.bin")

# ------------------------------------------------------- optional preview
if '--png' in sys.argv:
    cols, scale, pad = 8, 2, 4
    rowsn = (n + cols - 1) // cols
    tw, th = cols * (W * scale + pad) + pad, rowsn * (H * scale + pad) + pad
    pxs = [[40] * tw for _ in range(th)]
    for i, (fb, _) in enumerate(frames):
        ox = pad + (i % cols) * (W * scale + pad)
        oy = pad + (i // cols) * (H * scale + pad)
        for y in range(H * scale):
            for x in range(W * scale):
                pxs[oy + y][ox + x] = 255 if fb[y // scale][x // scale] else 0
    raw = b''.join(b'\0' + bytes(v for p in row for v in (p, p, p)) for row in pxs)
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', tw, th, 8, 2, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))
    outp = ROOT / 'assets' / 'boot_anim_preview.png'
    outp.write_bytes(png)
    print(f"wrote {outp.relative_to(ROOT)}")
