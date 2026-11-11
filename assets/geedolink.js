/* geedolink.js - one implementation of the cable.
 *
 * A web page cannot find a Geedo over WiFi. There is no browser API that
 * scans a network or resolves an mDNS name, and there is not going to be
 * one: a page that could list the things on your home network would be a
 * privacy hole with a nice UI. So the site does not look for him on WiFi -
 * and since v31 his radio is off between check-ins anyway, there would be
 * nothing to find most of the time.
 *
 * The cable is how a browser meets a robot. Web Serial gives three things
 * that together feel like detection rather than a file picker:
 *
 *   getPorts()      the ports this visitor ALREADY granted. A Geedo he has
 *                   connected before is reconnected with no picker at all.
 *   'connect'       fires when one of those is plugged in. He appears on
 *                   the page by himself, which is the bit that feels magic.
 *   requestPort()   with a USB filter, so the picker offers Espressif
 *                   devices rather than every serial port on the machine.
 *
 * Identity still costs a round trip: Web Serial deliberately does not hand
 * out serial numbers, so which Geedo a port is can only be learned by
 * opening it and asking. That is what INFO is for.
 *
 * A plain script, not a module, on purpose. Chrome refuses to load a module
 * into a page opened straight from the disk, and people do double-click
 * these pages - the old connect page worked that way and must keep working.
 * Load it with <script src="assets/geedolink.js"> and use window.GeedoLink.
 */
const ESP32 = 0x303a;                  // Espressif's USB vendor id

/* Everything above the bytes: the line discipline, ask/answer, INFO, the
   chunked transfers. A transport only has to open, close and _send text,
   and hand received text to _feed. The cable (GeedoLink) and Bluetooth
   (GeedoBle, firmware v37) are the two. */
class GeedoWire {
  constructor() {
    this.pending = null;
    this.listeners = [];
    this.info = null;
    this._buf = '';
  }

  onLine(fn) { this.listeners.push(fn); return this; }
  say(line, mine) { for (const fn of this.listeners) fn(line, mine); }

  _feed(text) {
    this._buf += text;
    let nl;
    while ((nl = this._buf.indexOf('\n')) >= 0) {
      const line = this._buf.slice(0, nl).replace(/\r$/, '');
      this._buf = this._buf.slice(nl + 1);
      this._line(line);
    }
    if (this._buf.length > 4096) this._buf = '';        // a robot mid-boot can spew
  }

  _line(line) {
    // He prints a great deal of ordinary debug chatter to the same port, so
    // every ANSWER starts with "GEEDO ". That prefix is the whole protocol.
    const mine = line.startsWith('GEEDO ');
    this.say(line, mine);
    if (!this.pending || !mine) return;
    this.pending.lines.push(line);
    // "Busy joining his WiFi" (v39) ends an ask whatever it was waiting
    // for: ask() hears it and asks again in a moment.
    if (this.pending.until.test(line) || GeedoWire.BUSY.test(line)) {
      clearTimeout(this.pending.timer);
      const { done, lines } = this.pending;
      this.pending = null;
      done(lines);
    }
  }

  /** One command; resolves to his reply lines, up to the one `until`
   *  matches. While he is joining his WiFi (firmware v39) he answers what
   *  he can and tells the radio commands to wait; those are asked again
   *  every 3 s, six times at most, which outlasts any join (12 s). */
  async ask(cmd, until, ms = 8000, shown) {
    for (let tries = 0; ; tries++) {
      const lines = await this._ask1(cmd, until, ms, shown);
      if (!GeedoWire.BUSY.test(lines[lines.length - 1] || '') || tries >= 6) return lines;
      if (tries === 0) this.say('(he is joining his WiFi - asking again in a moment)', false);
      await new Promise(r => setTimeout(r, 3000));
    }
  }

  _ask1(cmd, until, ms, shown) {
    return new Promise((done, fail) => {
      if (!this.ready) return fail(new Error('not connected'));
      this.pending = { lines: [], until, done, timer: setTimeout(() => {
        this.pending = null; fail(new Error('Geedo did not answer'));
      }, ms) };
      this.say('> ' + (shown || cmd), 'sent');
      this._send(cmd + '\n').catch(() => {});
    });
  }

  /** INFO, parsed. Also cached on the link as `.info`. */
  async hello() {
    let out;
    try { out = await this.ask('INFO', /^GEEDO INFO /, 8000); }
    catch (e) {
      // A check-in holds him for a few seconds (TLS on his chip blocks), and
      // firmware before v39 heard nothing at all while joining WiFi - so one
      // silence is asked again before it counts as "not answering".
      if (!this.ready) throw e;
      this.say('(he is busy - asking once more)', false);
      out = await this.ask('INFO', /^GEEDO INFO /, 15000);
    }
    const kv = {};
    out[out.length - 1].slice('GEEDO INFO '.length).trim()
      .split(/\s+/).forEach(p => {
        const eq = p.indexOf('=');
        if (eq > 0) kv[p.slice(0, eq)] = p.slice(eq + 1);
      });
    const [used, total] = (kv.fs || '0/0').split('/').map(Number);
    kv.usedKB = Math.round(used / 1024);
    kv.totalKB = Math.round(total / 1024);
    this.info = kv;
    return kv;
  }

