#!/usr/bin/env python3
"""Fire 7 72de colour cycle is CRAM, not per-frame tile remap.

Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2) 72de:
  LD A,(IX+0x04) / INC A / AND 0x8F / LD (IX+0x04),A
Fire 1 (72ea CALL 72de) and fire 7 (7306 JR 72de) share that INC.
MSX SAT colour is one byte; MD tile remap every frame + wrap/peek NT
DMA produced a full-width blue tear.

Bind comet pixels to PAL2[13] once and KEEP sat_col there. Cycle that
CRAM index with INC+AND 0x8F. Restoring sat_col to 0x81 after bind
lets a later spr_upload_color remap the comet to nibble 1 (TMS black)
so PAL2[13] pulses while the shot stays black-only.

Keep dma_nt_row HUD cols 24-31 restore. No playfield letter fill.
No opaque-recolor 0x20.

Usage (from zanac-md):
    python tools/test_fire7_cram_cycle.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
MAP = ROOT / "src" / "map_script.c"
MAIN = ROOT / "src" / "main.c"
ASM_CANDIDATES = [
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    Path.home() / "zanac-re" / "source" / "zanac.asm",
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
]


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


def load_asm() -> str | None:
    for p in ASM_CANDIDATES:
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    return None


def main() -> int:
    ent = ENT.read_text(encoding="utf-8")
    mp = MAP.read_text(encoding="utf-8")
    main_c = MAIN.read_text(encoding="utf-8")
    asm = load_asm()

    if "FIRE7_CRAM_NIB" not in ent:
        return fail("fire 7 must bind a dedicated PAL2 nibble")
    if "FIRE7_CRAM_NIB  13" not in ent and "FIRE7_CRAM_NIB 13" not in ent:
        return fail("fire 7 CRAM nibble must stay 13 (not half-green 2/3)")
    if "fire7_cycle_cram" not in ent:
        return fail("72de INC for fire 7 must be CRAM, not spr_set_sat_col")
    if "fire7_bind_cram" not in ent:
        return fail("spawn fire 7 must upload comet to the CRAM nibble once")
    if "fire7_cycle_cram(f)" not in ent:
        return fail("update_fire cycle path must CRAM-cycle fire 7")
    # 72de is shared by fire 0/1/2/7. Only one fire is live; they share
    # PAL2[13]. Per-frame spr_set_sat_col on 0/1/2 was the leftover hitch.
    spawn = fn_span(ent, "void entity_try_spawn_fire(s16 x, s16 y, u8 xvel_sel)")
    if not spawn or spawn.count("fire7_bind_cram") < 1:
        return fail("72de spawn must bind CRAM for fire 0/1/2/7")
    if "fn == 0 || fn == 1 || fn == 2 || fn == 7" not in (spawn or ""):
        return fail("72de CRAM bind must cover fire 0/1/2/7")
    if "spr_set_sat_col(f, (u8)(0x80 | ((f->sat_col + 1) & 0x0F)))" in ent:
        return fail("fire 0/1/2 must CRAM-cycle like fire 7, not remap tiles")
    if "s_fire7_col" not in ent:
        return fail("72de colour must be a dedicated INC+AND 0x8F register")

    bind = fn_span(ent, "static void fire7_bind_cram(Slot *f)")
    if not bind:
        return fail("fire7_bind_cram not found")
    if "sat_col = saved" in bind or "f->sat_col = saved" in bind:
        return fail("do not restore sat_col after bind (nibble 1 is black-only)")
    if "0x80 | FIRE7_CRAM_NIB" not in bind and "0x80 | FIRE7_CRAM_NIB" not in bind:
        return fail("bind must set sat_col to EC|13 and keep it")
    if "orb_paint_body_nibbles" not in bind and "fire7_paint_cram_tiles" not in ent:
        return fail("bind must paint every nonzero comet nibble to 13")

    cyc = fn_span(ent, "static void fire7_cycle_cram(Slot *f)")
    if not cyc:
        return fail("fire7_cycle_cram not found")
    if "spr_set_sat_col" in cyc or "spr_upload_color" in cyc:
        return fail("cycle must not remap tiles (NT tear)")
    if "& 0x8F" not in cyc:
        return fail("72de is INC then AND 0x8F, not (sat_col+1)&0x0F")
    if "f->sat_col =" in cyc:
        return fail("cycle must not walk sat_col off nibble 13")

    if asm:
        if not re.search(r"AND\s+0x8f\s*;\s*0x72e2", asm, re.I):
            return fail("zanac.asm 72e2 is not AND 0x8F")
        print("  ASM 72e2: AND 0x8F (fire 1 and fire 7)")

    if "VDP_setTileMapDataRow(BG_B, dst + MODE_BAR_COL" not in mp:
        return fail("dma_nt_row must restore HUD cols 24-31")
    if "mode_draw_letterbox" in mp.split("static void dma_nt_row")[1][:800]:
        return fail("dma_nt_row must not playfield-wide letter fill")
    if "0x20" in ent and "opaque" in ent.lower() and "recolor 0x20" in ent:
        return fail("do not opaque-recolor charset 0x20")
    if "DMA_setAutoFlush(FALSE)" not in main_c:
        return fail("60Hz: autoflush stays off")

    # Type 72 vehicle must stay FRAME_CIRCLE / Japan pats 7/8/9.
    if "k_japan_pat7" not in ent or "FRAME_CIRCLE" not in ent:
        return fail("KEEP: type 72 Japan pats / FRAME_CIRCLE vehicle")

    print("ok: fire 7 CRAM stays on nibble 13; 72de AND 0x8F; HUD restore")
    return 0


if __name__ == "__main__":
    sys.exit(main())
