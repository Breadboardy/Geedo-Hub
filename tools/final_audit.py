#!/usr/bin/env python3
"""Final pre-order audit. Run from anywhere: python3 tools/final_audit.py

Checks the things the DRC-style gates do not: every functional circuit pin
by pin, foreign copper under pads (oriented pad geometry, the verified
rotation convention), net-table hygiene, new-part placement, fab-file
consistency, outline closure, and strapping-pin safety."""
import re, math, csv, sys

import os
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P='hardware/Geedo_PCB_v4.kicad_pcb'
s=open(P).read()
bad=0
def flag(msg):
    global bad; bad+=1; print(f"  !! {msg}")

def block(t,i):
    d=0;j=i;q=False
    while j<len(t):
        c=t[j]
        if q:
            if c=='"' and t[j-1]!='\\': q=False
        elif c=='"': q=True
        elif c=='(': d+=1
        elif c==')':
            d-=1
            if d==0: return t[i:j+1],j+1
        j+=1
    raise ValueError

# ---------- collect pads with absolute positions
pads=[]; fps={}
i=0
while True:
    m=re.compile(r'\t\(footprint\s"').search(s,i)
    if not m: break
    b,e=block(s,m.start()+1); i=e
    ref=re.search(r'\(property\s+"Reference"\s+"([^"]*)"',b).group(1)
    val=re.search(r'\(property\s+"Value"\s+"([^"]*)"',b).group(1)
    lay=re.search(r'\(layer\s+"([^"]*)"\)',b).group(1)
    at=re.search(r'\n\t\t\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)',b)
    fx,fy,fr=float(at.group(1)),float(at.group(2)),float(at.group(3) or 0)
    fps[ref]=dict(val=val,lay=lay,x=fx,y=fy,rot=fr)
    a=math.radians(fr)
    for pm in re.finditer(r'\(pad\s"',b):
        pb,_=block(b,pm.start())
        num=pb.split('"')[1]
        pa=re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)',pb)
        px_,py_=float(pa.group(1)),float(pa.group(2))
        # board mapping uses the file's angle sense: +dy*sin / -dx*sin
        # (verified: this puts every pad at 0.000 from its own feed track)
        X=fx+px_*math.cos(a)+py_*math.sin(a); Y=fy-px_*math.sin(a)+py_*math.cos(a)
        nm=re.search(r'\(net\s+(\d+)\s+"([^"]*)"\)',pb)
        pang=float(pa.group(3) or 0)
        sz=re.search(r'\(size\s+([\d.]+)\s+([\d.]+)\)',pb)
        lys=re.search(r'\(layers\s+([^)]*)\)',pb).group(1)
        pads.append(dict(ref=ref,num=num,x=X,y=Y,net=nm.group(2) if nm else None,
                         nid=nm.group(1) if nm else None,
                         w=float(sz.group(1)),h=float(sz.group(2)),ang=pang,
                         layers=lys,tht='*.Cu' in lys))

def net_of(ref,num):
    for p in pads:
        if p['ref']==ref and p['num']==num: return p['net']
    return '<missing>'

