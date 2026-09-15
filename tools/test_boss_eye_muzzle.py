#!/usr/bin/env python3
"""Boss shots spawn from the red eye (olhinho), not live SAT (sprite bottom).

Japan 8ddb copies parent IX+01/+02 after 8a7d Y+=0x10 and 8ac7 xo/yo.
8c15 paints the olhinho at the 8948 cell: SAT Y *before* +0x10, X before
xo/yo (H = SAT_X-0x20). Live SAT is therefore 16px south of the lens —
the bottom of the 16x16 nametable sprite (73/74 2x2) or two tiles below
the 8x8 0xC2 lens (75-78).

MD must undo that arm transform in base_fire only, then sit on the lens
centre. Collision / other 8ddb (guns, swoop, luster) stay parent XY.

Usage (from zanac-md):
    python tools/test_boss_eye_muzzle.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"


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


def u8(n: int) -> int:
    return n & 0xFF


def muzzle(variant: int, sat_x: int, sat_y: int, xo: int, yo: int) -> tuple[int, int]:
    """Undo 8a7d +0x10 and 8ac7 xo/yo, then lens centre."""
    x = u8(u8(sat_x) - xo)
    y = u8(u8(sat_y) - yo - 0x10)
    cx = cy = 8 if variant in (73, 74) else 4
    return u8(x + cx), u8(y + cy)


def main() -> int:
    ent = ENT.read_text(encoding="utf-8")

    muz = fn_span(ent, "static void base_muzzle(const Slot *e, s16 *x, s16 *y)")
    if not muz:
        return fail("base_muzzle must undo 8a7d/8ac7 for the olhinho")
    if "0x10" not in muz or "k_base" not in muz:
        return fail("base_muzzle must subtract Y+0x10 and k_base xo/yo")
    if "variant == 73 || e->variant == 74" not in muz.replace(" ", "") and (
        "e->variant == 73 || e->variant == 74" not in muz
    ):
        return fail("73/74 2x2 lens centre is +8; 75-79 8x8 is +4")
    print("  base_muzzle: undo +0x10 and xo/yo; 2x2 +8 / 1x1 +4")

    fire = fn_span(ent, "static void base_fire(Slot *e)")
    if not fire:
        return fail("base_fire not found")
    if "base_muzzle(e, &x, &y)" not in fire:
        return fail("base_fire must spawn from base_muzzle, not live SAT")
    if re.search(r"s16 x = e->x;\s*\n\s*s16 y = e->y;", fire):
        return fail("base_fire still copies live SAT (bottom of sprite)")
    if "aim_4c91(x, y)" not in fire:
        return fail("type 78 aim must use the eye, not live SAT")
    if "spawn_frag(x, y," not in fire:
        return fail("children still spawn_frag at muzzle XY")
    print("  base_fire: muzzle XY for every variant 73-79")

    gun = fn_span(ent, "static void gun_fire(Slot *e)")
    if not gun or "spawn_child_dir((s16)(e->x + 8), e->y, stype, dir)" not in gun:
        return fail("do not retarget loga peak shots (X+8 stays)")
    print("  KEEP: gun_fire loga peak X+8")

    # Type 75: yo=0xFC xo=0xFC. Arm: Y' = ypre+0x10+(-4), X' = x+(-4).
    # Eye origin = (x, ypre). Centre +4,+4.
    ypre, sat_x = 0x40, 0x80
    live_y = u8(u8(ypre + 0x10) + 0xFC)
    live_x = u8(sat_x + 0xFC)
    mx, my = muzzle(75, live_x, live_y, 0xFC, 0xFC)
    if (mx, my) != (u8(sat_x + 4), u8(ypre + 4)):
        return fail("type 75 muzzle must be eye origin +4,+4, got (%d,%d)" % (mx, my))
    if my == live_y:
        return fail("type 75 muzzle must not stay on live SAT Y (bottom)")
    print("  type 75: live SAT is 12px below eye; muzzle is lens centre")

    mx, my = muzzle(73, sat_x, u8(ypre + 0x10), 0, 0)
    if (mx, my) != (sat_x + 8, ypre + 8):
        return fail("type 73 2x2 centre must be +8,+8 from 8948 cell")
    if my == u8(ypre + 0x10):
        return fail("type 73 muzzle must not be the bottom of the 16x16 eye")
    print("  type 73: 16x16 eye centre, not Y+16 bottom edge")

    if "base_muzzle" in (fn_span(ent, "static void spawn_swoop(Slot *e, u8 type)") or ""):
        return fail("do not move swoop 8ddb off parent XY")
    print("ok: boss shots leave the olhinho; other 8ddb unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
