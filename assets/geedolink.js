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
 */
const ESP32 = 0x303a;                  // Espressif's USB vendor id

export class GeedoLink {
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

  /** A pack, down the wire. `plain` is the decrypted pack, as bytes. */
  async sendPack(plain, onProgress) {
    const CHUNK = 1368;                       // base64 chars a line, like FRAME
    let bin = '';
    for (const b of plain) bin += String.fromCharCode(b);
    const b64 = btoa(bin);
    await this.ask(`PKNEW ${plain.length}`, /^GEEDO (OK|ERR) PKNEW/, 15000);
    for (let i = 0; i < b64.length; i += CHUNK) {
      const part = b64.slice(i, i + CHUNK);
      const out = await this.ask(`PKADD ${part}`, /^GEEDO (OK|ERR) PKADD/, 15000,
                                 `PKADD …${i + part.length}/${b64.length}`);
      if (out[out.length - 1].startsWith('GEEDO ERR')) throw new Error(out[out.length - 1]);
      if (onProgress) onProgress((i + part.length) / b64.length);
    }
    const end = await this.ask('PKEND', /^GEEDO (OK|ERR) PKEND/, 60000);
    const line = end[end.length - 1];
    if (line.startsWith('GEEDO ERR')) throw new Error(line);
    return line;
  }
}
