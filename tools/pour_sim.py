#!/usr/bin/env python3
"""Simulate KiCad's copper pour and check that GND ends up as one net.

The board in the repo is stored with its zone fills stripped (the router
removes them), so the stored `filled_polygon` blocks cannot be trusted.
Instead of reading them, re-derive the fill from the zone rules:

    fill = zone outline
         - foreign copper inflated by the zone clearance
         - keepout areas
         - everything outside the board edge clearance
         then morphologically opened by min_thickness/2 to drop slivers,
         then unioned with the net's own pads/tracks/vias,
         then islands that touch none of that copper are discarded.

Finally the two layers are merged wherever a through-hole pad or via
bridges them, and the result is flood-filled.
"""
import re, math, sys
import numpy as np
from scipy import ndimage

P = 'hardware/Geedo_PCB_v4.kicad_pcb'
src = open(P).read()

GRID = 0.05
CLEAR = 0.2           # zone clearance, per the GND zone settings
MIN_TH = 0.2          # zone min_thickness
EDGE_GAP = 0.5        # copper-to-board-edge
BOARD = (89.5, 75.0, 119.0, 126.5)
X0, Y0, X1, Y1 = 89.0, 74.5, 119.5, 127.0
W = int((X1 - X0) / GRID) + 1
H = int((Y1 - Y0) / GRID) + 1
LAYERS = ('F.Cu', 'B.Cu')


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
        if not m: return out
        t, e = block(s, m.start()); out.append(t); i = e


def gx(x): return (x - X0) / GRID
def gy(y): return (y - Y0) / GRID


def fill_poly(g, pts):
    """even-odd scanline fill, so zone keyholes stay holes"""
    if len(pts) < 3: return
    ys = [q[1] for q in pts]
    r0 = max(0, int(math.floor(gy(min(ys)))))
    r1 = min(H-1, int(math.ceil(gy(max(ys)))))
    n = len(pts)
    for row in range(r0, r1+1):
        yw = Y0 + row*GRID
        xs = []
        for k in range(n):
            ax, ay = pts[k]; bx, by = pts[(k+1) % n]
            if (ay > yw) != (by > yw):
                xs.append(ax + (yw-ay)*(bx-ax)/(by-ay))
        if not xs: continue
        xs.sort()
        for k in range(0, len(xs)-1, 2):
            c0 = max(0, int(math.ceil(gx(xs[k]))))
            c1 = min(W-1, int(math.floor(gx(xs[k+1]))))
            if c1 >= c0: g[row, c0:c1+1] = True


YY, XX = np.mgrid[0:H, 0:W]
WX = X0 + XX*GRID
WY = Y0 + YY*GRID


def fill_disc(g, x, y, r):
    if r <= 0: return
    m = (WX-x)**2 + (WY-y)**2 <= r*r
    g |= m


def fill_rect(g, x, y, hw, hh):
    g |= (np.abs(WX-x) <= hw) & (np.abs(WY-y) <= hh)


def fill_stadium(g, a, b, r):
    ax, ay = a; bx, by = b
    dx, dy = bx-ax, by-ay
    L2 = dx*dx + dy*dy
    if L2 == 0:
        fill_disc(g, ax, ay, r); return
    t = np.clip(((WX-ax)*dx + (WY-ay)*dy) / L2, 0, 1)
    px, py = ax + t*dx, ay + t*dy
    g |= (WX-px)**2 + (WY-py)**2 <= r*r


def disk(radius_mm):
    r = int(round(radius_mm / GRID))
    if r < 1: return np.ones((1, 1), bool)
    y, x = np.mgrid[-r:r+1, -r:r+1]
    return x*x + y*y <= r*r + 1e-9


# ---------------------------------------------------------------- parse copper
nets = dict(re.findall(r'\(net\s+(\d+)\s+"([^"]*)"\)', src))
GID = [k for k, v in nets.items() if v == 'GND'][0]

