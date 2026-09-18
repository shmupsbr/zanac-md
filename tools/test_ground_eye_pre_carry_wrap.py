#!/usr/bin/env python3
"""Ground objects / R1 lower eye: 97e3 must DMA wrap(pre-carry).

Filipe after PR #91 merge e01d4a8: ground structures look cut off
(pieces missing) and the R1 diamond lower eye is missing a tile. Both
were whole on the #90 ROM (c6ea679). Fire 7 multi-color stays fixed.

Japan v1 SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2: TMS has no
VSCROLL. 97e3 assembles one E800 row; 9a79 dumps the 24-row nametable.
MD peeks row+1 into wrap(scroll+8) so 1px VSCROLL is not stale.

#91 moved s_scroll_px to the post-carry pixel before 97e3 so
hidden_wrap == sat_to_nt(0) at the DMA. Stamps use wrap(scroll&~7)+Y/8
so leftover POST still hits wrap(pre). 97e3 DMA stays wrap(pre) RAW.
hidden_wrap uses the raw pixel. Boot E710=0x20 often has wrap(pre)==
wrap(post). 9480 ramps E710 toward SCROLL_SPEED_TGT 0x34; leftover
E711 at cruise makes wrap(post) one NT row north of wrap(pre) -- the
letterbox. 97e3 wrote the real assemble (stamps / multi-tile ground /
diamond body) there, while the live top kept the previous place-less
peek. One tile gone.

VSCROLL is still the pre-carry pixel during 97e3. Japan 8948 is Y/8 on
the 24-row nametable (no subtract). Do not move s_scroll_px until the
end of the tick (s_scroll_delta = post-pre on a carry).

Cmd 9 still must not peek (0x28 sky into wrap+8). Fire 7 tiles stay
nibble 13; s_fire7_col INC+AND 0x8F into PAL2[13] only.

Usage (from zanac-md):
    python tools/test_ground_eye_pre_carry_wrap.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "src" / "map_script.c"
ENT = ROOT / "src" / "entity.c"
MAIN = ROOT / "src" / "main.c"


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


def hidden_wrap_nt_at(scroll_px: int) -> int:
    off = (scroll_px + 16) & 0xFF
    py = (16 - off) & 0xFF
    return py >> 3


def sat_to_nt_y0(scroll_px: int) -> int:
    return hidden_wrap_nt_at(scroll_px & ~7)


def ramp_carries(frames: int = 400) -> list[tuple[int, int, int]]:
    """9480: E710 ramps 0x20->0x34 every 4 frames; E711 += E710.

    Returns (e710, pre_px, post_px) for each row carry.
    """
    e710 = 0x20
    e712 = 0x34
    e711 = 0
    e713 = 0
    row_off = 0
    out: list[tuple[int, int, int]] = []
    for _ in range(frames):
        e713 += 1
        if (e713 & 3) == 0 and e710 != e712:
            e710 = e710 + 1 if e710 < e712 else e710 - 1
        s = e711 + e710
        if s > 255:
            pre = row_off * 8 + (e711 >> 5)
            post = (row_off + 1) * 8 + ((s & 255) >> 5)
            out.append((e710, pre, post))
            row_off += 1
        e711 = s & 255
    return out


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


def skip_precompute_body(upd: str) -> str | None:
    skip = upd.split("if (!s_skip_precompute)")
    if len(skip) < 2:
        return None
    block = skip[1]
    i = block.find("{")
    if i < 0:
        return None
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
    return block[i : end + 1]


def main() -> int:
    mp = MAP.read_text(encoding="utf-8")
    ent = ENT.read_text(encoding="utf-8")
    main_c = MAIN.read_text(encoding="utf-8")

    # Boot *8+7 -> *8+8 is the same wrap slot. Cruise leftover is not.
    if hidden_wrap_nt_at(7) != hidden_wrap_nt_at(8):
        return fail("E710=0x20 *8+7 vs *8+8 must stay the same wrap slot")
    if hidden_wrap_nt_at(7) == hidden_wrap_nt_at(9):
        return fail("post-carry +2 must not share wrap(7)")

    carries = ramp_carries()
    if not carries:
        return fail("9480 ramp produced no E711 carries")
    shifted = [
        (e710, pre, post)
        for e710, pre, post in carries
        if hidden_wrap_nt_at(pre) != hidden_wrap_nt_at(post)
    ]
    if not shifted:
        return fail("9480 ramp toward 0x34 must produce wrap(pre)!=wrap(post)")
    if not any(e710 == 0x34 for e710, _, _ in shifted):
        return fail("cruise E710=0x34 leftover E711 must shift wrap(post)")
    e710, pre, post = shifted[0]
    if sat_to_nt_y0(post) != hidden_wrap_nt_at(pre):
        return fail(
            "leftover POST sat_to_nt(0) must hit wrap(pre) tile, not wrap(post) peek"
        )
    print(
        "  first shift E710 0x%02X wrap(%d)=%d != wrap(%d)=%d  sat0 %d/%d"
        % (
            e710,
            pre,
            hidden_wrap_nt_at(pre),
            post,
            hidden_wrap_nt_at(post),
            sat_to_nt_y0(pre),
            sat_to_nt_y0(post),
        )
    )
    print("  ramp carries %d shifted %d (incl. cruise 0x34)" % (len(carries), len(shifted)))

    if "SCROLL_SPEED_TGT    0x34" not in mp and "SCROLL_SPEED_TGT 0x34" not in mp:
        return fail("SCROLL_SPEED_TGT must stay 0x34 (Japan ramp target)")

    upd = fn_span(mp, "void map_script_update(void)")
    if not upd:
        return fail("map_script_update not found")
    body = skip_precompute_body(upd)
    if not body:
        return fail("carry path must still honor s_skip_precompute")
    if "scroll_precompute" not in body:
        return fail("97e3 must stay inside !s_skip_precompute")
    if "peek_next_row" not in body:
        return fail("peek must run only after a real 97e3 (not on cmd 9)")
    if "s_scroll_px =" in body:
        return fail(
            "PR #91 early scroll_px before 97e3: wrap(post) is the letterbox "
            "at cruise E710=0x34 so 97e3 parks the complete row off-screen"
        )

    # Delta must see the pre-carry pixel. Early assign makes prev_px==NEW.
    if "prev_px = s_scroll_px" not in upd:
        return fail("carry delta still needs prev_px = s_scroll_px")
    prev_at = upd.find("prev_px = s_scroll_px")
    dma_at = upd.find("scroll_precompute")
    if dma_at < 0 or prev_at < 0 or prev_at < dma_at:
        return fail("prev_px must be sampled after 97e3 (pre-carry still in s_scroll_px)")

    if "peek_next_row_at((u16)(s_ms.row + 1), (u16)(s_scroll_px + 8))" not in mp:
        return fail("boot peek must stay scroll_px+8 (NT 31)")
    if not re.search(
        r"peek_next_row_at\(map_row,\s*\(u16\)\(s_scroll_px \+ 8\)\)", mp
    ):
        return fail("in-game peek must stay +8 from the pre-carry pixel")

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
        return fail("wrap Y=8 is the letterbox row (south lens / seam)")

    sat = fn_span(mp, "static int sat_to_nt(s16 x, s16 y, u8 *col, u8 *row)")
    if not sat or "tile_wrap_nt_at(s_scroll_px)" not in sat:
        return fail("sat_to_nt Y must stay wrap(scroll&~7) + (Y/8)")
    if sat and "hidden_wrap_nt_at(s_scroll_px)" in sat:
        return fail("#95 wrap(raw)+Y/8 is peek at leftover")

    # 8c15 1x1 stays -- south repeat of 0xBF is the double stacked eye.
    fn = re.search(
        r"void map_script_base_8c15_at\(u8 col, u8 row, u8 variant, u8 phase\)\s*\{(.*?)^\}",
        mp,
        re.S | re.M,
    )
    if not fn:
        return fail("map_script_base_8c15_at not found")
    tail = fn.group(1).split("0xBF + p", 1)[-1]
    if "rows = 2" in tail or "cols = 2" in tail:
        return fail("75-78 south/east repeat is the double stacked eye")
    if "rows = 1" not in tail or "cols = 1" not in tail:
        return fail("75-78 must stay 1x1 0xBF+phase")
    if "sat_x_964c" not in mp:
        return fail("KEEP: sat_x_964c 8-bit wrap")

    # Fire 7 from #91 must stay.
    if "s_fire7_col" not in ent:
        return fail("KEEP: fire 7 72de uses s_fire7_col")
    if "AND 0x8F" not in ent and "and 0x8F" not in ent:
        return fail("KEEP: fire 7 INC+AND 0x8F")
    if "FIRE7_CRAM_NIB  13" not in ent and "FIRE7_CRAM_NIB 13" not in ent:
        return fail("KEEP: fire 7 tiles stay nibble 13")
    if re.search(r"f->sat_col = saved", ent):
        return fail("KEEP: do not restore sat_col 0x81 after fire7 bind")

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

    print("ok: 97e3 uses pre-carry wrap; peek after 97e3 only; fire7 KEEP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
