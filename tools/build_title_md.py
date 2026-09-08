#!/usr/bin/env python3
"""Build the Mega Drive title logo from the flat-color reference art.

The reference art is letterboxed with white side bars and is stored with JPEG
compression, so it carries 3px anti-aliased edges and ringing noise. This script
reduces it to three flat MD colors (blue ZANAC, red M, green D) over a
transparent background.

Two details matter for edge quality:

* Edge pixels are treated as alpha coverage over black rather than as their own
  colors. A plain nearest-centroid match sends half-lit blue edges to the dark
  green, which used to scatter green over the whole logo.
* The downscale uses a fixed integer box. A fractional scale alternates 2px and
  3px boxes, which turns straight diagonals into ragged staircases.

Outputs:
  res/title_md_logo.png       — indexed logo bitmap for ResComp
  inc/title_md.h              — placement constants
  src/data/title_md_palette.c — VDP palette
"""
from __future__ import annotations

import argparse
import struct
import subprocess
import sys
import zlib
from pathlib import Path

SCREEN_W = 256
MAX_W = 240
MAX_H = 88
# 16px (two 8×8 rows) below the SCORE/TOP line at nametable row 2.
# Y=24 sat on the next tile row and cramped the hiscore.
LOGO_Y = 40

BACKGROUND = 0
BLUE = 1
RED = 2
GREEN = 3
# Same RGB as BACKGROUND, but a nonzero index so it hides the plane behind it:
# on the Mega Drive color 0 is always transparent.
OPAQUE_BLACK = 4

# Coverage steps used to fake anti-aliasing, counting the fully covered one.
AA_LEVELS = 3
AA_BASE = 5

# Dominant colors measured in the reference art.
INK_COLORS = [
    (90, 157, 225),
    (174, 0, 0),
    (9, 100, 33),
]
CENTROIDS = [(0, 0, 0)] + INK_COLORS

# An edge pixel counts as ink once it is at least half lit.
ALPHA_THRESHOLD = 0.5

PALETTE_SIZE = 16


