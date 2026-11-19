"""Draws the CyberLoader icon (stdlib only) and writes launcher/cyberloader.ico (PNG-in-ICO, 256 + 64 + 32 px)."""
import math
import struct
import sys
import zlib
from pathlib import Path


# Square: top-left to bottom-right gradient; bars: the colour the top and bottom bars fade to, MID the lighter middle bar.
# These are the colours the app's own logo (ui/logo.js) draws for the default pink accent (#FF375F), so the icon and the
# logo in the window match: bars toned down a little, the middle bar lighter, the square a dark tint of the same hue.
A0 = (77, 25, 36)     # dark pink tint in the top-left corner, like the app's background glow
A1 = (26, 15, 17)     # near-black bottom-right
BAR = (241, 65, 100)  # hsl(348 86% 60%)
MID = (238, 113, 138) # hsl(348 79% 69%)


def draw(size: int, a0=None, a1=None, bar=None, mid=None) -> bytes:
    """RGBA pixels: a rounded square with a dark pink-tinted gradient and three stacked 'mod layer' bars (the middle one lighter)."""
    a0, a1, bar, mid = a0 or A0, a1 or A1, bar or BAR, mid or MID
    r = size * 0.22
    px = bytearray()
    # (y centre, x start, x end) as fractions. Two of the bars sit left, which makes the stack look left-heavy even when its
    # bounding box is centred, so the whole group is nudged right (+0.035, about 9 px at 256) to centre it optically.
    bars = [(0.36, 0.235, 0.735, bar), (0.51, 0.335, 0.815, mid), (0.66, 0.235, 0.735, bar)]
    bar_h = 0.062
    for y in range(size):
        for x in range(size):
            fx, fy = (x + 0.5) / size, (y + 0.5) / size
            # rounded-square mask with 1px antialiasing
            dx = max(abs(x + 0.5 - size / 2) - (size / 2 - r), 0)
            dy = max(abs(y + 0.5 - size / 2) - (size / 2 - r), 0)
            d = math.hypot(dx, dy) - r
            a = max(0.0, min(1.0, 0.5 - d))
            t = (fx + fy) / 2
            R, G, B = (a0[0] + (a1[0] - a0[0]) * t, a0[1] + (a1[1] - a0[1]) * t, a0[2] + (a1[2] - a0[2]) * t)
            for cy, x0, x1, col in bars:
                if abs(fy - cy) < bar_h and x0 <= fx <= x1:
                    # soft edge on the bar ends and top/bottom
                    e = min(bar_h - abs(fy - cy), fx - x0, x1 - fx) * size
                    k = max(0.0, min(1.0, e))
                    R, G, B = R + (col[0] - R) * k, G + (col[1] - G) * k, B + (col[2] - B) * k
            px += bytes((int(R), int(G), int(B), int(a * 255)))
    return bytes(px)


def png(size: int, **colors) -> bytes:
    raw = draw(size, **colors)
    rows = b"".join(b"\x00" + raw[y * size * 4:(y + 1) * size * 4] for y in range(size))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def main(out: Path) -> None:
    sizes = [256, 64, 32]
    images = [png(s) for s in sizes]
    head = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = b""
    for s, img in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", 0 if s == 256 else s, 0 if s == 256 else s, 0, 0, 1, 32, len(img), offset)
        offset += len(img)
    out.write_bytes(head + entries + b"".join(images))
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("cyberloader.ico"))
