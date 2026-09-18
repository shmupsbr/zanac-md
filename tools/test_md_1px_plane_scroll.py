#!/usr/bin/env python3
"""MD 1px plane camera: VSRAM fine scroll, not TMS 8×8 cell jumps.

Filipe after #156 (tip 6ab711b): residual MSX 8×8 chunkiness, wants
1×1 pixel motion via Genesis VDP scroll registers.

Verify:
  Camera is 1px (row*8 + E711>>5), never snapped to 8.
  E710=0x20 → exactly 1px/tick; cruise 0x34 deltas are 1 or 2, never 8.
  VSRAM is 10-bit, latched in-tick, committed from VInt (vblank port).
  Plane mode (not 2-cell). No horizontal camera.
  KEEP wrap/peek/stamp 8px grid, Original 256×192 letterbox, bolinhas.

No SGDK on this VM — static + numeric locks, not a ROM run.

Usage (from zanac-md):
    python tools/test_md_1px_plane_scroll.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPC = ROOT / "src" / "map_script.c"
MAIN = ROOT / "src" / "main.c"
MODE = ROOT / "src" / "mode.c"
ENT = ROOT / "src" / "entity.c"
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


def camera_px(row: int, base: int, e711: int) -> int:
    return ((row - base) << 3) + (e711 >> 5)


def walk(e710: int, frames: int) -> list[int]:
    e711 = 0
    row = 0
    out: list[int] = []
    for _ in range(frames):
        s = e711 + e710
        if s > 255:
            row += 1
        e711 = s & 0xFF
        out.append(camera_px(row, 0, e711))
    return out


def vsram_word(scroll_px: int, y_off: int = 16) -> int:
    off = (scroll_px + y_off) & 0xFF
    return (-off) & 0x3FF


def main() -> int:
    mapc = MAPC.read_text(encoding="utf-8")
    main_c = MAIN.read_text(encoding="utf-8")
    mode_c = MODE.read_text(encoding="utf-8")
    ent = ENT.read_text(encoding="utf-8")
    opt = OPT.read_text(encoding="utf-8")

    px20 = walk(0x20, 8)
    if px20 != list(range(1, 9)):
        return fail(f"E710=0x20 must be 1px/tick (got {px20})")
    d20 = [b - a for a, b in zip([0] + px20[:-1], px20)]
    if any(d != 1 for d in d20):
        return fail(f"E710=0x20 deltas must all be 1 (got {d20})")
    print("  sim: E710=0x20 is 1px/tick, no 8px step")

    px34 = walk(0x34, 16)
    d34 = [b - a for a, b in zip([0] + px34[:-1], px34)]
    if any(d > 2 or d < 1 for d in d34):
        return fail(f"E710=0x34 must stay 1–2px/tick, never 8 (got {d34})")
    if 8 in d34:
        return fail("E710=0x34 must not emit an 8px cell jump")
    print("  sim: E710=0x34 deltas", d34, "(1–2px, Zanac average)")

    vs = [vsram_word(p) for p in range(10)]
    step = [(vs[i] - vs[i - 1]) & 0x3FF for i in range(1, 10)]
    # Increasing camera → more-negative VSRAM = 0x3FF wrap of -1 each px.
    if any(s != 0x3FF for s in step):
        return fail(f"VSRAM must fine-scroll 1 unit/px (got {step})")
    print("  sim: 10-bit VSRAM walks 1 unit per camera pixel")

    if "VSCROLL_PLANE" not in mapc or "HSCROLL_PLANE" not in mapc:
        return fail("must use plane scroll (1px VSRAM / no H camera)")
    if re.search(r"VDP_setScrollingMode\([^)]*VSCROLL_2CELL", mapc):
        return fail("do not switch BG_B to 2-cell VSCROLL")

    bg = fn_span(mapc, "static void bg_set_vscroll(void)")
    if not bg:
        return fail("bg_set_vscroll not found")
    if "VDP_setVerticalScroll" in bg:
        return fail("do not write VSRAM mid-display from bg_set_vscroll")
    if "s_vsram_b" not in bg or "& 0x3FF" not in bg:
        return fail("bg_set_vscroll must latch 10-bit VSRAM")
    if "s_scroll_px + mode_y_off()" not in bg:
        return fail("camera must stay -(scroll_px + y_off)")

    apply = fn_span(mapc, "void map_script_apply_vscroll(void)")
    if not apply:
        return fail("map_script_apply_vscroll missing")
    if "vsram_write_b" not in apply:
        return fail("VInt apply must write VSRAM")
    if "s_vsram_arm" not in apply:
        return fail("title must be able to disarm VInt VSRAM writes")

    vint = fn_span(main_c, "static void vint_psg(void)")
    if not vint or "map_script_apply_vscroll()" not in vint:
        return fail("vint_psg must commit VSRAM in vblank")
    if vint.find("map_script_apply_vscroll()") > vint.find("sound_tick()"):
        return fail("commit VSRAM before PSG so the plane is ready this frame")

    rst = fn_span(mapc, "static void scroll_speed_reset(u8 target)")
    if not rst or "s_e710 = 0x20" not in rst:
        return fail("scroll_speed_reset must start E710=0x20 (1px from boot)")

    if "tile_wrap_nt_at" not in mapc:
        return fail("KEEP: tile_wrap stamps")
    sat = fn_span(mapc, "static int sat_to_nt(s16 x, s16 y, u8 *col, u8 *row)")
    if not sat or "tile_wrap_nt_at" not in sat:
        return fail("KEEP: sat_to_nt binds to tile_wrap, not wrap(raw)")

    # Original layout: 256×192 + 16px letterbox, not stretched.
    if "y_off = 16" not in mode_c:
        return fail("Original y_off must stay 16 (do not stretch 192→224)")
    if "playfield_h = 192" not in mode_c:
        return fail("Original playfield must stay 192")
    if "VDP_setScreenWidth256" not in mode_c:
        return fail("Original must stay H32 256")
    if "VDP_setWindowHPos(TRUE, 12)" not in mode_c:
        return fail("KEEP: right HUD WINDOW at col 24")

    # Bolinha hard lock (#156 / tip 6ab711b).
    m = re.search(r"#define\s+LEAD_MD_SPEED\s+(\d+)", ent)
    if not m or int(m.group(1)) != 4:
        return fail("HARD LOCK: LEAD_MD_SPEED must stay 4")
    if "lead_md_speed_is_4" not in ent:
        return fail("HARD LOCK: keep LEAD_MD_SPEED==4 compile assert")
    if "LEAD_MD_SPEED (4)" not in opt:
        return fail("HARD LOCK: options.h must still document LEAD_MD_SPEED 4")
    if "VDP_allocateTiles" in mapc:
        return fail("no new VDP_allocateTiles on the scroll path")

    print("ok: 1px MD plane camera + vblank VSRAM; bolinhas / layout KEEP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
