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
    if len(time_fn) < 2 or "hud_draw_logo();" not in time_fn[1].split("void hud_draw_player", 1)[0]:
        return fail("TIME off must restamp the mini logo (row 21 is the ZANAC band)")
    if "hud_fill_tile(WINDOW, HUD_TEXT, row, ' ', 6)" in hud:
        return fail("do not space-fill TIME's row — that would erase the logo")

    logo_h = HUD_LOGO_H.read_text()
    if "HUD_LOGO_MSX_ROW    21" not in logo_h:
        return fail("mini logo must sit at MSX row 21 (one MD-band / 8px up from 22)")
    if "HUD_LOGO_MSX_ROW    22" in logo_h:
        return fail("do not leave the mini logo on MSX row 22")
    if "HUD_LOGO_MSX_ROW    21" not in HUD_BUILD.read_text():
        return fail("build_hud_logo.py must emit HUD_LOGO_MSX_ROW 21")
    if "HUD_LOGO_TILE_W     6" not in logo_h or "HUD_LOGO_TILE_H     2" not in logo_h:
        return fail("mini logo must stay 6x2 (HUD interior cols 25-30)")
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
    if not m or int(m.group(1)) != 96:
        return fail("hud_logo_tiles must be 12*8 = 96 longs (384 bytes, word-aligned)")
    words = [int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{8})", tiles)]
    if len(words) != 96:
        return fail("hud_logo_tiles must list 96 u32 values")
    if "extern const u32 hud_logo_tiles" not in logo_h:
        return fail("hud_logo.h must export u32 hud_logo_tiles")
    if not (ROOT / "res" / "hud_zanac_md.png").is_file():
        return fail("res/hud_zanac_md.png missing")

    print("ok: title Y=40 / groove 12; MD Conversion by SHMUPSBR; 6x2 HUD logo @ MSX 21")
    return 0


if __name__ == "__main__":
    sys.exit(main())
