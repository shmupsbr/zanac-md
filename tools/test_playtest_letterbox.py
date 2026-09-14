#!/usr/bin/env python3
"""Filipe playtest vs Japan v1: wrap/letterbox, eyes, ship, expl, orb, totem.

PR #85/#86 orb/mspr/e800/X+1 claims are not sufficient. This lock is the
photo-proven set:

  A) One 0xBF+phase lens per pod (75-78 1x1). 8948 H is unsigned SUB 0x20
     (Japan 8a92). R1 left-eye open is 964C 8-bit SAT X (test_left_eye_open).
     hidden_wrap(aligned) == sat_to_nt(0). leftover wrap(raw) is peek.
  B) Ship black complement same X, Y+2 (Japan 0x7735 ADD 0xF1 vs
     0x48C0 SUB 0x11). Not X+1; not same-Y (29-bit hull eat).
  C) become_expl does not force ground=1 on 4898 type44/guns.
  D) Orb discs re-paint every place; no 4-tile 128-byte pad.
  E) 8833 has no 88ed — do not punch totem 3x2 to 0x28 (blue junk).
  F) 71f6 complement is parent X / color 0x81 (no ship X+1 / no Y+2).
  G) Wrap is SAT Y 0 (screen 16), not letterbox Y 8. Boot peek +8 = NT 31.
     HUD BG_B restore stays; no playfield letter fill; no opaque 0x20.

KEEP: type35 leftover vel; 4898 wrap; ebullet grouping; 4BDF; 60fps;
no 0xBFD6; half-greens; BFA0; gswoop 7f54; type 44 44BA.

Usage (from zanac-md):
    python tools/test_playtest_letterbox.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "src" / "map_script.c"
ENT = ROOT / "src" / "entity.c"
PLY = ROOT / "src" / "player.c"
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


def main() -> int:
    mp = MAP.read_text(encoding="utf-8")
    ent = ENT.read_text(encoding="utf-8")
    ply = PLY.read_text(encoding="utf-8")
    main_c = MAIN.read_text(encoding="utf-8")

    wrap = re.search(
        r"static u8 hidden_wrap_nt_at\(u16 scroll_px\)\s*\{(.*?)^\}",
        mp,
        re.S | re.M,
    )
    if not wrap:
        return fail("hidden_wrap_nt_at not found")
    if "16 - off" not in wrap.group(1):
        return fail("G: wrap must be playfield top (screen Y 16 / SAT Y 0)")
    if "8 - off" in wrap.group(1):
        return fail("G: wrap Y=8 is the letterbox row (hard blue/green seam)")
    for sc in (0, 8, 16, 64, 192):
        if hidden_wrap_nt_at(sc) != sat_to_nt_y0(sc):
            return fail(
                "A/G: hidden_wrap(%d)=%d != sat_to_nt(0)=%d"
                % (sc, hidden_wrap_nt_at(sc), sat_to_nt_y0(sc))
            )
    for sc in (1, 6, 7, 9):
        if sat_to_nt_y0(sc) == hidden_wrap_nt_at(sc):
            return fail("A/G: frac %d sat_to_nt(0) must not be wrap(raw) peek" % sc)
    satfn = re.search(
        r"static int sat_to_nt\(s16 x, s16 y, u8 \*col, u8 \*row\)\s*\{(.*?)^\}",
        mp,
        re.S | re.M,
    )
    if not satfn or "tile_wrap_nt_at(s_scroll_px)" not in satfn.group(1):
        return fail("A/G: sat_to_nt Y must be wrap(scroll&~7) + (Y/8)")
    if satfn and "hidden_wrap_nt_at(s_scroll_px)" in satfn.group(1):
        return fail("A/G: #95 wrap(raw)+Y/8 is peek at leftover")
    if "peek_next_row_at((u16)(s_ms.row + 1), (u16)(s_scroll_px + 8))" not in mp:
        return fail("G: boot peek must be scroll_px+8 (NT 31), not NT 0")

    if "u8 hx = (u8)((u8)sat_x - 0x20)" not in mp:
        return fail("A: 8948 H must be unsigned SUB 0x20 (Japan 8a92)")
    fn = re.search(
        r"void map_script_base_8c15_at\(u8 col, u8 row, u8 variant, u8 phase\)\s*\{(.*?)^\}",
        mp,
        re.S | re.M,
    )
    if not fn:
        return fail("A: map_script_base_8c15_at not found")
    tail = fn.group(1).split("0xBF + p", 1)[-1]
    if "rows = 2" in tail or "cols = 2" in tail:
        return fail("A: 75-78 south/east repeat is the double lens")
    if "rows = 1" not in tail or "cols = 1" not in tail:
        return fail("A: 75-78 must be 1x1 (one 0xBF+phase lens)")

    if "mode_draw_x(s_x, 0x81) + 1" in ply:
        return fail("B: do not draw ship black at white X+1")
    if "return mode_draw_x(s_x, 0x81)" not in ply:
        return fail("B: ship complement must share white draw X")
    if "mode_draw_y(s_y) + 2" not in ply:
        return fail("B: ship complement Y must be white Y+2 (Japan ADD 0xF1)")

    if "e->ground = hide" in ent:
        return fail("C: do not force become_expl ground=1 on 4898 type44/guns")
    if "if (sat_space)" not in ent or "e->ground = 0" not in ent:
        return fail("C: become_expl must clear ground on 4898 SAT-space")
    if "e->vx = 0" not in ent:
        return fail("KEEP: become_expl still zeros type-35 leftover vel")

    if "u16 out = 128" in ent:
        return fail("D: do not re-ship 4-tile pad as the orb fix")
    if "orb_paint_body_nibbles" not in ent:
        return fail("D: orb must paint every nonzero nibble")
    place = re.search(r"static void spr_place\(Slot \*s, u16 frame\)\s*\{(.*?)^\}",
                      ent, re.S | re.M)
    if not place:
        return fail("D: spr_place not found")
    if "s->kind == KIND_ORB" not in place.group(1):
        return fail("D: spr_place must invalidate disc VRAM cache")

    if "map_script_clear_totem_face" in mp or "map_script_clear_totem_face" in ent:
        return fail("E: 8833 must not punch totem face (no 88ed)")
    if "punch_cell(col, srow, 0x28)" in mp:
        return fail("E: 0x28 on the yellow totem is the blue/white junk")

    if "Do not add ship X+1" not in ent:
        return fail("F: 71f6 must stay parent X / 0x81 (no ship X+1)")
    if "mdx = dx" not in ent:
        return fail("F: flyer complement draw X shares primary SAT X")
    if "mdx = mode_draw_x(s->x, 0x81)" in ent:
        return fail("F: do not recompute complement X from 0x81")

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
    if "k_flyer_green_dim" in ent:
        return fail("KEEP: no PAL2 half-green override (it hid the 2/12 stipple bug)")
    collide = re.search(
        r"static void collide_player\(void\)\s*\{(.*?)^\}",
        ent,
        re.S | re.M,
    )
    if not collide or re.search(r"if\s*\(\s*e->kind == KIND_GROUND\s*\)", collide.group(1)):
        return fail("type 44 is 44BA; collide_player must not skip KIND_GROUND")

    print("ok: playtest A-G + KEEP (wrap=sat_to_nt(0), 1x1 eyes, ship Y+2, expl)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
