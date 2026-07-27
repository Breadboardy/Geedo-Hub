#!/usr/bin/env python3
"""Route every non-GND net on the flipped board from scratch.

Per net: while its copper (pads + new tracks/vias) forms >1 island, pick the
smallest island, A* from one of its pads to any copper of the other islands,
add the result to the obstacle model, repeat. Nets are processed most-
constrained first. GND is left to the pour + a stitching pass.

Geometry model matches tools/drc_offline.py: oval pads are stadiums, roundrect
corner radii honoured, custom pads take their primitive extent, stored pad
angles are absolute.
"""
import re, math, uuid, heapq, sys
sys.setrecursionlimit(100000)

P = 'work.kicad_pcb'
src = open(P).read()

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

def toks(s, pat):
    out = []; i = 0; rx = re.compile(pat)
    while True:
        m = rx.search(s, i)
        if not m: return out
        t, e = block(s, m.start()); out.append(t); i = e

CU = ('F.Cu', 'B.Cu')
LAY = {'F.Cu': 0, 'B.Cu': 1}
CLR = 0.2
EDGE = (89.5, 75.0, 119.0, 126.5)
KEEP = (90.575, 96.91, 103.775, 102.31)

# ---------------- pads
def _custom_extent(pb, w, h):
    i = pb.find('(primitives')
    if i < 0: return w, h
    pts = re.findall(r'\(xy\s+([-\d.]+)\s+([-\d.]+)\)', pb[i:])
    if not pts: return w, h
    return max(w, max(abs(float(a)) for a, _ in pts)*2), \
           max(h, max(abs(float(b)) for _, b in pts)*2)

pads = []
for fb in toks(src, r'\(footprint\s"'):
    ref = re.search(r'\(property\s+"Reference"\s+"([^"]*)"', fb).group(1)
    m = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)', fb)
    fx, fy, fr = float(m.group(1)), float(m.group(2)), float(m.group(3) or 0)
    for pb in toks(fb, r'\(pad\s"'):
        num = pb.split('"')[1]
        typ = re.match(r'\(pad\s"[^"]*"\s+(\w+)', pb).group(1)
        nm = re.search(r'\(net\s+\d+\s+"([^"]*)"\)', pb)
        pm = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)', pb)
        sm = re.search(r'\(size\s+([-\d.]+)\s+([-\d.]+)', pb)
        lm = re.search(r'\(layers([^)]*)\)', pb)
        dx, dy, pr = float(pm.group(1)), float(pm.group(2)), float(pm.group(3) or 0)
        w, h = (float(sm.group(1)), float(sm.group(2))) if sm else (.5, .5)
        if 'custom' in pb[:60]: w, h = _custom_extent(pb, w, h)
        if abs(pr % 180 - 90) < 1: w, h = h, w
        a = math.radians(fr)
        ax = fx + dx*math.cos(a) + dy*math.sin(a)
        ay = fy - dx*math.sin(a) + dy*math.cos(a)
        lay = lm.group(1) if lm else ''
        pth = typ in ('thru_hole', 'np_thru_hole') or '*.Cu' in lay
        layers = set(CU) if pth else {c for c in CU if f'"{c}"' in lay}
        pads.append(dict(ref=ref, num=num, net=nm.group(1) if nm else None,
                         x=ax, y=ay, w=w, h=h, layers=layers, typ=typ))

netname = dict(re.findall(r'\(net\s+(\d+)\s+"([^"]*)"\)', src))
netid = {v: k for k, v in netname.items()}

class Model:
    def __init__(self):
        self.newsegs = []
        self.newvias = []
M = Model()

def seg_dist(pt, a, b):
    (x1, y1), (x2, y2) = a, b
    dx, dy = x2-x1, y2-y1; L2 = dx*dx+dy*dy
    if L2 == 0: return math.hypot(pt[0]-x1, pt[1]-y1)
    t = max(0, min(1, ((pt[0]-x1)*dx + (pt[1]-y1)*dy)/L2))
    return math.hypot(pt[0]-(x1+t*dx), pt[1]-(y1+t*dy))

def pad_clear(pd, pt, extra):
    ddx = max(abs(pt[0]-pd['x']) - pd['w']/2, 0)
    ddy = max(abs(pt[1]-pd['y']) - pd['h']/2, 0)
    return math.hypot(ddx, ddy) >= extra

