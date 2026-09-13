#!/usr/bin/env python3
"""Filipe playtest wave after PR #94: boxes, mask, seam, digits, 60fps, GO.

Japan v1 SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2.

1) White boxes: types 4/5/6 via proto_box 68. Do not invent extra spawns.
   Invisible boxes were SPR_addSpriteEx NULL after spr=NULL leaked the
   previous SAT. spr_detach + reveal retry + SPR_initEx(512).
2) Enemy black mask: Japan 71f6 is parentY-0x11 / parent X / 0x81 -- the
   same SUB as 48C0. Do not apply ship Y+2 (7735 ADD 0xF1).
3+4) Horizontal tear + missing firebox digits: sat_to_nt is
   wrap(scroll&~7)+Y/8 (8px 97e3 tile). #95 wrap(raw)+Y/8 is the peek
   sliver at leftover frac 1-7 — stamps miss the live cell.
   KEEP: peek only after real 97e3; 97e3 DMA wrap(pre-carry) RAW.
5) Slowdown: no skipped Japan ticks. Cache complement DMA; detach leaks
   so SPR_update does not walk orphan SAT; SPR_initEx tile budget.
6) GO ev4: 3 voices, 0x00 is a rest (4F55), not END.

Usage (from zanac-md):
    python tools/test_playtest_filipe_wave.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "src" / "map_script.c"
ENT = ROOT / "src" / "entity.c"
MAIN = ROOT / "src" / "main.c"
SND = ROOT / "src" / "sound.c"
PLY = ROOT / "src" / "player.c"


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


def hidden_wrap_nt_at(scroll_px: int) -> int:
    off = (scroll_px + 16) & 0xFF
    py = (16 - off) & 0xFF
    return py >> 3


def old_sat_to_nt_y0(scroll_px: int) -> int:
    ntpix = (0 - (scroll_px & ~7)) & 0xFFFF
    return (ntpix >> 3) & 31


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
    ent = ENT.read_text(encoding="utf-8")
    main_c = MAIN.read_text(encoding="utf-8")
    snd = SND.read_text(encoding="utf-8")
    ply = PLY.read_text(encoding="utf-8")

    # --- 3+4 sat_to_nt ---
    sat = fn_span(mp, "static int sat_to_nt(s16 x, s16 y, u8 *col, u8 *row)")
    if not sat:
        return fail("sat_to_nt not found")
    if "tile_wrap_nt_at(s_scroll_px)" not in sat:
        return fail("sat_to_nt Y must be wrap(scroll&~7)+Y/8 (8px tile, not peek)")
    if "hidden_wrap_nt_at(s_scroll_px)" in sat:
        return fail("#95 wrap(raw)+Y/8 is peek at leftover — use tile_wrap")
    vis = fn_span(mp, "static u8 vis_nt_row(u8 tms_row)")
    if not vis or "tile_wrap_nt_at(s_scroll_px)" not in vis:
        return fail("vis_nt_row must use tile_wrap + tms_row")
    if vis and "hidden_wrap_nt_at(s_scroll_px)" in vis:
        return fail("vis_nt_row must not wrap(raw)")

    for sc in (0, 8, 16, 64, 192, 248):
        if hidden_wrap_nt_at(sc) != hidden_wrap_nt_at(sc):
            return fail("wrap self")
    for sc in (1, 6, 7, 9):
        if hidden_wrap_nt_at(sc) == old_sat_to_nt_y0(sc):
            return fail("frac %d: old &~7 accidentally matches wrap" % sc)
        print("  frac", sc, "wrap", hidden_wrap_nt_at(sc), "old", old_sat_to_nt_y0(sc))

    stamp = fn_span(mp, "void map_script_stamp_82_digit(s16 x, s16 y, u8 fire_num)")
    if not stamp or "0x30 + fire_num" not in stamp:
        return fail("87e2 digit must stay 0x30+fire#")
    if "sat_to_nt" not in stamp:
        return fail("87e2 must bind through sat_to_nt")

    # KEEP peek / pre-carry
    upd = fn_span(mp, "void map_script_update(void)")
    if not upd:
        return fail("map_script_update not found")
    skip = upd.split("if (!s_skip_precompute)")
    if len(skip) < 2:
        return fail("KEEP: s_skip_precompute")
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
    block = body[i : end + 1]
    if "peek_next_row" not in block:
        return fail("KEEP: peek only after real 97e3")
    if "s_scroll_px =" in block:
        return fail("KEEP: #92 pre-carry wrap — do not assign scroll before 97e3")

    # --- 1 boxes ---
    if "if (t == 68)" not in ent or "spawn_proto_box()" not in ent:
        return fail("type 68 must stay proto_box (do not invent 4/5/6 spawns)")
    box = fn_span(ent, "static void box_step(Slot *e)")
    if not box:
        return fail("box_step not found")
    if "e->bind = 0x00C0" not in box:
        return fail("KEEP: reveal Yvel 0x00C0")
    if "spr_place(e, FRAME_BOX)" not in box or "if (!e->spr)" not in box:
        return fail("box_step must retry spr_place after reveal")
    spawn_box = fn_span(ent, "static void spawn_box(Slot *e, u8 type, s16 x, s16 y, u8 sat_cd)")
    if not spawn_box or "spr_detach(e)" not in spawn_box:
        return fail("spawn_box must spr_detach leftover SAT")
    if "static void spr_detach(Slot *s)" not in ent:
        return fail("spr_detach must exist (release, do not orphan)")

    # --- 2 enemy mask vs ship ---
    sync = fn_span(ent, "static void spr_sync(Slot *s)")
    if not sync:
        return fail("spr_sync not found")
    if "mdy = dy" not in sync:
        return fail("71f6 complement Y matches primary (same SUB 0x11)")
    if "mdx = dx" not in sync:
        return fail("71f6 complement X shares primary SAT X")
    if "mode_draw_x(s->x, 0x81)" in sync:
        return fail("do not recompute complement X from 0x81")
    if "mode_draw_y(s->y) + 2" in ent:
        return fail("do not apply ship Y+2 to enemy complements")
    if "mode_draw_y(s_y) + 2" not in ply:
        return fail("KEEP: ship black stays Y+2")

    # --- 5 60fps / DMA ---
    if "SPR_initEx(512)" not in main_c:
        return fail("SPR_initEx(512) for dual-layer AUTO_VRAM")
    if main_c.count("SYS_doVBlankProcess()") != 1:
        return fail("KEEP: one VBlank per tick")
    if "DMA_setAutoFlush(FALSE)" not in main_c:
        return fail("KEEP: autoflush off")
    mspr = fn_span(ent, "static void mspr_upload(Slot *s)")
    if not mspr or "mvram_fr == s->mframe" not in mspr:
        return fail("mspr_upload must skip DMA when complement tiles are current")
    if "entity_update" in ent and re.search(r"if \(n > 8\).*continue", ent):
        return fail("do not drop entities to fake speed")

    # --- 6 GO ---
    if "if (b <= 0x7F)" not in snd:
        return fail("fetch_stream: 0x00-0x7F are notes (GO rests)")
    if "sound_play_event(SND_EV_GAMEOVER)" not in snd:
        return fail("KEEP: GO is ev4")

    # KEEP list
    if "sat_x_964c" not in mp:
        return fail("KEEP: sat_x_964c")
    if "0xBFD6" in ent or "0xbfd6" in ent:
        return fail("KEEP: no BFD6")
    if "VDP_fillTileMapRect(BG_A, mode_letter_attr(), 0, 2, MODE_BAR_COL, 24)" in mp:
        return fail("KEEP: no playfield letter fill")

    print("ok: filipe wave — tile_wrap+(Y/8), box detach/retry, 71f6 no Y+2, DMA cache, GO rest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
