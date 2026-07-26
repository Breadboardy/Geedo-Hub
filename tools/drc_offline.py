#!/usr/bin/env python3
"""Independent clearance audit of the whole board: every copper item against
every foreign-net copper item, plus board-edge and keepout checks.
Deliberately does NOT reuse the router's own geometry code."""
import re, math, sys
from itertools import combinations

P = 'hardware/Geedo_PCB_v4.kicad_pcb'
src = open(P).read()
CLEAR = 0.2
EDGE_GAP = 0.5          # board setup constraint, per the DRC report

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
    raise ValueError
def each(s, pat):
    out = []; i = 0; rx = re.compile(pat)
    while True:
        m = rx.search(s, i)
        if not m: break
        t, e = block(s, m.start()); out.append(t); i = e
    return out


def _custom_extent(pb, w, h):
    """A custom pad's (size ..) is only its anchor; the real copper is in
    (primitives ...). Take the bounding box of every primitive point."""
    i = pb.find('(primitives')
    if i < 0: return w, h
    pts = re.findall(r'\(xy\s+([-\d.]+)\s+([-\d.]+)\)', pb[i:])
    if not pts: return w, h
    mx = max(abs(float(a)) for a, _ in pts) * 2
    my = max(abs(float(b)) for _, b in pts) * 2
    for m in re.finditer(r'\(gr_circle[^)]*\(center\s+([-\d.]+)\s+([-\d.]+)\)[^)]*\(end\s+([-\d.]+)\s+([-\d.]+)\)', pb[i:]):
        cx, cy, ex, ey = map(float, m.groups())
        r = ((ex-cx)**2 + (ey-cy)**2) ** 0.5
        mx = max(mx, 2*(abs(cx)+r)); my = max(my, 2*(abs(cy)+r))
    return max(w, mx), max(h, my)

def _pad_geom(shape, ax, ay, w, h, rr=0.25):
    """An oval pad is a stadium, not a rectangle - squaring it off invents
    copper at the four corners, which is exactly where nearby diagonal tracks
    pass. A round pad is a disc. Everything else stays a bounding rectangle."""
    if shape == 'circle' or (shape == 'oval' and abs(w - h) < 1e-9):
        return ('circ', ax, ay, min(w, h)/2)
    if shape == 'oval':
        r = min(w, h)/2
        half = (max(w, h) - min(w, h))/2
        if h > w:
            return ('seg', (ax, ay-half), (ax, ay+half), r)
        return ('seg', (ax-half, ay), (ax+half, ay), r)
    if shape == 'roundrect':
        r = rr * min(w, h)
        return ('rrect', ax, ay, w/2, h/2, r)
    return ('rect', ax, ay, w/2, h/2)

def _copper_text(src):
    """Copper text is real copper. Approximate each string with a box."""
    out = []
    for m in re.finditer(r'\((?:gr|fp)_text\s+"([^"]*)"(.{0,600}?)\(layer\s+"([^"]*)"', src, re.S):
        txt, body, lay = m.group(1), m.group(2), m.group(3)
        if '.Cu' not in lay: continue
        at = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)', body)
        fs = re.search(r'\(size\s+([-\d.]+)\s+([-\d.]+)\)', src[m.end():m.end()+400])
        th = re.search(r'\(thickness\s+([-\d.]+)\)', src[m.end():m.end()+400])
        if not at: continue
        x, y, rot = float(at.group(1)), float(at.group(2)), float(at.group(3) or 0)
        sx, sy = (float(fs.group(1)), float(fs.group(2))) if fs else (1.0, 1.0)
        t = float(th.group(1)) if th else 0.15
        w = len(txt) * sx * 1.10 + t
        h = sy + t
        if abs(rot % 180 - 90) < 1: w, h = h, w
        # A justified string is anchored by an EDGE, not its centre. KiCad's y
        # grows downward, so `bottom` puts the anchor under the glyphs and the
        # copper sits above it; `mirror` (normal for a back-layer string) flips
        # which side of the anchor the text runs to.
        just = re.search(r'\(justify([^)]*)\)', src[m.end():m.end()+400])
        jt = just.group(1) if just else ''
        sign = -1 if 'mirror' in jt else 1
        if 'left' in jt:    x += sign * w/2
        elif 'right' in jt: x -= sign * w/2
        if 'top' in jt:     y += h/2
        elif 'bottom' in jt: y -= h/2
        out.append(dict(ref=f'text:{txt}', num='', net=f'~text~{txt}~{lay}', x=x, y=y,
                        w=w, h=h, layers={lay}, typ='smd'))
    return out

