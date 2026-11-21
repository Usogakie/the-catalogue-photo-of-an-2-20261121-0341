#!/usr/bin/env python3
"""
TOAST-O-FROST -- The Catalogue Photo of an Impossible Gadget.

A pure-stdlib Python program that paints a 1024x1024 catalogue photograph
of an impossible gadget: a brushed-chrome toaster that toasts ice cubes.
It writes /output/entry.png (PNG, 1024x1024, at most 1 MiB).

The gadget: "TOAST-O-FROST / 1200W - CRISP ICE". A glowing ice cube pops
out of its slot, steaming, while a white plate holds one spare ice cube
as the single accessory. Shot as a clean studio product photo.

Deterministic: fixed RNG seed, no clock, no network, no third-party libs.
Identical bytes on every run.
"""
import hashlib
import math
import os
import random
import struct
import zlib

W = H = 1024
OUT = "/output/entry.png"
SEED = 20261121

rng = random.Random(SEED)
canvas = [bytearray(W * 3) for _ in range(H)]


def _clamp(v):
    return 0 if v < 0 else (255 if v > 255 else int(v))


def _blend_row(row, x0, x1, r, g, b, a=255):
    if x1 < x0 or a <= 0:
        return
    if x0 < 0:
        x0 = 0
    if x1 > W - 1:
        x1 = W - 1
    if a >= 255:
        row[x0 * 3:(x1 + 1) * 3] = bytes((r, g, b)) * (x1 - x0 + 1)
        return
    inv = 255 - a
    for x in range(x0, x1 + 1):
        i = x * 3
        row[i] = (r * a + row[i] * inv) // 255
        row[i + 1] = (g * a + row[i + 1] * inv) // 255
        row[i + 2] = (b * a + row[i + 2] * inv) // 255


def fill_rect(x, y, w, h, rgb, a=255):
    r, g, b = rgb
    y0 = max(0, y)
    y1 = min(H - 1, y + h - 1)
    for yy in range(y0, y1 + 1):
        _blend_row(canvas[yy], x, x + w - 1, r, g, b, a)


def vgrad(y0, y1, top, bottom):
    n = max(1, y1 - y0)
    for y in range(max(0, y0), min(H - 1, y1) + 1):
        t = (y - y0) / n
        r = _clamp(top[0] + (bottom[0] - top[0]) * t)
        g = _clamp(top[1] + (bottom[1] - top[1]) * t)
        b = _clamp(top[2] + (bottom[2] - top[2]) * t)
        canvas[y][:] = bytes((r, g, b)) * W


def disc(cx, cy, r, rgb, a=255):
    r0, g0, b0 = rgb
    for y in range(max(0, cy - r), min(H - 1, cy + r) + 1):
        dy = y - cy
        dx = int(math.sqrt(max(0, r * r - dy * dy)))
        _blend_row(canvas[y], cx - dx, cx + dx, r0, g0, b0, a)


def ellipse(cx, cy, rx, ry, rgb, a=255):
    r0, g0, b0 = rgb
    for y in range(max(0, cy - ry), min(H - 1, cy + ry) + 1):
        t = (y - cy) / ry
        dx = int(rx * math.sqrt(max(0.0, 1.0 - t * t)))
        _blend_row(canvas[y], cx - dx, cx + dx, r0, g0, b0, a)


def rrect(x0, y0, x1, y1, rad, rgb, a=255):
    r0, g0, b0 = rgb
    for y in range(max(0, y0), min(H - 1, y1) + 1):
        if y < y0 + rad:
            dy = y0 + rad - y
            dx = int(rad - math.sqrt(max(0, rad * rad - dy * dy)))
            xa, xb = x0 + dx, x1 - dx
        elif y > y1 - rad:
            dy = y - (y1 - rad)
            dx = int(rad - math.sqrt(max(0, rad * rad - dy * dy)))
            xa, xb = x0 + dx, x1 - dx
        else:
            xa, xb = x0, x1
        _blend_row(canvas[y], xa, xb, r0, g0, b0, a)


