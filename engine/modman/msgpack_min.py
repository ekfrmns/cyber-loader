"""Tiny MessagePack decoder, just enough to read Vortex's vortex.deployment.msgpack."""
import struct


def _dec(b, i):
    t = b[i]
    i += 1
    if t <= 0x7F:
        return t, i
    if t >= 0xE0:
        return t - 256, i
    if 0xA0 <= t <= 0xBF:
        n = t & 31
        return b[i:i + n].decode("utf8", "replace"), i + n
    if 0x90 <= t <= 0x9F:
        return _arr(b, i, t & 15)
    if 0x80 <= t <= 0x8F:
        return _map(b, i, t & 15)
    if t == 0xC0:
        return None, i
    if t == 0xC2:
        return False, i
    if t == 0xC3:
        return True, i
    if t in (0xC4, 0xD9):
        n = b[i]; i += 1
        return b[i:i + n].decode("utf8", "replace"), i + n
    if t in (0xC5, 0xDA):
        n = struct.unpack(">H", b[i:i + 2])[0]; i += 2
        return b[i:i + n].decode("utf8", "replace"), i + n
    if t in (0xC6, 0xDB):
        n = struct.unpack(">I", b[i:i + 4])[0]; i += 4
        return b[i:i + n].decode("utf8", "replace"), i + n
    fixed = {0xCC: ">B", 0xCD: ">H", 0xCE: ">I", 0xCF: ">Q", 0xD0: ">b", 0xD1: ">h", 0xD2: ">i",
             0xD3: ">q", 0xCA: ">f", 0xCB: ">d"}
    if t in fixed:
        fmt = fixed[t]
        n = struct.calcsize(fmt)
        return struct.unpack(fmt, b[i:i + n])[0], i + n
    if t == 0xDC:
        return _arr(b, i + 2, struct.unpack(">H", b[i:i + 2])[0])
    if t == 0xDD:
        return _arr(b, i + 4, struct.unpack(">I", b[i:i + 4])[0])
    if t == 0xDE:
        return _map(b, i + 2, struct.unpack(">H", b[i:i + 2])[0])
    if t == 0xDF:
        return _map(b, i + 4, struct.unpack(">I", b[i:i + 4])[0])
    raise ValueError("unsupported msgpack type 0x%02x at %d" % (t, i - 1))


def _arr(b, i, n):
    out = []
    for _ in range(n):
        v, i = _dec(b, i)
        out.append(v)
    return out, i


def _map(b, i, n):
    out = {}
    for _ in range(n):
        k, i = _dec(b, i)
        v, i = _dec(b, i)
        out[k] = v
    return out, i


def loads(data: bytes):
    obj, _ = _dec(data, 0)
    return obj
