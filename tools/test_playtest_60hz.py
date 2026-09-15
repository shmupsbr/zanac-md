#!/usr/bin/env python3
"""NTSC MSX v1 is 60 logic ticks/sec. Do not cap the MD port at 30fps.

Cloud has no SGDK / VDP runtime -- this file is a static guard, not a
measured FPS meter. Do not treat a pass as "60 fps observed on hardware."

zanac.asm:
  vblank_isr 0x43DA increments E1F8 every VDP GINT.
  wait_one_frame 0x4306: spin until (E1F8)>=1, then zero it -- ONE retrace.
  gameplay_frame_loop 0x9393: wait_one_frame then entity_dispatch.
  Caller 0x407A is LD B,1 (one wait per logic tick).
  wait_frames 0x5BEC: title B=2, gameplay B=1.
  No 2-frame skip in the play loop. PAL MSX is 50Hz hardware, not a
  30fps loop.

Half-speed on MD was extra VBlanks (DMA auto-flush + per-tick letterbox),
not a missing 2px scroll. E710 starts 0x20 so E711>>5 is 1px/tick.

Usage (from zanac-md):
    python tools/test_playtest_60hz.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src" / "main.c"
MAPC = ROOT / "src" / "map_script.c"
GAME = ROOT / "src" / "game.c"
HUD = ROOT / "src" / "hud.c"


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


def main() -> int:
    main_c = MAIN.read_text(encoding="utf-8")
    map_c = MAPC.read_text(encoding="utf-8")
    game_c = GAME.read_text(encoding="utf-8")
    hud_c = HUD.read_text(encoding="utf-8")

    if "SPR_initEx(" not in main_c:
        return fail("main.c: SPR_initEx so dual-layer SAT still allocates")
    m_spr = re.search(r"SPR_initEx\((\d+)\)", main_c)
    if not m_spr or int(m_spr.group(1)) < 512:
        return fail("SPR_initEx must reserve >=512 sprite tiles (default 420)")
    if "DMA_setAutoFlush(FALSE)" not in main_c:
        return fail("main.c: DMA auto-flush must be off (extra VBlank = 30Hz)")
    if "DMA_setAutoFlush(TRUE)" in main_c:
        return fail("main.c: do not re-enable autoflush")
    if main_c.count("SYS_doVBlankProcess()") != 1:
        return fail("main.c: exactly one SYS_doVBlankProcess per tick")
    if main_c.count("DMA_flushQueue()") != 1:
        return fail("main.c: exactly one DMA_flushQueue per tick")
    if not re.search(
        r"SPR_update\(\);\s*"
        r"SYS_doVBlankProcess\(\);.*\n"
        r"\s*DMA_flushQueue\(\);",
        main_c,
    ):
        return fail("loop must be SPR_update; SYS_doVBlankProcess; DMA_flushQueue")
    flush_at = main_c.find("DMA_flushQueue()")
    wait_at = main_c.find("SYS_doVBlankProcess()")
    if flush_at < 0 or wait_at < 0 or flush_at < wait_at:
        return fail("DMA_flushQueue before the wait is a second retrace")
    if "DMA_setMaxQueueSize(" not in main_c:
        return fail("raise DMA command queue; default 80 fills mid-frame")
    m_q = re.search(r"DMA_setMaxQueueSize\((\d+)\)", main_c)
    if not m_q or int(m_q.group(1)) < 192:
        return fail("DMA queue must be >=192 (4-tile pad + NT + HUD restore)")
    if "DMA_setBufferSize(" not in main_c or "DMA_setMaxTransferSize(0)" not in main_c:
        return fail("raise DMA buffer / unlimited transfer; do not cap at 7200")
    if re.search(r"SYS_setFPS|setMaxFPS|30\s*\*\s*FPS|fps\s*=\s*30", main_c, re.I):
        return fail("main.c: do not add a 30fps cap")

    # Letterbox is stamped at boot / hud_wipe, not every scroll/HUD tick.
    bg = re.search(r"static void bg_set_vscroll\(void\)\s*\{(.*?)^\}", map_c, re.S | re.M)
    if not bg:
        return fail("bg_set_vscroll not found")
    if "mode_draw_letterbox" in bg.group(1):
        return fail("bg_set_vscroll must not refill letterbox every tick")

    hud = re.search(r"void map_script_draw_hud\(void\)\s*\{(.*?)^\}", map_c, re.S | re.M)
    if not hud:
        return fail("map_script_draw_hud not found")
    if "mode_draw_letterbox" in hud.group(1):
        return fail("map_script_draw_hud must not refill letterbox every tick")

    if "mode_draw_letterbox();" not in game_c:
        return fail("game_boot must still stamp letterbox once")
    if "mode_draw_letterbox();" not in hud_c:
        return fail("hud_wipe must still stamp letterbox once")

    # 1px/tick: (row-base)*8 + (E711>>5). E710 starts 0x20 (0x20>>5 == 1).
    if "s_e710 = 0x20" not in map_c:
        return fail("E710 start must stay 0x20 (1px/tick at E711>>5)")
    if not re.search(
        r"s_scroll_px = \(u16\)\(\(\(u16\)\(s_ms\.row - s_scroll_base\) << 3\)\s*"
        r"\+\s*\(s_e711 >> 5\)\)",
        map_c,
    ):
        return fail("s_scroll_px must stay (row-base)*8 + (E711>>5), not 2px/frame")
    if re.search(r"s_scroll_px\s*\+=\s*2|s_e711\s*>>\s*4", map_c):
        return fail("do not invent 2px/frame scroll")

    # Colour-cycle sprites must not remap tiles every tick.
    ent = (ROOT / "src" / "entity.c").read_text(encoding="utf-8")
    if "remap_cache_get" not in ent:
        return fail("XOR / leftover sat_col remaps must hit a (frame,nibble) cache")
    if "orb_cache_get" not in ent:
        return fail("KEEP: type-72 orb encoded-variant cache")
    if "fire7_cycle_cram" not in ent:
        return fail("KEEP: 72de colour cycle is CRAM")
    if "xor_cram_bind" not in ent or "xor_cram_cycle" not in ent:
        return fail("XOR leftovers (36/56/59/67/walkers) must CRAM-bind like fire 7")
    if "k_xor_cram_nib" not in ent:
        return fail("XOR CRAM must use dedicated PAL2 nibbles, not 2/3/13")
    if "s_xor_cram_kind" not in ent or "s_xor_cram_refs" not in ent:
        return fail("XOR CRAM must be shared by kind (not exclusive-per-sprite)")
    if "dma_nibble_defer" not in ent or "DMA_NIBBLE_SOFT_CAP" not in ent:
        return fail("nibble-only tile DMA must defer when the queue is hot")
    if "DMA_getQueueTransferSize" not in ent:
        return fail("defer uses DMA_getQueueTransferSize (bytes already queued)")
    if re.search(r"DMA_NIBBLE_SOFT_CAP\s+4096", ent) is None:
        return fail("soft cap must stay 4096 (leave ~3KB of NTSC vblank for SAT/NT)")

    # Depth bind is place-only; spr_sync must not sortSprite every tick.
    sync = re.search(r"static void spr_sync\(Slot \*s\)\s*\{(.*?)^\}", ent, re.S | re.M)
    if not sync:
        return fail("spr_sync not found")
    if "sat_bind_depth" in sync.group(1):
        return fail("spr_sync must not sat_bind_depth (SGDK 2.11 sortSprite)")
    if "sat_depth_ok" not in ent:
        return fail("SAT depth must be cached after the first slot walk")

    ply = (ROOT / "src" / "player.c").read_text(encoding="utf-8")
    show = re.search(r"static void show_ship\(int vis\)\s*\{(.*?)^\}", ply, re.S | re.M)
    if not show:
        return fail("show_ship not found")
    if "SPR_setDepth(" in show.group(1):
        return fail("show_ship must not SPR_setDepth every tick")
    if ply.count("SYS_doVBlankProcess()") != 0:
        return fail("player.c must not add a second VBlank wait")
    if "DMA_setAutoFlush(TRUE)" in ent or "DMA_setAutoFlush(TRUE)" in game_c:
        return fail("do not re-enable DMA autoflush outside main.c")

    # Shot / fire / ebullet hot path (dense spam). Do not redo #129.
    if "s_shot_bank" not in ent or "shot_vram_prepare" not in ent:
        return fail("static shot/lead/bar tiles must hit a shared VRAM bank")
    if "shot_vram_remember" not in ent:
        return fail("first shot/lead upload must be remembered for later sprites")
    if "spr_sync_proj" not in ent:
        return fail("fire/ebullet/shots need a cheap position+clip sync")
    proj = re.search(
        r"static void spr_sync_proj\(Slot \*s\)\s*\{(.*?)^\}", ent, re.S | re.M
    )
    if not proj:
        return fail("spr_sync_proj not found")
    if "sat_bind_depth" in proj.group(1) or "SPR_setDepth(" in proj.group(1):
        return fail("spr_sync_proj must not re-bind depth (shots never change SAT order)")
    if "mspr" in proj.group(1):
        return fail("projectiles have no 71f6 complement; skip marker work")
    if "proj_draw_hidden" not in ent:
        return fail("letterboxed shots must skip hardware sprite alloc")
    if "sat_box_miss" not in ent:
        return fail("shot/enemy SAT squares must early-out before AABB")
    bolt = re.search(
        r"static void collide_bolt_enemies\(Slot \*bolt, u8 persist\)\s*\{(.*?)^\}",
        ent,
        re.S | re.M,
    )
    if not bolt:
        return fail("collide_bolt_enemies not found")
    if "sat_box_miss" not in bolt.group(1):
        return fail("collide_bolt_enemies must sat_box_miss before takes_shots")
    if "hitbox_of(bolt_sat" not in bolt.group(1):
        return fail("bolt hitbox must be computed once per bolt, not per enemy")
    if "enemy_takes_shots" not in bolt.group(1) or "enemy_takes_fire" not in bolt.group(1):
        return fail("KEEP: 44F9 / E14E gates after the SAT-box reject")
    if "ebullet_sat_name" not in bolt.group(1):
        return fail("KIND_EBULLET AABB must still use ebullet_sat_name")
    colp = re.search(
        r"static void collide_player\(void\)\s*\{(.*?)^\}", ent, re.S | re.M
    )
    if not colp or "sat_box_miss" not in colp.group(1):
        return fail("collide_player must sat_box_miss before post_flags")
    if "ebullet_hits_player" not in colp.group(1):
        return fail("KEEP: ebullet ship hits after the SAT-box reject")
    # Japan spawn / motion unchanged.
    if "s_ebullet_init_ret" not in ent or "s_shot_init_ret" not in ent:
        return fail("KEEP: 7221 / 84fa init-RET skips")
    if re.search(r"SHOT_SLOTS\s+2|ENEMY_SLOTS\s+1[0-6]\b", ent):
        return fail("do not shrink shot/enemy pools to fake 60fps")

    print("ok: SPR_update; doVBlank; flush; DMA budget raised; no 30fps cap")
    print("ok: shared XOR CRAM; nibble DMA defer; depth bind at place only")
    print("ok: shot VRAM bank; spr_sync_proj; SAT-box collision early-out")
    return 0


if __name__ == "__main__":
    sys.exit(main())
