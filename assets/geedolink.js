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

class GeedoLink {
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
    this.port = port;
    this.writer = null;
    this.pending = null;
    this.listeners = [];
    this.info = null;
  }

  onLine(fn) { this.listeners.push(fn); return this; }
  say(line, mine) { for (const fn of this.listeners) fn(line, mine); }

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
    let buf = '';
    for (;;) {
      let chunk;
      try { chunk = await reader.read(); } catch (e) { break; }
      if (chunk.done) break;
      buf += chunk.value;
      let nl;
      while ((nl = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, nl).replace(/\r$/, '');
        buf = buf.slice(nl + 1);
        this._line(line);
      }
      if (buf.length > 4096) buf = '';        // a robot mid-boot can spew
    }
    this.say('(disconnected)', false);
  }

  _line(line) {
    // He prints a great deal of ordinary debug chatter to the same port, so
    // every ANSWER starts with "GEEDO ". That prefix is the whole protocol.
    const mine = line.startsWith('GEEDO ');
    this.say(line, mine);
    if (!this.pending || !mine) return;
    this.pending.lines.push(line);
    if (this.pending.until.test(line)) {
      clearTimeout(this.pending.timer);
      const { done, lines } = this.pending;
      this.pending = null;
      done(lines);
    }
  }

  ask(cmd, until, ms = 8000, shown) {
    return new Promise((done, fail) => {
      if (!this.writer) return fail(new Error('not connected'));
      this.pending = { lines: [], until, done, timer: setTimeout(() => {
        this.pending = null; fail(new Error('Geedo did not answer'));
      }, ms) };
      this.say('> ' + (shown || cmd), 'sent');
      this.writer.write(new TextEncoder().encode(cmd + '\n')).catch(() => {});
    });
  }

  /** INFO, parsed. Also cached on the link as `.info`. */
  async hello() {
    const out = await this.ask('INFO', /^GEEDO INFO /, 8000);
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
    await this._chunks(GeedoLink.b64(plain), onProgress);
    const end = await this.ask('PKEND', /^GEEDO (OK|ERR) PKEND/, 60000);
    const line = end[end.length - 1];
    if (line.startsWith('GEEDO ERR')) throw new Error(line);
    return line;
  }

  /** One animation of the owner's own, down the wire (firmware v35).
   *  `bytes` is a .bin as the Studio saves it, `name` what he calls it.
   *  Resolves to its id on him (up_xxxxxxxx); throws his reason when he
   *  refuses - too big, flashes too much, no room, already on him. */
  async sendAnim(bytes, name, onProgress) {
    const clean = String(name || '').replace(/[^\x20-\x7e]/g, '').trim().slice(0, 24);
    const start = await this.ask(`UPNEW ${bytes.length}${clean ? ' ' + clean : ''}`,
                                 /^GEEDO (OK|ERR) UPNEW/, 15000);
    if (start[start.length - 1].startsWith('GEEDO ERR'))
      throw new Error(GeedoLink.why(start[start.length - 1]));
    await this._chunks(GeedoLink.b64(bytes), onProgress);
    const end = await this.ask('UPEND', /^GEEDO (OK|ERR) UPEND/, 60000);
    const line = end[end.length - 1];
    if (line.startsWith('GEEDO ERR')) throw new Error(GeedoLink.why(line));
    return line.split(/\s+/)[3];
  }

  /** Bring his radio up on the network he remembers and hold it there ten
   *  minutes (firmware v35). Resolves to the address his own page is at. */
  async radioOn() {
    const out = await this.ask('RADIO on', /^GEEDO (OK|ERR) RADIO/, 20000);
    const line = out[out.length - 1];
    if (line.startsWith('GEEDO ERR')) throw new Error(GeedoLink.why(line));
    return line.split(/\s+/)[4];
  }
}

window.GeedoLink = GeedoLink;