pads = []          # dict(ref,num,net,layers,shape,geom,pth)
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
        i2 = pb.find('(primitives')
        if i2 > 0:
            q = re.findall(r'\(xy\s+([-\d.]+)\s+([-\d.]+)\)', pb[i2:])
            if q:
                w = max(w, max(abs(float(a)) for a, _ in q)*2)
                h = max(h, max(abs(float(b)) for _, b in q)*2)
        # the stored pad angle is already absolute
        if abs(pr % 180 - 90) < 1: w, h = h, w
        a = math.radians(fr)
        ax = fx + dx*math.cos(a) + dy*math.sin(a)
        ay = fy - dx*math.sin(a) + dy*math.cos(a)
        lay = lm.group(1) if lm else ''
        pth = typ in ('thru_hole', 'np_thru_hole') or '*.Cu' in lay
        L = set(LAYERS) if pth else {c for c in LAYERS if f'"{c}"' in lay}
        pads.append(dict(ref=ref, num=num, net=(nm.group(1) if nm else None),
                         layers=L, shape=shape, x=ax, y=ay, w=w, h=h, pth=pth))

tracks = []
for sb in each(src, r'\n\t\(segment\n'):
    st = re.search(r'\(start\s+([-\d.]+)\s+([-\d.]+)\)', sb)
    en = re.search(r'\(end\s+([-\d.]+)\s+([-\d.]+)\)', sb)
    lay = re.search(r'\(layer\s+"([^"]*)"\)', sb).group(1)
    wd = float(re.search(r'\(width\s+([\d.]+)\)', sb).group(1))
    nid = re.search(r'\(net\s+(\d+)\)', sb).group(1)
    tracks.append((nets.get(nid, '?'), lay,
                   (float(st.group(1)), float(st.group(2))),
                   (float(en.group(1)), float(en.group(2))), wd/2))

vias = []
for vb in each(src, r'\n\t\(via\n'):
    at = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)\)', vb)
    r = float(re.search(r'\(size\s+([\d.]+)\)', vb).group(1))/2
    nid = re.search(r'\(net\s+(\d+)\)', vb).group(1)
    vias.append((nets.get(nid, '?'), float(at.group(1)), float(at.group(2)), r))


def paint_pad(g, p):
    if p['shape'] == 'circle' or (p['shape'] == 'oval' and abs(p['w']-p['h']) < 1e-9):
        fill_disc(g, p['x'], p['y'], min(p['w'], p['h'])/2)
    elif p['shape'] == 'oval':
        r = min(p['w'], p['h'])/2
        half = (max(p['w'], p['h']) - min(p['w'], p['h']))/2
        if p['h'] > p['w']:
            fill_stadium(g, (p['x'], p['y']-half), (p['x'], p['y']+half), r)
        else:
            fill_stadium(g, (p['x']-half, p['y']), (p['x']+half, p['y']), r)
    else:
        fill_rect(g, p['x'], p['y'], p['w']/2, p['h']/2)


# ------------------------------------------------------------ zone geometry
zone_outline = {L: np.zeros((H, W), bool) for L in LAYERS}
keepout = {L: np.zeros((H, W), bool) for L in LAYERS}
for zb in each(src, r'\(zone\s'):
    head = zb[:zb.find('(polygon')] if '(polygon' in zb else zb
    zl = set(re.findall(r'"(F\.Cu|B\.Cu)"', re.search(r'\(layers?\s[^)]*\)', head).group(0)))
    pm = re.search(r'\(polygon\s', zb)
    if not pm: continue
    pblk, _ = block(zb, pm.start())
    pts = [(float(a), float(b)) for a, b in
           re.findall(r'\(xy\s+([-\d.]+)\s+([-\d.]+)\)', pblk)]
    if '(keepout' in zb:
        if 'copperpour not_allowed' in ' '.join(zb.split()):
            for L in zl: fill_poly(keepout[L], pts)
        continue
    nn = re.search(r'\(net_name\s+"([^"]*)"\)', zb)
    if nn and nn.group(1) == 'GND':
        for L in zl: fill_poly(zone_outline[L], pts)

