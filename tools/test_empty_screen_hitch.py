#!/usr/bin/env python3
"""Empty / sparse playfield hitch: leftover-4 must not double-assemble.

Filipe after #133: with nothing on screen the game still "da soquinho"
(intermittent hitch, not a steady 30 Hz). Cruise E710=0x20 walks
E711>>5 1..7 then carry. leftover 4 used to run two assemble_row
passes (discard R+1, keep R+2) on one tick — a 68000 spike even
when the playfield is empty 0x28 sky. Carry then CPU-OUTs two
24-col nametable rows, often reprinting the same sky.

Fix:
  leftover 2 (or 3 if 0x34 skips 2) parks the discarded R+1 cursors
  leftover 4 only assembles R+2 when that mid-state is present
  dma_nt_row skips the 24-col CPU OUT when s_nt already matches
  WINDOW HUD cells skip VDP_setTileMapXY when the glyph is unchanged

KEEP: two stream steps (not one-step labeled row+2); leftover 4 still
calls peek_assemble_two_ahead; 97e3 wrap(pre) RAW; peek after real
97e3; no VDP_allocateTiles; spawn rates untouched.

Usage (from zanac-md):
    python tools/test_empty_screen_hitch.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "src" / "map_script.c"
HUD = ROOT / "src" / "hud.c"
ENT = ROOT / "src" / "entity.c"
MAIN = ROOT / "src" / "main.c"


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


def cruise_work(e710: int, n: int = 16) -> list[str]:
    """One tick: E711 += E710; leftover is the new acc >> 5."""
    e711 = 0
    mid = False
    out: list[str] = []
    for _ in range(n):
        s = e711 + e710
        e711 = s & 0xFF
        frac = e711 >> 5
        if s > 255:
            mid = False
            out.append("carry")
        elif frac in (2, 3) and not mid:
            mid = True
            out.append("r1")
        elif frac == 4:
            out.append("r2" if mid else "r1+r2")
            mid = False
        else:
            out.append("idle")
    return out


def main() -> int:
    mp = MAP.read_text(encoding="utf-8")
    hud = HUD.read_text(encoding="utf-8")
    ent = ENT.read_text(encoding="utf-8")
    main_c = MAIN.read_text(encoding="utf-8")

    # --- cruise model: leftover 4 is one assemble when leftover 2/3 ran ---
    w20 = cruise_work(0x20, 16)
    if w20.count("r1+r2"):
        return fail("E710=0x20 leftover 4 must not do both assembles")
    if w20.count("r1") != 2 or w20.count("r2") != 2:
        return fail(f"E710=0x20 must split r1/r2 twice in 16 frames, got {w20}")
    if "r1" in w20 and "r2" in w20 and w20.index("r1") == w20.index("r2"):
        return fail("r1 and r2 must be different frames")
    # First cycle: leftover 2 (frame 1) then leftover 4 (frame 3).
    if w20[1] != "r1" or w20[3] != "r2" or w20[7] != "carry":
        return fail(f"E710=0x20 expected r1@1 r2@3 carry@7, got {w20[:8]}")
    print("  sim: E710=0x20 splits leftover 2 (R+1) / leftover 4 (R+2)")

    w34 = cruise_work(0x34, 10)
    if w34.count("r1+r2"):
        return fail("E710=0x34 leftover 4 must not do both assembles")
    if "r1" not in w34 or "r2" not in w34:
        return fail(f"E710=0x34 must still hit leftover 3 then 4, got {w34}")
    print("  sim: E710=0x34 leftover 3 parks R+1; leftover 4 keeps R+2")

    w40 = cruise_work(0x40, 8)
    if w40.count("r1+r2"):
        return fail("E710=0x40 leftover 2 must park R+1 before leftover 4")
    if w40[0] != "r1" or w40[1] != "r2":
        return fail(f"E710=0x40 expected r1 then r2, got {w40[:4]}")
    print("  sim: E710=0x40 leftover 2 / leftover 4 split")

    # Fast credits 0x80 skips leftover 2/3 — fallback both-steps is OK.
    w80 = cruise_work(0x80, 4)
    if "r1+r2" not in w80:
        return fail("E710=0x80 (no leftover 2/3) must fall back to both steps")
    print("  sim: E710=0x80 fallback keeps both steps on leftover 4")

    mid = fn_span(mp, "static void peek_assemble_r1_mid(void)")
    if not mid:
        return fail("leftover 2/3 must park R+1 in peek_assemble_r1_mid")
    if "assemble_row((u16)(s_ms.row + 1))" not in mid:
        return fail("r1_mid must assemble R+1 (the next 97e3 row, discarded)")
    if "assemble_row((u16)(s_ms.row + 2))" in mid:
        return fail("r1_mid must not assemble R+2 (that is leftover 4)")
    if "s_col_mid" not in mid or "s_stream_mid" not in mid:
        return fail("r1_mid must park col/stream cursors for leftover 4")
    if "s_assemble_peek = 1" not in mid or "s_idol_cur = idol_snap" not in mid:
        return fail("r1_mid must stay peek and restore live cursors")
    if "memcpy(s_stream, s_stream_snap" not in mid:
        return fail("r1_mid must restore stream cursors")

    two = fn_span(mp, "static void peek_assemble_two_ahead(void)")
    if not two:
        return fail("leftover 4 must still call peek_assemble_two_ahead")
    if "s_peek_mid" not in two:
        return fail("two_ahead must resume from leftover-2/3 mid-state")
    if "assemble_row((u16)(s_ms.row + 1))" not in two:
        return fail("two_ahead fallback must still assemble R+1")
    if "assemble_row((u16)(s_ms.row + 2))" not in two:
        return fail("two_ahead must assemble R+2 (the real peek)")
    if two.find("assemble_row((u16)(s_ms.row + 1))") > two.find(
        "assemble_row((u16)(s_ms.row + 2))"
    ):
        return fail("fallback R+1 must run before R+2")
    if "s_peek_maprow = (u16)(s_ms.row + 2)" not in two:
        return fail("cache key must stay row+2")

    upd = fn_span(mp, "void map_script_update(void)")
    if not upd:
        return fail("map_script_update not found")
    if "peek_assemble_r1_mid();" not in upd:
        return fail("leftover 2/3 must call peek_assemble_r1_mid")
    if "peek_assemble_two_ahead();" not in upd:
        return fail("KEEP: leftover 4 still calls peek_assemble_two_ahead")
    if "(s_e711 >> 5) == 2" not in upd or "(s_e711 >> 5) == 3" not in upd:
        return fail("R+1 park must run on leftover 2 or 3")
    if "(s_e711 >> 5) == 4" not in upd:
        return fail("KEEP: leftover 4 still finishes the peek")
    if upd.find("peek_assemble_r1_mid();") > upd.find("peek_assemble_two_ahead();"):
        return fail("leftover 2/3 park must be scheduled before leftover 4")

    dma = fn_span(mp, "static void dma_nt_row(u8 nt_y, const u8 *src, TransferMethod tm)")
    if not dma:
        return fail("dma_nt_row not found")
    if "s_nt[nt_y][x] != src[x]" not in dma:
        return fail("dma_nt_row must compare s_nt before the 24-col CPU OUT")
    if "if (x == PF_COLS)" not in dma and "x == PF_COLS" not in dma:
        return fail("identical wrap/peek rows must skip VDP")
    if "0, PF_COLS" not in dma:
        return fail("KEEP: 9a79 24-col playfield write")
    if "MODE_BAR_COL" not in dma:
        return fail("KEEP: HUD cols 24-31 restore after a real playfield write")

    put = fn_span(hud, "void hud_put_tile(u16 plane, u16 x, u16 y, u8 tid)")
    if not put:
        return fail("hud_put_tile not found")
    if "s_win_tid" not in put or "WINDOW" not in put:
        return fail("WINDOW HUD cells must cache last glyph")
    if "*cell == tid" not in put and "s_win_tid" not in put:
        return fail("unchanged HUD glyphs must skip VDP_setTileMapXY")
    if "hud_win_cache_reset" not in hud:
        return fail("wipe / init must reset the WINDOW glyph cache")

    if re.search(r"VDP_allocateTiles\s*\(", ent) or re.search(
        r"VDP_releaseTiles\s*\(", ent
    ):
        return fail("do not reintroduce VDP_allocateTiles / VDP_releaseTiles")
    if "SPR_setVRAMTileIndex" not in ent or "s_shot_bank" not in ent:
        return fail("KEEP: shot VRAM bank via SPR_setVRAMTileIndex")
    if re.search(r"SHOT_SLOTS\s+2|ENEMY_SLOTS\s+1[0-6]\b", ent):
        return fail("do not shrink spawn/shot pools to fake 60fps")
    if "s_spawn_timer" not in ent or "spawn_from_type" not in ent:
        return fail("KEEP: stream spawn_tick rates")
    if main_c.count("SYS_doVBlankProcess()") != 1:
        return fail("KEEP: one vblank per tick")

    print("ok: leftover 2/3 parks R+1; leftover 4 is one assemble")
    print("ok: identical NT rows skip CPU OUT; HUD WINDOW glyphs dirty-checked")
    print("ok: shot bank / spawn rates / 60Hz loop KEEP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
