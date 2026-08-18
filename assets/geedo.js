/* ===========================================================================
   GEEDO — shared front-end

   The site plays the SAME .bin files the robots download. Not previews, not
   exported GIFs - the exact bytes off the Hub, decoded in the browser. If it
   looks right here it looks right on the device, because it is the same data.

   Two things this has to get right:

   1. One clock, not thirty. Thirty animations on a page means thirty
      setTimeout chains all waking the browser independently, which is what
      makes a page like this feel like sludge on a phone. There is a single
      requestAnimationFrame loop and every screen is advanced from it.
   2. Off-screen screens do not draw. An IntersectionObserver parks anything
      scrolled out of view, so the cost is what you can actually see.
   =========================================================================== */
(() => {
'use strict';

const W = 128, H = 64;

/* ---- GDA1 -----------------------------------------------------------------
   'GDA1' + [ver, frameCount, fps, flags] + durations[frameCount] + pixels[]
   Pixels are page-major: 8 pages of 128 bytes, each byte holding 8 vertical
   pixels, bit 0 at the top. That is the SSD1306's own memory layout, which is
   why the robot can blit a frame straight to the panel with no conversion.
   flags: bit0 = loop, bit1 = ping-pong.                                     */
function unpackGda1(bytes){
  if (bytes.length < 8 || String.fromCharCode(...bytes.slice(0,4)) !== 'GDA1')
    throw new Error('not a GDA1 animation');
  const count = bytes[5], fps = bytes[6] || 8, flags = bytes[7];
  const body = 8 + count, frames = [];
  for (let f = 0; f < count; f++){
    const px = new Uint8Array(W * H), off = body + f * 1024;
    for (let page = 0; page < 8; page++){
      for (let x = 0; x < W; x++){
        const b = bytes[off + page * W + x];
        if (!b) continue;                     // blank column: skip 8 writes
        for (let bit = 0; bit < 8; bit++)
          if (b >> bit & 1) px[(page * 8 + bit) * W + x] = 1;
      }
    }
    frames.push({ pixels: px, dur: bytes[8 + f] || 1 });
  }
  return { frames, fps, loop: !!(flags & 1), pingpong: !!(flags & 2) };
}

/* ---- one clock for every screen on the page ----------------------------- */
const live = new Set();
let ticking = false, paused = false;

function tick(now){
  // Checked at the TOP: setting ticking=false from outside does not stop a
  // frame that is already scheduled, so the loop has to agree to stop here.
  if (paused){ ticking = false; return; }
  for (const s of live) s._advance(now);
  ticking = live.size > 0;
  if (ticking) requestAnimationFrame(tick);
}
function wake(){
  if (!ticking && !paused && live.size){ ticking = true; requestAnimationFrame(tick); }
}

const seen = new IntersectionObserver(entries => {
  for (const e of entries){
    const s = e.target._geedo;
    if (!s) continue;
    if (e.isIntersecting){ live.add(s); s.last = 0; wake(); }
    else live.delete(s);
  }
}, { rootMargin: '120px' });

/* Tab in the background: stop entirely rather than burn battery. */
document.addEventListener('visibilitychange', () => {
  paused = document.hidden;
  if (!paused){ for (const s of live) s.last = 0; wake(); }
});

class Screen {
  /* scale is a WHOLE number on purpose - a 128px-wide image drawn at 1.7x has
     pixels of two different widths, and on a pixel-art face that reads as a
     rendering bug rather than a style. Width is capped by CSS instead. */
  constructor(anim, { scale = 2, className = '' } = {}){
    this.anim = anim; this.i = 0; this.dir = 1; this.last = 0;
    const wrap = document.createElement('div');
    wrap.className = 'screen ' + className;
    const c = document.createElement('canvas');
    c.width = W; c.height = H;
    c.style.width = (W * scale) + 'px';
    wrap.appendChild(c);
    this.el = wrap;
    this.ctx = c.getContext('2d', { alpha: false });
    this.img = this.ctx.createImageData(W, H);
    this.img.data.fill(255);                   // opaque; only RGB changes below
    this.draw();
    wrap._geedo = this;
    seen.observe(wrap);
  }
  draw(){
    const px = this.anim.frames[this.i].pixels, d = this.img.data;
    for (let i = 0, p = 0; i < W * H; i++, p += 4){
      const v = px[i] ? 255 : 0;
      d[p] = v; d[p+1] = v; d[p+2] = v;
    }
    this.ctx.putImageData(this.img, 0, 0);
  }
  _advance(now){
    const f = this.anim.frames[this.i];
    const hold = 1000 / this.anim.fps * (f.dur || 1);
    if (!this.last){ this.last = now; return; }
    if (now - this.last < hold) return;
    this.last = now;
    const n = this.anim.frames.length;
    if (n < 2) return;
    if (this.anim.pingpong){
      if (this.i + this.dir >= n || this.i + this.dir < 0) this.dir *= -1;
      this.i += this.dir;
    } else {
      this.i = (this.i + 1) % n;
    }
    this.draw();
  }
  destroy(){ seen.unobserve(this.el); live.delete(this); }
}

/* ---- data ---------------------------------------------------------------- */
const HUB = location.pathname.replace(/\/[^/]*$/, '');
const cache = new Map();

async function loadBin(file){
  if (cache.has(file)) return cache.get(file);
  const p = fetch(`animations/${file}`)
    .then(r => { if (!r.ok) throw new Error(r.status); return r.arrayBuffer(); })
    .then(b => unpackGda1(new Uint8Array(b)));
  cache.set(file, p);
  return p;
}

/* manifest.json is the source of truth: it is what the robots read, so the
   site cannot drift from what is actually shipping. (index.json is an older,
   partial copy of the same idea and is deliberately not used.) */
const manifest = () => fetch('animations/manifest.json').then(r => r.json());
const firmware = () => fetch('firmware/manifest.json').then(r => r.json()).catch(() => null);

/* Names in the manifest were typed at different times by different tools, so
   they arrive as "Chill_Work", "helloo", "failed_to_connect". Raw identifiers
   showing through in the interface is most of what makes a site look
   unfinished. Tidied for display only - the manifest is what the robots read
   and is left exactly as it is. */
function pretty(name){
  const s = String(name || '').replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/* ---- nav ----------------------------------------------------------------- */
function nav(){
  const btn = document.querySelector('.nav-toggle');
  const links = document.querySelector('.nav-links');
  if (btn && links) btn.addEventListener('click', () => links.classList.toggle('open'));
  const here = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-links a.link').forEach(a => {
    if (a.getAttribute('href') === here) a.setAttribute('aria-current', 'page');
  });
}
document.readyState === 'loading'
  ? document.addEventListener('DOMContentLoaded', nav)
  : nav();

window.Geedo = { W, H, unpackGda1, Screen, loadBin, manifest, firmware, pretty, HUB };
})();
