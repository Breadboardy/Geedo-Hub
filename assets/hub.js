/* Geedo accounts and publishing: a page's side of the Hub's server.

   The Hub is plain files, and files cannot remember who somebody is or take
   a drawing in. A small server does those two things, and its address is in
   assets/hub.json. WHILE THAT ADDRESS IS EMPTY THERE ARE NO ACCOUNTS: on()
   answers false, and a page that asks keeps to what works without one (the
   Studio's save-and-hand-in steps).

   An account is a maker name and a password. No email, no real name. So:

   - The password never leaves this device. It is stretched here (PBKDF2,
     250,000 rounds, salted with the maker's name) and only the key that
     comes out is sent. The server keeps a salted hash of that key.
   - With no email there is no "send me a link". Signing up shows a recovery
     code once; that code and a new password are the way back in.
   - Being signed in is a token kept in this browser (localStorage). Signing
     out, or changing the password elsewhere, ends it.

   Nothing here can put an animation on a robot. publish() puts a drawing in
   a queue; a person looks at every one before it goes out, as always.

   window.GeedoHub:
     ready                       a promise: the address has been read
     on()                        is there a server?
     who()                       { name } of whoever is signed in here, or null
     changed(fn)                 call fn whenever that changes
     signup(name, password)      -> { name, recovery }
     login(name, password)       -> { name }
     reset(name, code, password) -> { name, recovery }   (forgot the password)
     logout()
     password(old, next), remove(password)
     free(name)                  -> { free, why }         (is this maker name taken?)
     publish({ name, bytes, remix_of })  -> { id }       bytes: the robot's file, as the Studio exports it
     mine()                      -> [{ id, name, at, state, note, anim, frames, fps }]
     withdraw(id)
     say(error)                  a sentence for a person, for anything thrown here            */
(() => {
'use strict';

const ROOT = document.currentScript && document.currentScript.src ? new URL('..', document.currentScript.src).href : '';
const STORE = 'geedoMaker';
const ROUNDS = 250000;
let api = '';

const ready = (async () => {
  // A server on this computer, for trying things - and only when the page is
  // on this computer too, so no link to the real site can point it elsewhere.
  const local = /^(localhost|127\.0\.0\.1)$/;
  const want = new URLSearchParams(location.search).get('api') || '';
  if (local.test(location.hostname) && /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(want)) { api = want; return; }
  try {
    const c = await (await fetch(ROOT + 'assets/hub.json', { cache: 'no-cache' })).json();
    if (typeof c.api === 'string' && /^https:\/\/[A-Za-z0-9.-]+(:\d+)?(\/[A-Za-z0-9._~\/-]*)?$/.test(c.api)) api = c.api.replace(/\/+$/, '');
  } catch (e) { /* no file, no server: the page carries on without accounts */ }
})();

// ---- names, the way the server tells them apart ------------------------------
const cleanName = v => String(v == null ? '' : v).normalize('NFKC').replace(/\s+/g, ' ').trim();
const goodName = v => { const s = cleanName(v); return s.length >= 3 && s.length <= 20 && /^[A-Za-z0-9](?:[A-Za-z0-9 _-]*[A-Za-z0-9])?$/.test(s); };
const makerKey = v => cleanName(v).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');

// ---- who is signed in, in this browser ----------------------------------------
const listeners = new Set();
function read() { try { const s = JSON.parse(localStorage.getItem(STORE) || 'null'); return s && s.name && /^[0-9a-f]{64}$/.test(s.token) ? s : null; } catch (e) { return null; } }
function keep(s) { try { if (s) localStorage.setItem(STORE, JSON.stringify(s)); else localStorage.removeItem(STORE); } catch (e) {} for (const fn of listeners) { try { fn(who()); } catch (e) {} } }
const who = () => { const s = read(); return s && api ? { name: s.name } : null; };
// signed in or out in another tab: this one follows
addEventListener('storage', e => { if (e.key === STORE) for (const fn of listeners) { try { fn(who()); } catch (x) {} } });

class HubError extends Error {
  constructor(code, more = {}) { super(code); this.code = code; Object.assign(this, more); }
}
async function call(method, path, body, signedIn) {
  if (!api) throw new HubError('no-server');
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (signedIn) { const s = read(); if (!s) throw new HubError('sign-in'); headers.Authorization = 'Bearer ' + s.token; }
  let r, j;
  try { r = await fetch(api + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) }); j = await r.json(); }
  catch (e) { throw new HubError('offline'); }
  if (j && j.ok) return j;
  const code = (j && j.error) || 'server';
  if (signedIn && (code === 'sign-in' || code === 'banned')) keep(null);       // the session is over: say so everywhere
  throw new HubError(code, j || {});
}

