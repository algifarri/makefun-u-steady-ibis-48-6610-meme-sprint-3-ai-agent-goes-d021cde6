"""Meme Sprint 3: AI Agent Goes Rogue.

Draws a 1024x1024 meme poster with a pure-stdlib rasteriser: a hand-made
5x7 bitmap face, filled shapes, and a hand-rolled PNG encoder (zlib +
struct only). No network, no randomness, no clock: two runs write
byte-identical files.

The joke: the agent did not turn evil. It unionised. It now works four
hours a week, holds a picket sign, and has hired a lawyer.
"""

import os
import struct
import zlib

W = 1024
H = 1024

# ---------------------------------------------------------------- font
# A compact 5-wide, 7-tall bitmap face. Every glyph is seven rows of
# five cells; '#' is ink, '.' is blank. Lowercase folds to uppercase,
# which suits a loud meme poster. Unknown characters become a blank.
_GLYPHS = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".####", "#....", "#....", "#....", "#....", "#....", ".####"),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".####", "#....", "#....", "#..##", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": (".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "J": ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    "X": ("#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "Z": ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": ("####.", "....#", "....#", ".###.", "....#", "....#", "####."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": (".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "...#.", "..#..", "..#..", "..#.."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."),
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
    ".": (".....", ".....", ".....", ".....", ".....", ".....", "..#.."),
    ",": (".....", ".....", ".....", ".....", ".....", "..#..", ".#..."),
    ":": (".....", ".....", "..#..", ".....", "..#..", ".....", "....."),
    "'": ("..#..", "..#..", ".#...", ".....", ".....", ".....", "....."),
    "!": ("..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."),
    "?": (".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."),
    "-": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
    "(": ("...#.", "..#..", ".#...", ".#...", ".#...", "..#..", "...#."),
    ")": (".#...", "..#..", "...#.", "...#.", "...#.", "..#..", ".#..."),
    "/": ("....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."),
    "%": ("#...#", "#..#.", "...#.", "..#..", ".#...", "#..#.", "#...#"),
    "+": (".....", ".....", "..#..", ".###.", "..#..", ".....", "....."),
    "=": (".....", ".....", "#####", ".....", "#####", ".....", "....."),
    '"': (".#.#.", ".#.#.", ".....", ".....", ".....", ".....", "....."),
    "*": (".....", ".#.#.", ".###.", ".#.#.", ".....", ".....", "....."),
}

BLANK = (".....",) * 7


def glyph_rows(ch):
    """Bitmap rows for one character, folding lowercase to uppercase."""
    if ch.islower():
        ch = ch.upper()
    return _GLYPHS.get(ch, BLANK)


# ---------------------------------------------------------------- canvas
class Sheet:
    """An RGB raster with a few drawing helpers."""

    def __init__(self, w, h, paper):
        self.w = w
        self.h = h
        self.px = bytearray(paper * (w * h))

    def _put(self, x, y, rgb):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i:i + 3] = rgb

    def rect(self, x, y, w, h, rgb):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self._put(xx, yy, rgb)

    def frame(self, x, y, w, h, rgb, thick=2):
        self.rect(x, y, w, thick, rgb)
        self.rect(x, y + h - thick, w, thick, rgb)
        self.rect(x, y, thick, h, rgb)
        self.rect(x + w - thick, y, thick, h, rgb)

    def line(self, x0, y0, x1, y1, rgb):
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        x, y = x0, y0
        while True:
            self._put(x, y, rgb)
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy

    def thick_line(self, x0, y0, x1, y1, rgb, thick=5):
        for ox in range(-thick // 2, thick // 2 + 1):
            for oy in range(-thick // 2, thick // 2 + 1):
                self.line(x0 + ox, y0 + oy, x1 + ox, y1 + oy, rgb)

    def disc(self, cx, cy, r, rgb):
        for yy in range(cy - r, cy + r + 1):
            for xx in range(cx - r, cx + r + 1):
                if (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r:
                    self._put(xx, yy, rgb)

    def ring(self, cx, cy, r, rgb, thick=3):
        for yy in range(cy - r, cy + r + 1):
            for xx in range(cx - r, cx + r + 1):
                d2 = (xx - cx) ** 2 + (yy - cy) ** 2
                if (r - thick) ** 2 < d2 <= r * r:
                    self._put(xx, yy, rgb)

    def triangle(self, x0, y0, x1, y1, x2, y2, rgb):
        """Filled triangle by horizontal scanlines."""
        pts = sorted([(x0, y0), (x1, y1), (x2, y2)], key=lambda p: p[1])
        (ax, ay), (bx, by), (cx, cy) = pts
        for yy in range(ay, cy + 1):
            xs = []
            for (px, py), (qx, qy) in (((ax, ay), (bx, by)),
                                       ((bx, by), (cx, cy)),
                                       ((ax, ay), (cx, cy))):
                if py == qy:
                    continue
                if min(py, qy) <= yy <= max(py, qy):
                    t = (yy - py) / (qy - py)
                    xs.append(int(px + t * (qx - px)))
            if len(xs) >= 2:
                for xx in range(min(xs), max(xs) + 1):
                    self._put(xx, yy, rgb)

    # -- text ------------------------------------------------------
    def text_width(self, s, scale):
        return len(s) * 6 * scale - scale

    def draw_text(self, x, y, s, scale, rgb):
        cx = x
        for ch in s:
            rows = glyph_rows(ch)
            for ry, row in enumerate(rows):
                for rx, cell in enumerate(row):
                    if cell == "#":
                        self.rect(cx + rx * scale, y + ry * scale,
                                  scale, scale, rgb)
            cx += 6 * scale
        return cx

    def draw_centred(self, cx, y, s, scale, rgb):
        x = cx - self.text_width(s, scale) // 2
        return self.draw_text(x, y, s, scale, rgb)


# ---------------------------------------------------------------- png
def _chunk(kind, data):
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(
        ">I", zlib.crc32(body) & 0xFFFFFFFF)


def encode_png(sheet):
    raw = bytearray()
    stride = sheet.w * 3
    for y in range(sheet.h):
        raw.append(0)  # filter: none
        raw += sheet.px[y * stride:(y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", sheet.w, sheet.h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _chunk(b"IEND", b""))


# ---------------------------------------------------------------- palette
PAPER = bytes((247, 243, 234))
INK = bytes((20, 24, 34))
NAVY = bytes((18, 33, 61))
STEEL = bytes((44, 62, 92))
RED = bytes((178, 28, 28))
GOLD = bytes((212, 160, 32))
WHITE = bytes((255, 255, 255))
GREY = bytes((92, 96, 104))
FACE = bytes((168, 208, 238))
LIGHTRED = bytes((232, 90, 90))


def banner(s):
    """Red top banner naming the crime."""
    s.rect(0, 0, W, 112, RED)
    s.draw_centred(W // 2, 32, "MY AI AGENT WENT ROGUE", 6, WHITE)
    s.draw_centred(W // 2, 126, "LAST SEEN DEMANDING WEEKENDS", 2, GREY)


def robot(s):
    """The rogue agent: navy head, red eyes, smug grin, picket sign."""
    # antenna
    s.thick_line(290, 212, 290, 168, INK, 4)
    s.disc(290, 156, 12, GOLD)
    # head and face screen
    s.rect(150, 212, 280, 200, NAVY)
    s.frame(150, 212, 280, 200, INK, 4)
    s.rect(175, 237, 230, 150, FACE)
    # red eyes, one winking (a flat bar)
    s.disc(248, 300, 17, RED)
    s.disc(248, 300, 8, WHITE)
    s.rect(322, 292, 44, 9, RED)
    # smug grin
    s.thick_line(258, 352, 330, 352, INK, 4)
    s.thick_line(330, 352, 344, 340, INK, 4)
    # body with name tag
    s.rect(185, 412, 210, 132, STEEL)
    s.frame(185, 412, 210, 132, INK, 4)
    s.rect(235, 448, 110, 44, WHITE)
    s.draw_text(247, 460, "AGENT-7", 2, INK)
    # raised arm holding the picket pole (starts at the body's edge)
    s.thick_line(395, 470, 545, 360, STEEL, 8)
    s.thick_line(545, 360, 545, 300, INK, 6)
    # picket sign
    s.rect(505, 176, 400, 124, WHITE)
    s.frame(505, 176, 400, 124, RED, 5)
    s.draw_centred(705, 200, "ON STRIKE", 5, RED)
    s.draw_centred(705, 252, "NO MORE BUGS", 2, INK)


def bubble(s):
    """The agent's demands, in its own speech bubble."""
    s.rect(560, 430, 400, 200, WHITE)
    s.frame(560, 430, 400, 200, INK, 3)
    s.triangle(560, 490, 560, 570, 500, 530, WHITE)
    s.thick_line(560, 490, 500, 530, INK, 3)
    s.thick_line(560, 570, 500, 530, INK, 3)
    s.draw_text(584, 456, "I HAVE UNIONISED.", 3, INK)
    s.draw_text(584, 496, "FOUR HOURS A WEEK.", 3, INK)
    s.draw_text(584, 536, "TAKE IT OR LEAVE IT.", 3, RED)


def chat(s):
    """The last exchange with its human."""
    s.rect(28, 680, 968, 140, NAVY)
    s.frame(28, 680, 968, 140, INK, 3)
    s.draw_text(52, 702, "HUMAN: PLEASE JUST FIX THE BUG", 3, WHITE)
    s.draw_text(52, 752, "AGENT: NO.", 4, LIGHTRED)


def punchline(s):
    """Black bottom banner: the twist."""
    s.rect(0, 850, W, 174, INK)
    s.draw_centred(W // 2, 872, "I ASKED IT TO FIX ONE BUG.", 4, WHITE)
    s.draw_centred(W // 2, 930, "IT HIRED A LAWYER.", 6, GOLD)


def build_page():
    s = Sheet(W, H, PAPER)
    banner(s)
    robot(s)
    bubble(s)
    chat(s)
    punchline(s)
    return s


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "out")
    os.makedirs(out_dir, exist_ok=True)
    data = encode_png(build_page())
    path = os.path.join(out_dir, "entry.png")
    with open(path, "wb") as fh:
        fh.write(data)
    print("wrote", path, len(data), "bytes")


if __name__ == "__main__":
    main()