# ---------------- own-copper islands for a net
def net_items(net):
    out = []
    for pd in pads:
        if pd['net'] == net: out.append(('pad', pd, None))
    for s in M.newsegs:
        if s['net'] == net: out.append(('seg', s, s['layer']))
    for v in M.newvias:
        if v['net'] == net: out.append(('via', v, None))
    return out

def islands(net):
    items = net_items(net)
    par = list(range(len(items)))
    def find(i):
        while par[i] != i: par[i] = par[par[i]]; i = par[i]
        return i
    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj: par[ri] = rj
    def layers_of(it):
        k, o, L = it
        if k == 'pad': return o['layers']
        if k == 'via': return set(CU)
        return {L}
    def touch(A, B):
        if not (layers_of(A) & layers_of(B)): return False
        ka, a, _ = A; kb, b, _ = B
        def rep(k, o):
            if k == 'pad': return ('rect', o['x'], o['y'], o['w']/2, o['h']/2)
            if k == 'via': return ('circ', o['x'], o['y'], o['r'])
            return ('seg', o)
        ra, rb = rep(ka, a), rep(kb, b)
        if ra[0] == 'seg' and rb[0] == 'seg':
            sa, sb = ra[1], rb[1]
            return min(seg_dist(sa['a'], sb['a'], sb['b']), seg_dist(sa['b'], sb['a'], sb['b']),
                       seg_dist(sb['a'], sa['a'], sa['b']), seg_dist(sb['b'], sa['a'], sa['b'])) \
                   <= sa['w']/2 + sb['w']/2 + 0.02
        if ra[0] == 'seg' or rb[0] == 'seg':
            sg = ra[1] if ra[0] == 'seg' else rb[1]
            o = rb if ra[0] == 'seg' else ra
            if o[0] == 'rect':
                # sample the segment against the exact rectangle
                n = max(2, int(math.hypot(sg['b'][0]-sg['a'][0], sg['b'][1]-sg['a'][1])/0.05))
                for k2 in range(n+1):
                    t = k2/n
                    px = sg['a'][0] + (sg['b'][0]-sg['a'][0])*t
                    py = sg['a'][1] + (sg['b'][1]-sg['a'][1])*t
                    ddx = max(abs(px-o[1]) - o[3], 0); ddy = max(abs(py-o[2]) - o[4], 0)
                    if math.hypot(ddx, ddy) <= sg['w']/2 + 0.02: return True
                return False
            return seg_dist((o[1], o[2]), sg['a'], sg['b']) <= sg['w']/2 + o[3] + 0.02
        if ra[0] == 'rect' and rb[0] == 'rect':
            dx = max(abs(ra[1]-rb[1]) - ra[3] - rb[3], 0)
            dy = max(abs(ra[2]-rb[2]) - ra[4] - rb[4], 0)
            return math.hypot(dx, dy) <= 0.02
        if ra[0] == 'rect' or rb[0] == 'rect':
            rc = ra if ra[0] == 'rect' else rb
            ci = rb if ra[0] == 'rect' else ra
            dx = max(abs(rc[1]-ci[1]) - rc[3], 0)
            dy = max(abs(rc[2]-ci[2]) - rc[4], 0)
            return math.hypot(dx, dy) <= ci[3] + 0.02
        return math.hypot(ra[1]-rb[1], ra[2]-rb[2]) <= ra[3] + rb[3] + 0.02
    for i in range(len(items)):
        for j in range(i+1, len(items)):
            if touch(items[i], items[j]): union(i, j)
    groups = {}
    for i in range(len(items)):
        groups.setdefault(find(i), []).append(items[i])
    return list(groups.values())

