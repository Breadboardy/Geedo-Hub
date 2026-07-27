#!/usr/bin/env python3
"""Flip footprints to the other board side, exactly as KiCad's 'F' does.

File-format ground truth, established empirically this session: the stored
local pad coordinates of BACK-side footprints already have the mirror baked
in, so the plain rotation transform
    ax = fx + dx*cos(th) + dy*sin(th)
    ay = fy - dx*sin(th) + dy*cos(th)
gives correct board positions for BOTH sides (verified repeatedly against
KiCad's own DRC coordinates).

Therefore a flip about the footprint's own origin is:
    footprint angle  th  -> -th (mod 360)
    every local x        -> -x        (pads, lines, polys, arcs, texts)
    every stored angle   -> -angle    (pads, texts store absolute angles)
    every F.* layer     <-> B.*
which yields board positions (2*fx - x, y): a pure mirror about the vertical
line through the footprint origin. Nets ride on the pads, so the netlist
cannot change; only geometry does.

Self-tests run first and abort on any failure:
  T1  flip(flip(fp)) is byte-identical to fp
  T2  every pad lands at exactly (2*fx - x_old, y_old)
  T3  the whole file still parses (balanced parens)
  T4  the pad->net table is unchanged
"""
import re, math, sys
from decimal import Decimal

SRC = sys.argv[1]
MOVE = sys.argv[2].split(',') if len(sys.argv) > 2 else []


def block(s, i):
    d = 0; j = i; q = False
    while j < len(s):
        c = s[j]
        if q:
            if c == '"' and s[j-1] != '\\': q = False
        elif c == '"': q = True
        elif c == '(': d += 1
        elif c == ')':
            d -= 1
            if d == 0: return s[i:j+1], j+1
        j += 1
    raise ValueError('unbalanced')


LAYER_PAIRS = [('F.Cu', 'B.Cu'), ('F.Paste', 'B.Paste'), ('F.Mask', 'B.Mask'),
               ('F.SilkS', 'B.SilkS'), ('F.Fab', 'B.Fab'),
               ('F.CrtYd', 'B.CrtYd'), ('F.Adhes', 'B.Adhes')]


def swap_layers(t):
    for a, b in LAYER_PAIRS:
        t = t.replace(f'"{a}"', '\x00TMP\x00').replace(f'"{b}"', f'"{a}"') \
             .replace('\x00TMP\x00', f'"{b}"')
    return t


def neg(numstr):
    """negate a numeric literal at string level - no float noise"""
    if float(numstr) == 0: return numstr if not numstr.startswith('-') else numstr[1:]
    return numstr[1:] if numstr.startswith('-') else '-' + numstr


def negang(numstr):
    """negate an angle literal at string level: self-inverse by construction,
    so double-flip is byte-identical even for angles stored as -90 or 180"""
    return neg(numstr)


def mirror_abs(numstr, fx_str):
    """Mirror an ABSOLUTE board x about the footprint origin: x -> 2*fx - x.

    Zones nested in a footprint (e.g. a module's antenna keepout) store BOARD
    coordinates, not footprint-local ones, so they must be mirrored about the
    origin rather than negated. Decimal keeps this exactly self-inverse, so
    double-flip stays byte-identical.
    """
    d = 2*Decimal(fx_str) - Decimal(numstr)
    s = format(d, 'f')
    if '.' in s: s = s.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def flip_footprint(fb):
    # 1. footprint's own (at x y [th]): th -> -th
    def fp_at(m):
        th = m.group(3)
        if th is None:
            return m.group(0)
        return f"\n\t\t(at {m.group(1)} {m.group(2)} {negang(th)})\n"
    out = re.sub(r'\n\t\t\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)\n',
                 fp_at, fb, count=1)

    # 2. every deeper (at x y [ang]) inside pads/texts/properties: x -> -x, ang -> -ang
    def sub_at(m):
        x, y, a = m.group(1), m.group(2), m.group(3)
        if a is None:
            return f"(at {neg(x)} {y})"
        return f"(at {neg(x)} {y} {negang(a)})"
    head_end = out.index('\n', out.index('(at', out.index('(layer')))  # after fp at-line
    body = out[head_end:]

    # 2a. nested zones hold ABSOLUTE board coords - hold them out of the
    #     local-coordinate rewrites below and mirror them separately (2b).
    fx_str = re.search(r'\n\t\t\(at\s+([-\d.]+)\s+', fb).group(1)
    zones = []
    while True:
        zm = re.search(r'\(zone\b', body)
        if not zm: break
        zb, _ = block(body, zm.start())
        body = body.replace(zb, f'\x01Z{len(zones)}\x01', 1)
        zones.append(zb)

    body = re.sub(r'\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)', sub_at, body)

    # 3. geometry primitives: negate x of start/end/mid/center/xy pairs
    def sub_pt(m):
        return f"({m.group(1)} {neg(m.group(2))} {m.group(3)})"
    body = re.sub(r'\((start|end|mid|center|xy)\s+([-\d.]+)\s+([-\d.]+)\)', sub_pt, body)

    # 4. offsets inside pads (drill offset) if any
    body = re.sub(r'\(offset\s+([-\d.]+)\s+([-\d.]+)\)',
                  lambda m: f"(offset {neg(m.group(1))} {m.group(2)})", body)

    # 2b. put the zones back, mirroring their absolute x about the origin
    for k, zb in enumerate(zones):
        zb2 = re.sub(r'\(xy\s+([-\d.]+)\s+([-\d.]+)\)',
                     lambda m: f"(xy {mirror_abs(m.group(1), fx_str)} {m.group(2)})", zb)
        body = body.replace(f'\x01Z{k}\x01', zb2, 1)

    out = out[:head_end] + body

    # 5. swap every F.* <-> B.* layer name
    out = swap_layers(out)

    # 6. toggle 'mirror' per (effects ...) block, byte-exactly reversible:
    #    - justify with other flags: add/remove ' mirror' in place
    #    - bare '(justify mirror)': remove its whole line / re-insert the
    #      identically-indented line before the block's closing paren
    res = []; i = 0
    while True:
        m = re.compile(r'\(effects\b').search(out, i)
        if not m:
            res.append(out[i:]); break
        eb, e = block(out, m.start())
        ls = out.rfind('\n', 0, m.start())
        indent = out[ls+1:m.start()]
        jm = re.search(r'\n(\s*)\(justify([^)]*)\)', eb)
        if jm:
            inner = jm.group(2)
            if 'mirror' in inner:
                inner2 = re.sub(r'\s+mirror', '', inner)
                if inner2.strip():
                    nb = eb.replace(f"(justify{inner})", f"(justify{inner2})", 1)
                else:
                    nb = eb.replace(jm.group(0), '', 1)
            else:
                nb = eb.replace(f"(justify{inner})", f"(justify{inner} mirror)", 1)
        else:
            k = eb.rfind('\n')
            nb = eb[:k] + f"\n{indent}\t(justify mirror)" + eb[k:]
        res.append(out[i:m.start()]); res.append(nb); i = e
    return ''.join(res)


