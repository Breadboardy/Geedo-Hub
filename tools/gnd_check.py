#!/usr/bin/env python3
"""Rasterise GND copper on both layers and flood-fill it, the way connectivity
actually works. Avoids point-in-polygon guesswork around zone keyholes."""
import re, math, sys
import numpy as np

import os
P = os.environ.get('BOARD', 'hardware/Geedo_PCB_v4.kicad_pcb')
p = open(P).read()
GRID = 0.05
X0, Y0, X1, Y1 = 89.0, 74.5, 119.5, 127.0
W = int((X1-X0)/GRID)+1
H = int((Y1-Y0)/GRID)+1

def block(s, i):
    d=0;j=i;q=False
    while j < len(s):
        c=s[j]
        if q:
            if c=='"' and s[j-1]!='\\': q=False
        elif c=='"': q=True
        elif c=='(': d+=1
        elif c==')':
            d-=1
            if d==0: return s[i:j+1], j+1
        j+=1
def each(s, pat):
    out=[];i=0;rx=re.compile(pat)
    while True:
        m=rx.search(s,i)
        if not m: return out
        t,e=block(s,m.start()); out.append(t); i=e

nets = dict(re.findall(r'\(net\s+(\d+)\s+"([^"]*)"\)', p))
GID = [k for k,v in nets.items() if v=='GND'][0]

grid = {'F.Cu': np.zeros((H, W), dtype=bool), 'B.Cu': np.zeros((H, W), dtype=bool)}
def gx(x): return (x - X0)/GRID
def gy(y): return (y - Y0)/GRID

def fill_poly(layer, pts):
    """even-odd scanline fill: handles zone keyholes correctly"""
    if len(pts) < 3: return
    ys = [q[1] for q in pts]
    r0 = max(0, int(math.floor(gy(min(ys)))))
    r1 = min(H-1, int(math.ceil(gy(max(ys)))))
    g = grid[layer]
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

def fill_disc(layer, x, y, r):
    c0 = max(0, int(gx(x-r))); c1 = min(W-1, int(gx(x+r))+1)
    r0 = max(0, int(gy(y-r))); r1 = min(H-1, int(gy(y+r))+1)
    for row in range(r0, r1+1):
        dy = (Y0+row*GRID) - y
        if abs(dy) > r: continue
        half = math.sqrt(max(r*r - dy*dy, 0))
        a = max(0, int(math.ceil(gx(x-half)))); b = min(W-1, int(math.floor(gx(x+half))))
        if b >= a: grid[layer][row, a:b+1] = True

def fill_rect(layer, x, y, hw, hh):
    c0 = max(0, int(math.ceil(gx(x-hw)))); c1 = min(W-1, int(math.floor(gx(x+hw))))
    r0 = max(0, int(math.ceil(gy(y-hh)))); r1 = min(H-1, int(math.floor(gy(y+hh))))
    if c1 >= c0 and r1 >= r0: grid[layer][r0:r1+1, c0:c1+1] = True

def fill_seg(layer, a, b, hw):
    n = max(2, int(math.hypot(b[0]-a[0], b[1]-a[1]) / (GRID/2)))
    for k in range(n+1):
        t = k/n
        fill_disc(layer, a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t, hw)

# ---- zone fills
nzone = 0
for zb in each(p, r'\(zone\s'):
    if '(keepout' in zb: continue
    nn = re.search(r'\(net_name\s+"([^"]*)"\)', zb)
    if not nn or nn.group(1) != 'GND': continue
    for fb in each(zb, r'\(filled_polygon\s'):
        lay = re.search(r'\(layer\s+"([^"]*)"\)', fb).group(1)
        pts = [(float(a), float(b)) for a,b in re.findall(r'\(xy\s+([-\d.]+)\s+([-\d.]+)\)', fb)]
        fill_poly(lay, pts); nzone += 1

# ---- GND tracks
ntr = 0
for sb in each(p, r'\n\t\(segment\n'):
    if re.search(r'\(net\s+(\d+)\)', sb).group(1) != GID: continue
    st = re.search(r'\(start\s+([-\d.]+)\s+([-\d.]+)\)', sb)
    en = re.search(r'\(end\s+([-\d.]+)\s+([-\d.]+)\)', sb)
    lay = re.search(r'\(layer\s+"([^"]*)"\)', sb).group(1)
    wdt = float(re.search(r'\(width\s+([\d.]+)\)', sb).group(1))
    fill_seg(lay, (float(st.group(1)), float(st.group(2))),
                  (float(en.group(1)), float(en.group(2))), wdt/2); ntr += 1

