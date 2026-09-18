#!/usr/bin/env python3
"""Hard blue cuts in green scenery: wrap/peek/97e3 vs Japan v1.

Filipe after #87 wrap=sat_to_nt(0): still full-width / long horizontal
blue seams in green. Japan TMS has no VSCROLL and no peek -- 97e3
assembles one row, 9a79 rewrites the 24-row nametable. MD peek is a
port invention so 1px VSCROLL does not reveal a stale NT slot.

Bug on main (c6ea679): peek_next_row ran even when cmd 9 skipped 97e3.
That assemble used the old columns on the jumped-to map_row (often a
full 0x28 sky line) and DMA'd it into wrap(scroll+8) -- the slot the
next 1-8px of VSCROLL reveals. Hard straight blue cut through live
green.

Do not set s_scroll_px to the post-carry pixel before 97e3. leftover
E711 at cruise E710=0x34 (9480 ramp) moves wrap/peek one NT row into
the letterbox so the live top keeps the place-less peek (cut-off
ground / R1 lower eye). Japan 9a79 dumps 24 rows; MD 97e3 must DMA
wrap(pre-carry) while VSCROLL is still that pixel. Peek stays +8 from
that pre-carry value.

sat_to_nt Y is wrap(scroll&~7)+Y/8 (the 8px 97e3 tile), not wrap(raw).
#95 wrap(raw)+Y/8 is the peek sliver at leftover frac 1-7 (seam + lost
firebox digits). 97e3 DMA stays wrap(pre) RAW.

KEEP: HUD BG_B cols 24-31 restore. No playfield-wide letter fill.
No opaque-recolor 0x20. wrap SAT Y 0 (screen 16). Boot peek +8 = NT 31.

Usage (from zanac-md):
    python tools/test_blue_cuts_wrap_peek.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "src" / "map_script.c"
MAIN = ROOT / "src" / "main.c"
ENT = ROOT / "src" / "entity.c"


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


def hidden_wrap_nt_at(scroll_px: int) -> int:
    off = (scroll_px + 16) & 0xFF
    py = (16 - off) & 0xFF
    return py >> 3


def sat_to_nt_y0(scroll_px: int) -> int:
    """Japan 8948: screen row 0 is the 8px tile, wrap(scroll&~7)."""
    return hidden_wrap_nt_at(scroll_px & ~7)


def old_sat_to_nt_y0(scroll_px: int) -> int:
    ntpix = (0 - (scroll_px & ~7)) & 0xFFFF
    return (ntpix >> 3) & 31


def playfield_rows(scroll_px: int) -> set[int]:
    """24 NT rows that occupy screen Y 16-207 (SAT 0-191).

    VSCROLL = -(scroll+16) so nametable Y increases down the 192.
    Top is hidden_wrap; next 23 rows are +1..+23.
    """
    top = hidden_wrap_nt_at(scroll_px)
    return {(top + i) & 31 for i in range(24)}


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


def main() -> int:
    mp = MAP.read_text(encoding="utf-8")
    main_c = MAIN.read_text(encoding="utf-8")
    ent = ENT.read_text(encoding="utf-8")

    wrap = re.search(
        r"static u8 hidden_wrap_nt_at\(u16 scroll_px\)\s*\{(.*?)^\}",
        mp,
        re.S | re.M,
    )
    if not wrap:
        return fail("hidden_wrap_nt_at not found")
    if "16 - off" not in wrap.group(1) and "mode_playfield_top() - off" not in wrap.group(1):
        return fail("wrap must stay SAT Y 0 / screen 16")
    if "8 - off" in wrap.group(1):
        return fail("wrap Y=8 is the letterbox row (traveling peek seam)")

    for sc in (0, 8, 16, 64, 192, 248, 256):
        if hidden_wrap_nt_at(sc) != sat_to_nt_y0(sc):
            return fail(
                "hidden_wrap(%d)=%d != sat_to_nt(0)=%d"
                % (sc, hidden_wrap_nt_at(sc), sat_to_nt_y0(sc))
            )
    # Frac 1-7: wrap(raw) is peek; sat_to_nt(0) is the 8px tile.
    for sc in (1, 6, 7, 9):
        if hidden_wrap_nt_at(sc) == sat_to_nt_y0(sc):
            return fail("frac %d: wrap(raw) peek must disagree with tile wrap" % sc)
        if sat_to_nt_y0(sc) != hidden_wrap_nt_at(sc & ~7):
            return fail("frac %d: sat_to_nt(0) must be wrap(scroll&~7)" % sc)
        if old_sat_to_nt_y0(sc) != sat_to_nt_y0(sc):
            return fail("frac %d: Y=0 unsigned (Y-(scroll&~7))>>3 is the tile" % sc)

    sat = fn_span(mp, "static int sat_to_nt(s16 x, s16 y, u8 *col, u8 *row)")
    if not sat:
        return fail("sat_to_nt not found")
    if "tile_wrap_nt_at(s_scroll_px)" not in sat:
        return fail("sat_to_nt Y must be wrap(scroll&~7) + (Y/8)")
    if "hidden_wrap_nt_at(s_scroll_px)" in sat:
        return fail("#95 wrap(raw)+Y/8 is peek at leftover")

    # Peek of the next 8px must not land in the live 24-row window.
    for sc in (0, 8, 16, 64, 192, 248):
        peek_row = hidden_wrap_nt_at(sc + 8)
        live = playfield_rows(sc)
        if peek_row in live:
            return fail(
                "peek wrap(%d+8)=NT %d is inside the live 24 at scroll %d"
                % (sc, peek_row, sc)
            )
        print("  peek NT", peek_row, "outside playfield at scroll", sc)

    # Carry from *8+7 -> *8+8: 97e3 old wrap == new wrap (same slot).
    for base in (0, 8, 16, 64, 192):
        old, new = base + 7, base + 8
        if hidden_wrap_nt_at(old) != hidden_wrap_nt_at(new):
            return fail(
                "97e3 at frac7 wrap %d != post-carry wrap %d"
                % (hidden_wrap_nt_at(old), hidden_wrap_nt_at(new))
            )

    upd = fn_span(mp, "void map_script_update(void)")
    if not upd:
        return fail("map_script_update not found")
    # peek must sit inside the !s_skip_precompute block with 97e3.
    skip = upd.split("if (!s_skip_precompute)")
    if len(skip) < 2:
        return fail("carry path must still honor s_skip_precompute")
    block = skip[1]
    # First brace-balanced body after the if.
    i = block.find("{")
    if i < 0:
        return fail("s_skip_precompute body missing")
    depth = 0
    end = i
    for j, ch in enumerate(block[i:], i):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = j
                break
    body = block[i : end + 1]
    if "scroll_precompute" not in body:
        return fail("97e3 must stay inside !s_skip_precompute")
    if "peek_next_row" not in body:
        return fail("peek must run only after a real 97e3 (not on cmd 9)")
    # The leftover after that block must not peek again.
    after = block[end + 1 : end + 200]
    if "peek_next_row" in after:
        return fail("cmd 9 skip must not peek a 0x28/foreign row into wrap")
    if "s_scroll_px =" in body:
        return fail(
            "do not set scroll_px before 97e3 — post-carry wrap is one "
            "NT row off at cruise E710=0x34 (cut-off ground / lower eye)"
        )

    if "peek_next_row_at((u16)(s_ms.row + 1), (u16)(s_scroll_px + 8))" not in mp:
        return fail("boot peek must stay scroll_px+8 (NT 31)")
    if not re.search(
        r"peek_next_row_at\(map_row,\s*\(u16\)\(s_scroll_px \+ 8\)\)", mp
    ):
        return fail("in-game peek must stay +8")

    if "VDP_setTileMapDataRow(BG_B, dst + MODE_BAR_COL, nt_y" not in mp:
        return fail("KEEP: dma_nt_row must restore HUD BG_B cols 24-31")
    if "recolor_charset_tile_opaque_bg" in mp:
        return fail("KEEP: no opaque 0x20")
    if "VDP_fillTileMapRect(BG_A, mode_letter_attr(), 0, 2, MODE_BAR_COL, 24)" in mp:
        return fail("KEEP: no playfield letter fill")
    if main_c.count("SYS_doVBlankProcess()") != 1:
        return fail("KEEP: 60fps — one VBlank per tick")
    if "0xBFD6" in ent or "0xbfd6" in ent:
        return fail("KEEP: no CALL 0xBFD6")

    print("ok: peek only after 97e3; pre-carry wrap at DMA; HUD restore")
    return 0


if __name__ == "__main__":
    sys.exit(main())