  /** Bytes as one base64 string, no line breaks: what PKADD carries. */
  static b64(bytes) {
    let bin = '';
    for (const b of bytes) bin += String.fromCharCode(b);
    return btoa(bin);
  }

  /** Why a WiFi join failed, from the reason he gives (firmware v39):
   *  INFO's wifi=, or the last word of a refused JOIN, RADIO, CODE or UPDATE. */
  static wifiWords(reason) {
    return {
      'not-found': 'he cannot see his network - is the router on, and is he in range?',
      'wrong-password': 'his network will not let him in - has the password changed?',
      'failed': 'the connection keeps failing - try him nearer the router',
      'none': 'he has no WiFi network saved',
    }[reason] || '';
  }

  /** His refusal in words: "GEEDO ERR UPEND no-room" -> "no room". */
  static why(line) {
    const m = /^GEEDO ERR \S+ (.+)$/.exec(line);
    return m ? m[1].replace(/-/g, ' ') : line;
  }

  /** The chunks of a transfer, whatever PKNEW or UPNEW opened. */
  async _chunks(b64, onProgress) {
    const CHUNK = 1368;                       // base64 chars a line, like FRAME
    for (let i = 0; i < b64.length; i += CHUNK) {
      const part = b64.slice(i, i + CHUNK);
      const out = await this.ask(`PKADD ${part}`, /^GEEDO (OK|ERR) PKADD/, 15000,
                                 `PKADD …${i + part.length}/${b64.length}`);
      if (out[out.length - 1].startsWith('GEEDO ERR')) throw new Error(out[out.length - 1]);
      if (onProgress) onProgress((i + part.length) / b64.length);
    }
  }

  /** A pack, down the wire. `plain` is the decrypted pack, as bytes. */
  async sendPack(plain, onProgress) {
    await this.ask(`PKNEW ${plain.length}`, /^GEEDO (OK|ERR) PKNEW/, 15000);
    await this._chunks(GeedoWire.b64(plain), onProgress);
    const end = await this.ask('PKEND', /^GEEDO (OK|ERR) PKEND/, 60000);
    const line = end[end.length - 1];
    if (line.startsWith('GEEDO ERR')) throw new Error(line);
    return line;
  }

  /** One animation of the owner's own, down the wire (firmware v35). */
  async sendAnim(bytes, name, onProgress) {
    const clean = String(name || '').replace(/[^\x20-\x7e]/g, '').trim().slice(0, 24);
    const start = await this.ask(`UPNEW ${bytes.length}${clean ? ' ' + clean : ''}`,
                                 /^GEEDO (OK|ERR) UPNEW/, 15000);
    if (start[start.length - 1].startsWith('GEEDO ERR'))
      throw new Error(GeedoWire.why(start[start.length - 1]));
    await this._chunks(GeedoWire.b64(bytes), onProgress);
    const end = await this.ask('UPEND', /^GEEDO (OK|ERR) UPEND/, 60000);
    const line = end[end.length - 1];
    if (line.startsWith('GEEDO ERR')) throw new Error(GeedoWire.why(line));
    return line.split(/\s+/)[3];
  }

  /** Bring his radio up on the network he remembers and hold it there ten
   *  minutes (firmware v35). Resolves to the address his own page is at. */
  async radioOn() {
    const out = await this.ask('RADIO on', /^GEEDO (OK|ERR) RADIO/, 20000);
    const line = out[out.length - 1];
    const reason = (line.match(/could-not-join (\S+)/) || [])[1];
    if (line.startsWith('GEEDO ERR')) throw new Error(GeedoWire.wifiWords(reason) || GeedoWire.why(line));
    return line.split(/\s+/)[4];
  }
}

GeedoWire.BUSY = /^GEEDO ERR \S+ busy-joining-wifi/;

/* ---- the cable: Web Serial ------------------------------------------------ */
class GeedoLink extends GeedoWire {
  static get supported() { return 'serial' in navigator; }

  /** Geedos this visitor has already allowed, ready to reconnect silently. */
  static async known() {
    if (!GeedoLink.supported) return [];
    const ports = await navigator.serial.getPorts();
    return ports.filter(GeedoLink.looksLikeGeedo).map(p => new GeedoLink(p));
  }

  /** The picker, narrowed to his chip so it is a short list. */
  static async pick() {
    const port = await navigator.serial.requestPort({
      filters: [{ usbVendorId: ESP32 }] });
    return new GeedoLink(port);
  }

