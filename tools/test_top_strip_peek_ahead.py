#!/usr/bin/env python3
"""Top ~8px duplicate strip: leftover-4 peek must be two stream steps.

Filipe after #119/#120: when ground objects / bosses enter, the first
playfield lines show an ~8px duplicated / garbage band.

Japan TMS has no VSCROLL and no peek. MD leftover E711>>5 1-7 reveals
the peek sliver at the playfield top (wrap(raw)), while 97e3 DMA sits
on wrap(pre) == tile_wrap(POST) — the rest of that 8px.

leftover 4 pre-assembles so the carry tick is 97e3 + DMA only. It
labeled the cache as row+2 (peek after the next INC) but ran ONE
assemble_row. After the last real 97e3 of R the stream is ready for
R+1, so that one step is the incoming 97e3 row — the same tiles
commit_wrap then writes to wrap(pre). Cache-hit peek DMA reprints
them into the sliver. At leftover 1-7 that is a duplicated ~8px
band of the entering ground / boss row.

Fix: leftover 4 steps once (discard = next 97e3) then once more
(keep = real peek). Post-97e3 peek_assemble_row stays one step.
KEEP: 97e3 wrap(pre) RAW; peek after real 97e3; tile_wrap stamps;
no letter fill; no opaque 0x20; 9a79 24-col; sat_x_964c; 40DA/4177.

Usage (from zanac-md):
    python tools/test_top_strip_peek_ahead.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "src" / "map_script.c"
GAME = ROOT / "src" / "game.c"
ENT = ROOT / "src" / "entity.c"
TITLE = ROOT / "inc" / "title_md.h"


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


def fn_span(src: str, sig: str) -> str | None:
    m = re.search(rf"{re.escape(sig)}\s*\{{", src)
    if not m:
        return None
    i = m.end() - 1
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i : j + 1]
    return None


def hidden_wrap_nt_at(scroll_px: int) -> int:
    off = (scroll_px + 16) & 0xFF
    py = (16 - off) & 0xFF
    return py >> 3


def tile_wrap_nt_at(scroll_px: int) -> int:
    return hidden_wrap_nt_at(scroll_px & ~7)


def toy_stream_rows(steps: int, head: int) -> list[int]:
    """Each assemble consumes one stamp run. head is the next 97e3 row id."""
    return [head + i for i in range(steps)]


def main() -> int:
    mp = MAP.read_text(encoding="utf-8")
    game = GAME.read_text(encoding="utf-8")
    ent = ENT.read_text(encoding="utf-8")
    title = TITLE.read_text(encoding="utf-8")

    # Prove the hole: one step from current stream == next 97e3, not +2.
    one = toy_stream_rows(1, head=100)
    two = toy_stream_rows(2, head=100)
    if one[-1] == 100 and two[-1] == 101:
        print("  hole: 1 step → row 100 (next 97e3); 2 steps → row 101 (peek)")
    else:
        return fail("toy stream model must distinguish 1-step vs 2-step")
    if one[-1] == two[-1]:
        return fail("one-step leftover-4 cache would equal two-step peek")

    # After leftover-1 POST, sliver is wrap(raw), 8px tile is tile_wrap.
    # Same tiles in both NT slots is the visible ~8px duplicate.
    post = 9
    sliver = hidden_wrap_nt_at(post)
    tile = tile_wrap_nt_at(post)
    if sliver == tile:
        return fail("leftover POST sliver must not be the 8px 97e3 tile")
    print("  leftover POST %d: sliver NT %d != tile NT %d" % (post, sliver, tile))

    wrap_pre = hidden_wrap_nt_at(6)
    if wrap_pre != tile:
        return fail("97e3 wrap(pre leftover 6) must still be tile_wrap(POST)")

    two_fn = fn_span(mp, "static void peek_assemble_two_ahead(void)")
    if not two_fn:
        return fail("leftover 4 must use peek_assemble_two_ahead (two stream steps)")
    if two_fn.count("assemble_row") < 2:
        return fail("two_ahead must assemble_row twice (discard R+1, keep R+2)")
    if "assemble_row((u16)(s_ms.row + 1))" not in two_fn:
        return fail("first leftover-4 step is R+1 (the next 97e3 row, discarded)")
    if "assemble_row((u16)(s_ms.row + 2))" not in two_fn:
        return fail("second leftover-4 step is R+2 (the real peek)")
    if two_fn.find("assemble_row((u16)(s_ms.row + 1))") > two_fn.find(
        "assemble_row((u16)(s_ms.row + 2))"
    ):
        return fail("R+1 discard must run before R+2 keep")
    if "s_assemble_peek = 1" not in two_fn or "s_assemble_peek = 0" not in two_fn:
        return fail("two_ahead must stay peek (no place_tile_group spawn)")
    if "s_idol_cur = idol_snap" not in two_fn:
        return fail("two_ahead must restore s_idol_cur")
    if "memcpy(s_stream, s_stream_snap" not in two_fn:
        return fail("two_ahead must restore stream cursors")
    if "s_peek_maprow = (u16)(s_ms.row + 2)" not in two_fn:
        return fail("cache key must stay row+2 (peek after the next INC)")

    one_fn = fn_span(mp, "static void peek_assemble_row(u16 map_row)")
    if not one_fn:
        return fail("post-97e3 peek_assemble_row (one step) must stay")
    if one_fn.count("assemble_row") != 1:
        return fail("post-97e3 peek is one assemble (stream already past 97e3)")

    upd = fn_span(mp, "void map_script_update(void)")
    if not upd:
        return fail("map_script_update not found")
    if "peek_assemble_two_ahead();" not in upd:
        return fail("leftover 4 must call peek_assemble_two_ahead")
    if "peek_assemble_row((u16)(s_ms.row + 2))" in upd:
        return fail("do not cache a one-step assemble as row+2 (duplicate strip)")
    if "(s_e711 >> 5) == 4" not in upd:
        return fail("KEEP: pre-assemble on leftover 4, not on carry")

    skip = upd.split("if (!s_skip_precompute)")
    if len(skip) < 2:
        return fail("carry path must still honor s_skip_precompute")
    body = skip[1]
    i = body.find("{")
    depth = 0
    end = i
    for j, ch in enumerate(body[i:], i):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = j
                break
    carry = body[i : end + 1]
    if "scroll_precompute" not in carry or "peek_next_row" not in carry:
        return fail("KEEP: peek only after a real 97e3")
    if "s_scroll_px =" in carry:
        return fail("KEEP: do not set scroll_px before 97e3")

    pre = fn_span(mp, "static void scroll_precompute(u16 map_row)")
    if not pre or "hidden_wrap_nt_at(s_scroll_px)" not in pre:
        return fail("KEEP: 97e3 DMA wrap(pre) RAW")
    if pre and "tile_wrap_nt_at" in pre:
        return fail("KEEP: 97e3 must not DMA tile_wrap")

    sat = fn_span(mp, "static int sat_to_nt(s16 x, s16 y, u8 *col, u8 *row)")
    if not sat or "tile_wrap_nt_at(s_scroll_px)" not in sat:
        return fail("KEEP: stamps use tile_wrap, not wrap(raw) peek")

    if "sat_x_964c" not in mp:
        return fail("KEEP: sat_x_964c")
    if "recolor_charset_tile_opaque_bg" in mp:
        return fail("KEEP: no opaque 0x20")
    if "VDP_fillTileMapRect(BG_A, mode_letter_attr(), 0, 2, MODE_BAR_COL, 24)" in mp:
        return fail("KEEP: no playfield letter fill")
    if "0, PF_COLS" not in (fn_span(mp, "static void dma_nt_row(u8 nt_y, const u8 *src, TransferMethod tm)") or ""):
        return fail("KEEP: 9a79 24-col")
    if "map_script_commit_wrap" not in game:
        return fail("KEEP: commit_wrap after entities")
    if "873e LDIRVM to SGT 0x1800" not in mp and "SGT 0x1800" not in mp:
        return fail("KEEP: type62 SGT, not nametable")
    if "#define TITLE_MD_Y          40" not in title:
        return fail("KEEP: TITLE_MD_Y=40")
    if "0xBFD6" in ent or "0xbfd6" in ent:
        return fail("KEEP: no CALL 0xBFD6")

    print("ok: leftover-4 is two stream steps; peek sliver is not the 97e3 row")
    return 0


if __name__ == "__main__":
    sys.exit(main())
