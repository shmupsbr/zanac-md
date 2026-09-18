#!/usr/bin/env python3
"""Zanac MD playfield/scenery after #161 (main d1af518).

Filipe: "O cenário tá ruim ainda, mas não se preocupe com os sprites agora."

#159 stretched 24→30 by duplicating whole 8px columns (every 4th source
col twice) and 24→28 in Y. #161 dropped the Y dup (wrap NT skipped rows /
wrap-1 mid-screen band) but kept the X column-dup plus a 10-col PAL0
letter fill. That is repeating/stretched map + black gutter/wrap bars.

Also: H40 on a 32-wide plane wraps cols 32–39 onto 0–7, so leftover
writes punch the left of the stage and the right 8 visible columns
repeat it.

Fix (ZANAC MD scenery only):
  Y stays 1:1 with the 8px wrap/peek grid (y_off 0, no *7/6, no 24→28).
  X is 1:1, centered in H40 (dest = 8 + msx_col, n = 1). No 24→30 dup.
  Gutters 0–7 / 32–63 and wrap NT 24–31 are sky 0x28 (empty stage).
  Plane is 64×32 so H40 cannot wrap.
  Row DMA and stamps share mode_map_dest_cols.

KEEP: MODE_ORIGINAL 256×192 letterbox + HUD; LEAD_MD_SPEED 4; sprites.

Usage (from zanac-md):
    python tools/test_zanac_md_scenery.py
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
    return 8 + msx_col, 1


def define_int(src: str, name: str) -> int | None:
    m = re.search(rf"#define\s+{name}\s+(\d+)", src)
    return int(m.group(1)) if m else None


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

    if define_int(mode_md, "MODE_MD_PF_COLS") != 24:
        return fail("MODE_MD_PF_COLS must be 24 (1:1, not 30)")
    if define_int(mode_md, "MODE_MD_X0") != 8:
        return fail("MODE_MD_X0 must be 8 (center 24 cols in H40)")
    if define_int(mode_md, "MODE_PLANE_COLS") != 64:
        return fail("MODE_PLANE_COLS must be 64 (H40-safe plane)")
    if (8 + 24 + 8) != 40:
        return fail("self-check: 8+24+8 must be H40")

    owned = [None] * 40
    for c in range(24):
        x0, n = dest_range(c)
        if n != 1:
            return fail(f"msx col {c} must occupy exactly 1 H40 col (n={n})")
        if x0 != 8 + c:
            return fail(f"msx col {c} dest must be {8 + c}, got {x0}")
        if owned[x0] is not None:
            return fail(f"dest col {x0} owned twice (column dup)")
        owned[x0] = c
    if any(owned[i] is None for i in range(8, 32)):
        return fail("1:1 centered map must cover dest cols 8-31 uniquely")
    if any(owned[i] is not None for i in list(range(0, 8)) + list(range(32, 40))):
        return fail("gutters 0-7 and 32-39 must not hold duplicated map cols")
    old_30 = []
    for c in range(24):
        a = c * 30 // 24
        b = (c + 1) * 30 // 24
        old_30.extend([c] * (b - a))
    if len(old_30) != 30 or len(set(old_30)) != 24:
        return fail("self-check: 24→30 must duplicate 6 columns")
    if 3 not in [c for c in range(24) if (c + 1) * 30 // 24 - c * 30 // 24 == 2]:
        return fail("self-check: 24→30 dup of col 3")
    print("  sim: 1:1 dest 8-31 unique; 24→30 would dup cols",
          [c for c in range(24) if (c + 1) * 30 // 24 - c * 30 // 24 == 2])

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

    # --- X: 1:1 centered; sky gutters; 64-wide plane ---
    dest = fn_span(mode_c, "void mode_map_dest_cols(u8 msx_col, u8 *x0, u8 *n)")
    if not dest:
        return fail("mode_map_dest_cols not found")
    if "MODE_MD_X0 + msx_col" not in dest and "MODE_MD_X0 + msx_col" not in dest.replace(" ", ""):
        if "MODE_MD_X0" not in dest or "msx_col" not in dest:
            return fail("mode_map_dest_cols must be 1:1 at MODE_MD_X0 + msx_col")
    if "*n = 1" not in dest and "*n=1" not in dest:
        return fail("mode_map_dest_cols n must be 1 (no column dup)")
    if "MODE_MD_PF_COLS / MODE_MSX_PF_COLS" in dest:
        return fail("do not stretch dest = col * 30/24")
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
        return fail("do not dest-sample src[d*24/30] (column dup)")
    if "tile_attr(0x28)" not in md:
        return fail("Zanac MD dma_nt_row must sky-fill H40 gutters (0x28)")
    if "MODE_H40_COLS" not in md:
        return fail("Zanac MD dma_nt_row must write a full H40 row")
    stamp = fn_span(mapc, "static void stamp_vram(u8 msx_col, u8 nt_row, u8 tid)")
    if not stamp or "mode_map_dest_cols" not in stamp:
        return fail("stamp_vram must share dest cols with row DMA")
    fillb = fn_span(mapc, "static void fill_letterbox_b(void)")
    if not fillb:
        return fail("fill_letterbox_b not found")
    if "MODE_H32_COLS" not in fillb:
        return fail("KEEP: Original fill_letterbox_b H32 wrap rows")
    if "MODE_PLANE_COLS" not in fillb or "MODE_MD_X0" not in fillb:
        return fail("Zanac MD fill_letterbox_b must sky-fill wrap + gutters")
    if "tile_attr(0x28)" not in fillb:
        return fail("Zanac MD wrap/gutters must be sky 0x28, not PAL0 letterbox")
    apply = fn_span(mode_c, "void mode_apply_video(void)")
    if not apply:
        return fail("mode_apply_video not found")
    md_apply = apply.split("else")[-1]
    if "VDP_setScreenWidth320" not in md_apply:
        return fail("Zanac MD must stay H40")
    if "VDP_setPlaneSize(64, 32, TRUE)" not in md_apply:
        return fail("Zanac MD must set 64×32 plane (H40 wrap)")
    if "VDP_setWindowOff" not in md_apply:
        return fail("Zanac MD must not keep the Original WINDOW HUD")
    print("  X: 1:1 centered + sky gutters + 64-wide plane; WINDOW off")

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

    print("ok: Zanac MD scenery: Y 1:1, X 1:1 centered, sky gutters, 64-wide plane")
    return 0


if __name__ == "__main__":
    sys.exit(main())