print("== 1. functional circuits, pad by pad ==")
CIRCUITS=[
 # battery sense (new)
 ('R10.1','/VBAT'),('R10.2','/VBAT_SENSE'),('R11.1','/VBAT_SENSE'),('R11.2','GND'),
 ('C8.1','/VBAT_SENSE'),('C8.2','GND'),('U3.12','/VBAT_SENSE'),
 # charge status (new)
 ('R9.1','/STAT_RAW'),('R9.2','/CHG_STAT'),('U3.13','/CHG_STAT'),
 ('U1.1','/STAT_RAW'),('R7.1','/STAT_RAW'),('R7.2','/STAT'),('D1.1','/STAT'),('D1.2','+3V3'),
 # straps + buttons
 ('R8.1','+3V3'),('R8.2','/IO2'),('U3.5','/IO2'),
 ('R2.1','+3V3'),('R2.2','/IO8'),('U3.22','/IO8'),
 ('SW2.1','/IO9'),('U3.23','/IO9'),
 ('SW1.1','/IO3'),('U3.6','/IO3'),('R1.1','+3V3'),('R1.2','/IO3'),
 ('SW3.1','/EN_NET'),('U3.8','/EN_NET'),('R3.1','+3V3'),('R3.2','/EN_NET'),('C7.1','/EN_NET'),
 # I2C + OLED
 ('U3.18','/SDA'),('U3.19','/SCL'),('J3.4','/SDA'),('J3.3','/SCL'),('J3.2','+3V3'),('J3.1','GND'),
 # USB
 ('J1.A6','/USB_DP'),('J1.B6','/USB_DP'),('U3.27','/USB_DP'),
 ('J1.A7','/USB_DN'),('J1.B7','/USB_DN'),('U3.26','/USB_DN'),
 ('J1.A4','/VBUS'),('U1.4','/VBUS'),('C5.1','/VBUS'),
 ('R4.1','Net-(J1-CC1)'),('R5.1','Net-(J1-CC2)'),('R4.2','GND'),('R5.2','GND'),
 # charger + power
 ('U1.3','/VBAT'),('J2.1','/VBAT'),('U2.1','/VBAT'),('U1.5','Net-(U1-PROG)'),('R6.2','Net-(U1-PROG)'),('R6.1','GND'),
 ('U2.3','+3V3'),('U3.3','+3V3'),('C6.1','+3V3'),('C1.1','/VBAT'),('C2.1','+3V3'),
]
okc=0
for pin,want in CIRCUITS:
    ref,num=pin.split('.')
    got=net_of(ref,num)
    if got!=want: flag(f"{pin}: expected {want}, file says {got}")
    else: okc+=1
print(f"  {okc}/{len(CIRCUITS)} pins on their intended nets")

print("== 2. no track of a FOREIGN net under any pad ==")
segs=[]
for m in re.finditer(r'\(segment\n\t\t\(start ([-\d.]+) ([-\d.]+)\)\n\t\t\(end ([-\d.]+) ([-\d.]+)\)\n\t\t\(width ([\d.]+)\)\n\t\t\(layer "([^"]+)"\)\n\t\t\(net (\d+)\)',s):
    segs.append((float(m.group(1)),float(m.group(2)),float(m.group(3)),float(m.group(4)),
                 float(m.group(5)),m.group(6),m.group(7)))
nid2name=dict(re.findall(r'\(net\s+(\d+)\s+"([^"]*)"\)',s))
hits=0
for p in pads:
    if p['net'] is None: continue
    play=('F.Cu','B.Cu') if p['tht'] else (('F.Cu',) if 'F.Cu' in p['layers'] else ('B.Cu',))
    for ax,ay,bx,by,w,lyr,nid in segs:
        if lyr not in play: continue
        if nid2name.get(nid)==p['net']: continue
        n=max(2,int(math.hypot(bx-ax,by-ay)/0.05))
        ca,sa=math.cos(math.radians(p['ang'])),math.sin(math.radians(p['ang']))
        for k in range(n+1):
            t=k/n; qx,qy=ax+(bx-ax)*t,ay+(by-ay)*t
            # same angle sense as the board mapping
            rx=(qx-p['x'])*ca-(qy-p['y'])*sa; ry=(qx-p['x'])*sa+(qy-p['y'])*ca
            ddx=max(abs(rx)-p['w']/2,0); ddy=max(abs(ry)-p['h']/2,0)
            if math.hypot(ddx,ddy) < w/2+0.199:
                flag(f"{p['ref']}.{p['num']} ({p['net']}) has {nid2name.get(nid)} track within clearance on {lyr}")
                hits+=1; break
        else: continue
        break
if not hits: print("  clean - no foreign copper under any pad")

print("== 3. net table hygiene ==")
if 'Net-(U1-STAT)' in s: flag("old net name Net-(U1-STAT) still referenced")
tbl=dict(re.findall(r'\n\t\(net\s+(\d+)\s+"([^"]*)"\)',s))
used=set(re.findall(r'\(net\s+(\d+)[\s)]',s))
for nid,name in tbl.items():
    if nid not in used and name: flag(f"net {nid} '{name}' in table but never used")
