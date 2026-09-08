#!/usr/bin/env python3
"""Build a static miniature Zanac MD mark for the Original HUD pocket.

Reads the already-quantized title composite (res/title_md_logo.png) and
emits a 48×16 (6×2 tile) 4bpp pattern packed for VDP_loadTileData, plus a
preview PNG. Colors are remapped onto the in-game PAL3 TMS ramp so the
dashboard does not steal PAL1 (objs) or flash with PAL0[1].

Writes:
  res/hud_zanac_md.png     — 48×16 indexed preview (TMS-ish RGB)
  inc/hud_logo.h
  src/data/hud_logo.c
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("title_md", ROOT / "tools" / "build_title_md.py")
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)

OUT_W, OUT_H = 48, 16
TILE_W, TILE_H = OUT_W // 8, OUT_H // 8
TILES = TILE_W * TILE_H

# Title palette families -> TMS nibble used by PAL3 / s_tms_pal.
# 0 stays transparent so WINDOW color 0 punches to the HUD black backing.
TMS_BLUE = 5
TMS_RED = 8
TMS_GREEN = 12
TMS_BLUE_DIM = 4
TMS_RED_DIM = 6
TMS_GREEN_DIM = 2

TMS_RGB = [
    (0x00, 0x00, 0x00), (0x00, 0x00, 0x00), (0x21, 0xC8, 0x42), (0x5E, 0xDC, 0x78),
    (0x54, 0x55, 0xED), (0x7D, 0x76, 0xFC), (0xD4, 0x52, 0x4D), (0x42, 0xEB, 0xF5),
    (0xFC, 0x55, 0x54), (0xFF, 0x79, 0x78), (0xD4, 0xC1, 0x54), (0xE6, 0xCE, 0x80),
    (0x21, 0xB0, 0x3B), (0xC9, 0x5B, 0xBA), (0xCC, 0xCC, 0xCC), (0xFF, 0xFF, 0xFF),
]


def classify_title(rgb: tuple[int, int, int]) -> int:
    """Map a title_md_logo pixel to TMS: 0 / blue / red / green."""
    r, g, b = rgb
    if r + g + b < 24:
        return 0
    # Title art is three inks. Pick the dominant channel.
    if b >= r and b >= g:
        return TMS_BLUE
    if r >= g:
        return TMS_RED
    return TMS_GREEN


def downsample(src: list[int], sw: int, sh: int, dw: int, dh: int) -> list[int]:
    out = [0] * (dw * dh)
    for y in range(dh):
        y0 = y * sh // dh
        y1 = max(y0 + 1, (y + 1) * sh // dh)
        for x in range(dw):
            x0 = x * sw // dw
            x1 = max(x0 + 1, (x + 1) * sw // dw)
            counts = {0: 0, TMS_BLUE: 0, TMS_RED: 0, TMS_GREEN: 0}
            n = 0
            for sy in range(y0, y1):
                base = sy * sw
                for sx in range(x0, x1):
                    counts[src[base + sx]] += 1
                    n += 1
            ink = counts[TMS_BLUE] + counts[TMS_RED] + counts[TMS_GREEN]
            if not n or ink * 2 < n:
                out[y * dw + x] = 0
                continue
            best = max((TMS_BLUE, TMS_RED, TMS_GREEN), key=counts.__getitem__)
            # Keep a dimmer nibble when the box is mostly edge coverage.
            if ink * 3 < n * 2:
                best = {TMS_BLUE: TMS_BLUE_DIM, TMS_RED: TMS_RED_DIM,
                        TMS_GREEN: TMS_GREEN_DIM}[best]
            out[y * dw + x] = best
    return out


def pack_md4(indices: list[int], w: int, h: int) -> bytes:
    tw, th = w // 8, h // 8
    out = bytearray()
    for ty in range(th):
        for tx in range(tw):
            for row in range(8):
                for pair in range(4):
                    px = (ty * 8 + row) * w + tx * 8 + pair * 2
                    out.append(((indices[px] & 0xF) << 4) | (indices[px + 1] & 0xF))
    return bytes(out)


def c_u32_array(name: str, data: bytes, per: int = 4) -> str:
    """Big-endian longs so VDP_loadTileData matches the u8 nibble stream."""
    if len(data) % 4:
        raise ValueError("tile bytes must be a multiple of 4")
    n = len(data) // 4
    lines = [
        "/* u32 so the linker cannot park this on an odd address. VDP_loadTileData",
        " * does long reads; a u8 blob took Address error (same class as s_orb_cache). */",
        "const u32 %s[%d] = {" % (name, n),
    ]
    for i in range(0, len(data), per * 4):
        words = []
        for j in range(i, min(i + per * 4, len(data)), 4):
            words.append("0x%02X%02X%02X%02X" % (data[j], data[j + 1], data[j + 2], data[j + 3]))
        lines.append("    " + ", ".join(words) + ",")
    lines.append("};")
    return "\n".join(lines)


def write_tms_png(path: Path, w: int, h: int, indices: list[int]) -> None:
    # Reuse the title writer but swap in TMS colors via a local palette dump.
    pal = list(TMS_RGB) + [(0, 0, 0)] * (256 - 16)
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw.extend(indices[y * w:(y + 1) * w])

    def chunk(tag: bytes, payload: bytes) -> bytes:
        import struct
        import zlib
        crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", crc)

    import struct
    import zlib
    flat = []
    for rgb in pal:
        flat.extend(rgb)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 3, 0, 0, 0))
    png += chunk(b"PLTE", bytes(flat[:256 * 3]))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def main() -> int:
    src_path = ROOT / "res" / "title_md_logo.png"
    if not src_path.is_file():
        print("missing %s" % src_path, file=sys.stderr)
        return 1

    sw, sh, rgb = B.read_png_rgb(src_path)
    classified = [classify_title(p) for p in rgb]
    mini = downsample(classified, sw, sh, OUT_W, OUT_H)
    tiles = pack_md4(mini, OUT_W, OUT_H)
    if len(tiles) != TILES * 32:
        print("tile pack size %d, expected %d" % (len(tiles), TILES * 32), file=sys.stderr)
        return 1

    png_path = ROOT / "res" / "hud_zanac_md.png"
    write_tms_png(png_path, OUT_W, OUT_H, mini)

    hdr = ROOT / "inc" / "hud_logo.h"
    hdr.write_text(
        """#ifndef HUD_LOGO_H
