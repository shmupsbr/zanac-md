#!/usr/bin/env python3
"""Original spr_vis_playfield hides on any letterbox overlap.

MSX SCREEN2 is 256×192. Original mode letterboxes that into MD 256×224
with y_off=16 (rows [0, 16) and [208, 224) are the black bars).

Old clip hid only when the 16px box was fully above (dy+16 <= y0) or
fully below (dy >= y1). A sprite with 1 <= dy <= 15 still painted the
top bar — shots / fire colour-cycle look like blinking dots. MSX had
no bar there.

Hide when [dy, dy+16) overlaps [0, y0) or [y0+192, 224). Primary and
marker/complement both go through spr_vis_playfield on their own box.
Draw-only: do not change SAT / collision Y or cull in screen Y.

Ship sits on the 192 bar (KEEP stored 0xB8 / white Y+2) instead of
hiding at the bottom.

KEEP: HUD #126 playfield dash / hbar MSX 23; type44 44BA ship hit;
palette #120; wrap/peek two-ahead; 4BDF; TITLE_MD_Y=40; fire ABC defaults.

Usage (from zanac-md):
    python tools/test_spr_vis_letterbox.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
PLY = ROOT / "src" / "player.c"
HUD = ROOT / "inc" / "hud.h"
HUD_C = ROOT / "src" / "hud.c"
TITLE = ROOT / "inc" / "title_md.h"
OPT = ROOT / "src" / "options.c"
MAP = ROOT / "src" / "map_script.c"
PAL = ROOT / "inc" / "map_script.h"

Y0 = 16
Y1 = Y0 + 192  # 208
SCREEN_H = 224
SPR_W = 16


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


def overlaps(a0: int, a1: int, b0: int, b1: int) -> bool:
    return a0 < b1 and a1 > b0


def spr_vis_playfield(dy: int, want_vis: bool = True) -> bool:
    """Original Y clip. Hide on any overlap with [0, y0) or [y1, 224)."""
    if not want_vis:
        return False
    box0, box1 = dy, dy + SPR_W
    if overlaps(box0, box1, 0, Y0) or overlaps(box0, box1, Y1, SCREEN_H):
        return False
    # Fully above / below the 224 is also off the TMS 192.
    if box1 <= Y0 or box0 >= Y1:
        return False
    return True


def main() -> int:
    # --- Documented clip: any letterbox overlap hides ---
    # Fully in the 192 (flush with each edge).
    if not spr_vis_playfield(Y0):
        return fail("dy=y0 (16) occupies [16, 32) — playfield, must show")
    if not spr_vis_playfield(Y1 - SPR_W):
        return fail("dy=192 occupies [192, 208) — playfield, must show")
    if not spr_vis_playfield(100):
        return fail("dy=100 is mid-playfield, must show")

    # Top letterbox: y0-15 < dy < y0  (and dy=0 / negative).
    for dy in range(Y0 - 15, Y0):
        if spr_vis_playfield(dy):
            return fail(f"dy={dy} overlaps [0, {Y0}), must hide")
    if spr_vis_playfield(0):
        return fail("dy=0 occupies [0, 16) — the top bar, must hide")
    if spr_vis_playfield(-8):
        return fail("dy=-8 occupies [-8, 8) — overlaps [0, 16), must hide")
    if spr_vis_playfield(-16):
        return fail("dy=-16 is fully above the playfield, must hide")

    # Bottom letterbox: any pixel at screen Y >= y0+192.
    if spr_vis_playfield(Y1 - SPR_W + 1):
        return fail("dy=193 occupies [193, 209) — overlaps [208, 224), must hide")
    if spr_vis_playfield(200):
        return fail("dy=200 occupies [200, 216) — SAT 0xB8 leak into the bar")
    if spr_vis_playfield(Y1):
        return fail("dy=208 is fully in the bottom bar, must hide")
    if spr_vis_playfield(220):
        return fail("dy=220 overlaps [208, 224), must hide")

    print("  sim: hide on overlap with [0, 16) or [208, 224); show in the 192")

    # --- C: intersection, not fully-outside-only ---
    ent = ENT.read_text(encoding="utf-8")
    ply = PLY.read_text(encoding="utf-8")
    vis = fn_span(
        ent, "static void spr_vis_playfield(Sprite *sp, s16 dx, s16 dy, int want_vis)"
    )
    if not vis:
        return fail("spr_vis_playfield not found")
    if "dy < y0 || dy + (s16)MODE_SPR_W > y1" not in vis:
        return fail("spr_vis_playfield must hide when the box intersects a letterbox")
    if "dy + (s16)MODE_SPR_W <= y0 || dy >= y1" in vis:
        return fail("old fully-outside clip still leaks dy=1..15 into the top bar")
    if "mode_hud_overlap(dx, MODE_SPR_W)" not in vis:
        return fail("KEEP: spr_vis_playfield still hides on HUD overlap")
    print("  spr_vis_playfield: hide on letterbox overlap (and HUD)")

    sync = fn_span(ent, "static void spr_sync(Slot *s)")
    if not sync:
        return fail("spr_sync not found")
    if "spr_vis_playfield(s->spr, dx, dy, 1)" not in sync:
        return fail("primary must clip via spr_vis_playfield on its own box")
    if "spr_vis_playfield(s->mspr, mdx, mdy, 1)" not in sync:
        return fail("marker/complement must clip via spr_vis_playfield on its own box")
    if re.search(r"spr_vis_playfield\(\s*s->mspr,\s*dx,\s*dy", sync):
        return fail("complement vis must not use the primary draw box")
    print("  spr_sync: primary and marker both use spr_vis_playfield")

    # Fire / shots share spr_vis_playfield (colour-cycle dots).
    if "spr_vis_playfield(f->spr, fdx, mode_draw_y(f->y)" not in ent:
        return fail("fire sprites must reuse spr_vis_playfield")
    print("  fire: spr_vis_playfield on mode_draw_y")

    # Draw-only: no screen-Y cull in 4898.
    xy = fn_span(ent, "static int step_88_4898(Slot *e)")
    if not xy or "(u8)e->y >= 0xD0" not in xy or "(u8)e->x >= 0xD1" not in xy:
        return fail("do not cull 4898 in screen Y; stay unsigned Y>=0xD0 / X>=0xD1")
    if "letterbox is" not in ent or "do not cull in screen Y" not in ent:
        return fail("4898 comment must keep letterbox draw-only / no screen-Y cull")
    print("  KEEP: 4898 sim Y; letterbox is draw-only")

    # Ship: sit on the 192 (KEEP), hide if a box still intersects.
    if "max_y = 0xB8" not in ply or "min_y = 0x1E" not in ply:
        return fail("KEEP: ship stored Y 0x1E..0xB8 (7640)")
    if "dy = (s16)(y1 - SHIP_H)" not in ply:
        return fail("KEEP: ship draw sits on the 192 letterbox")
    if "cdy = (s16)(dy + 2)" not in ply:
        return fail("KEEP: complement is white Y+2 (7735)")
    show = fn_span(ply, "static void show_ship(int vis)")
    if not show or "dy < y0 || dy + SHIP_H > y1" not in show:
        return fail("show_ship must hide white+black on letterbox overlap")
    if "dy + SHIP_H <= y0 || dy >= y1" in (show or ""):
        return fail("show_ship still uses the fully-outside clip")
    print("  ship: stored 0xB8; sit on bar; hide on leftover letterbox overlap")

    # --- KEEP locks (do not revert adjacent playtest work) ---
    hud_h = HUD.read_text(encoding="utf-8")
    hud_c = HUD_C.read_text(encoding="utf-8")
    if "HUD_CLOSE_HBAR_ROW   25" in hud_h:
        return fail("KEEP HUD #126: closing hbar must not sit in the letterbox")
    if "hud_hbar(HUD_CLOSE_HBAR_ROW)" not in hud_c and "hud_hbar(23)" not in hud_c:
        return fail("KEEP HUD #126: closing gray hbar at MSX 23")
    print("  KEEP: HUD #126 playfield dash / hbar MSX 23")

    if "Type 44 KIND_GROUND is 44BA" not in ent and "82ff JP 44BA" not in ent:
        return fail("KEEP: type44 ship hit is 44BA")
    print("  KEEP: type44 44BA ship hit")

    pal = PAL.read_text(encoding="utf-8")
    if "TMS_GAME_RGB_3" not in pal or "0x60E060" not in pal:
        return fail("KEEP: palette #120 TMS 3 stays V9938 light green")
    print("  KEEP: palette #120")

    mp = MAP.read_text(encoding="utf-8")
    if "assemble_row((u16)(s_ms.row + 1))" not in mp:
        return fail("KEEP: wrap/peek leftover-4 first stream step")
    if "assemble_row((u16)(s_ms.row + 2))" not in mp:
        return fail("KEEP: wrap/peek leftover-4 two-ahead")
    print("  KEEP: wrap/peek two-ahead")

    if "0x4BDF" not in hud_c and "4BDF" not in hud_c:
        return fail("KEEP: 4BDF HUD border")
    print("  KEEP: 4BDF")

    title = TITLE.read_text(encoding="utf-8")
    if "#define TITLE_MD_Y          40" not in title:
        return fail("KEEP: TITLE_MD_Y=40")
    print("  KEEP: TITLE_MD_Y=40")

    opt = OPT.read_text(encoding="utf-8")
    if not re.search(
        r"s_bind\[3\]\s*=\s*\{\s*FIRE_ROLE_BOTH\s*,\s*FIRE_ROLE_PRIMARY\s*,\s*FIRE_ROLE_SECONDARY",
        opt,
    ):
        return fail("KEEP: fire ABC defaults A=both B=primary C=secondary")
    print("  KEEP: fire ABC defaults")

    print("ok: Original spr_vis_playfield hides on letterbox overlap")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