def poly_fill(pts, rgb, a=255):
    r0, g0, b0 = rgb
    ys = [p[1] for p in pts]
    ymin = int(math.ceil(min(ys)))
    ymax = int(math.floor(max(ys)))
    n = len(pts)
    for y in range(max(0, ymin), min(H - 1, ymax) + 1):
        xs = []
        for i in range(n):
            px1, py1 = pts[i]
            px2, py2 = pts[(i + 1) % n]
            if (py1 <= y < py2) or (py2 <= y < py1):
                t = (y - py1) / (py2 - py1)
                xs.append(px1 + t * (px2 - px1))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            xa = int(math.ceil(xs[k]))
            xb = int(math.floor(xs[k + 1]))
            if xb >= xa:
                _blend_row(canvas[y], xa, xb, r0, g0, b0, a)


def soft_disc(cx, cy, r, rgb, a0):
    R, G, B = rgb
    r2 = float(r * r)
    for y in range(max(0, cy - r), min(H - 1, cy + r) + 1):
        dy = y - cy
        row = canvas[y]
        dx = int(math.sqrt(max(0, r2 - dy * dy)))
        for x in range(max(0, cx - dx), min(W - 1, cx + dx) + 1):
            ddx = x - cx
            t = 1.0 - (ddx * ddx + dy * dy) / r2
            if t <= 0:
                continue
            a = int(a0 * t * t)
            if a <= 0:
                continue
            i = x * 3
            inv = 255 - a
            row[i] = (R * a + row[i] * inv) // 255
            row[i + 1] = (G * a + row[i + 1] * inv) // 255
            row[i + 2] = (B * a + row[i + 2] * inv) // 255


def soft_ellipse(cx, cy, rx, ry, rgb, a0):
    R, G, B = rgb
    for y in range(max(0, cy - ry), min(H - 1, cy + ry) + 1):
        dy = (y - cy) / float(ry)
        row = canvas[y]
        dx = int(rx * math.sqrt(max(0.0, 1.0 - dy * dy)))
        for x in range(max(0, cx - dx), min(W - 1, cx + dx) + 1):
            t = 1.0 - ((x - cx) / float(rx)) ** 2 - dy * dy
            if t <= 0:
                continue
            a = int(a0 * t * t)
            if a <= 0:
                continue
            i = x * 3
            inv = 255 - a
            row[i] = (R * a + row[i] * inv) // 255
            row[i + 1] = (G * a + row[i + 1] * inv) // 255
            row[i + 2] = (B * a + row[i + 2] * inv) // 255


def line(x0, y0, x1, y1, rgb, a=255):
    R, G, B = rgb
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    x, y = x0, y0
    while True:
        if 0 <= x < W and 0 <= y < H:
            row = canvas[y]
            i = x * 3
            inv = 255 - a
            row[i] = (R * a + row[i] * inv) // 255
            row[i + 1] = (G * a + row[i + 1] * inv) // 255
            row[i + 2] = (B * a + row[i + 2] * inv) // 255
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


# --- tiny 5x7 bitmap font (only the glyphs the labels need) ---
FONT = {
    'A': ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    'C': ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    'E': ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    'F': ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    'I': ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    'O': ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    'P': ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    'R': ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    'S': ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    'T': ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    'W': ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    '0': ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    '1': ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    '2': ("01110", "10001", "00001", "00110", "01000", "10000", "11111"),
    '-': ("00000", "00000", "00000", "01110", "00000", "00000", "00000"),
    '·': ("00000", "00000", "00000", "00100", "00000", "00000", "00000"),
    ' ': ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
}


def text_width(s, scale):
    return len(s) * 6 * scale - scale


def draw_text(s, cx, y, scale, rgb, a=255):
    x = cx - text_width(s, scale) // 2
    for ch in s:
        glyph = FONT.get(ch, FONT[' '])
        for ri, bits in enumerate(glyph):
            for ci, bit in enumerate(bits):
                if bit == '1':
                    fill_rect(x + ci * scale, y + ri * scale,
                              scale, scale, rgb, a)
        x += 6 * scale


# --- brushed chrome: horizontal gradient stops across the body ---
CHROME_STOPS = [
    (300, (146, 148, 152)),
    (332, (206, 207, 209)),
    (382, (239, 240, 241)),
    (436, (196, 197, 199)),
    (506, (228, 229, 231)),
    (580, (243, 244, 245)),
    (642, (198, 199, 201)),
    (692, (232, 233, 235)),
    (724, (158, 160, 164)),
]


