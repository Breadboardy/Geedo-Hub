#!/usr/bin/env python3
"""GDA2 - Geedo's animation file, with the frames packed.

    import gda
    blob = gda.encode(frames, fps=10, loop=True, durs=[1]*len(frames))
    a = gda.decode(open('x.bin', 'rb').read())      # either magic
    a['frames'][0]                                   # a 1024-byte page buffer
    gda.to_gda2(old_blob)                            # GDA1 in, GDA2 out

A frame is a 1024-byte SSD1306 page buffer: 8 pages of 128 columns, one
byte per column, bit 0 the top row of the page. That never changes - the
robot blits a frame to the panel as it is. What GDA2 changes is how a frame
sits in the file: as runs and literals instead of the raw kilobyte. These
frames are bold shapes on black, so the free list and every pack together
pack to about a quarter of what they were, and the 704 KB shelf holds them
all with room over.

    0..3   "GDA2"        4  version (1)
    5      frame count   6  fps        7  flags (bit0 loop, bit1 ping-pong)
    8..    one duration byte per frame
    then   (count + 1) x uint32 little-endian: where each frame's packed
           bytes start, from the start of the file; the extra entry is
           where the last one ends, which is the end of the file
    then   the frames, packed, back to back

A packed frame is chunks until 1024 bytes are out:

    c < 0x80    the next c + 1 bytes are literal        (1..128)
    c >= 0x80   the next byte repeats c - 0x7F times   (1..128)

A frame of nothing but literals packs to 1032 bytes, and that is the most a
frame can be - so a reader on a small chip needs no more buffer than that.
The encoder is greedy and deterministic: the same frame always packs to the
same bytes, which is what lets the Hub, the bot and this file agree on a
hash. Runs shorter than three are written as literals - they cost the same.

GDA1 (the raw kilobyte per frame, straight after the durations) is still
read by everything, including the firmware: a redeemed pack sitting in a
robot's flash is GDA1 and stays that way.

The same layout is in the sketch between the GEEDO_GDA2_PURE markers, and
tools/test_gda2.sh has the C unpack the fixtures this file packs. This file
has no dependencies on purpose: it is copied verbatim into the Hub as
.github/scripts/gda.py, where the publish action packs with it.
"""
import struct

FRAME = 1024
FRAME_MAX = FRAME + 8          # every byte a literal: 8 chunks of 128
HEADER = 8


def pack_frame(page):
    """One raw 1024-byte page buffer -> its packed bytes."""
    if len(page) != FRAME:
        raise ValueError(f"a frame is {FRAME} bytes, not {len(page)}")
    page = bytes(page)
    out = bytearray()
    i = 0
    while i < FRAME:
        # how long is the run starting here?
        j = i + 1
        while j < FRAME and page[j] == page[i] and j - i < 128:
            j += 1
        if j - i >= 3:
            out.append(0x80 + (j - i - 1))
            out.append(page[i])
            i = j
            continue
        # literals, up to 128, until a run of three or more begins
        k = i
        while k < FRAME and k - i < 128:
            if k + 2 < FRAME and page[k] == page[k + 1] == page[k + 2]:
                break
            k += 1
        out.append(k - i - 1)
        out += page[i:k]
        i = k
    return bytes(out)


def unpack_frame(data):
    """Packed bytes -> the raw 1024-byte page buffer. Strict: the chunks must
    make exactly 1024 bytes and use exactly the bytes given."""
    data = bytes(data)
    out = bytearray()
    i = 0
    while len(out) < FRAME:
        if i >= len(data):
            raise ValueError("packed frame ends early")
        c = data[i]
        i += 1
        if c < 0x80:
            n = c + 1
            if len(out) + n > FRAME or i + n > len(data):
                raise ValueError("packed frame overruns")
            out += data[i:i + n]
            i += n
        else:
            n = c - 0x7F
            if len(out) + n > FRAME or i >= len(data):
                raise ValueError("packed frame overruns")
            out += bytes([data[i]]) * n
            i += 1
    if i != len(data):
        raise ValueError("packed frame has bytes left over")
    return bytes(out)


def lit(page):
    """Pixels on in a raw frame - what the flash guard counts."""
    return sum(bin(b).count('1') for b in page)