  static looksLikeGeedo(port) {
    const i = port.getInfo ? port.getInfo() : {};
    return i.usbVendorId === undefined || i.usbVendorId === ESP32;
  }

  /** Plugged in / pulled out, for ports already granted. */
  static watch(onPlug, onUnplug) {
    if (!GeedoLink.supported) return;
    navigator.serial.addEventListener('connect', e => {
      if (GeedoLink.looksLikeGeedo(e.target)) onPlug(new GeedoLink(e.target));
    });
    navigator.serial.addEventListener('disconnect', e => onUnplug(e.target));
  }

  constructor(port) {
    super();
    this.port = port;
    this.writer = null;
  }

  get ready() { return !!this.writer; }
  async _send(text) { await this.writer.write(new TextEncoder().encode(text)); }

  async open({ settle = 1500 } = {}) {
    await this.port.open({ baudRate: 115200 });
    this.writer = this.port.writable.getWriter();
    this._read();
    // Opening the port can reset him, so let him finish booting or the
    // first command lands in the bootloader's lap.
    if (settle) await new Promise(r => setTimeout(r, settle));
    return this;
  }

  async close() {
    try { this.writer && this.writer.releaseLock(); } catch (e) {}
    try { await this.port.close(); } catch (e) {}
    this.writer = null;
  }

  async _read() {
    const dec = new TextDecoderStream();
    this.port.readable.pipeTo(dec.writable).catch(() => {});
    const reader = dec.readable.getReader();
    for (;;) {
      let chunk;
      try { chunk = await reader.read(); } catch (e) { break; }
      if (chunk.done) break;
      this._feed(chunk.value);
    }
    this.say('(disconnected)', false);
  }

}

/* ---- Bluetooth: Web Bluetooth, firmware v37 -----------------------------
   He advertises as GEEDO-XXXXXX with a UART-style service: a phone or a
   PC with Bluetooth writes lines to RX and his answers arrive as
   notifications on TX. The same protocol as the cable, byte for byte.
   Android and desktop Chrome and Edge have Web Bluetooth; Safari does not. */
const NUS = '6e400001-b5a3-f393-e0a9-e50e24dcca9e';
const NUS_RX = '6e400002-b5a3-f393-e0a9-e50e24dcca9e';
const NUS_TX = '6e400003-b5a3-f393-e0a9-e50e24dcca9e';

class GeedoBle extends GeedoWire {
  static get supported() { return 'bluetooth' in navigator; }

  /** The picker, narrowed to Geedos by their name. */
  static async pick() {
    const device = await navigator.bluetooth.requestDevice({
      filters: [{ namePrefix: 'GEEDO-' }], optionalServices: [NUS] });
    return new GeedoBle(device);
  }

  /** Geedos this visitor has already allowed, where the browser keeps them. */
  static async known() {
    if (!GeedoBle.supported || !navigator.bluetooth.getDevices) return [];
    try {
      const devs = await navigator.bluetooth.getDevices();
      return devs.filter(d => (d.name || '').startsWith('GEEDO-')).map(d => new GeedoBle(d));
    } catch (e) { return []; }
  }

  constructor(device) {
    super();
    this.device = device;
    this.rx = null;
    this.tx = null;
    this.chunk = 180;                       // bytes a write; dropped to 20 if he will not take it
    this._q = Promise.resolve();            // writes go one after another
  }

  get ready() { return !!this.rx; }
  get name() { return this.device.name || 'GEEDO'; }

  async open() {
    const server = await this.device.gatt.connect();
    const svc = await server.getPrimaryService(NUS);
    this.rx = await svc.getCharacteristic(NUS_RX);
    this.tx = await svc.getCharacteristic(NUS_TX);
    const dec = new TextDecoder();
    this.tx.addEventListener('characteristicvaluechanged', e => this._feed(dec.decode(e.target.value)));
    await this.tx.startNotifications();
    this.device.addEventListener('gattserverdisconnected', () => {
      this.rx = this.tx = null;
      this.say('(disconnected)', false);
      if (this.onGone) this.onGone(this);
    });
    return this;
  }

  async close() {
    try { this.device.gatt.disconnect(); } catch (e) {}
    this.rx = this.tx = null;
  }

  _send(text) {
    const bytes = new TextEncoder().encode(text);
    this._q = this._q.then(async () => {
      for (let i = 0; i < bytes.length; i += this.chunk) {
        const part = bytes.slice(i, i + this.chunk);
        try { await this.rx.writeValueWithoutResponse(part); }
        catch (e) {
          if (this.chunk > 20) { this.chunk = 20; i -= part.length; continue; }   // smaller pieces, once
          throw e;
        }
      }
    }).catch(() => {});
    return this._q;
  }
}

window.GeedoWire = GeedoWire;
window.GeedoLink = GeedoLink;
window.GeedoBle = GeedoBle;