# ---- GND pads
bridges = []      # (x, y, r) items that tie F and B together
npad = 0
for fb in each(p, r'\(footprint\s"'):
    ref = re.search(r'\(property\s+"Reference"\s+"([^"]*)"', fb).group(1)
    m = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)', fb)
    fx, fy, fr = float(m.group(1)), float(m.group(2)), float(m.group(3) or 0)
    for pb in each(fb, r'\(pad\s"'):
        nm = re.search(r'\(net\s+\d+\s+"([^"]*)"\)', pb)
        if not nm or nm.group(1) != 'GND': continue
        typ = re.match(r'\(pad\s"[^"]*"\s+(\w+)', pb).group(1)
        pm = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)', pb)
        sm = re.search(r'\(size\s+([-\d.]+)\s+([-\d.]+)', pb)
        lm = re.search(r'\(layers([^)]*)\)', pb)
        dx, dy, pr = float(pm.group(1)), float(pm.group(2)), float(pm.group(3) or 0)
        w, h = (float(sm.group(1)), float(sm.group(2))) if sm else (.5,.5)
        i2 = pb.find('(primitives')
        if i2 > 0:
            q = re.findall(r'\(xy\s+([-\d.]+)\s+([-\d.]+)\)', pb[i2:])
            if q:
                w = max(w, max(abs(float(a)) for a,_ in q)*2)
                h = max(h, max(abs(float(b)) for _,b in q)*2)
        if abs((fr+pr) % 180 - 90) < 1: w, h = h, w
        r = math.radians(fr)
        ax = fx + dx*math.cos(r) + dy*math.sin(r)
        ay = fy - dx*math.sin(r) + dy*math.cos(r)
        lay = lm.group(1) if lm else ''
        th = typ in ('thru_hole',) or '*.Cu' in lay
        for L in (('F.Cu','B.Cu') if th else tuple(c for c in ('F.Cu','B.Cu') if f'"{c}"' in lay)):
            fill_rect(L, ax, ay, w/2, h/2)
        if th: bridges.append((f'{ref}.{pb.split(chr(34))[1]}', ax, ay, min(w,h)/2))
        npad += 1

# ---- GND vias
nv = 0
for vb in each(p, r'\n\t\(via\n'):
    if re.search(r'\(net\s+(\d+)\)', vb).group(1) != GID: continue
    at = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)\)', vb)
    rr = float(re.search(r'\(size\s+([\d.]+)\)', vb).group(1))/2
    x, y = float(at.group(1)), float(at.group(2))
    fill_disc('F.Cu', x, y, rr); fill_disc('B.Cu', x, y, rr)
    bridges.append((f'via@{x},{y}', x, y, rr)); nv += 1

print(f"rasterised {nzone} zone islands, {ntr} tracks, {npad} pads, {nv} vias "
      f"on a {W}x{H} grid at {GRID}mm")

# ---- label components per layer, then merge across layers at bridges
def label(g):
    lab = np.zeros(g.shape, dtype=np.int32)
    cur = 0
    idx = np.argwhere(g)
    seen = set()
    from collections import deque
    for sy, sx in idx:
        if lab[sy, sx]: continue
        cur += 1
        dq = deque([(sy, sx)]); lab[sy, sx] = cur
        while dq:
            y, x = dq.popleft()
            for ny, nx in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)):
                if 0 <= ny < g.shape[0] and 0 <= nx < g.shape[1] and g[ny,nx] and not lab[ny,nx]:
                    lab[ny,nx] = cur; dq.append((ny,nx))
    return lab, cur
labF, nF = label(grid['F.Cu'])
labB, nB = label(grid['B.Cu'])
print(f"copper blobs: F.Cu {nF}, B.Cu {nB}")

par = {}
def find(a):
    par.setdefault(a, a)
    while par[a] != a: par[a] = par[par[a]]; a = par[a]
    return a
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb: par[ra] = rb
for i in range(1, nF+1): find(('F', i))
for i in range(1, nB+1): find(('B', i))
for name, x, y, r in bridges:
    cy, cx = int(round(gy(y))), int(round(gx(x)))
    fs, bs = set(), set()
    rad = max(1, int(r/GRID))
    for dy in range(-rad, rad+1):
        for dx in range(-rad, rad+1):
            yy, xx = cy+dy, cx+dx
            if 0 <= yy < H and 0 <= xx < W:
                if labF[yy,xx]: fs.add(labF[yy,xx])
                if labB[yy,xx]: bs.add(labB[yy,xx])
    allb = [('F', i) for i in fs] + [('B', i) for i in bs]
    for k in allb[1:]: union(allb[0], k)

from collections import defaultdict
comp = defaultdict(list)
for i in range(1, nF+1): comp[find(('F', i))].append(('F', i))
for i in range(1, nB+1): comp[find(('B', i))].append(('B', i))
print(f"\nGND copper resolves to {len(comp)} electrically separate group(s)")
areas = {}
for k, g in comp.items():
    areas[k] = sum(int((labF == i).sum()) if L=='F' else int((labB == i).sum())
                   for L, i in g) * GRID*GRID
order = sorted(comp.items(), key=lambda kv: -areas[kv[0]])
for rank, (k, g) in enumerate(order):
    tag = "MAIN" if rank == 0 else "ORPHAN"
    print(f"\n  [{tag}] area {areas[k]:.2f} mm2 across {len(g)} blob(s)")
    for L, i in sorted(g, key=lambda t: -( (labF==t[1]).sum() if t[0]=='F' else (labB==t[1]).sum() )):
        lab = labF if L == 'F' else labB
        ys, xs = np.where(lab == i)
        a = len(xs)*GRID*GRID
        cx, cy = X0+xs.mean()*GRID, Y0+ys.mean()*GRID
        lo = (X0+xs.min()*GRID, Y0+ys.min()*GRID); hi = (X0+xs.max()*GRID, Y0+ys.max()*GRID)
        layer = 'F.Cu (front)' if L == 'F' else 'B.Cu (back)'
        print(f"      {layer:14s} {a:7.2f} mm2  centre ({cx:.2f}, {cy:.2f})  "
              f"box ({lo[0]:.1f},{lo[1]:.1f})-({hi[0]:.1f},{hi[1]:.1f})")

if len(comp) == 1:
    print("\nEverything on GND is one piece of copper. If DRC still reports an")
    print("unconnected zone, it is not a real break in the ground plane.")
else:
    print("\nZoom to the ORPHAN centre in KiCad and drop a GND via there (hover, press V).")
    print("A via at that spot ties it to the plane on the other layer.")
