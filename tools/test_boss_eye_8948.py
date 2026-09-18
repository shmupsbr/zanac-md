#!/usr/bin/env python3
"""Boss eyes: 8948 bind at arm; 8c15 paints ONE 0xBF+phase lens per pod.

Japan v1 8a7d Y+=0x10 then 8948 uses L (pre-+0x10), H=SAT_X-0x20 (unsigned
SUB). 8c15 types 75-78 use tile 0xBF+phase -- one 8x8 lens (0xC2 = red
weak). Repeating that tile south (Japan B=2 / type 77) is a second circle
on MD. Unsigned SUB is Japan 8a92; R1 left-eye open is 964C 8-bit SAT X
(see test_left_eye_open.py).

hidden_wrap is SAT Y 0 (screen 16) so the stored cell is the body, not
one row south in the letterbox.

Usage (from zanac-md):
    python tools/test_boss_eye_8948.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
MAP = ROOT / "src" / "map_script.c"
HDR = ROOT / "inc" / "map_script.h"


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


def hidden_wrap_nt_at(scroll_px: int, y_off: int = 16) -> int:
    off = (scroll_px + y_off) & 0xFF
    py = (16 - off) & 0xFF
    return py >> 3


def sat_to_nt_y0(scroll_px: int) -> int:
    return hidden_wrap_nt_at(scroll_px & ~7)


def main() -> int:
    ent = ENT.read_text(encoding="utf-8")
    mp = MAP.read_text(encoding="utf-8")
    hdr = HDR.read_text(encoding="utf-8")

    if "map_script_8948_cell" not in hdr or "map_script_base_8c15_at" not in hdr:
        return fail("8948 cell bind + 8c15_at must be declared")
    if "map_script_8948_cell(e->x, (s16)ypre, &col, &row)" not in ent:
        return fail("arm must 8948-bind SAT X / Y-pre-+0x10")
    if "0x8000 | ((u16)col << 8) | row" not in ent:
        return fail("bind must store NT col/row with valid bit")
    if "map_script_base_8c15_at" not in ent:
        return fail("8c15 must paint the stored NT cell")
    if "base_8c15(e);" not in ent:
        return fail("arm must paint phase 0 so all four eyes exist")
    if "variant == 79" not in mp:
        return fail("type 79 still skips 8c15 (8c80)")
    if "0xBF + p" not in mp:
        return fail("types 75-78 stay tile 0xBF+phase")

    # One lens: 75-78 must not stamp a south copy of 0xBF+phase.
    fn = re.search(
        r"void map_script_base_8c15_at\(u8 col, u8 row, u8 variant, u8 phase\)\s*\{(.*?)^\}",
        mp,
        re.S | re.M,
    )
    if not fn:
        return fail("map_script_base_8c15_at not found")
    body = fn.group(1)
    if "rows = 2" in body.split("0xBF + p")[-1] if "0xBF + p" in body else True:
        # After t0=0xBF+p the 75-78 path must stay 1x1.
        tail = body.split("0xBF + p", 1)[-1]
        if "rows = 2" in tail or "cols = 2" in tail:
            return fail("75-78 must be 1x1 (south repeat is the double lens)")
        if "rows = 1" not in tail or "cols = 1" not in tail:
            return fail("75-78 must set rows=1 cols=1")

    if "u8 hx = (u8)((u8)sat_x - 0x20)" not in mp:
        return fail("8948 H must be unsigned SUB 0x20 (left pod SAT X<32)")
    if "sat_x - 0x20)" in mp and "u8 hx" not in mp:
        return fail("do not signed-subtract SAT X-0x20")

    wrap = re.search(
        r"static u8 hidden_wrap_nt_at\(u16 scroll_px\)\s*\{(.*?)^\}",
        mp,
        re.S | re.M,
    )
    if not wrap:
        return fail("hidden_wrap_nt_at not found")
    if "16 - off" not in wrap.group(1) and "mode_playfield_top() - off" not in wrap.group(1):
        return fail("hidden_wrap must be playfield top (screen Y 16 / SAT Y 0)")
    if "8 - off" in wrap.group(1):
        return fail("hidden_wrap Y=8 is the letterbox row (south lens / seam)")

    for sc in (0, 8, 16, 64, 192):
        if hidden_wrap_nt_at(sc) != sat_to_nt_y0(sc):
            return fail(
                "hidden_wrap(%d)=%d != sat_to_nt(0)=%d"
                % (sc, hidden_wrap_nt_at(sc), sat_to_nt_y0(sc))
            )
    for sc in (1, 6, 7, 9):
        if sat_to_nt_y0(sc) == hidden_wrap_nt_at(sc):
            return fail("frac %d: sat_to_nt(0) must not be wrap(raw) peek" % sc)
    satfn = re.search(
        r"static int sat_to_nt\(s16 x, s16 y, u8 \*col, u8 \*row\)\s*\{(.*?)^\}",
        mp,
        re.S | re.M,
    )
    if not satfn or "tile_wrap_nt_at(s_scroll_px)" not in satfn.group(1):
        return fail("sat_to_nt Y must be wrap(scroll&~7) + (Y/8)")
    if satfn and "hidden_wrap_nt_at(s_scroll_px)" in satfn.group(1):
        return fail("#95 wrap(raw)+Y/8 is peek at leftover")

    if hidden_wrap_nt_at(0) != 0:
        return fail("scroll 0 playfield top is NT 0, got %d" % hidden_wrap_nt_at(0))
    if hidden_wrap_nt_at(8) != 31:
        return fail("scroll 8 playfield top is NT 31, got %d" % hidden_wrap_nt_at(8))

    print("ok: 8948 unsigned X; 8c15 1x1 0xBF+phase; wrap=sat_to_nt(0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
