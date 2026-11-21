#!/usr/bin/env python3
"""TOAST-O-FROST: catalogue photo of an impossible gadget.

A brushed-chrome 2-slice toaster that toasts ice cubes. Pure standard
library: a small software rasteriser renders the studio product shot and
a hand-rolled PNG encoder (zlib + struct) writes it out.

Deterministic: fixed seed, no wall-clock, no unseeded randomness.
Output: 1024x1024 PNG, written to $ENTRY_OUTPUT (default /output/entry.png).
"""

import math
import os
import random
import struct
import zlib

W = H = 1024
SEED = 20261121


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_c(c1, c2, t):
    return (int(round(lerp(c1[0], c2[0], t))),
            int(round(lerp(c1[1], c2[1], t))),
            int(round(lerp(c1[2], c2[2], t))))


# ---------------------------------------------------------------- rasteriser

class Canvas:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.buf = bytearray(w * h * 3)

    def span(self, y, x0, x1, c):
        """Solid horizontal span, clipped."""
        if y < 0 or y >= self.h:
            return
        x0 = max(0, int(x0))
        x1 = min(self.w, int(x1))
        if x1 <= x0:
            return
        base = (y * self.w + x0) * 3
        self.buf[base:(y * self.w + x1) * 3] = bytes(c) * (x1 - x0)

    def blend_span(self, y, x0, x1, c, a):
        """Alpha-blended horizontal span (a: 0..255)."""
        if a <= 0 or y < 0 or y >= self.h:
            return
        if a >= 255:
            self.span(y, x0, x1, c)
            return
        x0 = max(0, int(x0))
        x1 = min(self.w, int(x1))
        if x1 <= x0:
            return
        buf = self.buf
        r, g, b = c
        ia = 255 - a
        for x in range(x0, x1):
            i = (y * self.w + x) * 3
            buf[i] = (buf[i] * ia + r * a) // 255
            buf[i + 1] = (buf[i + 1] * ia + g * a) // 255
            buf[i + 2] = (buf[i + 2] * ia + b * a) // 255

    def blend_pixel(self, x, y, c, a):
        if a <= 0 or x < 0 or x >= self.w or y < 0 or y >= self.h:
            return
        if a >= 255:
            i = (y * self.w + x) * 3
            self.buf[i:i + 3] = bytes(c)
            return
        i = (y * self.w + x) * 3
        buf = self.buf
        ia = 255 - a
        buf[i] = (buf[i] * ia + c[0] * a) // 255
        buf[i + 1] = (buf[i + 1] * ia + c[1] * a) // 255
        buf[i + 2] = (buf[i + 2] * ia + c[2] * a) // 255

    def rect(self, x0, y0, x1, y1, c, alpha=255):
        for y in range(int(y0), int(y1)):
            self.blend_span(y, x0, x1, c, alpha)

    def ellipse(self, cx, cy, rx, ry, c, alpha=255):
        for dy in range(-int(ry), int(ry) + 1):
            t = dy / ry
            dx = int(rx * math.sqrt(max(0.0, 1.0 - t * t)))
            self.blend_span(cy + dy, cx - dx, cx + dx + 1, c, alpha)

    def soft_ellipse(self, cx, cy, rx, ry, c, max_alpha):
        """Elliptical soft shadow / glow with parabolic falloff."""
        for dy in range(-int(ry), int(ry) + 1):
            t = dy / ry
            dx = int(rx * math.sqrt(max(0.0, 1.0 - t * t)))
            y = cy + dy
            if y < 0 or y >= self.h:
                continue
            for x in range(cx - dx, cx + dx + 1):
                if x < 0 or x >= self.w:
                    continue
                nx = (x - cx) / rx
                ny = (y - cy) / ry
                d2 = nx * nx + ny * ny
                if d2 >= 1.0:
                    continue
                a = int(max_alpha * (1.0 - d2) * (1.0 - d2))
                self.blend_pixel(x, y, c, a)

    def rrect(self, x0, y0, x1, y1, r, c, alpha=255, color_fn=None):
        """Rounded rect; color_fn(y) -> colour overrides c per row."""
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        for y in range(y0, y1):
            inset = 0
            if y < y0 + r:
                dy = (y0 + r) - y
                inset = int(r - math.sqrt(max(0.0, r * r - dy * dy)))
            elif y >= y1 - r:
                dy = y - (y1 - r)
                inset = int(r - math.sqrt(max(0.0, r * r - dy * dy)))
            col = color_fn(y) if color_fn else c
            self.blend_span(y, x0 + inset, x1 - inset, col, alpha)

    def polygon(self, pts, c, alpha=255):
        """Scanline fill of a convex (or simple) polygon."""
        if not pts:
            return
        ys = [p[1] for p in pts]
        y0, y1 = int(max(0, min(ys))), int(min(self.h - 1, max(ys)))
        n = len(pts)
        for y in range(y0, y1 + 1):
            xs = []
            for i in range(n):
                x1, y1p = pts[i]
                x2, y2p = pts[(i + 1) % n]
                if (y1p <= y < y2p) or (y2p <= y < y1p):
                    t = (y - y1p) / (y2p - y1p)
                    xs.append(x1 + t * (x2 - x1))
            if len(xs) >= 2:
                xs.sort()
                self.blend_span(y, xs[0], xs[-1] + 1, c, alpha)

    def line(self, x0, y0, x1, y1, c, width=1, alpha=255):
        steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        for i in range(steps + 1):
            t = i / max(1, steps)
            x = x0 + (x1 - x0) * t
            y = y0 + (y1 - y0) * t
            self.ellipse(int(x), int(y), max(1, width // 2),
                         max(1, width // 2), c, alpha)

    def circle(self, cx, cy, r, c, alpha=255):
        self.ellipse(cx, cy, r, r, c, alpha)

    def ring(self, cx, cy, r_outer, r_inner, c, alpha=255):
        for dy in range(-r_outer, r_outer + 1):
            t = dy / r_outer
            dx = int(r_outer * math.sqrt(max(0.0, 1.0 - t * t)))
            for x in range(cx - dx, cx + dx + 1):
                ddx, ddy = x - cx, y if False else dy
                if ddx * ddx + ddy * ddy >= r_inner * r_inner:
                    self.blend_pixel(x, cy + dy, c, alpha)


# ---------------------------------------------------------------- tiny 5x7 font

FONT = {
    'A': ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    'B': ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    'C': ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    'D': ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    'E': ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    'F': ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    'G': ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    'H': ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    'I': ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    'J': ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    'K': ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    'L': ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    'M': ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    'N': ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    'O': ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    'P': ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    'Q': ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    'R': ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    'S': ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    'T': ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    'U': ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    'V': ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    'W': ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    'X': ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    'Y': ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    'Z': ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    '0': ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    '1': ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    '2': ("01110", "10001", "00001", "00110", "01000", "10000", "11111"),
    '3': ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    '4': ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    '5': ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    '6': ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    '7': ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    '8': ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    '9': ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    '-': ("00000", "00000", "00000", "01110", "00000", "00000", "00000"),
    ' ': ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    '.': ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    chr(183): ("00000", "00000", "00000", "00100", "00000", "00000", "00000"),
}


def text_width(s, scale):
    return len(s) * (5 * scale + scale) - scale


def draw_text(cv, x, y, s, scale, color):
    cx = x
    for ch in s:
        glyph = FONT.get(ch, FONT[' '])
        for row in range(7):
            bits = glyph[row]
            for col in range(5):
                if bits[col] == '1':
                    cv.rect(cx + col * scale, y + row * scale,
                            cx + col * scale + scale, y + row * scale + scale,
                            color)
        cx += 6 * scale


# ---------------------------------------------------------------- PNG encoder

def write_png(path, cv):
    raw = bytearray()
    stride = W * 3
    for y in range(H):
        raw.append(0)
        raw += cv.buf[y * stride:(y + 1) * stride]

    def chunk(typ, data):
        out = struct.pack('>I', len(data)) + typ + data
        out += struct.pack('>I', zlib.crc32(typ + data) & 0xffffffff)
        return out

    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(bytes(raw), 6))
    png += chunk(b'IEND', b'')
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, 'wb') as f:
        f.write(png)
    return len(png)


# ---------------------------------------------------------------- scene

def rot(px, py, cx, cy, ang):
    ca, sa = math.cos(ang), math.sin(ang)
    dx, dy = px - cx, py - cy
    return (cx + dx * ca - dy * sa, cy + dx * sa + dy * ca)


def draw_ice_cube(cv, cx, cy, s, tilt=-0.14):
    """Translucent ice cube, top face bright, tilted. cy = cube centre."""
    top = rot(cx, cy - s * 0.52, cx, cy, tilt)
    right = rot(cx + s * 0.52, cy - s * 0.20, cx, cy, tilt)
    bottom = rot(cx, cy + s * 0.12, cx, cy, tilt)
    left = rot(cx - s * 0.52, cy - s * 0.20, cx, cy, tilt)
    bl = rot(cx - s * 0.52, cy + s * 0.44, cx, cy, tilt)
    bb = rot(cx, cy + s * 0.76, cx, cy, tilt)
    br = rot(cx + s * 0.52, cy + s * 0.44, cx, cy, tilt)
    # left + right faces (slightly translucent over whatever is behind)
    cv.polygon([left, bottom, bb, bl], (186, 219, 238), 235)
    cv.polygon([right, bottom, bb, br], (148, 193, 224), 235)
    # top face, brightest
    cv.polygon([top, right, bottom, left], (232, 245, 252), 245)
    # edges
    edge = (118, 168, 202)
    for a, b in [(top, right), (right, bottom), (bottom, left), (left, top),
                 (left, bl), (bl, bb), (bb, br), (br, right),
                 (bottom, bb)]:
        cv.line(int(a[0]), int(a[1]), int(b[0]), int(b[1]), edge, 2, 200)
    # inner diagonal refraction streaks
    cv.line(int(left[0] + 8), int(left[1] + 26), int(bottom[0] - 6),
            int(bottom[1] + 34), (255, 255, 255), 3, 110)
    cv.line(int(right[0] - 10), int(right[1] + 22), int(bottom[0] + 8),
            int(bottom[1] + 30), (255, 255, 255), 2, 90)
    cv.line(int(top[0] - 14), int(top[1] + 12), int(bottom[0] - 2),
            int(bottom[1] - 6), (255, 255, 255), 3, 130)
    # bright highlight on the top face
    hx, hy = int(top[0] - 6), int(top[1] + 10)
    cv.ellipse(hx, hy, 16, 7, (255, 255, 255), 200)
    cv.ellipse(hx, hy, 8, 4, (255, 255, 255), 220)


def draw_steam(cv, x0, y_top, y_base):
    """Two thin translucent wisps curling upward."""
    for phase, dx0, amp in [(0.0, -14, 11), (1.4, 16, 9)]:
        steps = 26
        for i in range(steps):
            t = i / (steps - 1)
            y = y_base - t * (y_base - y_top)
            x = x0 + dx0 * t + math.sin(t * 5.0 + phase) * amp * t
            r = 5 + 8 * t
            a = int(82 * (1.0 - t) + 12)
            cv.ellipse(int(x), int(y), int(r), int(r * 1.25),
                       (255, 255, 255), a)


def render():
    rng = random.Random(SEED)
    cv = Canvas(W, H)

    # --- studio seamless background: warm off-white, lighter at top ---
    top_c = (250, 247, 240)
    bot_c = (233, 226, 212)
    for y in range(H):
        t = y / (H - 1)
        # gentle ease so the floor area darkens a little more
        c = lerp_c(top_c, bot_c, t * t * 0.6 + t * 0.4)
        cv.span(y, 0, W, c)
    # soft radial key light, upper centre
    cv.soft_ellipse(512, 380, 560, 460, (255, 255, 255), 26)

    # --- contact shadows ---
    cv.soft_ellipse(470, 806, 265, 42, (90, 78, 60), 78)
    cv.soft_ellipse(470, 806, 200, 30, (70, 58, 44), 90)
    cv.soft_ellipse(848, 800, 118, 26, (90, 78, 60), 70)

    # --- toaster body: front face, vertical brushed chrome gradient ---
    bx0, bx1, by0, by1 = 258, 662, 420, 782
    grad_top = (226, 230, 233)
    grad_bot = (176, 182, 188)

    def body_row(y):
        t = (y - by0) / (by1 - by0)
        return lerp_c(grad_top, grad_bot, t)

    cv.rrect(bx0, by0, bx1, by1, 30, grad_top, color_fn=body_row)

    # brushed-metal streaks (seeded, subtle vertical lines)
    for _ in range(150):
        x = rng.randint(bx0 + 8, bx1 - 8)
        light = rng.random() < 0.55
        a = rng.randint(5, 15)
        col = (255, 255, 255) if light else (120, 126, 132)
        for y in range(by0 + 12, by1 - 12):
            cv.blend_pixel(x, y, col, a)

    # bright specular band from the upper-left key light
    cv.polygon([(300, by0), (430, by0), (330, by1), (268, by1)],
               (255, 255, 255), 46)
    cv.polygon([(430, by0), (470, by0), (380, by1), (330, by1)],
               (255, 255, 255), 22)

    # --- right side face (darker chrome) ---
    cv.polygon([(bx1, by0 + 6), (706, by0 - 26), (706, 748), (bx1, by1 - 4)],
               (150, 156, 162), 255)
    # side-face vertical shading
    for i in range(44):
        t = i / 43
        x = int(lerp(bx1, 706, t))
        col = lerp_c((150, 156, 162), (128, 134, 141), t)
        cv.line(x, by0 - 20 + int(t * 26), x, by1 - 10 - int(t * 30),
                col, 1, 255)

    # --- top face ---
    cv.polygon([(bx0 + 4, by0), (bx1, by0 + 6), (706, by0 - 26),
                (bx0 + 48, by0 - 26)], (238, 241, 244), 255)
    cv.polygon([(bx0 + 4, by0), (bx1, by0 + 6), (706, by0 - 26),
                (bx0 + 48, by0 - 26)], (255, 255, 255), 40)

    # --- slots on the top face (dark openings) ---
    # slot 1 (left, holds the ice cube), slot 2 (right, empty)
    cv.polygon([(318, 402), (428, 402), (452, 388), (342, 388)],
               (28, 30, 33), 255)
    cv.polygon([(486, 402), (596, 402), (620, 388), (510, 388)],
               (28, 30, 33), 255)
    cv.polygon([(318, 402), (428, 402), (452, 388), (342, 388)],
               (90, 96, 102), 60)
    # slot inner rims
    cv.line(318, 402, 428, 402, (70, 74, 80), 2, 255)
    cv.line(486, 402, 596, 402, (70, 74, 80), 2, 255)

    # --- the joke: one glowing ice cube half-popped out of slot 1 ---
    # Cube sits low so its lower third is inside the toaster; the top
    # face is then redrawn over it, so the cube visibly emerges from
    # the slot instead of floating on a bar.
    draw_ice_cube(cv, 388, 329, 118)
    cv.polygon([(bx0 + 4, by0), (bx1, by0 + 6), (706, by0 - 26),
                (bx0 + 48, by0 - 26)], (238, 241, 244), 255)
    # slot 2 redrawn (the top-face redraw covered it)
    cv.polygon([(486, 402), (596, 402), (620, 388), (510, 388)],
               (28, 30, 33), 255)
    cv.line(486, 402, 596, 402, (70, 74, 80), 2, 255)
    # slot 1: only the sliver left of the cube stays visible
    cv.polygon([(318, 402), (334, 402), (346, 388), (330, 388)],
               (28, 30, 33), 255)
    cv.line(318, 402, 334, 402, (70, 74, 80), 2, 255)

    # --- steam wisps above the cube ---
    draw_steam(cv, 388, 160, 276)

    # --- chrome lever on the right side, pressed down ---
    cv.rect(668, 560, 678, 660, (52, 54, 58), 255)
    cv.polygon([(668, 640), (700, 636), (700, 652), (668, 656)],
               (205, 209, 213), 255)
    cv.circle(704, 644, 13, (28, 30, 33), 255)
    cv.circle(701, 641, 5, (90, 96, 102), 255)

    # --- browning dial on the front face ---
    dcx, dcy, dr = 566, 648, 44
    cv.circle(dcx, dcy, dr + 5, (120, 126, 132), 255)
    cv.circle(dcx, dcy, dr, (238, 240, 242), 255)
    for k in range(9):
        ang = math.radians(-210 + k * 30)
        x1 = dcx + int(math.cos(ang) * (dr - 4))
        y1 = dcy + int(math.sin(ang) * (dr - 4))
        x2 = dcx + int(math.cos(ang) * (dr - 12))
        y2 = dcy + int(math.sin(ang) * (dr - 12))
        cv.line(x1, y1, x2, y2, (70, 74, 80), 2, 255)
    # pointer at "crisp" (upper right)
    pa = math.radians(-50)
    cv.line(dcx, dcy, dcx + int(math.cos(pa) * (dr - 12)),
            dcy + int(math.sin(pa) * (dr - 12)), (40, 42, 46), 4, 255)
    cv.circle(dcx, dcy, 7, (60, 64, 70), 255)

    # --- brand plate + product-only text ---
    cv.rrect(300, 516, 512, 566, 8, (196, 200, 204), 255)
    cv.rrect(300, 516, 512, 566, 8, (140, 146, 152), 90)
    brand = "TOAST-O-FROST"
    tw = text_width(brand, 2)
    draw_text(cv, 306 + (200 - tw) // 2, 530, brand, 2, (52, 56, 62))
    sub = "1200W " + chr(183) + " CRISP ICE"
    tw2 = text_width(sub, 2)
    draw_text(cv, 300 + (362 - tw2) // 2, 586, sub, 2, (74, 78, 84))

    # --- tiny red indicator light ---
    cv.soft_ellipse(620, 540, 16, 16, (255, 60, 50), 70)
    cv.circle(620, 540, 8, (214, 38, 30), 255)
    cv.circle(617, 537, 3, (255, 140, 130), 255)

    # --- feet ---
    for fx in (292, 596):
        cv.rrect(fx, 780, fx + 40, 796, 5, (30, 32, 35), 255)
    cv.rrect(668, 748, 700, 762, 5, (30, 32, 35), 255)

    # --- the ONE accessory: white ceramic plate, one spare ice cube ---
    cv.ellipse(848, 762, 118, 40, (226, 222, 214), 255)
    cv.ellipse(848, 756, 118, 40, (252, 251, 248), 255)
    cv.ellipse(848, 756, 96, 30, (238, 236, 232), 255)
    # melt puddle beside the spare cube
    cv.ellipse(892, 770, 42, 11, (178, 208, 228), 150)
    cv.ellipse(892, 770, 30, 8, (200, 222, 238), 130)
    # spare ice cube on the plate
    draw_ice_cube(cv, 838, 716, 62, tilt=0.22)

    # --- gentle vignette to keep the hero centred ---
    cv.soft_ellipse(512, 512, 760, 760, (120, 100, 70), 0)  # no-op guard
    return cv


def main():
    out = os.environ.get("ENTRY_OUTPUT", "/output/entry.png")
    cv = render()
    n = write_png(out, cv)
    print(f"wrote {out} ({n} bytes)")


if __name__ == "__main__":
    main()