def _chrome_at(x):
    if x <= CHROME_STOPS[0][0]:
        return CHROME_STOPS[0][1]
    for (x0, c0), (x1, c1) in zip(CHROME_STOPS, CHROME_STOPS[1:]):
        if x0 <= x <= x1:
            t = (x - x0) / float(x1 - x0)
            return tuple(_clamp(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))
    return CHROME_STOPS[-1][1]


CHROME_COLS = [_chrome_at(x) for x in range(300, 725)]


def draw_chrome_body(x0, y0, x1, y1, rad):
    for y in range(y0, y1 + 1):
        if y < y0 + rad:
            dy = y0 + rad - y
            dx = int(rad - math.sqrt(max(0, rad * rad - dy * dy)))
            xa, xb = x0 + dx, x1 - dx
        elif y > y1 - rad:
            dy = y - (y1 - rad)
            dx = int(rad - math.sqrt(max(0, rad * rad - dy * dy)))
            xa, xb = x0 + dx, x1 - dx
        else:
            xa, xb = x0, x1
        shade = 1.0
        shade += 0.07 * math.exp(-((y - 446) / 16.0) ** 2)  # top highlight
        shade -= 0.06 * math.exp(-((y - 758) / 22.0) ** 2)  # bottom shade
        brush = 3.0 * math.sin(y * 1.9) + 2.0 * math.sin(y * 0.83 + 1.2)
        row = canvas[y]
        for x in range(xa, xb + 1):
            cr, cg, cb = CHROME_COLS[x - 300]
            i = x * 3
            row[i] = _clamp(cr * shade + brush)
            row[i + 1] = _clamp(cg * shade + brush)
            row[i + 2] = _clamp(cb * shade + brush)


def draw_cube(cx, cy, s, tilt_deg, with_glow=True):
    """A translucent glowing ice cube: front face + top + right faces."""
    if with_glow:
        soft_disc(cx, cy - 6, int(s * 1.05), (186, 222, 244), 66)
        soft_disc(cx, cy - 6, int(s * 0.68), (228, 244, 252), 55)
    th = math.radians(tilt_deg)
    ct, st = math.cos(th), math.sin(th)

    def rot(px, py):
        return (cx + px * ct - py * st, cy + px * st + py * ct)

    h = s / 2.0
    d = s * 0.32
    front = [(-h, -h), (h, -h), (h, h), (-h, h)]
    top = [(-h, -h), (h, -h), (h + d, -h - d), (-h + d, -h - d)]
    right = [(h, -h), (h + d, -h - d), (h + d, h - d), (h, h)]
    poly_fill([rot(*p) for p in front], (198, 228, 243))
    poly_fill([rot(*p) for p in right], (140, 193, 226))
    poly_fill([rot(*p) for p in top], (236, 248, 255))
    # crisp white edges around the silhouette and the inner seams
    outline = [(-h, -h), (h + d, -h - d), (h + d, h - d), (h, h), (-h, h)]
    pts = [rot(*p) for p in outline]
    for a, b in zip(pts, pts[1:] + pts[:1]):
        line(int(a[0]), int(a[1]), int(b[0]), int(b[1]),
             (255, 255, 255), 220)
    ft = [rot(-h, -h), rot(h, -h)]
    line(int(ft[0][0]), int(ft[0][1]), int(ft[1][0]), int(ft[1][1]),
         (255, 255, 255), 200)
    fr = [rot(h, -h), rot(h, h)]
    line(int(fr[0][0]), int(fr[0][1]), int(fr[1][0]), int(fr[1][1]),
         (255, 255, 255), 200)
    # frost speckles inside the front face
    for _ in range(14):
        px = rng.uniform(-h + 8, h - 8)
        py = rng.uniform(-h + 8, h - 8)
        qx, qy = rot(px, py)
        fill_rect(int(qx), int(qy), 3, 3, (255, 255, 255), 150)
    # sparkle on the top face
    sx, sy = rot(h * 0.45, -h * 0.45)
    sx, sy = int(sx), int(sy)
    line(sx - 9, sy, sx + 9, sy, (255, 255, 255), 235)
    line(sx, sy - 9, sx, sy + 9, (255, 255, 255), 235)
    disc(sx, sy, 3, (255, 255, 255), 235)


