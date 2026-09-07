#!/usr/bin/env python3
"""Type 67 83d8 SAT XOR 0x34 is 0x20 <-> 0x14 (pat 5 small star).

handler_type67 0x839f writes SAT 0x20 / color 0x86, then 0x83d8:
  XOR (IX+03), 0x34   ; 0x20 <-> 0x14
  XOR (IX+04), 0x0c
SAT 0x14 is gfx_sprite_patterns pat 5 (small star). objs.png frame 60
is that pattern baked TMS 15 (same remap source as FRAME_MED_CIRCLE).
Type 67 still remaps 15 -> sat_col nibble (0x86 -> 6).

Usage (from zanac-md):
    python tools/test_type67_sat14.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
PNG = ROOT / "res" / "sprites" / "objs.png"
REBUILD = ROOT / "tools" / "rebuild_sprites.py"

# collision_size_table 0x45C9
K_COL = [
    0x00, 0x00, 0x03, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03, 0x03, 0x05, 0x00, 0x06, 0x06,
    0x01, 0x01, 0x00, 0x00, 0x00, 0x06, 0x00, 0x03, 0x00, 0x00, 0x02, 0x02, 0x04, 0x04, 0x04, 0x04,
]


def hitbox(sat: int) -> tuple[int, int]:
    idx = sat >> 1
    hy = K_COL[idx]
    hx = K_COL[idx + 1]
    return (16 - 2 * hx, 16 - 2 * hy)


def png_frame_hist(i: int) -> dict[int, int]:
    from PIL import Image

    im = Image.open(PNG)
    fr = im.crop((i * 16, 0, (i + 1) * 16, 16))
    hist: dict[int, int] = {}
    for p in fr.getdata():
        hist[p] = hist.get(p, 0) + 1
    return hist


def main() -> int:
    fails = 0
    ent = ENT.read_text(encoding="utf-8")
    reb = REBUILD.read_text(encoding="utf-8")

    if (0x20 ^ 0x34) != 0x14 or (0x14 ^ 0x34) != 0x20:
        print("FAIL: 0x20 XOR 0x34 is not 0x14", file=sys.stderr)
        fails += 1
    else:
        print("  0x20 XOR 0x34 = 0x14; 0x14 XOR 0x34 = 0x20")

    if (0x14 >> 2) != 5:
        print("FAIL: SAT 0x14 is not pat 5", file=sys.stderr)
        fails += 1
    else:
        print("  SAT 0x14 = gfx pat 5 (small star)")

    m = re.search(
        r"static const u8 k_frame_sat\[FRAME_N\] = \{([^}]+)\}",
        ent,
        re.S,
    )
    if not m:
        print("FAIL: k_frame_sat not found", file=sys.stderr)
        return 1
    body = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
    vals = re.findall(r"0x[0-9A-Fa-f]+", body)
    if len(vals) < 61 or int(vals[52], 16) != 0x20:
        print("FAIL: k_frame_sat[52] must stay 0x20", file=sys.stderr)
        fails += 1
    else:
        print("  k_frame_sat[FRAME_MED_CIRCLE] = 0x20")
    if len(vals) < 61 or int(vals[60], 16) != 0x14:
        print(
            f"FAIL: k_frame_sat[60] want 0x14 got {vals[60] if len(vals) > 60 else '?'}",
            file=sys.stderr,
        )
        fails += 1
    else:
        print("  k_frame_sat[FRAME_SMALL_STAR] = 0x14")

    if "#define FRAME_N         61" not in ent:
        print("FAIL: FRAME_N must be 61", file=sys.stderr)
        fails += 1
    if "#define FRAME_SMALL_STAR 60" not in ent:
        print("FAIL: FRAME_SMALL_STAR must be 60", file=sys.stderr)
        fails += 1

    if "(5, 15, False)" not in reb:
        print("FAIL: rebuild_sprites SMALL_STAR bake must be TMS 15", file=sys.stderr)
        fails += 1
    else:
        print("  rebuild_sprites pat 5 bake 15")
    if "(8, 15, False)" not in reb:
        print("FAIL: MED_CIRCLE bake must stay TMS 15", file=sys.stderr)
        fails += 1
    else:
        print("  rebuild_sprites pat 8 bake 15 (not reverted)")

    if "frame_from_sat(e->sat)" not in ent:
        print("FAIL: circle_step must spr_place frame_from_sat after XOR", file=sys.stderr)
        fails += 1
    else:
        print("  circle_step: frame_from_sat after SAT XOR")

    wanted = re.search(
        r"static int xor_cram_wanted\(const Slot \*s\)\s*\{(.*?)^\}",
        ent,
        re.S | re.M,
    )
    if not wanted or "KIND_CIRCLE" in wanted.group(1):
        print("FAIL: type 67 must not CRAM-bind (SAT name walks)", file=sys.stderr)
        fails += 1
    else:
        print("  type 67 not in XOR CRAM walker pool")

    w14, h14 = hitbox(0x14)
    w20, h20 = hitbox(0x20)
    if (w14, h14) != (10, 10):
        print(f"FAIL: SAT 0x14 hitbox {w14}x{h14}, want 10x10", file=sys.stderr)
        fails += 1
    else:
        print("  SAT 0x14: 10x10 (4560 half 3,3)")
    if (w20, h20) != (14, 14):
        print(f"FAIL: SAT 0x20 hitbox {w20}x{h20}, want 14x14", file=sys.stderr)
        fails += 1
    else:
        print("  SAT 0x20: 14x14 (4560 half 1,1)")

    hist60 = png_frame_hist(60)
    if hist60.get(6, 0):
        print("FAIL: FRAME_SMALL_STAR has TMS 6 pixels", hist60, file=sys.stderr)
        fails += 1
    elif hist60.get(15, 0) != 33 or hist60.get(0, 0) != 223:
        print("FAIL: FRAME_SMALL_STAR pattern bits changed", hist60, file=sys.stderr)
        fails += 1
    else:
        print("  objs.png FRAME_SMALL_STAR bake 15 (33 body px)")

    hist52 = png_frame_hist(52)
    if hist52.get(6, 0) or hist52.get(15, 0) != 96:
        print("FAIL: FRAME_MED_CIRCLE bake reverted", hist52, file=sys.stderr)
        fails += 1
    else:
        print("  objs.png FRAME_MED_CIRCLE still bake 15 (96 body px)")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