def snap_md_rgb(r: int, g: int, b: int) -> tuple[int, int, int]:
    """Round to the nearest MD 3-bit-per-channel level."""

    def q(v: int) -> int:
        return min(252, ((v + 18) // 36) * 36)

    return q(r), q(g), q(b)


def _srgb_to_linear(v: int) -> float:
    x = v / 255.0
    return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(v: float) -> int:
    v = max(0.0, min(1.0, v))
    x = 12.92 * v if v <= 0.0031308 else 1.055 * (v ** (1 / 2.4)) - 0.055
    return round(255 * x)


def mix_with_black(color: tuple[int, int, int], alpha: float) -> tuple[int, int, int]:
    """Blend towards black in linear light, which is how real coverage reads."""
    return tuple(_linear_to_srgb(_srgb_to_linear(c) * alpha) for c in color)


def pick_tones(color: tuple[int, int, int], levels: int) -> list[tuple[int, int, int]]:
    """Palette ramp from faint to full, skipping tones the VDP cannot separate.

    The hardware only has 3 bits per channel, so most requested blends collapse
    onto a neighbour once snapped. Spending a palette entry on a duplicate buys
    nothing, so candidates are matched against the set of colors the VDP can
    actually reach and deduplicated.
    """
    reachable: list[tuple[int, int, int]] = []
    for i in range(1, 101):
        snapped = snap_md_rgb(*mix_with_black(color, i / 100))
        if snapped != (0, 0, 0) and snapped not in reachable:
            reachable.append(snapped)

    out: list[tuple[int, int, int]] = []
    for i in range(1, levels + 1):
        want = mix_with_black(color, i / levels)
        best = min(reachable, key=lambda c: sum((a - b) ** 2 for a, b in zip(c, want)))
        if best not in out:
            out.append(best)
    return out


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter_row(ftype: int, row: bytearray, prev: bytes, bpp: int) -> bytearray:
    if ftype == 0:
        return row
    if ftype == 1:
        for i in range(bpp, len(row)):
            row[i] = (row[i] + row[i - bpp]) & 0xFF
    elif ftype == 2:
        for i in range(len(row)):
            row[i] = (row[i] + prev[i]) & 0xFF
    elif ftype == 3:
        for i in range(len(row)):
            left = row[i - bpp] if i >= bpp else 0
            row[i] = (row[i] + ((left + prev[i]) >> 1)) & 0xFF
    elif ftype == 4:
        for i in range(len(row)):
            left = row[i - bpp] if i >= bpp else 0
            up_left = prev[i - bpp] if i >= bpp else 0
            row[i] = (row[i] + _paeth(left, prev[i], up_left)) & 0xFF
    else:
        sys.exit("unsupported PNG filter %d" % ftype)
    return row


def read_png_rgb(path: Path) -> tuple[int, int, list[tuple[int, int, int]]]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        sys.exit("not a PNG: %s" % path)

    pos = 8
    width = height = color_type = 0
    palette: list[tuple[int, int, int]] = []
    idat = bytearray()

    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        pos += 4
        ctype = data[pos:pos + 4]
        pos += 4
        chunk = data[pos:pos + length]
        pos += length + 4

        if ctype == b"IHDR":
            width, height, _, color_type, _, _, _ = struct.unpack(">IIBBBBB", chunk)
        elif ctype == b"PLTE":
            palette = [(chunk[i], chunk[i + 1], chunk[i + 2]) for i in range(0, len(chunk), 3)]
        elif ctype == b"IDAT":
            idat.extend(chunk)
        elif ctype == b"IEND":
            break

    bpp = {2: 3, 6: 4, 3: 1}.get(color_type)
    if bpp is None:
        sys.exit("unsupported PNG color type %d" % color_type)

    raw = zlib.decompress(bytes(idat))
    stride = width * bpp
    pixels: list[tuple[int, int, int]] = []
    prev = bytes(stride)
    off = 0

    for _y in range(height):
        ftype = raw[off]
        off += 1
        row = _unfilter_row(ftype, bytearray(raw[off:off + stride]), prev, bpp)
        off += stride
        prev = bytes(row)

        if color_type == 3:
            pixels.extend(palette[row[x]] for x in range(width))
        else:
            pixels.extend((row[x * bpp], row[x * bpp + 1], row[x * bpp + 2]) for x in range(width))

    return width, height, pixels


def classify_image(pixels: list[tuple[int, int, int]]) -> list[int]:
    """Quantize to background/blue/red/green.

    Each ink color is treated as a ramp from black, so an edge pixel is matched
    by hue and then accepted or dropped on how lit it is. Matching on raw
    distance instead would pull half-lit blue edges into the dark green.
    """
    norms = [sum(c * c for c in color) for color in INK_COLORS]
    cache: dict[tuple[int, int, int], int] = {}
    out = []

    for px in pixels:
        idx = cache.get(px)
        if idx is None:
            r, g, b = px
            # The reference art is letterboxed with white bars; not artwork.
            if r > 200 and g > 200 and b > 200:
                idx = BACKGROUND
            else:
                best = BACKGROUND
                best_residual = float("inf")
                best_alpha = 0.0

                for i, (cr, cg, cb) in enumerate(INK_COLORS):
                    alpha = (r * cr + g * cg + b * cb) / norms[i]
                    alpha = min(1.0, max(0.0, alpha))
                    residual = ((r - alpha * cr) ** 2 + (g - alpha * cg) ** 2
                                + (b - alpha * cb) ** 2)
                    if residual < best_residual:
                        best_residual = residual
                        best_alpha = alpha
                        best = i + 1

                idx = best if best_alpha >= ALPHA_THRESHOLD else BACKGROUND
            cache[px] = idx
        out.append(idx)

    return out


def denoise(indices: list[int], w: int, h: int) -> list[int]:
    """Clean the full-resolution classification.

    JPEG ringing scatters stray ink over the black background and leaves color
    fringes where two shapes meet. An ink pixel that lacks same-color support is
    either pulled to the dominant neighbouring color or dropped.
    """
    out = list(indices)
    offsets = (-w - 1, -w, -w + 1, -1, 1, w - 1, w, w + 1)

    for y in range(1, h - 1):
        base = y * w
        for x in range(1, w - 1):
            i = base + x
            c = indices[i]
            if not c:
                continue

            counts = [0, 0, 0, 0]
            for off in offsets:
                counts[indices[i + off]] += 1

            if counts[c] >= 3:
                continue

            best = max((BLUE, RED, GREEN), key=counts.__getitem__)
            out[i] = best if counts[best] >= 5 else BACKGROUND

    for x in range(w):
        out[x] = BACKGROUND
        out[(h - 1) * w + x] = BACKGROUND
    for y in range(h):
        out[y * w] = BACKGROUND
        out[y * w + w - 1] = BACKGROUND

    return out


def crop_to_ink(indices: list[int], w: int, h: int) -> tuple[int, int, int, int]:
    minx, miny, maxx, maxy = w, h, -1, -1
    for y in range(h):
        base = y * w
        for x in range(w):
            if indices[base + x]:
                if x < minx:
                    minx = x
                if x > maxx:
                    maxx = x
                if y < miny:
                    miny = y
                if y > maxy:
                    maxy = y
    if maxx < 0:
        sys.exit("no logo pixels found in source")
    return minx, miny, maxx, maxy


def pick_scale(src_w: int, src_h: int) -> int:
    """Largest integer downscale whose tile-aligned result still fits on screen."""
    scale = 1
    while scale < 16:
        tw = ((src_w // scale) + 7) & ~7
        th = ((src_h // scale) + 7) & ~7
        if tw <= MAX_W and th <= MAX_H:
            return scale
        scale += 1
    sys.exit("cannot fit logo within %dx%d" % (MAX_W, MAX_H))


def downsample_uniform(indices: list[int], sw: int, box: tuple[int, int, int, int],
                       scale: int) -> tuple[int, int, list[int]]:
    """Downscale with a fixed scale x scale box.

    Every destination pixel consumes the same number of source pixels, so a
    straight edge in the source produces an evenly stepped edge here. A
    fractional scale would alternate box sizes and visibly break up diagonals.
    """
    x0, y0, x1, y1 = box
    tw = (x1 - x0 + 1) // scale
    th = (y1 - y0 + 1) // scale
    area = scale * scale
    out = [BACKGROUND] * (tw * th)

    for y in range(th):
        sy0 = y0 + y * scale
        for x in range(tw):
            sx0 = x0 + x * scale

            counts = [0, 0, 0, 0]
            for dy in range(scale):
                base = (sy0 + dy) * sw + sx0
                for dx in range(scale):
                    counts[indices[base + dx]] += 1

            if (area - counts[BACKGROUND]) * 2 <= area:
                continue
            out[y * tw + x] = max((BLUE, RED, GREEN), key=counts.__getitem__)

    return tw, th, out


def drop_isolated(indices: list[int], w: int, h: int) -> list[int]:
    """Drop ink pixels with no orthogonal neighbour at all.

    Deliberately conservative: requiring two neighbours would erase the thin
    radiating strokes inside the green D.
    """
    out = list(indices)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if not indices[i]:
                continue
            if ((x > 0 and indices[i - 1])
                    or (x < w - 1 and indices[i + 1])
                    or (y > 0 and indices[i - w])
                    or (y < h - 1 and indices[i + w])):
                continue
            out[i] = BACKGROUND
    return out


def pad_to_tiles(indices: list[int], w: int, h: int) -> tuple[int, int, list[int]]:
    nw = (w + 7) & ~7
    nh = (h + 7) & ~7
    if nw == w and nh == h:
        return w, h, indices
    out = [BACKGROUND] * (nw * nh)
    for y in range(h):
        out[y * nw:y * nw + w] = indices[y * w:(y + 1) * w]
    return nw, nh, out


def _build_ramps():
    """Assign palette slots to the anti-alias tones of the MD mark colors."""
    tones: dict[int, tuple[int, int, int]] = {}
    slots: dict[int, list[int]] = {}
    nxt = AA_BASE

    for full_idx, color in ((RED, INK_COLORS[RED - 1]), (GREEN, INK_COLORS[GREEN - 1])):
        ramp = pick_tones(color, AA_LEVELS)
        idxs = []
        for rgb in ramp[:-1]:
            tones[nxt] = rgb
            idxs.append(nxt)
            nxt += 1
        idxs.append(full_idx)
        slots[full_idx] = idxs

    if nxt > PALETTE_SIZE:
        sys.exit("anti-alias ramps need %d palette entries, only %d available"
                 % (nxt, PALETTE_SIZE))
    return tones, slots


AA_TONES, AA_SLOTS = _build_ramps()


def tone_for(color_idx: int, alpha: float) -> int:
    """Palette index for `alpha` coverage of `color_idx` over black."""
    ramp = AA_SLOTS[color_idx]
    level = int(alpha * len(ramp) + 0.5)
    if level <= 0:
        return BACKGROUND
    return ramp[min(len(ramp), level) - 1]


def palette_rgb() -> list[tuple[int, int, int]]:
    pal = [snap_md_rgb(*c) for c in CENTROIDS]
    pal[BACKGROUND] = (0, 0, 0)
    pal.extend([(0, 0, 0)] * (PALETTE_SIZE - len(pal)))
    for idx, rgb in AA_TONES.items():
        pal[idx] = rgb
    return pal


def write_png(path: Path, width: int, height: int, indices: list[int]):
    flat: list[int] = []
    for rgb in palette_rgb():
        flat.extend(rgb)
    flat.extend([0] * ((256 - PALETTE_SIZE) * 3))

    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw.extend(indices[y * width:(y + 1) * width])

    def chunk(tag: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", crc)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0))
    png += chunk(b"PLTE", bytes(flat[:256 * 3]))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def to_png(source: Path) -> Path:
    tmp = source.parent / ".title_build_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    out = tmp / "src.png"
    subprocess.run(
        ["sips", "-s", "format", "png", str(source), "--out", str(out)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return out


def find_groove(indices: list[int], w: int, h: int) -> int:
    """Y of the first row below the blue artwork -- the mouth of the groove.

    The blue ZANAC wordmark sits on top of a thick horizontal bar, and that bar
    is the lowest blue in the art, so the bottom edge of the blue bounding box
    is the slot the logo slides out of. Rounded up to a tile boundary, because
    the mask that hides the unemerged logo is built from whole tiles.
    """
    bottom = max(y for y in range(h) for x in range(w) if indices[y * w + x] == BLUE)
    groove = bottom + 1
    if (LOGO_Y + groove) % 8:
        groove += 8 - ((LOGO_Y + groove) % 8)
    return groove


def split_layers(indices: list[int], w: int, h: int, groove: int, sample):
    """Cut the logo into a scrolling blue layer and a static MD layer.

    Blue layer keeps every blue pixel and nothing else, so it can be scrolled
    up out of the groove on BG_B.

    The MD layer covers the tiles holding the red M and green D. Blue there
    always becomes transparent so the bar can be seen passing behind the mark.
    Black, though, depends on which side of the groove it falls on: below the
    groove it must be opaque, since that is the wall keeping the unemerged
    wordmark hidden, but above the groove it must stay transparent -- an opaque
    background up there would be a static black patch sitting on top of the
    blue as it rises.
    """
    zanac = [BLUE if indices[y * w + x] == BLUE else BACKGROUND
             for y in range(groove) for x in range(w)]

    mark = [(x, y) for y in range(h) for x in range(w)
            if indices[y * w + x] in (RED, GREEN)]
    tx0 = min(x for x, _ in mark) // 8
    tx1 = max(x for x, _ in mark) // 8
    ty0 = min(y for _, y in mark) // 8
    ty1 = max(y for _, y in mark) // 8
    mx, my = tx0 * 8, ty0 * 8
    mw, mh = (tx1 - tx0 + 1) * 8, (ty1 - ty0 + 1) * 8

    if my < groove < my + mh and (groove - my) % 8:
        raise SystemExit("groove splits an MD tile row; adjust LOGO_Y")

    def touches_glyph(x: int, y: int) -> bool:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and indices[ny * w + nx] in (RED, GREEN):
                    return True
        return False

    md = []
    for y in range(my, my + mh):
        # Anti-aliasing is a blend with black, so a fringe painted outside the
        # glyph is only truthful where the backdrop really is black. Below the
        # groove it is; above it the backdrop is the blue sliding past, and a
        # fringe there would freeze a dark halo over the animation.
        smooth = y >= groove
        for x in range(mx, mx + mw):
            v = indices[y * w + x]

            if v == BLUE:
                md.append(BACKGROUND)
                continue

            counts = sample(x, y)
            ink = counts[RED] + counts[GREEN]
            total = sum(counts)
            alpha = ink / total if total else 0.0
            hue = RED if counts[RED] >= counts[GREEN] else GREEN

            if v in (RED, GREEN):
                # Shading a pixel that is already glyph turns no transparent
                # pixel opaque, so it costs nothing on either side of the
                # groove -- and the D's fan sits mostly above it.
                md.append(tone_for(v, alpha) or v)
            elif not smooth:
                md.append(BACKGROUND)
            elif ink and touches_glyph(x, y):
                md.append(tone_for(hue, alpha) or OPAQUE_BLACK)
            else:
                md.append(OPAQUE_BLACK)

    # Above the groove the opaque silhouette must still be exactly the glyph:
    # shading is allowed to recolor those pixels but never to add one, or the
    # extra pixels become a halo frozen over the rising blue.
    for y in range(my, min(groove, my + mh)):
        for x in range(mx, mx + mw):
            was = indices[y * w + x] in (RED, GREEN)
            now = md[(y - my) * mw + (x - mx)] != BACKGROUND
            if was != now:
                raise SystemExit("MD silhouette changed above the groove at %d,%d" % (x, y))

    return (zanac, w, groove), (md, mw, mh, tx0, ty0)


def build(source: Path, out_root: Path):
    sw, sh, pixels = read_png_rgb(to_png(source))

    # Denoise at full resolution: cropping first would let a single stray pixel
    # inflate the bounding box and shrink the logo.
    full = denoise(classify_image(pixels), sw, sh)

    box = crop_to_ink(full, sw, sh)
    src_w = box[2] - box[0] + 1
    src_h = box[3] - box[1] + 1

    scale = pick_scale(src_w, src_h)
    tw, th, indices = downsample_uniform(full, sw, box, scale)
    indices = drop_isolated(indices, tw, th)

    x0, y0, x1, y1 = crop_to_ink(indices, tw, th)
    cw = x1 - x0 + 1
    ch = y1 - y0 + 1
    cropped = [indices[(y0 + y) * tw + x0 + x] for y in range(ch) for x in range(cw)]
    tw, th, indices = pad_to_tiles(cropped, cw, ch)

    print("source ink %dx%d, scale 1/%d -> %dx%d" % (src_w, src_h, scale, tw, th))

    res = out_root / "res"
    inc = out_root / "inc"
    res.mkdir(parents=True, exist_ok=True)
    inc.mkdir(parents=True, exist_ok=True)

    logo_path = res / "title_md_logo.png"

    def sample(x: int, y: int) -> list[int]:
        """Class counts of the source box that collapsed into output pixel x,y.

        Lets the MD layer recover the sub-pixel coverage that the binary
        downsample threw away, without disturbing the rest of the pipeline.
        """
        counts = [0, 0, 0, 0]
        sx = box[0] + (x + x0) * scale
        sy = box[1] + (y + y0) * scale
        for dy in range(scale):
            if sy + dy > box[3]:
                break
            base = (sy + dy) * sw
            for dx in range(scale):
                if sx + dx > box[2]:
                    break
                counts[full[base + sx + dx]] += 1
        return counts

    groove = find_groove(indices, tw, th)
    (zanac, zw, zh), (md, mw, mh, mtx, mty) = split_layers(indices, tw, th, groove, sample)

    ox = ((SCREEN_W - tw) // 2) & ~7
    press_row = (LOGO_Y + th) // 8 + 2

    zanac_path = res / "title_zanac.png"
    mark_path = res / "title_mdmark.png"
    write_png(zanac_path, zw, zh, zanac)
    write_png(mark_path, mw, mh, md)

    # Reference image: the two layers composited where they come to rest. This
    # is what the screen owes us once the intro finishes, so it is what the
    # verifier compares against.
    ref = list(zanac) + [BACKGROUND] * (tw * (th - zh))
    for y in range(mh):
        for x in range(mw):
            v = md[y * mw + x]
            if v:
                ref[(mty * 8 + y) * tw + mtx * 8 + x] = v
    write_png(logo_path, tw, th, ref)

    aa_px = sum(1 for v in ref if v >= AA_BASE)
    print("anti-alias: %d edge pixels over %d tones" % (aa_px, len(AA_TONES)))

    (inc / "title_md.h").write_text(f"""#ifndef TITLE_MD_H
#define TITLE_MD_H

#include <genesis.h>

#define TITLE_MD_W          {tw}
#define TITLE_MD_IMG_H      {th}
#define TITLE_MD_X          {ox}
#define TITLE_MD_Y          {LOGO_Y}
#define TITLE_MD_TILE_X     ({ox} >> 3)
#define TITLE_MD_TILE_Y     ({LOGO_Y} >> 3)
#define TITLE_MD_TILE_W     ({tw} >> 3)
#define TITLE_MD_TILE_H     ({th} >> 3)
#define TITLE_MD_PRESS_ROW  {press_row}

/* Blue wordmark, scrolled up out of the groove on BG_B. */
#define TITLE_ZANAC_TILE_X  ({ox} >> 3)
#define TITLE_ZANAC_TILE_Y  ({LOGO_Y} >> 3)
#define TITLE_ZANAC_TILE_W  ({zw} >> 3)
#define TITLE_ZANAC_TILE_H  ({zh} >> 3)
#define TITLE_ZANAC_TRAVEL  {zh}

/* Static MD mark on BG_A, drawn over the blue. */
#define TITLE_MDMARK_TILE_X (({ox} >> 3) + {mtx})
#define TITLE_MDMARK_TILE_Y (({LOGO_Y} >> 3) + {mty})
#define TITLE_MDMARK_TILE_W ({mw} >> 3)
#define TITLE_MDMARK_TILE_H ({mh} >> 3)

/* First BG_A row that stays opaque black: the lip of the groove. */
#define TITLE_GROOVE_ROW    (({LOGO_Y} + {groove}) >> 3)

extern const u16 title_md_palette[16];

#endif
""", encoding="utf-8")

    c_src = out_root / "src" / "data" / "title_md_palette.c"
    c_src.parent.mkdir(parents=True, exist_ok=True)
    names = ["background", "ZANAC blue", "M red", "D green", "opaque black"]
    for full_idx, ramp in AA_SLOTS.items():
        for step, slot in enumerate(ramp[:-1]):
            while len(names) <= slot:
                names.append("unused")
            names[slot] = "%s edge %d/%d" % (names[full_idx], step + 1, len(ramp))
    lines = ["#include \"title_md.h\"", "", "const u16 title_md_palette[16] = {"]
    for i, (r, g, b) in enumerate(palette_rgb()):
        label = names[i] if i < len(names) else "unused"
        lines.append(f"    RGB24_TO_VDPCOLOR(0x{r:02X}{g:02X}{b:02X}),  /* {i} {label} */")
    lines.append("};")
    lines.append("")
    c_src.write_text("\n".join(lines), encoding="utf-8")

    ink = sum(1 for v in indices if v)
    print("wrote %s (%dx%d, %d tiles, %d ink px)" % (logo_path, tw, th, (tw // 8) * (th // 8), ink))
    print("groove at logo y=%d -> screen y=%d, row %d" % (groove, LOGO_Y + groove, (LOGO_Y + groove) // 8))
    print("  zanac layer %dx%d (%d tiles)" % (zw, zh, (zw // 8) * (zh // 8)))
    print("  mdmark layer %dx%d (%d tiles) at tile +%d,+%d" % (mw, mh, (mw // 8) * (mh // 8), mtx, mty))
    print("wrote %s, %s" % (inc / "title_md.h", c_src))


def main():
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(root / "res" / "title_md_source.png"))
    ap.add_argument("--out", default=str(root))
    args = ap.parse_args()

    source = Path(args.source)
    if not source.is_file():
        sys.exit("source not found: %s" % args.source)
    build(source, Path(args.out))


if __name__ == "__main__":
    main()