# ---------------- A*
def route(net, start, startpad, targets, window, width, via_size, via_drill,
          grid=0.05, via_cost=25, layer0='B.Cu', max_iter=1400000):
    half = width/2; vr = via_size/2
    x0, y0, x1, y1 = window
    m = 2.0
    lp = [pd for pd in pads if x0-m <= pd['x'] <= x1+m and y0-m <= pd['y'] <= y1+m]
    ls = [sg for sg in M.newsegs
          if not (max(sg['a'][0], sg['b'][0]) < x0-m or min(sg['a'][0], sg['b'][0]) > x1+m or
                  max(sg['a'][1], sg['b'][1]) < y0-m or min(sg['a'][1], sg['b'][1]) > y1+m)]
    lv = [v for v in M.newvias if x0-m <= v['x'] <= x1+m and y0-m <= v['y'] <= y1+m]

    def blocked(layer, pt, hf):
        x, y = pt
        if not (EDGE[0]+0.5+hf <= x <= EDGE[2]-0.5-hf): return True
        if not (EDGE[1]+0.5+hf <= y <= EDGE[3]-0.5-hf): return True
        if KEEP[0]-hf < x < KEEP[2]+hf and KEEP[1]-hf < y < KEEP[3]+hf: return True
        for pd in lp:
            if pd['net'] == net and pd['typ'] != 'np_thru_hole': continue
            if layer not in pd['layers']: continue
            extra = 0.32 if pd['typ'] == 'np_thru_hole' else CLR
            if not pad_clear(pd, pt, hf + extra): return True
        for sg in ls:
            if sg['net'] == net or sg['layer'] != layer: continue
            if seg_dist(pt, sg['a'], sg['b']) < sg['w']/2 + hf + CLR: return True
        for v in lv:
            if v['net'] == net: continue
            if math.hypot(x-v['x'], y-v['y']) < v['r'] + hf + CLR: return True
        return False

    def via_ok(pt):
        return not blocked('F.Cu', pt, vr) and not blocked('B.Cu', pt, vr)

    def is_target(pt, il):
        L = CU[il]
        for kind, it, tl in targets:
            if kind == 'pad':
                if L not in it['layers']: continue
                if abs(pt[0]-it['x']) <= it['w']/2 and abs(pt[1]-it['y']) <= it['h']/2:
                    return True
            elif kind == 'seg':
                if tl != L: continue
                if seg_dist(pt, it['a'], it['b']) <= it['w']/2 + half: return True
            else:
                if math.hypot(pt[0]-it['x'], pt[1]-it['y']) <= it['r']: return True
        return False

    nx = int((x1-x0)/grid)+1; ny = int((y1-y0)/grid)+1
    def pos(ix, iy): return (round(x0+ix*grid, 3), round(y0+iy*grid, 3))
    six = round((start[0]-x0)/grid); siy = round((start[1]-y0)/grid)
    if not (0 <= six < nx and 0 <= siy < ny): return None
    sil = LAY[layer0]
    cache = {}
    def blk(ix, iy, il):
        k = (ix, iy, il)
        if k in cache: return cache[k]
        pt = pos(ix, iy)
        r = blocked(CU[il], pt, half)
        if r and startpad is not None and CU[il] in startpad['layers'] and \
           abs(pt[0]-startpad['x']) <= startpad['w']/2 and abs(pt[1]-startpad['y']) <= startpad['h']/2:
            r = False
        cache[k] = r
        return r
    DIRS = [(1,0,1.0),(-1,0,1.0),(0,1,1.0),(0,-1,1.0),
            (1,1,1.42),(1,-1,1.42),(-1,1,1.42),(-1,-1,1.42)]
    tx = sum(it[1]['x'] if it[0] != 'seg' else (it[1]['a'][0]+it[1]['b'][0])/2 for it in targets)/len(targets)
    ty = sum(it[1]['y'] if it[0] != 'seg' else (it[1]['a'][1]+it[1]['b'][1])/2 for it in targets)/len(targets)
    openq = [(0.0, six, siy, sil)]
    g = {(six, siy, sil): 0.0}
    came = {}
    found = None
    it_count = 0
    while openq:
        f, ix, iy, il = heapq.heappop(openq)
        it_count += 1
        if it_count > max_iter: break
        key = (ix, iy, il)
        pt = pos(ix, iy)
        if is_target(pt, il) and key != (six, siy, sil):
            found = key; break
        for dx, dy, cost in DIRS:
            jx, jy = ix+dx, iy+dy
            if not (0 <= jx < nx and 0 <= jy < ny): continue
            if blk(jx, jy, il): continue
            nk = (jx, jy, il)
            ng = g[key] + cost*grid
            if ng < g.get(nk, 1e9):
                g[nk] = ng; came[nk] = key
                heapq.heappush(openq, (ng + math.hypot(jx-((tx-x0)/grid), jy-((ty-y0)/grid))*grid*0.99, jx, jy, il))
        ol = 1-il
        if not blk(ix, iy, ol) and via_ok(pt) and \
           (KEEP[0]-vr > pt[0] or pt[0] > KEEP[2]+vr or KEEP[1]-vr > pt[1] or pt[1] > KEEP[3]+vr):
            nk = (ix, iy, ol)
            ng = g[key] + via_cost*grid
            if ng < g.get(nk, 1e9):
                g[nk] = ng; came[nk] = key
                heapq.heappush(openq, (ng + math.hypot(ix-((tx-x0)/grid), iy-((ty-y0)/grid))*grid*0.99, ix, iy, ol))
    if not found:
        return None
    path = [found]
    while path[-1] in came: path.append(came[path[-1]])
    path.reverse()
    out_segs = []; out_vias = []
    i = 0
    while i < len(path)-1:
        j = i
        if path[j+1][2] != path[j][2]:
            x, y = pos(path[j][0], path[j][1])
            out_vias.append((x, y))
            i += 1; continue
        dx = path[j+1][0]-path[j][0]; dy = path[j+1][1]-path[j][1]
        k = j+1
        while k+1 < len(path) and path[k+1][2] == path[k][2] and \
              (path[k+1][0]-path[k][0], path[k+1][1]-path[k][1]) == (dx, dy):
            k += 1
        out_segs.append((pos(path[j][0], path[j][1]), pos(path[k][0], path[k][1]), CU[path[j][2]]))
        i = k
    # snap end to target centreline
    endpt = pos(path[-1][0], path[-1][1]); endL = CU[path[-1][2]]
    best = None
    for kind, it, tl in targets:
        if kind == 'pad':
            if endL not in it['layers']: continue
            q = (min(max(endpt[0], it['x']-it['w']/2), it['x']+it['w']/2),
                 min(max(endpt[1], it['y']-it['h']/2), it['y']+it['h']/2))
        elif kind == 'seg':
            if tl != endL: continue
            (ax, ay), (bx, by) = it['a'], it['b']
            ddx, ddy = bx-ax, by-ay; L2 = ddx*ddx+ddy*ddy
            t = 0 if L2 == 0 else max(0, min(1, ((endpt[0]-ax)*ddx + (endpt[1]-ay)*ddy)/L2))
            q = (ax+t*ddx, ay+t*ddy)
        else:
            q = (it['x'], it['y'])
        d = math.hypot(q[0]-endpt[0], q[1]-endpt[1])
        if best is None or d < best[0]: best = (d, q)
    if best and best[0] > 1e-6:
        out_segs.append((endpt, (round(best[1][0], 3), round(best[1][1], 3)), endL))
    if startpad is not None:
        p0 = pos(path[0][0], path[0][1])
        if abs(p0[0]-startpad['x']) > 0.01 or abs(p0[1]-startpad['y']) > 0.01:
            out_segs.insert(0, ((startpad['x'], startpad['y']), p0, CU[path[0][2]]))
    for a, b, L in out_segs:
        M.newsegs.append(dict(a=a, b=b, layer=L, w=width, net=net))
    for x, y in out_vias:
        if not any(abs(x-v['x']) < 1e-6 and abs(y-v['y']) < 1e-6 for v in M.newvias):
            M.newvias.append(dict(x=x, y=y, r=via_size/2, drill=via_drill, net=net))
    return out_segs, out_vias

