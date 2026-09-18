#!/usr/bin/env python3
"""Zanac MD mid-screen duplicate/broken garbage after #159+#160.

Filipe after 94b594b: "Tem coisa saindo duplicada e quebrada no meio
da tela." Root cause was the 24→28 nametable row-dup plus a *224/192
camera: wrap NT skipped plane rows, wrap-1 overwrote live cells, and
row DMA sampled dest[d]=src[d*24/30] while stamps used src→dest.

Fix (ZANAC MD only):
  Y 1:1 with the 8px wrap/peek grid (y_off 0, no *7/6, no 24→28).
  X still 24→30 via mode_map_dest_cols (row DMA and stamps agree).
  Leftover H40 cols 30-39 / NT 24-31 letter-filled (no title leftover).

KEEP: MODE_ORIGINAL 256×192 letterbox + HUD; LEAD_MD_SPEED 4.

Usage (from zanac-md):
    python tools/test_zanac_md_mid_screen.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODE_C = ROOT / "src" / "mode.c"
MODE_H = ROOT / "inc" / "mode.h"
MODE_MD = ROOT / "inc" / "mode_md.h"
MAPC = ROOT / "src" / "map_script.c"
ENT = ROOT / "src" / "entity.c"
HUD = ROOT / "src" / "hud.c"


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


def wrap_nt(scroll_px: int, y_off: int) -> int:
    off = (scroll_px + y_off) & 0xFF
    py = (y_off - off) & 0xFF
    return py >> 3


def wrap_nt_76(scroll_px: int) -> int:
    off = (scroll_px * 224 // 192) & 0xFF
    py = (0 - off) & 0xFF
    return py >> 3


def dest_range(msx_col: int) -> tuple[int, int]:
    a = msx_col * 30 // 24
    b = (msx_col + 1) * 30 // 24
    return a, b - a


def main() -> int:
    mode_c = MODE_C.read_text(encoding="utf-8")
    mode_h = MODE_H.read_text(encoding="utf-8")
    mode_md = MODE_MD.read_text(encoding="utf-8")
    mapc = MAPC.read_text(encoding="utf-8")
    ent = ENT.read_text(encoding="utf-8")
    hud = HUD.read_text(encoding="utf-8")

    # --- numeric: 1:1 wrap vs the 7/6 skip that parked garbage mid-screen ---
    if wrap_nt(0, 16) != 0 or wrap_nt(8, 16) != 31:
        return fail("Original wrap(0)=0 wrap(8)=31 (y_off 16)")
    if wrap_nt(0, 0) != 0 or wrap_nt(8, 0) != 31:
        return fail("Zanac MD wrap must match Original 1:1 (y_off 0 → wrap(8)=31)")
    if wrap_nt_76(8) != 30:
        return fail("self-check: 7/6 camera at scroll=8 must be the NT-30 skip")
    print("  sim: wrap(8)=31 both modes; 7/6 camera would skip to NT 30")

    owned = [None] * 30
    for c in range(24):
        x0, n = dest_range(c)
        if n not in (1, 2):
            return fail(f"msx col {c} must occupy 1 or 2 H40 dest cols (n={n})")
        for i in range(n):
            owned[x0 + i] = c
    if any(v is None for v in owned):
        return fail("24→30 dest map must cover cols 0-29")
    old_dma = [d * 24 // 30 for d in range(30)]
    disagree = [d for d in range(30) if old_dma[d] != owned[d]]
    if 1 not in disagree:
        return fail("self-check: dest[d]=src[d*24/30] must disagree with stamps")
    print("  sim: stamp src→dest covers 30 cols; old dest-sample disagreed at",
          disagree)

    # --- Y must not scale or duplicate rows ---
    dy = fn_span(mode_c, "s16 mode_draw_y(s16 y)")
    if not dy or "y + (s16)s_cur->y_off" not in dy:
        return fail("mode_draw_y must stay sim Y + y_off")
    if "MODE_MD_H" in dy:
        return fail("mode_draw_y must not * MODE_MD_H / MODE_MSX_H")
    cam = fn_span(mode_c, "u16 mode_camera_off(u16 scroll_px)")
    if not cam or "scroll_px + s_cur->y_off" not in cam:
        return fail("mode_camera_off must stay scroll_px + y_off")
    if "MODE_MD_H" in (cam or "") or "* 224" in (cam or ""):
        return fail("mode_camera_off must not *224/192")
    if "mode_map_dup_row" in mode_c or "mode_map_dup_row" in mode_h:
        return fail("mode_map_dup_row must not exist (24→28 was the mid-screen dup)")
    if "s_wrap_dup" in mapc or "s_peek_dup" in mapc:
        return fail("wrap/peek must not DMA wrap-1 duplicate rows")
    boot = fn_span(mapc, "static void flush_boot_playfield(void)")
    if not boot:
        return fail("flush_boot_playfield not found")
    if "% 6" in boot or "md_y" in boot:
        return fail("flush_boot must not duplicate 24→28 rows")
    lin = fn_span(mapc, "static void e800_flush_linear(void)")
    if not lin:
        return fail("e800_flush_linear not found")
    if "% 6" in lin or "md_y" in lin:
        return fail("e800_flush_linear must not duplicate 24→28 rows")
    print("  Y: 1:1 draw/camera; no 24→28 row dup; no wrap-1 DMA")

    # --- X stretch: row DMA agrees with stamps; leftover H40 filled ---
    dma = fn_span(mapc, "static void dma_nt_row(u8 nt_y, const u8 *src, TransferMethod tm)")
    if not dma:
        return fail("dma_nt_row not found")
    orig, _, md = dma.partition("else")
    if "VDP_setTileMapDataRow(BG_B, dst, nt_y, 0, PF_COLS, play_tm)" not in orig:
        return fail("KEEP: Original dma_nt_row 24-col write at x=0")
    if "MODE_BAR_COL" not in orig or "MODE_BAR_W" not in orig:
        return fail("KEEP: Original dma_nt_row HUD cols 24-31 restore")
    if "mode_map_dest_cols" not in md:
        return fail("Zanac MD row DMA must use mode_map_dest_cols (same as stamps)")
    if "d * MODE_MSX_PF_COLS / MODE_MD_PF_COLS" in md:
        return fail("do not dest-sample src[d*24/30] (disagrees with stamps)")
    if "MODE_H40_COLS" not in md:
        return fail("Zanac MD dma_nt_row must letter-fill leftover H40 cols")
    stamp = fn_span(mapc, "static void stamp_vram(u8 msx_col, u8 nt_row, u8 tid)")
    if not stamp or "mode_map_dest_cols" not in stamp:
        return fail("stamp_vram must keep 24→30 dest cols")
    fillb = fn_span(mapc, "static void fill_letterbox_b(void)")
    if not fillb:
        return fail("fill_letterbox_b not found")
    if "MODE_H32_COLS" not in fillb:
        return fail("KEEP: Original fill_letterbox_b H32 wrap rows")
    if "MODE_H40_COLS" not in fillb or "MODE_MD_PF_COLS" not in fillb:
        return fail("Zanac MD fill_letterbox_b must clear wrap + cols 30-39")
    apply = fn_span(mode_c, "void mode_apply_video(void)")
    if not apply:
        return fail("mode_apply_video not found")
    md_apply = apply.split("else")[-1]
    if "VDP_setScreenWidth320" not in md_apply:
        return fail("Zanac MD must stay H40")
    if "load_letter_tile" not in md_apply:
        return fail("Zanac MD must load the PAL0 letter tile (leftover fill)")
    if "VDP_setWindowOff" not in md_apply:
        return fail("Zanac MD must not keep the Original WINDOW HUD")
    print("  X: 24→30 dest-cols + H40 leftover letter fill; WINDOW off")

    # --- Original / Enhanced locks ---
    if "y_off = 16" not in mode_c:
        return fail("Original y_off must stay 16")
    if "VDP_setScreenWidth256" not in mode_c:
        return fail("Original must stay H32 256")
    if "VDP_setWindowHPos(TRUE, 12)" not in mode_c:
        return fail("KEEP: right HUD WINDOW at col 24")
    letter = fn_span(mode_c, "void mode_draw_letterbox(void)")
    if not letter or "if (s_mode != MODE_ORIGINAL)" not in letter:
        return fail("mode_draw_letterbox must stay Original-only")
    hud_init = fn_span(hud, "void hud_init(void)")
    if not hud_init or "mode_get() != MODE_ORIGINAL" not in hud_init:
        return fail("hud_init must stay Original-only")
    m = re.search(r"#define\s+LEAD_MD_SPEED\s+(\d+)", ent)
    if not m or int(m.group(1)) != 4:
        return fail("HARD LOCK: LEAD_MD_SPEED must stay 4")
    if "lead_md_speed_is_4" not in ent:
        return fail("HARD LOCK: keep LEAD_MD_SPEED==4 compile assert")
    if "VDP_allocateTiles" in mapc:
        return fail("no VDP_allocateTiles on the map path")
    if "MODE_MD_H_INCLUDED" not in mode_md:
        return fail("KEEP: include guard MODE_MD_H_INCLUDED (not MODE_MD_H)")
    print("  KEEP: Original letterbox/HUD/H32; LEAD_MD_SPEED 4")

    print("ok: Zanac MD mid-screen dup/garbage: Y 1:1, X 24→30 dest-cols")
    return 0


if __name__ == "__main__":
    sys.exit(main())
