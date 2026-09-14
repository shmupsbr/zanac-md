#!/usr/bin/env python3
"""Remaining Filipe playtest items vs Japan v1 (after PR #88 left-eye).

Start from main 7ce3895. Do not assume #85-#87 closed these. This lock
must FAIL on that main for items 1/2/4 (same-Y ship, become_expl
ground=1 on type44/guns, invented totem 0x28 punch).

  1) Ship black: same X, Y+2 (0x7735 ADD 0xF1 vs 0x48C0 SUB 0x11),
     name 0x3C color 0x81, behind white. Same-Y eats 29 hull bits.
  2) Ground death: 4898 type44/guns stay SAT-space (ground=0). 84d1
     keeps live SAT Y. Do not add VSCROLL frac (prints BELOW).
  3) Bomb orb: 8a16 names/colors + pats 7/8/9 body bits. First pair
     is lead shard 0x1C/0x8F (Japan), then clean discs.
  4) Totem 8833: CALL 0xbfc8 / 4a6a / child 0xD1 SAT 0x24. No JP 88ed.
     Do not punch 3x2 of 0x28 onto the yellow face.
  5) Green flyer 71f6: Y SUB 0x11 (same as primary), X = parent, 0x81.
     No ship X+1 / no ship Y+2.
  6) Wrap(aligned) = sat_to_nt(Y=0) = screen 16. leftover wrap(raw) is peek.
     HUD BG_B 24-31 restore stays.
     No playfield letter fill. No opaque 0x20.
  7) R1 eyes: type 75 is 1x1 0xBF+phase. sat_x_964c() 8-bit stays.

KEEP: 964C 8-bit; 4898 wrap; ebullet grouping; 4BDF; wrap/peek; 60fps;
no 0xBFD6; half-greens; BFA0; gswoop 7f54; type 44 44BA;
type35 leftover vel OK.

Usage (from zanac-md):
    python tools/test_playtest_remaining_japan_v1.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "src" / "map_script.c"
ENT = ROOT / "src" / "entity.c"
PLY = ROOT / "src" / "player.c"
HDR = ROOT / "inc" / "map_script.h"
MAIN = ROOT / "src" / "main.c"
SHIP = ROOT / "res" / "sprites" / "ship.png"
OBJS = ROOT / "res" / "sprites" / "objs.png"
EX = ROOT / "tools" / "extract_map_scripts.py"

ASM_CANDIDATES = [
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
]

JAPAN_8A16_DB = (
    "0x1c, 0x8f, 0x20, 0x83, 0x24, 0x8a, 0x20, 0x8b, "
    "0x1c, 0x81, 0x20, 0x81, 0x24, 0x81, 0x20, 0x81 ; 0x8a16"
)


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


def hidden_wrap_nt_at(scroll_px: int) -> int:
    off = (scroll_px + 16) & 0xFF
    py = (16 - off) & 0xFF
    return py >> 3


def sat_to_nt_y0(scroll_px: int) -> int:
    return hidden_wrap_nt_at(scroll_px & ~7)


def sat_x_8bit(ybase: int, blob_x: int) -> int:
    return (ybase * 8 + blob_x - 0x20) & 0xFF


def load_asm() -> str | None:
    for p in ASM_CANDIDATES:
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    return None


def load_extract():
    spec = importlib.util.spec_from_file_location("extract_map_scripts", EX)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def pat16(raw: bytes, idx: int) -> list[list[int]]:
    p = raw[idx * 32 : (idx + 1) * 32]
    pix = [[0] * 16 for _ in range(16)]
    for y in range(16):
        if y < 8:
            left, right = p[y], p[16 + y]
        else:
            left, right = p[8 + (y - 8)], p[24 + (y - 8)]
        for x in range(8):
            if left & (0x80 >> x):
                pix[y][x] = 1
            if right & (0x80 >> x):
                pix[y][x + 8] = 1
    return pix


def overlap(w: list[list[int]], k: list[list[int]], dx: int, dy: int) -> int:
    n = 0
    for y in range(16):
        for x in range(16):
            yy, xx = y + dy, x + dx
            if 0 <= yy < 16 and 0 <= xx < 16 and w[y][x] and k[yy][xx]:
                n += 1
    return n


def png_bits(im, box):
    fr = im.crop(box)
    pix = list(fr.getdata())
    bits = [[0] * 16 for _ in range(16)]
    for i, p in enumerate(pix):
        bits[i // 16][i % 16] = 1 if p else 0
    return bits


def main() -> int:
    mp = MAP.read_text(encoding="utf-8")
    ent = ENT.read_text(encoding="utf-8")
    ply = PLY.read_text(encoding="utf-8")
    hdr = HDR.read_text(encoding="utf-8")
    main_c = MAIN.read_text(encoding="utf-8")

    # --- 1 ship black complement ---
    if "mode_draw_x(s_x, 0x81) + 1" in ply:
        return fail("1: do not draw ship black at white X+1")
    if "return mode_draw_x(s_x, 0x81)" not in ply:
        return fail("1: ship complement X must match white EC")
    if "mode_draw_y(s_y) + 2" not in ply:
        return fail("1: ship complement Y must be white Y+2 (ADD 0xF1)")
    if "SPR_setDepth(s_cspr, 1)" not in ply or "SPR_setDepth(s_spr, 0)" not in ply:
        return fail("1: white depth 0, black depth 1 (later SAT behind)")
    if "SPR_setAnimAndFrame(s_cspr, 0, 1)" not in ply:
        return fail("1: s_cspr is pat 15 / ship.png frame 1")
    if "0x3C" not in ply:
        return fail("1: Japan complement SAT name 0x3C must stay documented")

    # --- 2 ground death Y ---
    if "e->ground = hide" in ent:
        return fail("2: do not force become_expl ground=1 on 4898 type44/guns")
    if "if (sat_space)" not in ent or "e->ground = 0" not in ent:
        return fail("2: become_expl must clear ground on KIND_GROUND/GUN")
    if "e->kind == KIND_GROUND || e->kind == KIND_GUN" not in ent:
        return fail("2: sat_space is KIND_GROUND / KIND_GUN")
    if "0xD0, 0x1C, 0x20, 0x24, 0x20, 0x1C" not in ent:
        return fail("2: k_t35_sat stays 84d1 names")
    if "0x48, 0x8A, 0x8E, 0x8F, 0x8D, 0x89" not in ent:
        return fail("2: k_t35_col stays 84d1 colors (blue shard / orange)")
    if "e->vx = 0" not in ent or "e->vy = 0" not in ent:
        return fail("KEEP: become_expl still zeros type-35 leftover vel")

    # --- 3 bomb orb ---
    if "0x1C, 0x20, 0x24, 0x20" not in ent:
        return fail("3: k_orb_sat must stay 8a16 names")
    if "0x8F, 0x83, 0x8A, 0x8B" not in ent:
        return fail("3: k_orb_yel_col must stay 8a16 yellow pair")
    if "0x81, 0x81, 0x81, 0x81" not in ent:
        return fail("3: k_orb_blk_col must stay 8a1e black pair")
    if "orb_paint_body_nibbles" not in ent:
        return fail("3: orb must paint every nonzero nibble")
    if "u16 out = 128" in ent:
        return fail("3: do not re-ship 4-tile pad as the orb fix")
    place = re.search(
        r"static void spr_place\(Slot \*s, u16 frame\)\s*\{(.*?)^\}",
        ent,
        re.S | re.M,
    )
    if not place or "s->kind == KIND_ORB" not in place.group(1):
        return fail("3: spr_place must invalidate disc VRAM cache")

    # --- 4 totem ---
    if "map_script_clear_totem_face" in mp or "map_script_clear_totem_face" in ent:
        return fail("4: 8833 must not punch totem face (no 88ed)")
    if "map_script_clear_totem_face" in hdr:
        return fail("4: do not declare an invented totem punch")
    if "punch_cell(col, srow, 0x28)" in mp:
        return fail("4: 0x28 on the yellow totem is the blue/white junk")
    if "spawn_d1_child" not in ent:
        return fail("4: 8833 still allocs child 0xD1 SAT 0x24")

    # --- 5 green flyer ---
    if "mdx = dx" not in ent:
        return fail("5: flyer complement X shares primary draw X (71f6 parent SAT X)")
    if "mdx = mode_draw_x(s->x, 0x81)" in ent:
        return fail("5: do not recompute complement X from 0x81")
    if "mdy = dy" not in ent:
        return fail("5: flyer complement Y matches primary (71f6 SUB 0x11)")
    if "Do not add ship X+1" not in ent:
        return fail("5: 71f6 must not inherit ship X+1 / Y+2")
    if "mode_draw_y(s->y) + 2" in ent:
        return fail("5: do not apply ship Y+2 to flyer complement")

    # --- 6 seam / wrap ---
    wrap = re.search(
        r"static u8 hidden_wrap_nt_at\(u16 scroll_px\)\s*\{(.*?)^\}",
        mp,
        re.S | re.M,
    )
    if not wrap:
        return fail("6: hidden_wrap_nt_at not found")
    if "16 - off" not in wrap.group(1):
        return fail("6: wrap must be playfield top (screen Y 16 / SAT Y 0)")
    if "8 - off" in wrap.group(1):
        return fail("6: wrap Y=8 is the letterbox row (hard blue/green seam)")
    for sc in (0, 8, 16, 64, 192):
        if hidden_wrap_nt_at(sc) != sat_to_nt_y0(sc):
            return fail(
                "6: hidden_wrap(%d)=%d != sat_to_nt(0)=%d"
                % (sc, hidden_wrap_nt_at(sc), sat_to_nt_y0(sc))
            )
    for sc in (1, 6, 7, 9):
        if sat_to_nt_y0(sc) == hidden_wrap_nt_at(sc):
            return fail("6: frac %d sat_to_nt(0) must not be wrap(raw) peek" % sc)
    satfn = re.search(
        r"static int sat_to_nt\(s16 x, s16 y, u8 \*col, u8 \*row\)\s*\{(.*?)^\}",
        mp,
        re.S | re.M,
    )
    if not satfn or "tile_wrap_nt_at(s_scroll_px)" not in satfn.group(1):
        return fail("6: sat_to_nt Y must be wrap(scroll&~7) + (Y/8)")
    if satfn and "hidden_wrap_nt_at(s_scroll_px)" in satfn.group(1):
        return fail("6: #95 wrap(raw)+Y/8 is peek at leftover")
    if "peek_next_row_at((u16)(s_ms.row + 1), (u16)(s_scroll_px + 8))" not in mp:
        return fail("6: boot peek must be scroll_px+8 (NT 31)")
    if "VDP_setTileMapDataRow(BG_B, dst + MODE_BAR_COL, nt_y" not in mp:
        return fail("KEEP: dma_nt_row must restore HUD BG_B cols 24-31")
    if "recolor_charset_tile_opaque_bg" in mp:
        return fail("KEEP: no opaque 0x20")
    if "VDP_fillTileMapRect(BG_A, mode_letter_attr(), 0, 2, MODE_BAR_COL, 24)" in mp:
        return fail("KEEP: no playfield letter fill")

    # --- 7 one eye / pod + KEEP 964C ---
    fn = re.search(
        r"void map_script_base_8c15_at\(u8 col, u8 row, u8 variant, u8 phase\)\s*\{(.*?)^\}",
        mp,
        re.S | re.M,
    )
    if not fn:
        return fail("7: map_script_base_8c15_at not found")
    tail = fn.group(1).split("0xBF + p", 1)[-1]
    if "rows = 2" in tail or "cols = 2" in tail:
        return fail("7: 75-78 south/east repeat is the double stacked eye")
    if "rows = 1" not in tail or "cols = 1" not in tail:
        return fail("7: 75-78 must be 1x1 (one 0xBF+phase lens)")
    if "sat_x_964c" not in mp:
        return fail("KEEP: sat_x_964c() must stay")
    sx = re.search(
        r"static s16 sat_x_964c\(u8 ybase, u8 blob_x\)\s*\{(.*?)^\}",
        mp,
        re.S | re.M,
    )
    if not sx:
        return fail("KEEP: sat_x_964c body missing")
    if "(u8)" not in sx.group(1) or "- 0x20" not in sx.group(1):
        return fail("KEEP: sat_x_964c must wrap ybase*8 + blob_X - 0x20 as u8")
    if sat_x_8bit(0x15, 0xE8) != 112:
        return fail("KEEP: R1 west blob 0xE8 must SAT 112")
    if "u8 hx = (u8)((u8)sat_x - 0x20)" not in mp:
        return fail("KEEP: 8948 H stays unsigned SUB 0x20")

    # --- KEEP remainder ---
    if main_c.count("SYS_doVBlankProcess()") != 1:
        return fail("KEEP: 60fps — one VBlank per tick")
    if "0xBFD6" in ent or "0xbfd6" in ent:
        return fail("KEEP: no CALL 0xBFD6")
    if "k_flyer_green_dim" in ent:
        return fail("KEEP: no PAL2 half-green override")
    collide = re.search(
        r"static void collide_player\(void\)\s*\{(.*?)^\}",
        ent,
        re.S | re.M,
    )
    if not collide or re.search(r"if\s*\(\s*e->kind == KIND_GROUND\s*\)", collide.group(1)):
        return fail("type 44 is 44BA; collide_player must not skip KIND_GROUND")
    if "KIND_TRACKER" not in ent or "KIND_VEYBAR" not in ent:
        return fail("KEEP: ebullet grouping kinds")
    if "7f54" not in ent:
        return fail("KEEP: gswoop 7f54 unsigned")
    if "BFA0" not in ent:
        return fail("KEEP: BFA0 type 44 path")

    # --- Japan v1 asm immediates (when zanac-re is present) ---
    asm = load_asm()
    if asm:
        if "ADD	 A, 0xf1					; 0x7735" not in asm:
            return fail("Japan 0x7735 must be ADD A,0xF1")
        if "SUB	 0x11						; 0x48c0" not in asm:
            return fail("Japan 0x48C0 must be SUB 0x11")
        if "LD	 (HL), 0x3c					; 0x773e" not in asm:
            return fail("Japan 0x773E complement name is 0x3C")
        if "LD	 (HL), 0x81					; 0x7741" not in asm:
            return fail("Japan 0x7741 complement color is 0x81")
        if "CALL	 0xbfc8						; 0x8833" not in asm:
            return fail("Japan 0x8833 must CALL 0xbfc8 (no 88ed)")
        if "JP	 0x88ed						; 0x8833" in asm:
            return fail("Japan 0x8833 must not JP 0x88ed")
        if "SUB	 0x11						; 0x71fd" not in asm:
            return fail("Japan 0x71FD flyer complement is SUB 0x11")
        if JAPAN_8A16_DB not in asm.lower():
            return fail("Japan 0x8A16 orb pair table mismatch")
        if "LD	 B, 0x01					; 0x8c62" not in asm:
            return fail("Japan type 75 8c62 is B=1 (1x1)")
        if "LD	 D, 0x00					; 0x8c64" not in asm:
            return fail("Japan type 75 8c64 is D=0 (1x1)")

        ext = load_extract()
        if ext is not None:
            asm_path = next((p for p in ASM_CANDIDATES if p.is_file()), None)
            if asm_path is None:
                return fail("zanac-re asm vanished after load")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rom = ext.parse_asm(asm_path)
            raw = ext.decompress(rom, ext.SPRITE_RLE[0], ext.SPRITE_RLE[1], max_out=4096)
            if len(raw) < 2048:
                return fail("sprite RLE must decompress to 2048 bytes")
            white = pat16(raw, 14)
            black = pat16(raw, 15)
            same = overlap(white, black, 0, 0)
            x1 = overlap(white, black, 1, 0)
            japan = overlap(white, black, 0, -2)
            if same != 29:
                return fail("1: pats 14/15 same-X same-Y overlap must be 29, got %d" % same)
            if x1 != 35:
                return fail("1: pats 14/15 X+1 overlap must be 35, got %d" % x1)
            if japan != 0:
                return fail("1: pats 14/15 same-X Y+2 visual overlap must be 0, got %d" % japan)
            # pats 7/8/9: lead shard + two discs, body bits only
            for idx, name, expect_on in ((7, "lead", 14), (8, "med", 96), (9, "lg", 192)):
                bits = pat16(raw, idx)
                on = sum(sum(row) for row in bits)
                if on != expect_on:
                    return fail("3: pat %d (%s) on-bits must be %d, got %d" % (idx, name, expect_on, on))

    # --- ship.png / objs.png when Pillow is present ---
    try:
        from PIL import Image
    except ImportError:
        print("ok: remaining playtest locks (Pillow missing; skip png hist)")
        return 0

    im = Image.open(SHIP)
    if im.size != (32, 16):
        return fail("1: ship.png must be 32x16, got %s" % (im.size,))
    wbits = png_bits(im, (0, 0, 16, 16))
    kbits = png_bits(im, (16, 0, 32, 16))
    if overlap(wbits, kbits, 0, 0) == 0:
        return fail("1: ship.png same-Y must still overlap (desconjuntado proof)")
    if overlap(wbits, kbits, 0, -2) != 0:
        return fail("1: ship.png Japan Y+2 visual overlap must be 0")

    objs = Image.open(OBJS)
    # FRAME_LEAD=6, FRAME_CIRCLE=11, FRAME_MED_CIRCLE=52 in rebuild/entity
    for fi, name in ((6, "LEAD"), (11, "CIRCLE"), (52, "MED_CIRCLE")):
        fr = objs.crop((fi * 16, 0, fi * 16 + 16, 16))
        stray = [p for p in fr.getdata() if p not in (0, 15)]
        if stray:
            return fail("3: objs.png FRAME_%s has garbage pixels %s" % (name, sorted(set(stray))))

    print("ok: remaining playtest 1-7 + KEEP vs Japan v1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
