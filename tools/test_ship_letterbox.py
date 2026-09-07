#!/usr/bin/env python3
"""Ship stored Y clamp stays 0x1E..0xB8 (Japan 0x7640).

MD skips 48C0 SUB 0x11, so stored 0xB8 draws at 200-215 through the
bottom letterbox (208). Draw-only: sit the hull on the 192 bar. Do
not invent a stored 0xB0/0xA7 wall. Complement stays white Y+2 (7735).
Restamp letterbox after bg_init.

Usage (from zanac-md):
    python tools/test_ship_letterbox.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLY = ROOT / "src" / "player.c"
MAPC = ROOT / "src" / "map_script.c"
MODE = ROOT / "src" / "mode.c"


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


def main() -> int:
    ply = PLY.read_text(encoding="utf-8")
    map_c = MAPC.read_text(encoding="utf-8")
    mode = MODE.read_text(encoding="utf-8")

    if "max_y = 0xB8" not in ply:
        return fail("Y clamp must stay 0xB8 (0x7640)")
    if "min_y = 0x1E" not in ply:
        return fail("Y clamp must stay 0x1E (0x7636)")
    if "max_y = 0xB0" in ply or "max_y = 0xA7" in ply:
        return fail("do not invent a stored mid-playfield Y wall")
    if "dy = (s16)(y1 - SHIP_H)" not in ply:
        return fail("draw must sit the hull on the bottom letterbox (192)")
    if "cdy = (s16)(dy + 2)" not in ply:
        return fail("KEEP: complement is drawn white Y+2 (7735) after clamp")
    if "VDP_fillTileMapRect(BG_A, attr, 0, 26, MODE_H32_COLS, 2)" not in mode:
        return fail("bottom letterbox must be full-width high-pri BG_A")
    if "mode_draw_letterbox();" not in map_c:
        return fail("bg_init must restamp letterbox after the plane fill")

    print("ok: ship SAT 0xB8; draw stops at letterbox; Y+2 KEEP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