def encode(frames, fps, loop, durs, pp=False):
    """Raw 1024-byte frames -> a GDA2 file."""
    n = len(frames)
    if not 0 < n <= 255:
        raise ValueError(f"{n} frames: the format holds 1..255")
    if len(durs) != n:
        raise ValueError("one duration per frame")
    flags = (1 if loop else 0) | (2 if pp else 0)
    head = bytearray(b'GDA2') + bytes([1, n, int(fps) & 0xFF, flags])
    head += bytes(min(255, max(1, int(d))) for d in durs)
    packed = [pack_frame(f) for f in frames]
    off = len(head) + 4 * (n + 1)
    table = bytearray()
    for p in packed:
        table += struct.pack('<I', off)
        off += len(p)
    table += struct.pack('<I', off)
    return bytes(head + table + b''.join(packed))


def encode_gda1(frames, fps, loop, durs, pp=False):
    """The old layout, for anything that still needs it (tests, mostly)."""
    n = len(frames)
    if not 0 < n <= 255:
        raise ValueError(f"{n} frames: the format holds 1..255")
    flags = (1 if loop else 0) | (2 if pp else 0)
    out = bytearray(b'GDA1') + bytes([1, n, int(fps) & 0xFF, flags])
    out += bytes(min(255, max(1, int(d))) for d in durs)
    for f in frames:
        if len(f) != FRAME:
            raise ValueError(f"a frame is {FRAME} bytes, not {len(f)}")
        out += bytes(f)
    return bytes(out)


def is_anim(blob):
    return len(blob) >= HEADER and bytes(blob[:4]) in (b'GDA1', b'GDA2')


def decode(blob):
    """Either file -> dict(fmt, n, fps, flags, loop, pp, durs, frames).
    frames are raw 1024-byte page buffers whichever way they were stored.
    Raises ValueError on anything malformed, the way the robot refuses it."""
    blob = bytes(blob)
    if len(blob) < HEADER:
        raise ValueError("too short to be an animation")
    magic = blob[:4]
    n, fps, flags = blob[5], blob[6], blob[7]
    if n == 0:
        raise ValueError("no frames")
    durs = list(blob[HEADER:HEADER + n])
    if len(durs) != n:
        raise ValueError("truncated before the durations end")
    if magic == b'GDA1':
        body = HEADER + n
        if len(blob) < body + n * FRAME:
            raise ValueError(f"truncated: {len(blob)} bytes cannot hold {n} frames")
        frames = [blob[body + i * FRAME:body + (i + 1) * FRAME] for i in range(n)]
        fmt = 1
    elif magic == b'GDA2':
        toff = HEADER + n
        tend = toff + 4 * (n + 1)
        if len(blob) < tend:
            raise ValueError("truncated before the frame table ends")
        table = struct.unpack('<%dI' % (n + 1), blob[toff:tend])
        if table[0] != tend:
            raise ValueError("the first frame is not where the table says")
        frames = []
        for i in range(n):
            a, b = table[i], table[i + 1]
            if b <= a or b - a > FRAME_MAX:
                raise ValueError(f"frame {i} has an impossible length")
            if b > len(blob):
                raise ValueError(f"frame {i} runs past the end of the file")
            frames.append(unpack_frame(blob[a:b]))
        if table[n] != len(blob):
            raise ValueError("bytes after the last frame")
        fmt = 2
    else:
        raise ValueError("not a Geedo animation - no GDA1 or GDA2 header")
    return {'fmt': fmt, 'n': n, 'fps': fps, 'flags': flags,
            'loop': bool(flags & 1), 'pp': bool(flags & 2),
            'durs': durs, 'frames': frames}


def to_gda2(blob):
    """Any animation -> GDA2 bytes. A file already packed comes back as is."""
    a = decode(blob)
    if a['fmt'] == 2:
        return bytes(blob)
    return encode(a['frames'], a['fps'], a['loop'], a['durs'], pp=a['pp'])


def playlist(flags, n):
    """Frame indices for one pass: ping-pong comes back without repeating
    either end, the way the robot and the site both play it."""
    order = list(range(n))
    if flags & 2 and n > 2:
        order += list(range(n - 2, 0, -1))
    return order


if __name__ == '__main__':
    import sys
    for path in sys.argv[1:]:
        raw = open(path, 'rb').read()
        a = decode(raw)
        packed = to_gda2(raw)
        print(f"{path}: {a['n']} frames @ {a['fps']} fps, GDA{a['fmt']}, "
              f"{len(raw)} B, packed {len(packed)} B ({len(raw) / max(1, len(packed)):.1f}x)")
