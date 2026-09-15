#!/usr/bin/env python3
"""Boss shots leave the exact centre of the red eye lens.

Japan 8ddb copies parent IX+01/+02 after 8a7d Y+=0x10 and 8ac7 xo/yo.
8c15 paints the olhinho at the 8948 cell: SAT Y *before* +0x10, X before
xo/yo. Live SAT is 16px south of that lens.

#139 sat SAT origin on the lens centre. FRAME_LEAD / LIGHT_BAR are 16x16
sprites whose disc/bar centroid is ~(8,8) (objs.png LEAD 7.5,8; bar 7,7),
so the *graphic* sat 8px down-right of the lens — still "near the
olhinhos", and for type 73 that is the bottom of the 16x16 eye.

SAT must be lens_centre - (8,8) so the visible disc sits on the lens.

Measured (charset_tiles.bin / objs.png):
  0xC2 red lens (75-78 phase 3) centroid (3.5, 3.5) in the 8x8.
  type 73/74 2x2 centroid ~(7.5, 7.5).
  FRAME_LEAD disc centroid (7.5, 8.0).

Offset from 8948 origin to SAT:
  73/74: (0, 0)   → disc at origin+(8,8) = 16x16 centre
  75-79: (-4, -4) → disc at origin+(4,4) = 8x8 centre

Collision / other 8ddb (guns, swoop, luster) stay parent XY.

Usage (from zanac-md):
    python tools/test_boss_eye_muzzle.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
PNG = ROOT / "res" / "sprites" / "objs.png"
CHR = ROOT / "res" / "charset_tiles.bin"

FRAME_LEAD = 6
DISC_CX = 8
DISC_CY = 8
LENS8 = 4
LENS16 = 8


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
    """Undo 8a7d +0x10 and 8ac7 xo/yo, then lens centre minus disc (8,8)."""
    x = u8(u8(sat_x) - xo)
    y = u8(u8(sat_y) - yo - 0x10)
    if variant in (73, 74):
        return x, y
    return u8(x - LENS8), u8(y - LENS8)


def disc_on_lens(sat: tuple[int, int], lens: tuple[int, int]) -> bool:
    return (sat[0] + DISC_CX) % 256 == lens[0] and (sat[1] + DISC_CY) % 256 == lens[1]


def tile_centroid_8(tid: int) -> tuple[float, float] | None:
    ct = CHR.read_bytes()
    off = tid * 32
    t = ct[off : off + 32]
    xs = ys = n = 0
    for y in range(8):
        for x in range(4):
            b = t[y * 4 + x]
            for k, p in enumerate(((b >> 4) & 0xF, b & 0xF)):
                if p:
                    xs += x * 2 + k
                    ys += y
                    n += 1
    if not n:
        return None
    return xs / n, ys / n


def main() -> int:
    ent = ENT.read_text(encoding="utf-8")

    muz = fn_span(ent, "static void base_muzzle(const Slot *e, s16 *x, s16 *y)")
    if not muz:
        return fail("base_muzzle must undo 8a7d/8ac7 for the olhinho")
    if "0x10" not in muz or "k_base" not in muz:
        return fail("base_muzzle must subtract Y+0x10 and k_base xo/yo")
    if "+ 8" in muz.replace(" ", "") or "+8" in muz.replace(" ", ""):
        return fail("do not sit SAT on the 16x16 centre (disc would be at the bottom)")
    if "variant != 73 && e->variant != 74" not in muz.replace(" ", "") and (
        "e->variant != 73 && e->variant != 74" not in muz
    ):
        return fail("75-79 SAT is origin-4 (8x8 centre minus disc 8,8)")
    if "- 4" not in muz and "-4" not in muz.replace(" ", ""):
        return fail("8x8 lens: SAT = origin - 4 so disc +8 lands on +4")
    print("  base_muzzle: 73/74 origin; 75-79 origin-4 (lens minus disc 8,8)")

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
    # Eye origin = (x, ypre). 8x8 lens centre +4,+4. SAT = centre - 8.
    ypre, sat_x = 0x40, 0x80
    live_y = u8(u8(ypre + 0x10) + 0xFC)
    live_x = u8(sat_x + 0xFC)
    mx, my = muzzle(75, live_x, live_y, 0xFC, 0xFC)
    lens = (u8(sat_x + LENS8), u8(ypre + LENS8))
    if (mx, my) != (u8(sat_x - LENS8), u8(ypre - LENS8)):
        return fail("type 75 SAT must be eye origin -4,-4, got (%d,%d)" % (mx, my))
    if not disc_on_lens((mx, my), lens):
        return fail("type 75 disc centre must land on 8x8 lens centre")
    if my == live_y:
        return fail("type 75 SAT must not stay on live SAT Y (bottom)")
    # #139 sat SAT on lens centre: disc would appear at live SAT Y.
    old139_y = u8(ypre + LENS8)
    if u8(old139_y + DISC_CY) != live_y:
        return fail("fixture: #139 disc-on-bottom math changed")
    print("  type 75: SAT origin-4; disc on 8x8 lens (not live SAT / #139 +8)")

    mx, my = muzzle(73, sat_x, u8(ypre + 0x10), 0, 0)
    lens73 = (sat_x + LENS16, ypre + LENS16)
    if (mx, my) != (sat_x, ypre):
        return fail("type 73 SAT must be 8948 origin (disc +8 = 16x16 centre)")
    if not disc_on_lens((mx, my), lens73):
        return fail("type 73 disc centre must land on 16x16 eye centre")
    if my == u8(ypre + 0x10):
        return fail("type 73 SAT must not be the bottom of the 16x16 eye")
    old139_y = u8(ypre + LENS16)
    if u8(old139_y + DISC_CY) != u8(ypre + 0x10):
        return fail("fixture: #139 type 73 disc sat on Y+16 bottom")
    print("  type 73: SAT = origin; disc on 16x16 centre, not Y+16 bottom")

    if "base_muzzle" in (fn_span(ent, "static void spawn_swoop(Slot *e, u8 type)") or ""):
        return fail("do not move swoop 8ddb off parent XY")

    if CHR.is_file():
        c2 = tile_centroid_8(0xC2)
        if not c2:
            return fail("charset 0xC2 red lens has no pixels")
        if abs(c2[0] - 3.5) > 0.6 or abs(c2[1] - 3.5) > 0.6:
            return fail("0xC2 lens centroid expected ~(3.5,3.5), got %s" % (c2,))
        print("  charset 0xC2 centroid (%.2f, %.2f) → 8x8 centre 4,4" % c2)

    try:
        from PIL import Image
    except ImportError:
        print("  (Pillow missing; skip objs.png disc centroid)")
        print("ok: boss shots leave the red-eye centre; other 8ddb unchanged")
        return 0
    if PNG.is_file():
        im = Image.open(PNG)
        crop = im.crop((FRAME_LEAD * 16, 0, FRAME_LEAD * 16 + 16, 16))
        xs = ys = n = 0
        for y in range(16):
            for x in range(16):
                p = crop.getpixel((x, y))
                if p:
                    xs += x
                    ys += y
                    n += 1
        if n < 8:
            return fail("FRAME_LEAD disc missing")
        cx, cy = xs / n, ys / n
        if abs(cx - 7.5) > 1.0 or abs(cy - 8.0) > 1.5:
            return fail("FRAME_LEAD centroid expected ~(7.5,8), got (%.2f,%.2f)" % (cx, cy))
        print("  FRAME_LEAD centroid (%.2f, %.2f) → disc offset 8,8" % (cx, cy))

    print("ok: boss shots leave the olhinho centre; other 8ddb unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
