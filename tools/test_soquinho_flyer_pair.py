#!/usr/bin/env python3
"""Filipe after #157 (1px vblank VSRAM): remaining soquinhos + missing black SAT.

Task A — scroll smoothness (keep 1px plane camera, LEAD_MD_SPEED 4):
  The 24-col CPU nametable OUT during the sim tick is a VDP-port punch
  every 8px even with 1px VSRAM. Japan 9a79 copies E800 in vblank.
  Queue the 24-col row + dst[0] rewrite (coast notch was 32-col skip of
  word 0). Unchanged VSRAM skips the VInt port (hold / warp freeze).
  leftover 2/3/4 assemble split KEEP. Peek DMA stays after fire_pending
  so cmd 9 cannot stamp a 0x28 sky line.

Task B — flying enemies are 2 sprites (black + coloured):
  Japan spawn_col_marker 0x71da allocates type 0x27; CF -> entity_clear
  the parent. 71f6 writes the complement SAT every handler tick.
  Port addSprite NULL left the coloured primary. Retry marker_bind from
  spr_sync; hide the body until the black SAT exists. Bank FRAME_*_C
  tiles (SPR_setVRAMTileIndex, no VDP_allocateTiles). Type 30 DEGID
  pair retries the type31 sibling while aux==0xFF.

Usage (from zanac-md):
    python tools/test_soquinho_flyer_pair.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "src" / "map_script.c"
ENT = ROOT / "src" / "entity.c"
MAIN = ROOT / "src" / "main.c"
OPT = ROOT / "inc" / "options.h"


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


def main() -> int:
    mp = MAP.read_text(encoding="utf-8")
    ent = ENT.read_text(encoding="utf-8")
    main_c = MAIN.read_text(encoding="utf-8")
    opt = OPT.read_text(encoding="utf-8")

    # --- A: 1px camera KEEP ---
    m = re.search(r"#define\s+LEAD_MD_SPEED\s+(\d+)", ent)
    if not m or int(m.group(1)) != 4:
        return fail("HARD LOCK: LEAD_MD_SPEED must stay 4")
    if "LEAD_MD_SPEED (4)" not in opt:
        return fail("HARD LOCK: options.h must still document LEAD_MD_SPEED 4")
    rst = fn_span(mp, "static void scroll_speed_reset(u8 target)")
    if not rst or "s_e710 = 0x20" not in rst:
        return fail("E710 start must stay 0x20 (1px/tick)")
    if "VSCROLL_PLANE" not in mp:
        return fail("KEEP: 1px plane VSRAM")

    dma = fn_span(mp, "static void dma_nt_row(u8 nt_y, const u8 *src, TransferMethod tm)")
    if not dma:
        return fail("dma_nt_row not found")
    if "play_tm = (tm == DMA_QUEUE) ? CPU : tm" in dma:
        return fail("24-col CPU OUT during the sim is the remaining soquinho")
    if "0, PF_COLS, play_tm" not in dma:
        return fail("KEEP: 9a79 24-col playfield at x=0")
    if "0, 1, DMA_QUEUE" not in dma:
        return fail("queue dst[0] again so skipped word 0 cannot leave 0x28 sky")
    if "MODE_H32_COLS" in dma and "width = MODE_H32_COLS" in dma:
        return fail("do not DMA 32 H32 cols (coast notch)")
    if "s_nt[nt_y][x] != src[x]" not in dma:
        return fail("identical wrap/peek rows must still skip VDP")
    print("  A: 24-col vblank DMA + col0 rewrite; identical rows skip")

    apply = fn_span(mp, "void map_script_apply_vscroll(void)")
    if not apply or "s_vsram_b == s_vsram_last" not in apply:
        return fail("VInt must skip unchanged VSRAM")
    vint = fn_span(main_c, "static void vint_psg(void)")
    if not vint or "map_script_apply_vscroll()" not in vint:
        return fail("VSRAM still commits from VInt")
    if "peek_assemble_r1_mid" not in mp or "peek_assemble_two_ahead" not in mp:
        return fail("KEEP: leftover 2/3/4 assemble split")
    upd = fn_span(mp, "void map_script_update(void)")
    if not upd or "peek_next_row" not in upd:
        return fail("KEEP: peek after real 97e3 (cmd 9 must not DMA sky)")
    print("  A: VSRAM skip-unchanged; leftover assemble split KEEP")

    # --- B: 71f6 pair always black+colour ---
    pairs = (
        ("FRAME_DUSTER", "FRAME_DUSTER_C"),
        ("FRAME_TERUZO", "FRAME_TERUZO_C"),
        ("FRAME_LUSTER_A", "FRAME_LUSTER_A_C"),
        ("FRAME_PLANE", "FRAME_PLANE_C"),
        ("FRAME_UMBER", "FRAME_UMBER_C"),
        ("FRAME_STEALTH", "FRAME_STEALTH_C"),
        ("FRAME_VEYBAR_0", "FRAME_VEYBAR_C0"),
        ("FRAME_SPINNER_0", "FRAME_SPINNER_C0"),
        ("FRAME_SART", "FRAME_SART_C"),
        ("FRAME_BOX", "FRAME_BOX_C"),
        ("FRAME_LOGA", "FRAME_LOGA_B"),
    )
    for body, compl in pairs:
        if "marker_place(e, %s)" % compl not in ent and \
           "marker_place(e, (u16)(%s" % compl not in ent:
            return fail("%s must keep 71da complement %s" % (body, compl))
    print("  B: every 71da flyer still marker_place FRAME_*_C")

    sync = fn_span(ent, "static void spr_sync(Slot *s)")
    bind = fn_span(ent, "static void marker_bind(Slot *s, u16 frame)")
    if not sync or not bind:
        return fail("spr_sync / marker_bind missing")
    if "marker_bind(s, s->mframe)" not in sync:
        return fail("spr_sync must retry 71f6 marker_bind (Japan writes SAT every tick)")
    if "pair_ok" not in sync:
        return fail("hide coloured primary until the black SAT exists")
    if "SPR_FLAG_AUTO_VRAM_ALLOC" not in bind:
        return fail("marker_bind must still addSprite the complement")
    if "ccomp_bank_lookup" not in bind:
        return fail("share FRAME_*_C VRAM so AUTO_VRAM cannot drop the black SAT")
    if re.search(r"VDP_allocateTiles\s*\(", ent):
        return fail("no VDP_allocateTiles")
    if "s_ccomp_bank" not in ent or "CCOMP_BANK_N" not in ent:
        return fail("complement VRAM bank missing")
    upload = fn_span(ent, "static void mspr_upload(Slot *s)")
    if not upload or "ccomp_bank_lookup" not in upload:
        return fail("mspr_upload must hit the complement bank")
    if "mvram_fr == s->mframe" not in upload:
        return fail("KEEP: skip complement DMA when tiles are current")
    print("  B: spr_sync retries 71f6; ccomp bank; hide until pair")

    gs = fn_span(ent, "static void gswoop_step(Slot *e)")
    child = fn_span(ent, "static Slot *spawn_gswoop_pair_child(Slot *e)")
    if not child or "c->x = 0xC0" not in child:
        return fail("type 30 71da child stays X=0xC0 DEGID_R")
    if not gs or "spawn_gswoop_pair_child" not in gs:
        return fail("gswoop_step must retry the DEGID_R sibling while aux==0xFF")
    if "e->aux == 0xFF" not in gs:
        return fail("do not respawn a killed right half")
    print("  B: type 30 DEGID pair retries sibling")

    if main_c.count("SYS_doVBlankProcess()") != 1:
        return fail("KEEP: one vblank per tick")
    if re.search(r"SHOT_SLOTS\s+2|ENEMY_SLOTS\s+1[0-6]\b", ent):
        return fail("do not shrink spawn/shot pools")

    print("ok: vblank 24-col NT DMA; 71f6 pair always black+colour")
    return 0


if __name__ == "__main__":
    sys.exit(main())