def zone_pts_of(fb):
    """absolute (x, y) of every vertex of every zone nested in the footprint"""
    out = []
    i = 0
    while True:
        zm = re.compile(r'\(zone\b').search(fb, i)
        if not zm: return out
        zb, i = block(fb, zm.start())
        out += [(float(a), float(b))
                for a, b in re.findall(r'\(xy\s+([-\d.]+)\s+([-\d.]+)\)', zb)]


def pads_of(fb):
    m = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)', fb)
    fx, fy, fr = float(m.group(1)), float(m.group(2)), float(m.group(3) or 0)
    out = []
    i = 0
    while True:
        pm = re.compile(r'\(pad\s+"').search(fb, i)
        if not pm: break
        pb, i = block(fb, pm.start())
        num = pb.split('"')[1]
        pa = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)', pb)
        nm = re.search(r'\(net\s+\d+\s+"([^"]*)"\)', pb)
        dx, dy = float(pa.group(1)), float(pa.group(2))
        a = math.radians(fr)
        out.append((num, nm.group(1) if nm else None,
                    fx + dx*math.cos(a) + dy*math.sin(a),
                    fy - dx*math.sin(a) + dy*math.cos(a)))
    return fx, fy, out


src = open(SRC).read()

# collect footprints
fps = {}
i = 0
while True:
    m = re.compile(r'\t\(footprint\s"').search(src, i)
    if not m: break
    fb, e = block(src, m.start()+1)
    ref = re.search(r'\(property\s+"Reference"\s+"([^"]*)"', fb).group(1)
    fps[ref] = (m.start()+1, fb)
    i = e

# ---------------- self-tests on EVERY footprint (not just the moving ones)
fails = 0
for ref, (pos, fb) in fps.items():
    if ref == 'LOGO1':   # logo has no pads; still test T1
        pass
    f1 = flip_footprint(fb)
    f2 = flip_footprint(f1)
    if f2 != fb:
        print(f"T1 FAIL {ref}: double flip not identity")
        for a, b in zip(fb.split('\n'), f2.split('\n')):
            if a != b:
                print(f"   orig: {a.strip()[:90]}")
                print(f"   got : {b.strip()[:90]}")
                break
        fails += 1
        continue
    fx, fy, before = pads_of(fb)
    _, _, after = pads_of(f1)
    for (n1, net1, x1, y1), (n2, net2, x2, y2) in zip(before, after):
        if n1 != n2 or net1 != net2:
            print(f"T4 FAIL {ref}.{n1}: pad/net order changed"); fails += 1; break
        ex = 2*fx - x1
        if abs(x2 - ex) > 1e-6 or abs(y2 - y1) > 1e-6:
            print(f"T2 FAIL {ref}.{n1}: expected ({ex:.4f},{y1:.4f}) got ({x2:.4f},{y2:.4f})")
            fails += 1; break
    # T5 nested zones (absolute coords) mirror about the origin, same as pads
    zb_before, zb_after = zone_pts_of(fb), zone_pts_of(f1)
    if len(zb_before) != len(zb_after):
        print(f"T5 FAIL {ref}: zone vertex count changed"); fails += 1; continue
    for (x1, y1), (x2, y2) in zip(zb_before, zb_after):
        ex = 2*fx - x1
        if abs(x2 - ex) > 1e-6 or abs(y2 - y1) > 1e-6:
            print(f"T5 FAIL {ref}: zone vertex expected ({ex:.4f},{y1:.4f}) got ({x2:.4f},{y2:.4f})")
            fails += 1; break
print(f"self-test over {len(fps)} footprints: {'ALL PASS' if not fails else f'{fails} FAILURES'}")
if fails: sys.exit(1)
if not MOVE:
    print("(dry run - no footprints flipped)"); sys.exit(0)

# ---------------- apply
for ref in MOVE:
    assert ref in fps, ref
    _, fb = fps[ref]
    src = src.replace(fb, flip_footprint(fb), 1)

# T3 whole-file balance
d = 0; q = False
for j, c in enumerate(src):
    if q:
        if c == '"' and src[j-1] != '\\': q = False
    elif c == '"': q = True
    elif c == '(': d += 1
    elif c == ')': d -= 1
assert d == 0, f"paren imbalance {d}"
open(SRC, 'w').write(src)
print(f"flipped: {', '.join(MOVE)}")