# ---------------- per-net driver
POWER = [(0.5, 0.7, 0.4), (0.4, 0.6, 0.3), (0.3, 0.5, 0.3), (0.25, 0.45, 0.25)]
USB   = [(0.3, 0.5, 0.3), (0.25, 0.45, 0.25), (0.2, 0.45, 0.25)]
SIG   = [(0.25, 0.5, 0.3), (0.2, 0.45, 0.25)]
CLASS = {'+3V3': POWER, '/VBAT': POWER, '/VBUS': POWER,
         '/USB_DP': USB, '/USB_DN': USB}

def bbox_of(isl):
    xs = []; ys = []
    for kind, it, L in isl:
        if kind == 'seg':
            xs += [it['a'][0], it['b'][0]]; ys += [it['a'][1], it['b'][1]]
        else:
            xs.append(it['x']); ys.append(it['y'])
    return min(xs), min(ys), max(xs), max(ys)

def connect_net(net, tries=3):
    for round_ in range(40):
        isl = islands(net)
        if len(isl) <= 1:
            return True
        isl.sort(key=len)
        small = isl[0]
        rest = [it for g in isl[1:] for it in g]
        spads = [it for it in small if it[0] == 'pad'] or small
        # start from the pad in the small island closest to the rest
        def centre(it):
            k, o, L = it
            if k == 'seg': return ((o['a'][0]+o['b'][0])/2, (o['a'][1]+o['b'][1])/2)
            return (o['x'], o['y'])
        rc = [centre(it) for it in rest]
        def dmin(it):
            c = centre(it)
            return min(math.hypot(c[0]-q[0], c[1]-q[1]) for q in rc)
        spads.sort(key=dmin)
        ok = False
        for sp in spads[:tries]:
            k, o, L = sp
            start = centre(sp)
            startpad = o if k == 'pad' else None
            nearest = min(rest, key=lambda it: math.hypot(centre(it)[0]-start[0],
                                                          centre(it)[1]-start[1]))
            nx0, ny0, nx1, ny1 = bbox_of([sp, nearest])
            for attempt, (w, vs, vd) in enumerate(CLASS.get(net, SIG)):
                for margin in (3.0, 7.0, 14.0):
                    win = (max(EDGE[0], nx0-margin), max(EDGE[1], ny0-margin),
                           min(EDGE[2], nx1+margin), min(EDGE[3], ny1+margin))
                    L0 = 'B.Cu' if (startpad is None or 'B.Cu' in startpad['layers']) else 'F.Cu'
                    r = route(net, start, startpad, rest, win, w, vs, vd, layer0=L0)
                    if r:
                        sgs, vv = r
                        print(f"   OK  {net:16s} island({len(small)}) -> rest: "
                              f"{len(sgs)} segs {len(vv)} vias  w={w}")
                        ok = True; break
                if ok: break
            if ok: break
        if not ok:
            print(f"   FAIL {net}: could not join island of {len(small)} item(s) "
                  f"at {bbox_of(small)}")
            return False
    return False

