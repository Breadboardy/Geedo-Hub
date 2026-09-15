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

/* ---- the robot's file --------------------------------------------------------
   'GDA1' + [ver, frameCount, fps, flags] + durations[frameCount] + pixels[]
   Pixels are page-major: 8 pages of 128 bytes, each byte holding 8 vertical
   pixels, bit 0 at the top. That is the SSD1306's own memory layout, which is
   why the robot can blit a frame straight to the panel with no conversion.
   flags: bit0 = loop, bit1 = ping-pong.

   'GDA2' is the same header, then a table of uint32 offsets - one per frame
   and one for the end of the last - and each frame packed as chunks: a
   control byte c < 0x80 means "the next c+1 bytes are literal", c >= 0x80
   means "the next byte repeats c-0x7F times", until the 1024 bytes of the
   page are out. Bold shapes on black pack to about a quarter, which is what
   lets a robot's shelf hold every pack. tools/gda.py in the source repo
   writes it; this and the firmware read it the same way.                   */
function unpackFrame(bytes, off, end){
  const page = new Uint8Array(1024);
  let ip = off, op = 0;
  while (op < 1024){
    if (ip >= end) throw new Error('packed frame ends early');
    const c = bytes[ip++];
    if (c < 0x80){
      const n = c + 1;
      if (op + n > 1024 || ip + n > end) throw new Error('packed frame overruns');
      page.set(bytes.subarray(ip, ip + n), op); ip += n; op += n;
    } else {
      const n = c - 0x7F;
      if (op + n > 1024 || ip >= end) throw new Error('packed frame overruns');
      page.fill(bytes[ip++], op, op + n); op += n;
    }
  }
  if (ip !== end) throw new Error('packed frame has bytes left over');
  return page;
}
function pageToPixels(page){
  const px = new Uint8Array(W * H);
  for (let p = 0; p < 8; p++){
    for (let x = 0; x < W; x++){
      const b = page[p * W + x];
      if (!b) continue;                       // blank column: skip 8 writes
      for (let bit = 0; bit < 8; bit++)
        if (b >> bit & 1) px[(p * 8 + bit) * W + x] = 1;
    }
  }
  return px;
}
function unpack(bytes){
  const magic = bytes.length >= 8 ? String.fromCharCode(...bytes.slice(0,4)) : '';
  if (magic !== 'GDA1' && magic !== 'GDA2') throw new Error('not a Geedo animation');
  const count = bytes[5], fps = bytes[6] || 8, flags = bytes[7], frames = [];
  if (magic === 'GDA1'){
    const body = 8 + count;
    for (let f = 0; f < count; f++)
      frames.push({ pixels: pageToPixels(bytes.subarray(body + f * 1024, body + (f + 1) * 1024)),
                    dur: bytes[8 + f] || 1 });
  } else {
    const t = 8 + count, dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const off = i => dv.getUint32(t + 4 * i, true);
    for (let f = 0; f < count; f++)
      frames.push({ pixels: pageToPixels(unpackFrame(bytes, off(f), off(f + 1))),
                    dur: bytes[8 + f] || 1 });
  }
  return { frames, fps, loop: !!(flags & 1), pingpong: !!(flags & 2) };
}
const unpackGda1 = unpack;                   // the old name, for anything still calling it

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
    .then(b => unpack(new Uint8Array(b)));
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

/* ---- the whole shelf ------------------------------------------------------
   Everything a robot can play: the free list, plus every pack channel the
   main manifest names. One flat list, each entry knowing where it came from,
   so the browse page, the maker pages and the search see packs too. */
let allP = null;
function all(){
  if (allP) return allP;
  allP = (async () => {
    const m = await manifest();
    const anims = (m.animations || []).map(a => ({
      ...a, pack: null, by: a.author || 'breadboard', src: a.file,
      key: a.id, href: `animation.html?id=${encodeURIComponent(a.id)}`
    }));
    const packs = [];
    for (const id of m.packs || []){
      try {
        const r = await fetch(`animations/packs/${id}/manifest.json`);
        if (!r.ok) throw new Error(r.status);
        const pm = await r.json();
        pm.id = pm.id || id;
        pm.animations = pm.animations || [];
        packs.push(pm);
        for (const a of pm.animations) anims.push({
          ...a, pack: id, packName: pm.name || pretty(id), rarity: pm.rarity || 'common',
          by: a.author || pm.author || 'breadboard', category: a.category || `pack:${id}`,
          published_at: a.published_at || pm.published_at || null,
          src: `packs/${id}/${a.file}`, key: `${id}/${a.id}`,
          href: `animation.html?id=${encodeURIComponent(a.id)}&pack=${encodeURIComponent(id)}`
        });
      } catch (e) { /* a missing channel is the packs page's job to report */ }
    }
    return { anims, packs, manifest: m };
  })();
  return allP;
}