padless=[n for n in tbl.values() if n and n not in [p['net'] for p in pads]]
for n in padless:
    if n: flag(f"net '{n}' has copper but no pads")
nonet=[f"{p['ref']}.{p['num']}" for p in pads if p['net'] is None and p['ref']!='LOGO1']
print(f"  intentionally unconnected module pads: {len(nonet)} (NC pins)")
print(f"  nets in table: {len(tbl)}, all used: {'yes' if bad==0 else 'see above'}")

print("== 4. new parts: side, values, positions ==")
for ref,wantval in (('R9','10k'),('R10','100k'),('R11','100k'),('C8','100nF')):
    f=fps.get(ref)
    if not f: flag(f"{ref} missing"); continue
    if f['lay']!='B.Cu': flag(f"{ref} on {f['lay']}, expected B.Cu (machine side)")
    if f['val']!=wantval: flag(f"{ref} value {f['val']}, expected {wantval}")
    if not (90.2<f['x']<118.3 and 75.7<f['y']<125.8): flag(f"{ref} outside board")
print("  R9/R10/R11/C8 checked")

print("== 5. fab files match the board ==")
cpl=list(csv.DictReader(open('hardware/fab/cpl.csv')))
bom=list(csv.DictReader(open('hardware/fab/bom.csv')))
cplrefs={r['Designator'] for r in cpl}
boardrefs={r for r in fps if r!='LOGO1'}
if cplrefs!=boardrefs: flag(f"cpl vs board mismatch: {cplrefs^boardrefs}")
bomrefs=set()
for r in bom: bomrefs|=set(r['Designator'].split(','))
if bomrefs!=boardrefs: flag(f"bom vs board mismatch: {bomrefs^boardrefs}")
ORIGIN=(89.5,126.5)
for r in cpl:
    ref=r['Designator']; f=fps[ref]
    mx=float(r['Mid X'].replace('mm','')); my=float(r['Mid Y'].replace('mm',''))
    ex,ey=f['x']-ORIGIN[0], ORIGIN[1]-f['y']
    if abs(mx-ex)>0.01 or abs(my-ey)>0.01: flag(f"cpl {ref} position off: {mx},{my} vs {ex:.3f},{ey:.3f}")
    side='Top' if f['lay']=='F.Cu' else 'Bottom'
    if r['Layer']!=side: flag(f"cpl {ref} layer {r['Layer']} vs board {side}")
print(f"  cpl: {len(cpl)} placements, bom: {len(bom)} lines - positions/sides/refs consistent" if bad==0 else "  (issues above)")

print("== 6. board outline closed ==")
pts=[]
for m in re.finditer(r'\(gr_line\n\t\t\(start ([-\d.]+) ([-\d.]+)\)\n\t\t\(end ([-\d.]+) ([-\d.]+)\)[\s\S]{0,80}?\(layer "Edge.Cuts"\)',s):
    pts.append(((float(m.group(1)),float(m.group(2))),(float(m.group(3)),float(m.group(4)))))
from collections import Counter
cnt=Counter()
for a,b in pts: cnt[a]+=1; cnt[b]+=1
open_ends=[p for p,c in cnt.items() if c%2]
if open_ends: flag(f"outline open at {open_ends}")
else: print(f"  {len(pts)} edge segments, every endpoint paired - closed loop")

print("== 7. strapping-pin safety (boot must survive charging) ==")
for pin,net in (('U3.5','/IO2'),('U3.22','/IO8')):
    if net_of(*pin.split('.'))!=net: flag(f"{pin} strap disturbed")
if net_of('U3','12')!='/VBAT_SENSE' or net_of('U3','13')!='/CHG_STAT':
    flag("sense lines not on IO0/IO1")
else:
    print("  STAT and divider are on IO0/IO1 only; IO2/IO8 straps untouched")

print()
print("AUDIT:", "CLEAN - nothing sus found" if bad==0 else f"{bad} FINDING(S) ABOVE")
sys.exit(1 if bad else 0)