items = []   # (kind, net, layers, geom)
for fb in each(src, r'\(footprint\s"'):
    ref = re.search(r'\(property\s+"Reference"\s+"([^"]*)"', fb).group(1)
    m = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)', fb)
    fx, fy, fr = float(m.group(1)), float(m.group(2)), float(m.group(3) or 0)
    for pb in each(fb, r'\(pad\s"'):
        num = pb.split('"')[1]
        typ, shape = re.match(r'\(pad\s"[^"]*"\s+(\w+)\s+(\w+)', pb).groups()
        nm = re.search(r'\(net\s+\d+\s+"([^"]*)"\)', pb)
        pm = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)', pb)
        sm = re.search(r'\(size\s+([-\d.]+)\s+([-\d.]+)', pb)
        lm = re.search(r'\(layers([^)]*)\)', pb)
        dx, dy, pr = float(pm.group(1)), float(pm.group(2)), float(pm.group(3) or 0)
        w, h = (float(sm.group(1)), float(sm.group(2))) if sm else (.5, .5)
        if 'custom' in pb[:60]: w, h = _custom_extent(pb, w, h)
        # KiCad stores the pad's ABSOLUTE orientation, already including the
        # footprint's rotation - adding fr again double-counts it.
        if abs(pr % 180 - 90) < 1: w, h = h, w
        a = math.radians(fr)
        ax = fx + dx*math.cos(a) + dy*math.sin(a)
        ay = fy - dx*math.sin(a) + dy*math.cos(a)
        lay = lm.group(1) if lm else ''
        layers = {'F.Cu', 'B.Cu'} if (typ in ('thru_hole','np_thru_hole') or '*.Cu' in lay) \
                 else {c for c in ('F.Cu','B.Cu') if f'"{c}"' in lay}
        net = nm.group(1) if nm else f'~unconnected~{ref}.{num}'
        rrm = re.search(r'\(roundrect_rratio\s+([-\d.]+)\)', pb)
        rr = float(rrm.group(1)) if rrm else 0.25
        items.append(('pad', net, layers, _pad_geom(shape, ax, ay, w, h, rr), f'{ref}.{num}'))
for t in _copper_text(src):
    items.append(('pad', t['net'], t['layers'], ('rect', t['x'], t['y'], t['w']/2, t['h']/2), t['ref']))
nets = dict(re.findall(r'\(net\s+(\d+)\s+"([^"]*)"\)', src))
for sb in each(src, r'\n\t\(segment\n'):
    st = re.search(r'\(start\s+([-\d.]+)\s+([-\d.]+)\)', sb)
    en = re.search(r'\(end\s+([-\d.]+)\s+([-\d.]+)\)', sb)
    lay = re.search(r'\(layer\s+"([^"]*)"\)', sb).group(1)
    w = float(re.search(r'\(width\s+([\d.]+)\)', sb).group(1))
    nid = re.search(r'\(net\s+(\d+)\)', sb).group(1)
    items.append(('seg', nets.get(nid, '?'), {lay},
                  ('seg', (float(st.group(1)), float(st.group(2))),
                          (float(en.group(1)), float(en.group(2))), w/2), 'track'))
for vb in each(src, r'\n\t\(via\n'):
    at = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)\)', vb)
    r = float(re.search(r'\(size\s+([\d.]+)\)', vb).group(1))/2
    nid = re.search(r'\(net\s+(\d+)\)', vb).group(1)
    items.append(('via', nets.get(nid, '?'), {'F.Cu','B.Cu'},
                  ('circ', float(at.group(1)), float(at.group(2)), r), 'via'))

