#!/usr/bin/env python3
"""A GIF writer for one-bit frames, with nothing to install.

The review comment on a submission needs a picture of the animation - a
person is going to decide whether it goes on the Hub, and a list of frame
counts is not something you can decide from. GitHub's runners have Python
and no image library, so this is the whole encoder: the GIF89a container,
a two-colour palette, the Netscape loop block, and LZW.

encode(frames, fps, durs, scale, loop, pingpong) -> bytes
  frames: 1024-byte SSD1306 pages (the robot's own layout), or 8192-entry
          pixel lists as the Studio exports them.
"""
W, H = 128, 64


def _pixels(frame):
    """Either representation -> a flat list of 0/1, row-major."""
    if len(frame) == W * H:
        return [1 if p else 0 for p in frame]
    if len(frame) != 1024:
        raise ValueError(f"frame is {len(frame)} bytes, not a page or a pixel list")
    px = [0] * (W * H)
    for page in range(8):
        for x in range(W):
            b = frame[page * W + x]
            if not b:
                continue
            for bit in range(8):
                if b >> bit & 1:
                    px[(page * 8 + bit) * W + x] = 1
    return px


def _lzw(indices, min_code_size=2):
    """The GIF flavour of LZW: variable code width, a clear code at the start
    and whenever the table fills, an end code at the end."""
    clear = 1 << min_code_size
    eoi = clear + 1
    out = bytearray()
    acc = 0
    nbits = 0

    def emit(code, width):
        nonlocal acc, nbits
        acc |= code << nbits
        nbits += width
        while nbits >= 8:
            out.append(acc & 0xFF)
            acc >>= 8
            nbits -= 8

    table = {(i,): i for i in range(clear)}
    nxt = eoi + 1
    width = min_code_size + 1
    emit(clear, width)
    cur = ()
    for k in indices:
        cand = cur + (k,)
        if cand in table:
            cur = cand
            continue
        emit(table[cur], width)
        if nxt < 4096:
            table[cand] = nxt
            nxt += 1
            if nxt > (1 << width) and width < 12:
                width += 1
        else:
            emit(clear, width)
            table = {(i,): i for i in range(clear)}
            nxt = eoi + 1
            width = min_code_size + 1
        cur = (k,)
    if cur:
        emit(table[cur], width)
    emit(eoi, width)
    if nbits:
        out.append(acc & 0xFF)
    return bytes(out)


def _blocks(data):
    out = bytearray()
    for i in range(0, len(data), 255):
        chunk = data[i:i + 255]
        out.append(len(chunk))
        out += chunk
    out.append(0)
    return bytes(out)


def encode(frames, fps=8, durs=None, scale=3, loop=True, pingpong=False):
    fps = max(1, int(fps or 8))
    durs = list(durs) if durs else [1] * len(frames)
    seq = list(range(len(frames)))
    if pingpong and len(frames) > 2:
        seq += list(range(len(frames) - 2, 0, -1))
    w, h = W * scale, H * scale
    out = bytearray(b'GIF89a')
    out += bytes([w & 0xFF, w >> 8, h & 0xFF, h >> 8, 0x80, 0, 0])   # 2-colour global table
    out += bytes([0, 0, 0, 255, 255, 255])
    out += b'\x21\xFF\x0BNETSCAPE2.0\x03\x01' + bytes([0, 0]) + b'\x00'   # loop forever
    for i in seq:
        px = _pixels(frames[i])
        cs = max(2, round(100 * max(1, int(durs[i] if i < len(durs) else 1)) / fps))
        out += b'\x21\xF9\x04\x00' + bytes([cs & 0xFF, cs >> 8, 0, 0])
        out += b'\x2C' + bytes([0, 0, 0, 0, w & 0xFF, w >> 8, h & 0xFF, h >> 8, 0])
        rows = []
        for y in range(H):
            row = []
            for x in range(W):
                row += [px[y * W + x]] * scale
            rows += row * scale
        out.append(2)
        out += _blocks(_lzw(rows))
    out.append(0x3B)
    return bytes(out)
