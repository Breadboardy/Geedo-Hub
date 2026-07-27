#!/usr/bin/env python3
"""Build a self-contained HTML player for Geedo animations.

    python3 tools/preview_anim.py                  # every animation in the library
    python3 tools/preview_anim.py a.bin b.bin      # just these
    python3 tools/preview_anim.py -o /tmp/out.html

Decodes GDA1 the same way the firmware does - SSD1306 page order, per-frame
durations, loop and ping-pong flags - so what you see is what Geedo shows.
The frames are embedded as base64, so the page works offline with no server.
"""
import base64, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
args = [a for a in sys.argv[1:] if not a.startswith('-')]
out = Path(sys.argv[sys.argv.index('-o') + 1]) if '-o' in sys.argv else ROOT / 'assets' / 'preview.html'

paths = [Path(a) for a in args] or sorted((ROOT / 'animations' / 'bin').glob('*.bin'))

anims = []
for p in paths:
    d = p.read_bytes()
    if d[:4] != b'GDA1':
        print(f"skip {p.name}: not GDA1", file=sys.stderr)
        continue
    n, fps, flags = d[5], d[6], d[7]
    if len(d) != 8 + n + n * 1024:
        print(f"skip {p.name}: size {len(d)} != expected {8+n+n*1024}", file=sys.stderr)
        continue
    anims.append({
        'name': p.stem,
        'n': n, 'fps': fps, 'flags': flags,
        'dur': list(d[8:8 + n]),
        'data': base64.b64encode(d[8 + n:]).decode(),
        'ms': sum(d[8:8 + n]) * (1000 // max(1, fps)),
    })

if not anims:
    sys.exit("no animations found")
anims.sort(key=lambda a: a['name'])

HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Geedo animation preview</title>
<style>
 :root{--ink:#dfe7ff;--dim:#7b86a8;--line:#232a44;--on:#cfe3ff}
 *{box-sizing:border-box}
 body{margin:0;background:#0a0d18;color:var(--ink);
      font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
 .wrap{display:flex;gap:20px;padding:20px;min-height:100vh;flex-wrap:wrap}
 .side{width:270px;flex:0 0 auto;max-height:92vh;overflow:auto;
       border:1px solid var(--line);border-radius:10px;padding:6px}
 .side b{display:block;padding:8px 10px;color:var(--dim);font-weight:600;
         letter-spacing:.08em;font-size:11px;text-transform:uppercase}
 .it{padding:7px 10px;border-radius:7px;cursor:pointer;white-space:nowrap;
     overflow:hidden;text-overflow:ellipsis}
 .it:hover{background:#151c33}
 .it.on{background:#1d284a;color:#fff}
 .it small{color:var(--dim);display:block;font-size:11px}
 .main{flex:1 1 420px;min-width:320px}
 canvas{width:100%;max-width:768px;image-rendering:pixelated;display:block;
        background:#000;border:1px solid var(--line);border-radius:10px}
 .row{display:flex;gap:10px;align-items:center;margin-top:14px;flex-wrap:wrap}
 button{background:#18213c;color:var(--ink);border:1px solid var(--line);
        border-radius:8px;padding:8px 14px;cursor:pointer;font:inherit}
 button:hover{background:#222d4e}
 input[type=range]{flex:1 1 160px;min-width:120px;accent-color:#5b8cff}
 .meta{color:var(--dim);margin-top:10px;font-size:12px}
 h1{font-size:15px;margin:0 0 4px;letter-spacing:.04em}
</style></head><body>
<div class="wrap">
 <div class="side" id="list"></div>
 <div class="main">
  <h1 id="title"></h1>
  <div class="meta" id="sub"></div>
  <canvas id="cv" width="128" height="64"></canvas>
  <div class="row">
   <button id="pp">Pause</button>
   <button id="prev">&#8592; frame</button>
   <button id="next">frame &#8594;</button>
   <label style="color:var(--dim)">speed</label>
   <input type="range" id="spd" min="10" max="300" value="100">
   <span id="spdv" style="color:var(--dim);min-width:44px">1.00x</span>
  </div>
  <div class="row">
   <input type="range" id="scrub" min="0" max="0" value="0">
   <span id="fno" style="color:var(--dim);min-width:96px"></span>
  </div>
  <div class="meta" id="info"></div>
 </div>
</div>
<script>
const ANIMS = __DATA__;
const cv = document.getElementById('cv'), cx = cv.getContext('2d');
const img = cx.createImageData(128, 64);
let cur = 0, fi = 0, playing = true, dir = 1, acc = 0, last = 0, speed = 1;

function bytes(a) {
  if (a._b) return a._b;
  const s = atob(a.data), b = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) b[i] = s.charCodeAt(i);
  return (a._b = b);
}
function draw(a, f) {
  const b = bytes(a), off = f * 1024, d = img.data;
  for (let y = 0; y < 64; y++) for (let x = 0; x < 128; x++) {
    const on = (b[off + (y >> 3) * 128 + x] >> (y & 7)) & 1;
    const i = (y * 128 + x) * 4;
    d[i] = on ? 207 : 6; d[i+1] = on ? 227 : 9; d[i+2] = on ? 255 : 20; d[i+3] = 255;
  }
  cx.putImageData(img, 0, 0);
}
function frameMs(a, f) { return (1000 / Math.max(1, a.fps)) * (a.dur[f] || 1); }

function select(i) {
  cur = i; fi = 0; dir = 1; acc = 0;
  const a = ANIMS[i];
  document.getElementById('title').textContent = a.name;
  const fl = [(a.flags & 1) ? 'loop' : 'once', (a.flags & 2) ? 'ping-pong' : null]
             .filter(Boolean).join(' + ');
  document.getElementById('sub').textContent =
    a.n + ' frames . ' + a.fps + ' fps . ' + (a.ms/1000).toFixed(1) + 's . ' + fl;
  document.getElementById('info').textContent =
    (a.n * 1024 / 1024).toFixed(0) + ' KB of frame data';
  const sc = document.getElementById('scrub'); sc.max = a.n - 1; sc.value = 0;
  [...document.querySelectorAll('.it')].forEach((e, k) => e.classList.toggle('on', k === i));
  draw(a, 0); stamp();
}
function stamp() {
  document.getElementById('fno').textContent =
    'frame ' + (fi + 1) + ' / ' + ANIMS[cur].n + '  (' + ANIMS[cur].dur[fi] + 'x)';
  document.getElementById('scrub').value = fi;
}
function step(ts) {
  if (!last) last = ts;
  const dt = (ts - last) * speed; last = ts;
  const a = ANIMS[cur];
  if (playing) {
    acc += dt;
    let guard = 0;
    while (acc >= frameMs(a, fi) && guard++ < 300) {
      acc -= frameMs(a, fi);
      fi += dir;
      if (fi >= a.n) {
        if (a.flags & 2) { dir = -1; fi = Math.max(0, a.n - 2); }
        else fi = 0;
      } else if (fi < 0) {
        if (a.flags & 2) { dir = 1; fi = Math.min(a.n - 1, 1); }
        else fi = a.n - 1;
      }
    }
    draw(a, fi); stamp();
  }
  requestAnimationFrame(step);
}
const list = document.getElementById('list');
list.innerHTML = '<b>' + ANIMS.length + ' animations</b>';
ANIMS.forEach((a, i) => {
  const e = document.createElement('div');
  e.className = 'it';
  e.innerHTML = a.name.replace(/</g,'&lt;') +
    '<small>' + a.n + ' frames . ' + (a.ms/1000).toFixed(1) + 's</small>';
  e.onclick = () => select(i);
  list.appendChild(e);
});
document.getElementById('pp').onclick = e => {
  playing = !playing; e.target.textContent = playing ? 'Pause' : 'Play';
};
document.getElementById('prev').onclick = () => {
  playing = false; document.getElementById('pp').textContent = 'Play';
  fi = (fi - 1 + ANIMS[cur].n) % ANIMS[cur].n; draw(ANIMS[cur], fi); stamp();
};
document.getElementById('next').onclick = () => {
  playing = false; document.getElementById('pp').textContent = 'Play';
  fi = (fi + 1) % ANIMS[cur].n; draw(ANIMS[cur], fi); stamp();
};
document.getElementById('spd').oninput = e => {
  speed = e.target.value / 100;
  document.getElementById('spdv').textContent = speed.toFixed(2) + 'x';
};
document.getElementById('scrub').oninput = e => {
  playing = false; document.getElementById('pp').textContent = 'Play';
  fi = +e.target.value; draw(ANIMS[cur], fi); stamp();
};
select(Math.max(0, ANIMS.findIndex(a => /boot_boot|boot_anim/.test(a.name))));
requestAnimationFrame(step);
</script></body></html>"""

out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(HTML.replace('__DATA__', json.dumps(anims, separators=(',', ':'))))
kb = out.stat().st_size / 1024
print(f"{len(anims)} animations, {sum(a['n'] for a in anims)} frames -> {out} ({kb:.0f} KB)")
for a in anims[:6]:
    print(f"   {a['name']:44s} {a['n']:3d} frames  {a['ms']/1000:5.1f}s")
if len(anims) > 6:
    print(f"   ... and {len(anims)-6} more")
