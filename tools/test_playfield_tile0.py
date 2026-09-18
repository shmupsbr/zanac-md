#!/usr/bin/env python3
"""Do not stamp the letterbox tile across the BG_A playfield.

3d1a7b0 reverted the PR #42 fill of BG_A cols 0-23 rows 2-25 with
mode_letter_attr() (high-pri PAL0[1] letterbox). That stamp left the
whole 192 opaque black. Do not restore it and do not replace it with
another playfield-wide fill.

Do not opaque-recolor shared charset 0x20 (ROUND banner spaces).
HUD stripe stays BG_B cols 24-31. hidden_wrap is SAT Y 0 (screen 16).
Tile 0 pattern is loaded empty (not a playfield letter fill).
hud_wipe must not write charset 0 into WINDOW rows 0-1 (letterbox).

Usage (from zanac-md):
    python tools/test_playfield_tile0.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPC = ROOT / "src" / "map_script.c"
HUD = ROOT / "src" / "hud.c"

REGRESS_FILL = (
    "VDP_fillTileMapRect(BG_A, mode_letter_attr(), 0, 2, MODE_BAR_COL, 24)"
)


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


def main() -> int:
    map_c = MAPC.read_text(encoding="utf-8")
    hud = HUD.read_text(encoding="utf-8")

    if REGRESS_FILL in map_c:
        return fail(
            "bg_init must not fill BG_A playfield with mode_letter_attr "
            "(high-pri letterbox tiles the whole 192 black)"
        )
    if re.search(
        r"VDP_fillTileMapRect\(\s*BG_A\s*,\s*mode_letter_attr\(\)",
        map_c,
    ):
        return fail("do not replace the playfield fill with another letter-tile rect")

    bg = re.search(r"static void bg_init\(void\)\s*\{(.*?)^\}", map_c, re.S | re.M)
    if not bg:
        return fail("bg_init not found")
    if "VDP_fillTileMapRect" in bg.group(1):
        return fail("bg_init must not playfield-wide fill (letterbox is mode_draw_letterbox)")

    if "recolor_charset_tile_opaque_bg" in map_c:
        return fail("do not opaque-recolor shared charset 0x20")
    if "recolor_charset_tile(0x20, charset_ct + 0x20 * 8)" not in map_c:
        return fail("space 0x20 must keep ROM CT (bg nibble 0)")
    if "VDP_fillTileMapRect(BG_B, blank, HUD_COL, 0, MODE_BAR_W, 32)" not in hud:
        return fail("HUD stripe must stay BG_B cols 24-31 only")
    if "16 - off" not in map_c and "mode_playfield_top() - off" not in map_c:
        return fail("hidden_wrap_nt_at must be playfield top (screen Y 16)")
    if re.search(r"u8 py = \(u8\)\(8 - off\)", map_c):
        return fail("hidden_wrap Y=8 is the letterbox row (seam / south lens)")
    if "VDP_fillTileMapRect(WINDOW, trans, 0, 0, MODE_H32_COLS, 28)" in hud:
        return fail("do not write charset 0 into WINDOW letterbox rows 0-1")
    if "VDP_fillTileMapRect(WINDOW, trans, 0, 2, MODE_H32_COLS, 26)" not in hud:
        return fail("hud_wipe WINDOW charset 0 must start at row 2")

    mode = (ROOT / "src" / "mode.c").read_text(encoding="utf-8")
    if "VDP_loadTileData(clear0, 0, 1, CPU)" not in mode:
        return fail("tile 0 must be loaded empty so leftover cannot punch the top")

    print("ok: no BG_A playfield letter-tile fill; 0x20 CT; wrap SAT Y=16")
    return 0


if __name__ == "__main__":
    sys.exit(main())