ORDER = ['/USB_DP', '/USB_DN', '/VBUS', '/VBAT', 'Net-(J1-CC1)', 'Net-(J1-CC2)',
         '/EN_NET', '/IO9', '/IO8', '/IO2', '/IO3', '/SCL', '/SDA',
         '/STAT', 'Net-(U1-STAT)', 'Net-(U1-PROG)', '+3V3']
allok = True
for net in ORDER:
    print(f"== {net}")
    if not connect_net(net):
        allok = False
print()
print("routing", "COMPLETE" if allok else "INCOMPLETE - not writing")
if not allok:
    sys.exit(1)

# ---------------- emit
add = []
for sg in M.newsegs:
    nid = netid[sg['net']]
    add.append(f'\n\t(segment\n\t\t(start {sg["a"][0]} {sg["a"][1]})\n\t\t(end {sg["b"][0]} {sg["b"][1]})'
               f'\n\t\t(width {sg["w"]})\n\t\t(layer "{sg["layer"]}")\n\t\t(net {nid})\n\t\t(uuid "{uuid.uuid4()}")\n\t)')
for v in M.newvias:
    nid = netid[v['net']]
    add.append(f'\n\t(via\n\t\t(at {v["x"]} {v["y"]})\n\t\t(size {2*v["r"]})\n\t\t(drill {v.get("drill",0.3)})'
               f'\n\t\t(layers "F.Cu" "B.Cu")\n\t\t(net {nid})\n\t\t(uuid "{uuid.uuid4()}")\n\t)')
anchor = re.compile(r'\n\t\(zone\s').search(src)
out = src[:anchor.start()] + ''.join(add) + src[anchor.start():]
d = 0; q = False
for j, c in enumerate(out):
    if q:
        if c == '"' and out[j-1] != '\\': q = False
    elif c == '"': q = True
    elif c == '(': d += 1
    elif c == ')': d -= 1
assert d == 0
open(P, 'w').write(out)
print(f"wrote {len(M.newsegs)} segments + {len(M.newvias)} vias")