def steam_wisp(x_base, top_y, phase, drift):
    steps = 14
    for k in range(steps):
        t = k / float(steps - 1)
        y = int(432 - (432 - top_y) * t)
        x = int(x_base + drift * t + 16 * math.sin(t * 5.0 + phase))
        r = int(13 + 20 * t)
        a = int(30 - 20 * t)
        soft_disc(x, y, r, (255, 255, 255), max(6, a))


def build():
    # studio backdrop: pale wall above, slightly darker surface below
    vgrad(0, 800, (243, 241, 236), (222, 218, 210))
    vgrad(800, 1024, (216, 211, 204), (198, 192, 184))
    # soft contact shadows (drawn first, products sit on top of them)
    soft_ellipse(512, 796, 315, 42, (58, 52, 44), 62)
    soft_ellipse(820, 884, 145, 24, (58, 52, 44), 52)

    # --- the single accessory: white plate holding one spare ice cube ---
    ellipse(820, 862, 152, 46, (206, 204, 201))
    ellipse(820, 859, 146, 43, (252, 252, 250))
    ellipse(820, 856, 128, 34, (238, 238, 236))
    draw_cube(820, 806, 64, 10)

    # --- the toaster: brushed-chrome body ---
    draw_chrome_body(300, 430, 724, 770, 26)
    # slots on the top face
    rrect(356, 436, 474, 460, 10, (36, 38, 42))
    rrect(550, 436, 668, 460, 10, (36, 38, 42))
    line(360, 458, 470, 458, (140, 142, 146), 150)
    line(554, 458, 664, 458, (140, 142, 146), 150)
    # seam, lever, browning dial, feet
    line(312, 470, 712, 470, (120, 122, 126), 90)
    fill_rect(724, 580, 34, 12, (110, 112, 116))
    rrect(750, 568, 776, 604, 9, (88, 90, 94))
    rrect(754, 572, 772, 600, 7, (150, 152, 156))
    disc(368, 700, 20, (96, 98, 102))
    disc(368, 700, 16, (178, 180, 184))
    line(368, 700, 379, 692, (60, 62, 66), 255)
    rrect(338, 768, 386, 784, 6, (42, 42, 44))
    rrect(638, 768, 686, 784, 6, (42, 42, 44))

    # cold glow reflected on the toaster's top face
    soft_disc(415, 472, 85, (172, 212, 236), 22)
    # steam rising from both slots, curling around the popping cube
    steam_wisp(392, 196, 0.4, -18)
    steam_wisp(436, 176, 2.1, 10)
    steam_wisp(470, 220, 4.0, 26)
    steam_wisp(600, 210, 1.2, -8)
    steam_wisp(636, 240, 3.3, 14)
    # --- the hero: a glowing ice cube popping out of the left slot ---
    draw_cube(415, 360, 150, -10)

    # --- product label, embossed on the chrome ---
    draw_text("TOAST-O-FROST", 512, 585, 4, (255, 255, 255), 110)
    draw_text("TOAST-O-FROST", 512, 583, 4, (52, 54, 58), 255)
    draw_text("1200W · CRISP ICE", 512, 630, 2, (70, 72, 76), 255)


def _chunk(tag, data):
    out = struct.pack(">I", len(data)) + tag + data
    out += struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return out


def write_png(path):
    raw = bytearray()
    for row in canvas:
        raw.append(0)
        raw.extend(row)
    comp = zlib.compress(bytes(raw), 9)
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
    png += _chunk(b"IDAT", comp)
    png += _chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


def main():
    build()
    size = write_png(OUT)
    with open(OUT, "rb") as f:
        data = f.read()
    digest = hashlib.sha256(data).hexdigest()
    w, h = struct.unpack(">II", data[16:24])
    print("output:", OUT)
    print("size_bytes:", size)
    print("sha256:", digest)
    print("dimensions:", w, "x", h)
    gate = (data[:8] == b"\x89PNG\r\n\x1a\n" and w == 1024 and h == 1024
            and size <= 1048576)
    print("gate_valid:", 1 if gate else 0)


if __name__ == "__main__":
    main()