#define HUD_LOGO_H

#include "hud.h"
#include "mode.h"

/*
 * Static miniature of the title Zanac MD mark for the Original dashboard.
 * Generated by tools/build_hud_logo.py from res/title_md_logo.png.
 * 6x2 tiles, PAL3 TMS nibbles (color 0 transparent).
 *
 * Pocket: WINDOW cols 25-30, MSX rows 22-23 (screen rows 24-25) — the
 * empty interior above / on the closing hbar, under FIRE, clear of TIME.
 */
#define HUD_LOGO_TILE_W     6
#define HUD_LOGO_TILE_H     2
#define HUD_LOGO_TILES      (HUD_LOGO_TILE_W * HUD_LOGO_TILE_H)
#define HUD_LOGO_MSX_ROW    22
#define HUD_LOGO_COL        (MODE_BAR_COL + 1)
#define HUD_LOGO_VDP        (HUD_TILE_BASE + 256)

/* u32, not u8: VDP_loadTileData long-reads the source. A u8 blob can
 * start odd and the 68000 takes Address error (same class as s_orb_cache). */
extern const u32 hud_logo_tiles[HUD_LOGO_TILES * 8];

#endif
""",
        encoding="utf-8",
    )

    src = ROOT / "src" / "data" / "hud_logo.c"
    src.write_text(
        '#include "hud.h"\n#include "hud_logo.h"\n\n'
        + c_u32_array("hud_logo_tiles", tiles)
        + "\n",
        encoding="utf-8",
    )

    ink = sum(1 for v in mini if v)
    print("wrote %s (%dx%d, %d tiles, %d ink px, %d bytes)"
          % (png_path, OUT_W, OUT_H, TILES, ink, len(tiles)))
    print("wrote %s, %s" % (hdr, src))
    return 0


if __name__ == "__main__":
    sys.exit(main())
