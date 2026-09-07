#!/usr/bin/env python3
"""MD fine VSCROLL is an intentional enhancement (not MSX 8px steps).

Japan TMS nametable has no VSCROLL: 97e3 assembles one row on E711 carry.
This port keeps that assemble, then slides the plane with E711>>5 so
cruise E710=0x20 is 1px/tick.

Do not snap s_scroll_px to 8. KEEP wrap/peek/stamp binding from the
post-#98 / msx-divergences baseline:

  tile_wrap stamps (scroll&~7)
  97e3 DMA wrap(pre-carry) RAW
  peek only after real 97e3
  commit_wrap after entity punches
  24-col playfield write (col 0 included)

Usage (from zanac-md):
    python tools/test_fine_scroll_vscroll.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPC = ROOT / "src" / "map_script.c"
GAME = ROOT / "src" / "game.c"


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


def scroll_px(row: int, base: int, e711: int) -> int:
    return ((row - base) << 3) + (e711 >> 5)


def main() -> int:
    mapc = MAPC.read_text(encoding="utf-8")
    game = GAME.read_text(encoding="utf-8")

    # Pixel VSCROLL, not 8px snap.
    if not re.search(
        r"s_scroll_px = \(u16\)\(\(\(u16\)\(s_ms\.row - s_scroll_base\) << 3\)\s*"
        r"\+\s*\(s_e711 >> 5\)\)",
        mapc,
    ):
        return fail("s_scroll_px must stay (row-base)*8 + (E711>>5)")
    if re.search(r"s_scroll_px\s*&=\s*(~7|0xFFF8)", mapc):
        return fail("do not snap s_scroll_px to 8px (that is TMS, not MD fine scroll)")
    if "s_e710 = 0x20" not in mapc:
        return fail("E710 start must stay 0x20 (1px/tick at E711>>5)")

    bg = fn_span(mapc, "static void bg_set_vscroll(void)")
    if not bg:
        return fail("bg_set_vscroll not found")
    if "s_scroll_px & 0xFFF8" in bg or "s_scroll_px & ~7" in bg:
        return fail("bg_set_vscroll must use raw s_scroll_px, not tile snap")
    if "s_scroll_px + mode_y_off()" not in bg:
        return fail("VSCROLL must be -(scroll_px + y_off)")

    # Sub-tile leftover: E710=0x20 walks 1px for 8 frames then carry.
    px = [scroll_px(0, 0, (i * 0x20) & 0xFF) for i in range(8)]
    if px != list(range(8)):
        return fail(f"E710=0x20 must be 1px/tick (got {px})")
    print("  sim: E710=0x20 is 1px/tick for 8 frames")

    # KEEP: tile_wrap for stamps, wrap(pre) for 97e3.
    if "tile_wrap_nt_at" not in mapc:
        return fail("KEEP: tile_wrap_nt_at for 8948/87e2/88ed stamps")
    sat = fn_span(mapc, "static int sat_to_nt(s16 x, s16 y, u8 *col, u8 *row)")
    if not sat or "tile_wrap_nt_at" not in sat:
        return fail("sat_to_nt must bind stamps to tile_wrap, not wrap(raw) peek")
    pre = fn_span(mapc, "static void scroll_precompute(u16 map_row)")
    if not pre or "hidden_wrap_nt_at(s_scroll_px)" not in pre:
        return fail("97e3 DMA must stay wrap(pre) RAW")
    if "s_scroll_px & 0xFFF8" in (pre or ""):
        return fail("97e3 must not DMA tile_wrap (that is stamp binding)")

    upd = fn_span(mapc, "void map_script_update(void)")
    if not upd:
        return fail("map_script_update not found")
    if "peek_next_row" not in upd:
        return fail("peek after real 97e3 was reverted")
    # Peek stays inside !s_skip_precompute (cmd 9 must not peek).
    if "if (!s_skip_precompute)" not in upd:
        return fail("cmd 9 must still skip peek")
    block = re.search(r"if \(!s_skip_precompute\)\s*\{(.*?)\n                \}", upd, re.S)
    if not block or "peek_next_row" not in block.group(1):
        return fail("peek must stay inside the real-97e3 block")
    if "scroll_precompute" not in block.group(1):
        return fail("97e3 must stay inside the same block as peek")

    if "void map_script_commit_wrap(void)" not in mapc:
        return fail("KEEP: commit_wrap after entity punches")
    if "map_script_commit_wrap" not in game:
        return fail("game_update must still commit_wrap after entities")
    commit = fn_span(mapc, "void map_script_commit_wrap(void)")
    if not commit or "s_peek_line" not in commit:
        return fail("commit_wrap must flush deferred peek (not mid-carry DMA)")
    if "peek_assemble_row" not in mapc:
        return fail("peek assemble must be spannable onto leftover 4")
    if "s_e711 >> 5) == 4" not in mapc and "(s_e711 >> 5) == 4" not in mapc:
        return fail("pre-assemble peek on leftover 4 (quiet), not on carry")

    dma = fn_span(mapc, "static void dma_nt_row(u8 nt_y, const u8 *src, TransferMethod tm)")
    if not dma:
        return fail("dma_nt_row not found")
    if "PF_COLS" not in dma or "MODE_H32_COLS" in dma.split("play_tm")[0][-80:]:
        pass
    if "0, PF_COLS" not in dma:
        return fail("KEEP: 24-col playfield write from col 0")

    print("ok: fine VSCROLL + wrap/peek/stamp/24-col KEEP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
