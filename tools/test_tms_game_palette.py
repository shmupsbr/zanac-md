#!/usr/bin/env python3
"""In-game TMS→MD palette is WebMSX / V9938-default; TMS 2 ≠ 12.

Playfield (PAL3 s_tms_pal) and sprite remap (PAL2 k_tms_vdp) share the
V9938 3-bit triples scaled n*32. Lord-Nightmare 0x21C842 / 0x21B03B
collapsed through RGB24_TO_VDPCOLOR and flattened the 2/12 ground stipple.

Title k_tms / title_md_palette are not this table.

Usage (from zanac-md):
    python tools/test_tms_game_palette.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HDR = ROOT / "inc" / "map_script.h"
MAP = ROOT / "src" / "map_script.c"
ENT = ROOT / "src" / "entity.c"
TITLE = ROOT / "src" / "title.c"
TITLE_PAL = ROOT / "src" / "data" / "title_md_palette.c"

# V9938 default triples. RGB24 = n*32 so +0x10 rounding keeps the triple.
V9938 = (
    (0, 0, 0),
    (0, 0, 0),
    (1, 6, 1),
    (3, 7, 3),
    (1, 1, 7),
    (2, 3, 7),
    (5, 1, 1),
    (2, 6, 7),
    (7, 1, 1),
    (7, 3, 3),
    (6, 6, 1),
    (6, 6, 4),
    (1, 4, 1),
    (6, 2, 5),
    (5, 5, 5),
    (7, 7, 7),
)


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


def rgb24_to_vdp(rgb: int) -> int:
    r = min(255, ((rgb >> 16) & 0xFF) + 0x10) >> 5
    g = min(255, ((rgb >> 8) & 0xFF) + 0x10) >> 5
    b = min(255, (rgb & 0xFF) + 0x10) >> 5
    return ((b & 7) << 9) | ((g & 7) << 5) | ((r & 7) << 1)


def cram_rgb(word: int) -> tuple[int, int, int]:
    return ((word >> 1) & 7, (word >> 5) & 7, (word >> 9) & 7)


def parse_rgb_defines(hdr: str) -> list[int]:
    out = []
    for i in range(16):
        m = re.search(rf"#define TMS_GAME_RGB_{i}\s+0x([0-9A-Fa-f]+)", hdr)
        if not m:
            raise ValueError("TMS_GAME_RGB_%d missing" % i)
        out.append(int(m.group(1), 16))
    return out


def table_entries(src: str, name: str) -> list[str]:
    m = re.search(rf"static const u16 {name}\[16\] = \{{([^}}]+)\}}", src)
    if not m:
        raise ValueError("%s not found" % name)
    return [ln.strip().rstrip(",") for ln in m.group(1).splitlines() if ln.strip()]


def main() -> int:
    hdr = HDR.read_text(encoding="utf-8")
    mp = MAP.read_text(encoding="utf-8")
    ent = ENT.read_text(encoding="utf-8")
    title = TITLE.read_text(encoding="utf-8")
    title_pal = TITLE_PAL.read_text(encoding="utf-8")

    try:
        rgb = parse_rgb_defines(hdr)
    except ValueError as e:
        return fail(str(e))

    cram = [rgb24_to_vdp(v) for v in rgb]
    print("  in-game RGB24 / CRAM (V9938 n*32):")
    for i, (rgb24, word) in enumerate(zip(rgb, cram)):
        r, g, b = cram_rgb(word)
        print("    %2d  #%06X  CRAM 0x%04X  (%d,%d,%d)" % (i, rgb24, word, r, g, b))

    if cram[2] == cram[12]:
        return fail("TMS 2 and 12 must differ after MD quantization (got 0x%04X)" % cram[2])
    if cram_rgb(cram[2]) != (1, 6, 1):
        return fail("TMS 2 must be V9938 (1,6,1), got %s" % (cram_rgb(cram[2]),))
    if cram_rgb(cram[12]) != (1, 4, 1):
        return fail("TMS 12 must be V9938 (1,4,1), got %s" % (cram_rgb(cram[12]),))
    print("  TMS 2 CRAM 0x%04X ≠ TMS 12 CRAM 0x%04X" % (cram[2], cram[12]))

    for i, trip in enumerate(V9938):
        if cram_rgb(cram[i]) != trip:
            return fail("index %d must be V9938 %s, got %s" % (i, trip, cram_rgb(cram[i])))
        expect = (trip[0] * 32) << 16 | (trip[1] * 32) << 8 | (trip[2] * 32)
        if rgb[i] != expect:
            return fail("TMS_GAME_RGB_%d must be 0x%06X (n*32), got 0x%06X" % (i, expect, rgb[i]))
    print("  all 16 match V9938 default triples")

    try:
        k_tms = table_entries(ent, "k_tms_vdp")
        s_tms = table_entries(mp, "s_tms_pal")
    except ValueError as e:
        return fail(str(e))
    if len(k_tms) != 16 or len(s_tms) != 16:
        return fail("k_tms_vdp / s_tms_pal must have 16 entries")

    for i in range(16):
        want = "RGB24_TO_VDPCOLOR(TMS_GAME_RGB_%d)" % i
        if k_tms[i] != want:
            return fail("k_tms_vdp[%d] must be %s, got %r" % (i, want, k_tms[i]))
        if i == 8:
            if s_tms[i] != "TMS_DARK_RED_PINK":
                return fail("s_tms_pal[8] must be TMS_DARK_RED_PINK, got %r" % s_tms[i])
        elif s_tms[i] != want:
            return fail("s_tms_pal[%d] must be %s, got %r" % (i, want, s_tms[i]))
    print("  k_tms_vdp full V9938; s_tms_pal[8] darkened")

    pink = re.search(r"#define TMS_DARK_RED_PINK\s+0x([0-9A-Fa-f]+)", hdr)
    if not pink:
        return fail("TMS_DARK_RED_PINK missing")
    dark = int(pink.group(1), 16)
    faded = rgb24_to_vdp(
        ((rgb[8] >> 16) * 4 // 5) << 16
        | (((rgb[8] >> 8) & 0xFF) * 4 // 5) << 8
        | ((rgb[8] & 0xFF) * 4 // 5)
    )
    if dark != faded:
        return fail(
            "TMS_DARK_RED_PINK 0x%04X must be TMS 8 * 0.8 → 0x%04X" % (dark, faded)
        )
    if dark == cram[8]:
        return fail("PAL3[8] must be darker than k_tms_vdp[8] 0x%04X" % cram[8])
    if dark == cram[9]:
        return fail("PAL3[8] must differ from BONUS PAL3[9]")
    print("  PAL3[8] 0x%04X = TMS 8 * 0.8; PAL2[8] 0x%04X" % (dark, cram[8]))

    if "PAL_setPalette(PAL2, k_tms_vdp, CPU)" not in ent:
        return fail("entity_init must load k_tms_vdp onto PAL2")
    if "PAL_setPalette(PAL3, s_tms_pal, CPU)" not in mp:
        return fail("map_script must still load s_tms_pal onto PAL3")

    # Title / opening branding stays on the old tables.
    if "RGB24_TO_VDPCOLOR(0x21C842)" not in title:
        return fail("title k_tms must keep Lord-Nightmare TMS 2")
    if "TMS_DARK_GREEN" not in title:
        return fail("title k_tms[12] must stay TMS_DARK_GREEN")
    if "TMS_GAME_RGB_" in title:
        return fail("do not retarget title k_tms to the in-game table")
    if "RGB24_TO_VDPCOLOR(0x6C90D8)" not in title_pal:
        return fail("do not change title_md_palette ZANAC blue")
    if "RGB24_TO_VDPCOLOR(0xB40000)" not in title_pal:
        return fail("do not change title_md_palette M red")
    print("  title k_tms / title_md_palette KEEP")

    if "WebMSX" not in hdr or "title branding" not in hdr.lower():
        return fail("header must say this is WebMSX/original-MSX, not title branding")

    print("ok: in-game TMS 2 ≠ 12; title palette untouched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