def seg_seg(a1, a2, b1, b2):
    def d(p, q1, q2):
        dx, dy = q2[0]-q1[0], q2[1]-q1[1]; L = dx*dx+dy*dy
        if L == 0: return math.hypot(p[0]-q1[0], p[1]-q1[1])
        t = max(0, min(1, ((p[0]-q1[0])*dx + (p[1]-q1[1])*dy)/L))
        return math.hypot(p[0]-(q1[0]+t*dx), p[1]-(q1[1]+t*dy))
    def cross(p1,p2,p3,p4):
        def o(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        d1,d2,d3,d4 = o(p3,p4,p1),o(p3,p4,p2),o(p1,p2,p3),o(p1,p2,p4)
        return ((d1>0)!=(d2>0)) and ((d3>0)!=(d4>0))
    if cross(a1,a2,b1,b2): return 0.0
    return min(d(a1,b1,b2), d(a2,b1,b2), d(b1,a1,a2), d(b2,a1,a2))
def rect_pt(g, p):
    _, cx, cy, hw, hh = g
    return math.hypot(max(abs(p[0]-cx)-hw, 0), max(abs(p[1]-cy)-hh, 0))
def _gap(g1, g2):
    t1, t2 = g1[0], g2[0]
    if t1 == 'circ' and t2 == 'circ':
        return math.hypot(g1[1]-g2[1], g1[2]-g2[2]) - g1[3] - g2[3]
    if t1 == 'rect' and t2 == 'circ':
        return rect_pt(g1, (g2[1], g2[2])) - g2[3]
    if t1 == 'circ' and t2 == 'rect':
        return rect_pt(g2, (g1[1], g1[2])) - g1[3]
    if t1 == 'rect' and t2 == 'rect':
        dx = max(abs(g1[1]-g2[1]) - g1[3] - g2[3], 0)
        dy = max(abs(g1[2]-g2[2]) - g1[4] - g2[4], 0)
        return math.hypot(dx, dy)
    if t1 == 'seg' and t2 == 'seg':
        return seg_seg(g1[1], g1[2], g2[1], g2[2]) - g1[3] - g2[3]
    if t1 == 'seg':
        g1, g2 = g1, g2
    else:
        g1, g2 = g2, g1
    # seg vs rect/circ
    _, a, b, hw = g1
    if g2[0] == 'circ':
        return seg_seg(a, b, (g2[1], g2[2]), (g2[1], g2[2])) - hw - g2[3]
    _, cx, cy, rw, rh = g2
    corners = [(cx-rw, cy-rh), (cx+rw, cy-rh), (cx+rw, cy+rh), (cx-rw, cy+rh)]
    best = min(seg_seg(a, b, corners[i], corners[(i+1) % 4]) for i in range(4))
    if rect_pt(g2, a) == 0 or rect_pt(g2, b) == 0: best = 0.0
    return best - hw

def _split(g):
    if g[0] == 'rrect':
        return ('rect', g[1], g[2], max(g[3]-g[5], 0), max(g[4]-g[5], 0)), g[5]
    return g, 0.0
def gap(g1, g2):
    c1, i1 = _split(g1); c2, i2 = _split(g2)
    return _gap(c1, c2) - i1 - i2

print(f"auditing {len(items)} copper items at {CLEAR} mm clearance...")
viol = []
for (k1, n1, l1, g1, t1), (k2, n2, l2, g2, t2) in combinations(items, 2):
    if n1 == n2: continue
    if n1.startswith('~unconnected~') and n2.startswith('~unconnected~'): continue
    if not (l1 & l2): continue
    d = gap(g1, g2)
    if d < CLEAR - 1e-6:
        viol.append((d, k1, n1, t1, k2, n2, t2, g1, g2))
viol.sort()
for d, k1, n1, t1, k2, n2, t2, g1, g2 in viol[:40]:
    def where(g):
        if g[0] == 'seg': return f"({g[1][0]:.2f},{g[1][1]:.2f})-({g[2][0]:.2f},{g[2][1]:.2f})"
        return f"({g[1]:.2f},{g[2]:.2f})"
    print(f"  {d:6.3f}mm  {k1}[{n1}]{t1} {where(g1)}   vs   {k2}[{n2}]{t2} {where(g2)}")
print(f"\nclearance violations: {len(viol)}")

# board edge + keepout
EDGE = (89.5, 75.0, 119.0, 126.5)
KEEP = (90.575, 96.91, 103.775, 102.31)
edge_bad = keep_bad = 0
for k, n, l, g, t in items:
    if k == 'pad' and t.startswith('text:'): continue
    if g[0] == 'rrect':
        g = ('rect', g[1], g[2], g[3], g[4])
    if g[0] == 'rect':
        # a pad's own copper has to clear the outline too - U2's tab did not
        _, cx, cy, hw, hh = g
        if not (EDGE[0]+EDGE_GAP <= cx-hw and cx+hw <= EDGE[2]-EDGE_GAP and
                EDGE[1]+EDGE_GAP <= cy-hh and cy+hh <= EDGE[3]-EDGE_GAP):
            print(f"  EDGE  {k}[{n}] {t} at ({cx:.2f},{cy:.2f})"); edge_bad += 1
        continue
    pts = [(g[1], g[2])] if g[0] == 'circ' else [g[1], g[2]]
    rad = g[3]
    for x, y in pts:
        if not (EDGE[0]+EDGE_GAP <= x-rad and x+rad <= EDGE[2]-EDGE_GAP and
                EDGE[1]+EDGE_GAP <= y-rad and y+rad <= EDGE[3]-EDGE_GAP):
            print(f"  EDGE  {k}[{n}] at ({x:.2f},{y:.2f})"); edge_bad += 1
        if KEEP[0]-rad < x < KEEP[2]+rad and KEEP[1]-rad < y < KEEP[3]+rad:
            print(f"  KEEPOUT {k}[{n}] at ({x:.2f},{y:.2f})"); keep_bad += 1
print(f"edge violations: {edge_bad}   keepout violations: {keep_bad}")
sys.exit(0 if not (viol or edge_bad or keep_bad) else 1)
