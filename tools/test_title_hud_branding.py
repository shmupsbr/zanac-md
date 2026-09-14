#!/usr/bin/env python3
"""Title logo drop, SHMUPSBR credit, and HUD mini-logo stay in-bounds.

Usage (from zanac-md):
    python tools/test_title_hud_branding.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TITLE_MD = ROOT / "inc" / "title_md.h"
TITLE_C = ROOT / "src" / "title.c"
HUD_C = ROOT / "src" / "hud.c"
HUD_LOGO_H = ROOT / "inc" / "hud_logo.h"
HUD_LOGO_C = ROOT / "src" / "data" / "hud_logo.c"
BUILD = ROOT / "tools" / "build_title_md.py"
HUD_BUILD = ROOT / "tools" / "build_hud_logo.py"

# #119 6x1 smeared MD's M into Zanac via an all-blue bbox. Do not reuse.
BROKEN_119 = (
    0x00055555, 0x00444455, 0x00000055, 0x00000555,
    0x00005555, 0x00055555, 0x00555555, 0x45555555,
    0x55555555, 0x55555555, 0x55555555, 0x55045550,
    0x54055550, 0x55555550, 0x55555554, 0x55555555,
    0x00550455, 0x50554555, 0x55555555, 0x55555055,
    0x05554055, 0x45555555, 0x55555555, 0x55555555,
    0x05555550, 0x55544400, 0x55000000, 0x55000000,
    0x55400000, 0x45555550, 0x45555540, 0x555CC550,
    0x55555555, 0x55558555, 0x44488448, 0x00688088,
    0x00888088, 0x06888688, 0x08888888, 0x88888888,
    0x55CC5555, 0x55CC5C55, 0x8CCCCCC2, 0x62CC02CC,
    0x62CC0CCC, 0x62CC2CCC, 0x62CCCCC0, 0x62CCCC00,
)


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


def consts(path: Path) -> dict:
    out = {}
    for name, expr in re.findall(r"#define\s+(\w+)\s+(.+)", path.read_text()):
        expr = expr.split("/*")[0].strip()
        try:
            out[name] = eval(expr, {}, dict(out))
        except Exception:
            out[name] = expr
    return out


def unpack_tiles(words: list[int], tw: int, th: int) -> list[int]:
    idx = [0] * (tw * 8 * th * 8)
    for ti, base in enumerate(range(0, len(words), 8)):
        ty, tx = divmod(ti, tw)
        for row in range(8):
            w32 = words[base + row]
            bs = [(w32 >> 24) & 0xFF, (w32 >> 16) & 0xFF, (w32 >> 8) & 0xFF, w32 & 0xFF]
            pix = []
            for b in bs:
                pix.append((b >> 4) & 0xF)
                pix.append(b & 0xF)
            for i, p in enumerate(pix):
                idx[(ty * 8 + row) * (tw * 8) + tx * 8 + i] = p
    return idx


def main() -> int:
    md = consts(TITLE_MD)
    if md.get("TITLE_MD_Y") != 40:
        return fail("TITLE_MD_Y must be 40 (two 8x8 rows below Y=24)")
    if md.get("TITLE_ZANAC_TILE_Y") != 5:
        return fail("TITLE_ZANAC_TILE_Y must follow TITLE_MD_Y (40>>3 == 5)")
    if md.get("TITLE_MDMARK_TILE_Y") != 10:
        return fail("TITLE_MDMARK_TILE_Y must stay mark-relative (+5 tiles)")
    if md.get("TITLE_GROOVE_ROW") != 12:
        return fail("TITLE_GROOVE_ROW must move with the wordmark (12)")
    if md.get("TITLE_ZANAC_TRAVEL") != 56:
        return fail("do not change swirl travel")
    if "LOGO_Y = 40" not in BUILD.read_text():
        return fail("tools/build_title_md.py LOGO_Y must stay 40")

    title = TITLE_C.read_text()
    if 'draw_str_pal("MD Conversion by SHMUPSBR", 3, (u16)(TITLE_NT0 + 19), PAL3)' not in title:
        return fail("conversion line must sit under COPYRIGHT at NT0+19, col 3, PAL3")
    for line in (
        'draw_str_pal("GAME DESIGNED BY COMPILE", 3, (u16)(TITLE_NT0 + 15), PAL3)',
        'draw_str_pal("PRODUCED      BY AII", 3, (u16)(TITLE_NT0 + 16), PAL3)',
        'draw_str_pal("PRESENTED     BY PONY INC.", 3, (u16)(TITLE_NT0 + 17), PAL3)',
        'draw_str_pal("COPYRIGHT @ 1986 PONY INC.", 3, (u16)(TITLE_NT0 + 18), PAL3)',
    ):
        if line not in title:
            return fail("do not rewrite MSX credit lines (%s)" % line)
    if "draw_score_top" not in title or "TITLE_NT0" not in title:
        return fail("SCORE/TOP must stay on TITLE_NT0")

    hud = HUD_C.read_text()
    if "hud_draw_logo();" not in hud:
        return fail("hud_draw_static_labels must stamp the mini logo")
    if "hud_load_logo();" not in hud:
        return fail("hud_init must load hud_logo_tiles")
    if "0x03, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20, 0x03" not in hud:
        return fail("0x4BDF border must stay 8 tiles")
    if "recolor_charset_tile_opaque_bg" in hud:
        return fail("do not opaque-recolor 0x20")
    if 'hud_str_win(HUD_TEXT, hud_y(18), "FIRE ")' not in hud:
        return fail("FIRE must stay MSX row 18")
    if "hud_y(21)" not in hud:
        return fail("TIME must stay MSX row 21")
    time_fn = hud.split("void hud_draw_time(u8 on, u8 e155)", 1)
    if len(time_fn) < 2:
        return fail("hud_draw_time missing")
    time_body = time_fn[1].split("void hud_draw_player", 1)[0]
    if "hud_draw_logo();" in time_body:
        return fail("TIME no longer overlaps the 6x1 logo — do not restamp it")
    if "hud_border_row(21)" not in time_body:
        return fail("TIME off must restore 0x4BDF on MSX row 21")
    if "hud_fill_tile(WINDOW, HUD_TEXT, row, ' ', 6)" in hud:
        return fail("do not space-fill TIME's row — that would erase the logo")

    logo_h = HUD_LOGO_H.read_text()
    # 6x2 cannot sit above FIRE. Empty pocket is MSX 17 (between ROUND and FIRE).
    if "HUD_LOGO_MSX_ROW    17" not in logo_h:
        return fail("mini logo must sit at MSX row 17 (empty pocket above FIRE)")
    if "HUD_LOGO_MSX_ROW    16" in logo_h:
        return fail("MSX 16 is the ROUND digit")
    if "HUD_LOGO_MSX_ROW    18" in logo_h:
        return fail("MSX 18 is FIRE")
    if "HUD_LOGO_MSX_ROW    20" in logo_h:
        return fail("do not leave the mini logo on MSX row 20")
    if "HUD_LOGO_MSX_ROW    21" in logo_h:
        return fail("do not leave the mini logo on MSX row 21")
    if "HUD_LOGO_MSX_ROW    22" in logo_h:
        return fail("do not leave the mini logo on MSX row 22")
    if "HUD_LOGO_MSX_ROW    17" not in HUD_BUILD.read_text():
        return fail("build_hud_logo.py must emit HUD_LOGO_MSX_ROW 17")
    if "TITLE_MD_Y" in logo_h:
        return fail("do not touch title constants from the HUD logo header")
    if "HUD_LOGO_TILE_W     6" not in logo_h or "HUD_LOGO_TILE_H     1" not in logo_h:
        return fail("mini logo must be 6x1 (HUD interior cols 25-30, one row)")
    if "HUD_TILE_BASE + 256" not in logo_h:
        return fail("logo VRAM must sit after the 256-tile charset")
    if "title_md_logo.png" not in logo_h and "title_md_logo.png" not in HUD_BUILD.read_text():
        return fail("mini logo must be derived from res/title_md_logo.png")

    tiles = HUD_LOGO_C.read_text()
    if "const u32 hud_logo_tiles" not in tiles:
        return fail("hud_logo_tiles must be u32 (u8 can start odd → Address error)")
    if "const u8 hud_logo_tiles" in tiles:
        return fail("do not revert hud_logo_tiles to u8")
    m = re.search(r"hud_logo_tiles\[(\d+)\]", tiles)
    if not m or int(m.group(1)) != 48:
        return fail("hud_logo_tiles must be 6*8 = 48 longs (192 bytes, word-aligned)")
    words = [int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{8})", tiles)]
    if len(words) != 48:
        return fail("hud_logo_tiles must list 48 u32 values")
    if tuple(words) == BROKEN_119:
        return fail("do not reuse the broken #119 6x1 tile words")
    if "extern const u32 hud_logo_tiles" not in logo_h:
        return fail("hud_logo.h must export u32 hud_logo_tiles")
    if not (ROOT / "res" / "hud_zanac_md.png").is_file():
        return fail("res/hud_zanac_md.png missing")

    pix = unpack_tiles(words, 6, 1)
    z_blue = md_red = md_green = 0
    for y in range(8):
        row = pix[y * 48:(y + 1) * 48]
        z_blue += sum(1 for v in row[:32] if v in (4, 5))
        md_red += sum(1 for v in row[32:] if v in (6, 8))
        md_green += sum(1 for v in row[32:] if v in (2, 12))
    if z_blue < 80:
        return fail("6x1 left 4 tiles must carry the Zanac word (blue ink)")
    if md_red < 8 or md_green < 8:
        return fail("6x1 right 2 tiles must carry the MD mark (red + green)")

    print("ok: title Y=40 / groove 12; MD Conversion by SHMUPSBR; 6x1 HUD logo @ MSX 17")
    return 0


if __name__ == "__main__":
    sys.exit(main())