board = ((WX >= BOARD[0]+EDGE_GAP) & (WX <= BOARD[2]-EDGE_GAP) &
         (WY >= BOARD[1]+EDGE_GAP) & (WY <= BOARD[3]-EDGE_GAP))

# --------------------------------------------------------------- build fill
own = {L: np.zeros((H, W), bool) for L in LAYERS}      # GND pads/tracks/vias
foreign = {L: np.zeros((H, W), bool) for L in LAYERS}  # everything else
for p in pads:
    tgt = own if p['net'] == 'GND' else foreign
    for L in p['layers'] & set(LAYERS):
        paint_pad(tgt[L], p)
for net, lay, a, b, hw in tracks:
    if lay not in LAYERS: continue
    fill_stadium((own if net == 'GND' else foreign)[lay], a, b, hw)
for net, x, y, r in vias:
    for L in LAYERS:
        fill_disc((own if net == 'GND' else foreign)[L], x, y, r)

CD = disk(CLEAR)
OD = disk(MIN_TH/2)
total = {}
for L in LAYERS:
    blocked = ndimage.binary_dilation(foreign[L], CD) | keepout[L]
    pour = zone_outline[L] & board & ~blocked
    # min_thickness: deflate then reinflate, dropping anything thinner
    pour = ndimage.binary_dilation(ndimage.binary_erosion(pour, OD), OD)
    total[L] = pour | own[L]
    print(f"  {L}: pour {pour.sum()*GRID*GRID:7.1f} mm2   "
          f"+ net copper -> {total[L].sum()*GRID*GRID:7.1f} mm2")

# ------------------------------------- island removal, then merge the layers
lab = {}; nlab = {}
for L in LAYERS:
    lab[L], nlab[L] = ndimage.label(total[L])

# a pour island with no pad/track/via of the net on it is deleted by KiCad
for L in LAYERS:
    keep = np.unique(lab[L][own[L]])
    keep = keep[keep > 0]
    drop = [i for i in range(1, nlab[L]+1) if i not in set(keep.tolist())]
    for i in drop:
        area = (lab[L] == i).sum()*GRID*GRID
        ys, xs = np.where(lab[L] == i)
        print(f"  {L}: island removed (no net copper on it), "
              f"{area:.2f} mm2 at ({X0+xs.mean()*GRID:.1f},{Y0+ys.mean()*GRID:.1f})")
        lab[L][lab[L] == i] = 0

par = {}
def find(a):
    par.setdefault(a, a)
    while par[a] != a: par[a] = par[par[a]]; a = par[a]
    return a
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb: par[ra] = rb

for L in LAYERS:
    for i in range(1, nlab[L]+1):
        if (lab[L] == i).any(): find((L, i))

def ids_at(x, y, r):
    out = {}
    m = (WX-x)**2 + (WY-y)**2 <= max(r, GRID)**2
    for L in LAYERS:
        v = np.unique(lab[L][m]); v = v[v > 0]
        out[L] = set(v.tolist())
    return out

bridges = 0
for p in pads:
    if p['net'] != 'GND' or not p['pth']: continue
    got = ids_at(p['x'], p['y'], min(p['w'], p['h'])/2)
    allb = [(L, i) for L in LAYERS for i in got[L]]
    for k in allb[1:]: union(allb[0], k)
    bridges += 1
for net, x, y, r in vias:
    if net != 'GND': continue
    got = ids_at(x, y, r)
    allb = [(L, i) for L in LAYERS for i in got[L]]
    for k in allb[1:]: union(allb[0], k)
    bridges += 1

from collections import defaultdict
groups = defaultdict(list)
for k in list(par):
    if isinstance(k, tuple) and k[0] in LAYERS: groups[find(k)].append(k)

