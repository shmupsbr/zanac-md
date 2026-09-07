#!/usr/bin/env python3
"""Peek assemble must not place_tile_group-spawn.

97e3 scroll_precompute clears s_assemble_peek before assemble_row so
a leaked wrap-preview flag cannot skip entity_place_ground.

peek_next_row_at snapshots cols/streams, assembles row+1 for wrap DMA,
then restores. stream_stamp_buf can expire a delay during that assemble
and call 95ed. Entities are not in the snapshot -- a delay that hits 0
on peek would spawn, then the next real 97e3 would spawn again
(stacked 964C bases).

hidden_wrap_nt_at is SAT Y 0 / screen Y 16 (playfield top), matching
sat_to_nt(0). Boot peek +8 = NT 31; in-game peek stays +8.
964C / proto_box +0x20 / k_base 8ac7 stay.

Usage (from zanac-md):
    python tools/test_peek_no_place.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPC = ROOT / "src" / "map_script.c"
ENT = ROOT / "src" / "entity.c"


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


def hidden_wrap_nt_at(scroll_px: int, y_off: int = 16) -> int:
    off = (scroll_px + y_off) & 0xFF
    py = (16 - off) & 0xFF
    return py >> 3


def main() -> int:
    map_c = MAPC.read_text(encoding="utf-8")
    ent = ENT.read_text(encoding="utf-8")

    peek = re.search(
        r"static void peek_assemble_row\(u16 map_row\)\s*\{(.*?)^\}",
        map_c,
        re.S | re.M,
    )
    if not peek:
        return fail("peek_assemble_row not found")
    body = peek.group(1)
    if "s_assemble_peek = 1" not in body:
        return fail("peek must set s_assemble_peek around assemble_row")
    if "s_assemble_peek = 0" not in body:
        return fail("peek must clear s_assemble_peek after assemble_row")
    if body.find("s_assemble_peek = 1") > body.find("s_assemble_peek = 0"):
        return fail("peek must clear s_assemble_peek after setting it")
    if "idol_snap" not in body or "s_idol_cur = idol_snap" not in body:
        return fail("peek must restore s_idol_cur (IX+0x1D)")
    if "memcpy(s_stream, s_stream_snap" not in body:
        return fail("peek must still restore stream cursors")

    pre = re.search(
        r"static void scroll_precompute\(u16 map_row\)\s*\{(.*?)^\}",
        map_c,
        re.S | re.M,
    )
    if not pre:
        return fail("scroll_precompute not found")
    if "s_assemble_peek = 0" not in pre.group(1):
        return fail("97e3 must clear s_assemble_peek before assemble_row")
    if pre.group(1).find("s_assemble_peek = 0") > pre.group(1).find("assemble_row"):
        return fail("97e3 must clear s_assemble_peek before assemble_row")
    if "entity_place_ground" not in map_c:
        return fail("real assemble must still call entity_place_ground")
    if "!s_assemble_peek && entity_check_col_clear()" not in map_c:
        return fail("peek must skip check_col_clear and place; real 97e3 must not")

    # hidden_wrap_nt_at is SAT Y 0 / screen Y 16 (playfield top)
    wrap = re.search(
        r"static u8 hidden_wrap_nt_at\(u16 scroll_px\)\s*\{(.*?)^\}",
        map_c,
        re.S | re.M,
    )
    if not wrap:
        return fail("hidden_wrap_nt_at not found")
    if "16 - off" not in wrap.group(1):
        return fail("hidden_wrap_nt_at must be playfield top (screen Y 16)")
    if "8 - off" in wrap.group(1):
        return fail("hidden_wrap Y=8 is the letterbox row (seam / south lens)")

    if "peek_next_row_at((u16)(s_ms.row + 1), (u16)(s_scroll_px + 8))" not in map_c:
        return fail("boot peek must be hidden_wrap_nt_at(scroll_px+8) = NT 31")
    if not re.search(
        r"peek_next_row_at\(map_row,\s*\(u16\)\(s_scroll_px \+ 8\)\)", map_c
    ):
        return fail("in-game peek must stay +8")

    if hidden_wrap_nt_at(0) != 0:
        return fail("playfield top at scroll_px=0 must be NT 0")
    if hidden_wrap_nt_at(8) != 31:
        return fail("+8 playfield top must be NT 31")

    if "sat_x_964c(st->ybase, r[2])" not in map_c:
        return fail("place_tile_group SAT X must be sat_x_964c (8-bit 964C)")
    if "x + 0x20" not in ent:
        return fail("proto_box children must stay +0x20 apart (77a1)")
    if "e->y = (s16)(u8)((u8)e->y + k_base[idx][2])" not in ent:
        return fail("k_base yo applies at arm (8ac7), not at place")

    print("ok: peek no-place; 97e3 clears peek; wrap SAT Y=16 / 964C / 8ac7 stay")
    return 0


if __name__ == "__main__":
    sys.exit(main())