/* System screens: what he shows while booting, updating or failing. Real
   animations, on the Hub like the rest, but not what a visitor came to see
   first, so the front page's picks skip them. */
const isSystem = a => /hello_geedo|boot|update|error|charging|low_battery|failed|connecting|turning/.test(a.id);

/* Newest first; something with no date sorts after everything with one. */
function newest(anims){
  return [...anims].sort((a, b) =>
    String(b.published_at || '').localeCompare(String(a.published_at || '')) ||
    pretty(a.name).localeCompare(pretty(b.name)));
}

/* "3 days ago" for cards, the full date for the animation page. */
function ago(iso){
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return '';
  const days = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (days <= 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days} days ago`;
  if (days < 30){ const w = Math.floor(days / 7); return w === 1 ? 'last week' : `${w} weeks ago`; }
  return d.toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
}
function datestr(iso){
  const d = new Date(iso);
  return isNaN(d) ? '' : d.toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' });
}
const isNew = a => a.published_at && (Date.now() - new Date(a.published_at).getTime()) < 7 * 86400000;
const kb = n => `${(n / 1024).toFixed(1)} KB`;
const param = name => new URLSearchParams(location.search).get(name);

/* The people. Grouped from the manifest's author fields - there is no
   separate list to fall out of date with. */
function makers(anims){
  const by = new Map();
  for (const a of anims){
    if (!by.has(a.by)) by.set(a.by, { name: a.by, anims: [], latest: '' });
    const m = by.get(a.by);
    m.anims.push(a);
    if ((a.published_at || '') > m.latest) m.latest = a.published_at || '';
  }
  return [...by.values()]
    .map(m => ({ ...m, count: m.anims.length }))
    .sort((x, y) => y.count - x.count || x.name.localeCompare(y.name));
}
const makerHref = name => `maker.html?name=${encodeURIComponent(name)}`;
const initial = name => (name || '?').trim().charAt(0);

/* ---- a card: one animation on a page ---------------------------------------
   The screen, the name, who drew it, and how long ago. The file loads after
   the card is on the page, so a hundred cards appear at once and fill in. */
function card(a, { sticker = true, scale = 2 } = {}){
  const el = document.createElement('a');
  el.className = 'card';
  el.href = a.href;
  const holder = document.createElement('div');
  holder.className = 'screen sm blank';
  const name = document.createElement('div');
  name.className = 'name';
  name.textContent = pretty(a.name || a.id);
  const by = document.createElement('div');
  by.className = 'by';
  const who = document.createElement('span');
  who.innerHTML = 'by <b></b>';
  who.querySelector('b').textContent = a.by;
  const when = document.createElement('span');
  when.className = 'when';
  when.textContent = a.pack ? pretty(a.packName) : ago(a.published_at);
  by.append(who, when);
  el.append(holder, name, by);
  if (sticker && isNew(a) && !a.pack){
    const s = document.createElement('span');
    s.className = 'sticker';
    s.textContent = 'NEW';
    el.append(s);
  }
  loadBin(a.src).then(anim => {
    const s = new Screen(anim, { scale, className: 'sm' });
    s.el.querySelector('canvas').style.width = '100%';
    el.replaceChild(s.el, holder);
    el._screen = s;
  }).catch(() => {
    holder.classList.remove('blank');
    holder.style.aspectRatio = '2/1';
    el.style.opacity = '.5';
    when.textContent = 'unavailable';
  });
  return el;
}

/* A big screen for a hero or an animation page: integer scale, capped by
   the column it sits in. */
function bigScreen(anim, scale = 3, className = ''){
  const s = new Screen(anim, { scale, className });
  return s;
}

/* ---- nav ----------------------------------------------------------------- */
function nav(){
  const btn = document.querySelector('.nav-toggle');
  const links = document.querySelector('.nav-links');
  if (btn && links) btn.addEventListener('click', () => links.classList.toggle('open'));
  const here = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-links a').forEach(a => {
    if (a.getAttribute('href') === here) a.setAttribute('aria-current', 'page');
  });
}
document.readyState === 'loading'
  ? document.addEventListener('DOMContentLoaded', nav)
  : nav();

window.Geedo = { W, H, unpack, unpackGda1, Screen, loadBin, manifest, firmware, pretty, HUB,
                 all, isSystem, newest, ago, datestr, isNew, kb, param, makers, makerHref, initial, card, bigScreen };
})();