print(f"\nbridged the two layers at {bridges} through-hole GND pads / vias")
print(f"GND resolves to {len(groups)} electrically separate group(s)")
areas = {k: sum((lab[L] == i).sum() for L, i in v)*GRID*GRID for k, v in groups.items()}
for k, v in sorted(groups.items(), key=lambda kv: -areas[kv[0]]):
    print(f"  group {areas[k]:8.1f} mm2  ({len(v)} blob(s))")
    for L, i in sorted(v, key=lambda t: -(lab[t[0]] == t[1]).sum()):
        m = lab[L] == i
        ys, xs = np.where(m)
        print(f"      {L} blob {(m.sum()*GRID*GRID):7.2f} mm2  "
              f"x {X0+xs.min()*GRID:.1f}-{X0+xs.max()*GRID:.1f}  "
              f"y {Y0+ys.min()*GRID:.1f}-{Y0+ys.max()*GRID:.1f}")
        onit = []
        for q in pads:
            if q['net'] != 'GND': continue
            if m[int(round(gy(q['y']))), int(round(gx(q['x'])))]:
                onit.append(f"{q['ref']}.{q['num']}")
        for net, vx, vy, vr in vias:
            if net == 'GND' and m[int(round(gy(vy))), int(round(gx(vx)))]:
                onit.append(f"via@({vx},{vy})")
        print(f"        GND copper on it: {', '.join(onit) if onit else '(none)'}")

# ------------------------------------- where could a via join a stray island?
if len(groups) > 1:
    big = max(groups, key=lambda k: areas[k])
    VIA_R, VIA_CLR = 0.3, 0.2
    need = VIA_R + VIA_CLR
    free = ~(foreign['F.Cu'] | foreign['B.Cu'])
    dist = ndimage.distance_transform_edt(free) * GRID
    inb = ((WX >= BOARD[0]+EDGE_GAP+VIA_R) & (WX <= BOARD[2]-EDGE_GAP-VIA_R) &
           (WY >= BOARD[1]+EDGE_GAP+VIA_R) & (WY <= BOARD[3]-EDGE_GAP-VIA_R))
    mainB = np.zeros((H, W), bool); mainF = np.zeros((H, W), bool)
    for L, i in groups[big]:
        (mainF if L == 'F.Cu' else mainB)[lab[L] == i] = True
    for k, v in groups.items():
        if k == big: continue
        strayF = np.zeros((H, W), bool); strayB = np.zeros((H, W), bool)
        for L, i in v:
            (strayF if L == 'F.Cu' else strayB)[lab[L] == i] = True
        cand = (((strayF & mainB) | (strayB & mainF)) & inb & (dist >= need)
                & (WX <= 118.0))   # keep clear of the board edge
        print(f"\nvia sites joining the {areas[k]:.1f} mm2 island to the main plane: "
              f"{int(cand.sum())} grid cells qualify")
        if cand.any():
            d2 = np.where(cand, dist, -1)
            order = np.argsort(d2, axis=None)[::-1][:60000]
            shown = []
            for f in order:
                r, c = np.unravel_index(f, d2.shape)
                if d2[r, c] < need: break
                x, y = X0+c*GRID, Y0+r*GRID
                if any(abs(x-sx) < 3.5 and abs(y-sy) < 3.5 for sx, sy in shown): continue
                shown.append((x, y))
                print(f"    ({x:6.2f},{y:6.2f})  nearest foreign copper "
                      f"{d2[r, c]:.2f} mm   F.Cu={'stray' if strayF[r, c] else 'main'}"
                      f"  B.Cu={'main' if mainB[r, c] else ('stray' if strayB[r, c] else '-')}")
                if len(shown) >= 8: break

# ------------------------------------------------ which pads land where
print("\nGND pad membership:")
orphans = []
for p in pads:
    if p['net'] != 'GND': continue
    got = ids_at(p['x'], p['y'], min(p['w'], p['h'])/2 * 0.6)
    hit = {find((L, i)) for L in LAYERS for i in got[L]}
    if not hit:
        orphans.append(f"{p['ref']}.{p['num']} @({p['x']:.2f},{p['y']:.2f})")
if orphans:
    print(f"  {len(orphans)} GND pad(s) touching NO poured copper:")
    for o in orphans: print(f"    {o}")
else:
    print("  every GND pad sits on poured copper")
sys.exit(0 if len(groups) == 1 and not orphans else 1)
