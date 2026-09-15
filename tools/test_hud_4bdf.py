#!/usr/bin/env python3
"""WINDOW HUD layout stays 0x4BD4 / assembled 0x4BDF. No shared 0x20 opaque.

draw_hud_labels 0x4BD4: B=0x0E rows from 0x3958.
5C28 prints after CALL until 00. Inline at 0x4BE2 assembles to
03 20 20 20 20 20 20 03 (8 tiles, cols 24-31), not 03 20 20 20 03.
hbars 0x4C29 at 0x3818/3878/38d8/3938/3af8 (rows 0/3/6/9/23 col 24).
Labels: TOP 0x3899, SCORE 0x38F9, ZANAC 0x3959, LEVEL 0x3999, ROUND 0x39F9.
Score 0x3918, TOP 0x38B8, lives 0x397A, level 0x39BB, round 0x3A1B.
FIRE 0x3A59. WPV=2 letterbox. Charset 0x20 keeps CT bg=0.

Usage (from zanac-md):
    python tools/test_hud_4bdf.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HUD = ROOT / "src" / "hud.c"
MODE = ROOT / "src" / "mode.c"
MAPC = ROOT / "src" / "map_script.c"


def jr_disp(pc: int, target: int) -> int:
    """Z80 JR displacement: offset = target - (pc + 2)."""
    return (target - (pc + 2)) & 0xFF


# zanac.asm after CALL 0x5C28 at 0x4BDF. Addresses from the listing.
INLINE_4BE2 = bytes(
    (
        0x03,  # INC BC
        0x20,
        jr_disp(0x4BE3, 0x4C05),
        0x20,
        jr_disp(0x4BE5, 0x4C07),
        0x20,
        jr_disp(0x4BE7, 0x4C09),
        0x03,  # INC BC
        0x00,  # NOP terminator
    )
)
BORDER_8 = bytes((0x03, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20, 0x03))


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


def main() -> int:
    if INLINE_4BE2 != BORDER_8 + b"\x00":
        return fail(
            "0x4BE2 JR offsets must assemble to 03 20 20 20 20 20 20 03 00 "
            f"(got {INLINE_4BE2.hex(' ')})"
        )
    if len(BORDER_8) != 8:
        return fail("0x4BDF writes 8 tiles (cols 24-31)")

    hud = HUD.read_text(encoding="utf-8")
    mode = MODE.read_text(encoding="utf-8")
    map_c = MAPC.read_text(encoding="utf-8")

    if "0x03, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20, 0x03" not in hud:
        return fail("hud_draw_border must write assembled 8-tile 0x4BDF")
    # The 5-tile misread must not be the live border (comments may mention it).
    if "hud_put_win((u16)(HUD_COL + 4), y, 0x03)" in hud:
        return fail("do not restore the 5-tile 03 20 20 20 03 border")
    if 'hud_str_win(HUD_TEXT, hud_y(4), "TOP")' not in hud:
        return fail("TOP must stay 0x3899 row 4 col 25")
    if 'hud_str_win(HUD_TEXT, hud_y(7), "SCORE")' not in hud:
        return fail("SCORE must stay 0x38F9 row 7 col 25")
    if 'hud_str_win(HUD_TEXT, hud_y(10), "ZANAC")' not in hud:
        return fail("ZANAC must stay 0x3959 row 10 col 25")
    if 'hud_str_win(HUD_TEXT, hud_y(12), "LEVEL")' not in hud:
        return fail("LEVEL must stay 0x3999 row 12 col 25")
    if 'hud_str_win(HUD_TEXT, hud_y(15), "ROUND")' not in hud:
        return fail("ROUND must stay 0x39F9 row 15 col 25")
    if "hud_score6(HUD_COL, hud_y(8), player_score())" not in hud:
        return fail("SCORE digits must stay 0x3918 row 8 col 24")
    if "hud_digit2((u16)(HUD_COL + 3), hud_y(13), player_shot_level())" not in hud:
        return fail("LEVEL digits must stay 0x39BB row 13 col 27")
    if "hud_digit3((u16)(HUD_COL + 2), hud_y(11), (u8)(lives - 1))" not in hud:
        return fail("lives must stay 0x397A DEC E10A")
    if 'hud_str_win(HUD_TEXT, hud_y(18), "FIRE ")' not in hud:
        return fail("FIRE label must stay 0x3A59")
    if "hud_put_win((u16)(HUD_TEXT + 5), hud_y(18), (u8)('0' + (fire % 10)))" not in hud:
        return fail("FIRE digit must stay 0x3A5E col 30")
    if "hud_hbar(0)" not in hud:
        return fail("0x4C29 opening hbar must stay row 0")
    if "hud_hbar(HUD_CLOSE_HBAR_ROW)" not in hud and "hud_hbar(23)" not in hud:
        return fail("closing gray hbar must sit at MSX 23 (playfield end)")
    if "HUD_CLOSE_HBAR_ROW   25" in (ROOT / "inc" / "hud.h").read_text():
        return fail("do not leave the closing hbar in the letterbox (MSX 25)")
    if "VDP_setWindowVPos(FALSE, 2)" not in mode:
        return fail("WPV must stay 2 (rows 0-1 full-width WINDOW)")
    if "recolor_charset_tile_opaque_bg" in map_c:
        return fail("do not opaque-recolor shared 0x20")

    print("ok: 0x4BDF is 8 tiles (JR 20 20 x3); labels / WPV=2; 0x20 CT bg=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
