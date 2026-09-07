#!/usr/bin/env python3
"""NTSC MSX v1 is 60 logic ticks/sec. Do not cap the MD port at 30fps.

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

    print("ok: SPR_update; doVBlank; flush; DMA budget raised; no 30fps cap")
    return 0


if __name__ == "__main__":
    sys.exit(main())