// The password, stretched: slow on purpose, so a stolen copy of the server's
// list is no use for guessing. The same name always gives the same salt,
// however its capitals and spaces are typed.
async function stretch(name, password) {
  if (!(window.crypto && crypto.subtle)) throw new HubError('old-browser');
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey('raw', enc.encode(String(password).normalize('NFKC')), 'PBKDF2', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits({ name: 'PBKDF2', hash: 'SHA-256', salt: enc.encode('geedo-hub|' + makerKey(name)), iterations: ROUNDS }, key, 256);
  return [...new Uint8Array(bits)].map(b => b.toString(16).padStart(2, '0')).join('');
}
function base64(bytes) { let s = ''; for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000)); return btoa(s); }

async function signup(name, password) {
  const j = await call('POST', '/signup', { name: cleanName(name), key: await stretch(name, password) });
  keep({ name: j.name, token: j.token });
  return { name: j.name, recovery: j.recovery };
}
async function login(name, password) {
  const j = await call('POST', '/login', { name: cleanName(name), key: await stretch(name, password) });
  keep({ name: j.name, token: j.token });
  return { name: j.name };
}
async function reset(name, code, password) {
  const j = await call('POST', '/reset', { name: cleanName(name), code, key: await stretch(name, password) });
  keep({ name: j.name, token: j.token });
  return { name: j.name, recovery: j.recovery };
}
async function logout() { try { await call('POST', '/logout', {}, true); } catch (e) {} keep(null); }
async function password(old, next) { const s = read(); if (!s) throw new HubError('sign-in'); await call('POST', '/password', { key: await stretch(s.name, old), next: await stretch(s.name, next) }, true); }
async function remove(pass) { const s = read(); if (!s) throw new HubError('sign-in'); await call('POST', '/delete', { key: await stretch(s.name, pass) }, true); keep(null); }
const free = name => call('GET', '/maker?name=' + encodeURIComponent(cleanName(name)));
async function publish({ name, bytes, remix_of }) {
  const body = { name: String(name || '').trim(), rules: true, bin: base64(bytes) };
  if (remix_of) body.remix_of = remix_of;
  return call('POST', '/publish', body, true);
}
const mine = async () => (await call('GET', '/mine', undefined, true)).items;
const withdraw = id => call('POST', '/withdraw', { id }, true);
// Is the session still good? (Signs out here if the server says it is not.)
async function check() { if (!read() || !api) return null; try { const j = await call('GET', '/me', undefined, true); return { name: j.name, waiting: j.waiting, room: j.room }; } catch (e) { return e.code === 'offline' ? who() : null; } }

// ---- words for people ----------------------------------------------------------
function wait(seconds) {
  const s = Math.max(1, seconds | 0);
  if (s < 90) return 'a minute';
  if (s < 3600) return Math.round(s / 60) + ' minutes';
  if (s < 2 * 3600) return 'an hour';
  return s < 20 * 3600 ? Math.round(s / 3600) + ' hours' : 'until tomorrow';
}
function say(e) {
  const c = e && e.code;
  switch (c) {
    case 'offline':          return 'Could not reach the Hub. Check the internet and try again.';
    case 'no-server':        return 'Accounts are not switched on yet.';
    case 'old-browser':      return 'This browser is too old to keep a password safe. Try a newer one.';
    case 'wrong':            return 'That name and password do not match.';
    case 'name-taken':       return 'Somebody already has that name. Try another.';
    case 'name-bad':         return 'A maker name is 3 to 20 letters or numbers. Spaces, - and _ are fine in the middle.';
    case 'slow-down':        return e.retry >= 20 * 3600 ? 'That is enough for today. There is room again tomorrow.' : `That is a lot of tries. Wait ${wait(e.retry)} and try again.`;
    case 'too-many-waiting': return `You already have ${e.max || 3} waiting for a look. When one has been looked at there is room for another.`;
    case 'title-bad':        return 'Give it a name of up to 40 letters, and keep it kind.';
    case 'rules':            return 'Tick the three rules first.';
    case 'not-an-animation': return 'That is not an animation Geedo can play. Try saving the project and opening it again.';
    case 'too-big':          return 'Packed, it is too big for Geedo’s shelf: the limit is 32 KB. Fewer frames, or simpler ones.';
    case 'too-many-frames':  return `${e.frames || 'That many'} frames is more than Geedo has room for: ${e.max || 96} at most.`;
    case 'too-fast':         return 'Geedo plays 1 to 30 frames a second.';
    case 'flashes':          return `It flashes ${e.flashes || 'too many'} times in one second. More than 3 big flashes a second can hurt people, so Geedo refuses to play it.`;
    case 'banned':           return 'This account has been switched off. Ask on the Discord if that looks like a mistake.';
    case 'sign-in':          return 'Sign in again.';
    case 'not-waiting':      return 'That one has already been looked at.';
    default:                 return 'The Hub’s server is having a moment. Try again in a little while.';
  }
}

window.GeedoHub = { ready, on: () => !!api, who, check, changed: fn => { listeners.add(fn); return () => listeners.delete(fn); },
                    signup, login, reset, logout, password, remove, free, publish, mine, withdraw, say,
                    goodName, cleanName, makerKey, root: ROOT };
})();
