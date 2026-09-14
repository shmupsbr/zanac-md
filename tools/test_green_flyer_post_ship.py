#!/usr/bin/env python3
"""Green flyer is type 44 (KIND_GROUND, sat_col 0x83) — must 44BA.

Japan v1 (zanac-re / SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  handler_type44_ground_structure 0x82d0:
    +04 = 0x83 (TMS colour 3). After palette #120 that nibble is
    V9938 light green (1,6,1)/(3,7,3) — the green flying plane.
    SAT 0x40 / marker 0x44. 82f9 CALL 4898, 82fc CALL 71f6,
    82ff JP 44BA (ship 44D4 then shots 44F9).

  handler_type22_veybar 0x7d25: +04 = 0x83 (same TMS 3 green stripe).
    7d89 JP 44BA. SAT 0x84.

  Types 16/17 luster are 0x8E (TMS 14 gray). Type 18 is 0x8B yellow.

Port hole: collide_player skipped KIND_GROUND and post_flags(44) was
POST_SHOT only (44CA). Japan never calls 44CA for type 44 (8806/8b7a
only). spawn_type_list is ~25% 0x2C, so the green plane is the common
flyer that passed through the ship.

4560 SAT vs SAT: SAT 0x38 ship half 4,4 => 8x8; SAT 0x40 plane
half 2,1 => 14x12. Same SAT XY overlaps. Collision never uses
mode_draw_x (EC is draw-only).

Usage (from zanac-md):
    python tools/test_green_flyer_post_ship.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
PAL = ROOT / "inc" / "map_script.h"
SPAWN = ROOT / "src" / "data" / "spawn_table.c"
ASM_CANDIDATES = (
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    Path.home() / "zanac-re" / "source" / "zanac.asm",
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
)


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


def c_array(src: str, name: str) -> list[int] | None:
    m = re.search(rf"static const u8 {name}\[128\] = \{{([^}}]+)\}}", src)
    if not m:
        return None
    return [int(x, 0) for x in m.group(1).split(",") if x.strip()]


def hitbox(col: list[int], sat: int, x: int, y: int) -> tuple[int, int, int, int]:
    idx = sat >> 1
    hy = min(col[idx], 7)
    hx = min(col[(idx + 1) & 0xFF] if idx + 1 < len(col) else 7, 7)
    return (x + hx, y + hy, 16 - 2 * hx, 16 - 2 * hy)


def aabb(ax, ay, aw, ah, bx, by, bw, bh) -> bool:
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def main() -> int:
    ent = ENT.read_text(encoding="utf-8")
    pal = PAL.read_text(encoding="utf-8")
    spawn = SPAWN.read_text(encoding="utf-8")

    if "TMS_GAME_RGB_3" not in pal or "0x60E060" not in pal:
        return fail("palette #120 TMS 3 must stay V9938 light green")
    print("  KEEP: palette #120 TMS 3 = 0x60E060")

    # spawn_type_list: 0x2C = 44 is the common green flyer
    nums = [int(x, 0) for x in re.findall(r"0x[0-9A-Fa-f]+", spawn.split("{", 1)[1].split("}", 1)[0])]
    n44 = sum(1 for n in nums if n == 0x2C)
    if n44 < 4:
        return fail(f"spawn_type_list must keep type 44 (0x2C); found {n44}")
    print(f"  spawn_type_list: {n44}x type 44 (0x2C)")

    gf = fn_span(ent, "static void spawn_ground_fall(Slot *e, u8 type, s16 x, s16 y, u16 dest)")
    if not gf:
        return fail("spawn_ground_fall not found")
    if "e->sat_col = 0x83" not in gf:
        return fail("type 44 +04 must stay 0x83 (82f1, TMS 3 green)")
    if "e->kind = KIND_GROUND" not in gf:
        return fail("type 44 stays KIND_GROUND")
    if "FRAME_PLANE" not in gf:
        return fail("type 44 visual is FRAME_PLANE SAT 0x40")
    print("  type 44: KIND_GROUND sat_col 0x83 FRAME_PLANE")

    lust = fn_span(ent, "static void spawn_luster(Slot *e, u8 type)")
    if not lust:
        return fail("spawn_luster not found")
    if "e->sat_col = 0x8E" not in lust:
        return fail("luster 16/17 stay 0x8E (gray, not the green flyer)")
    if "e->sat_col = 0x8B" not in lust:
        return fail("luster 18 stays 0x8B (yellow yo-yo)")
    print("  luster 16/17 0x8E gray; 18 0x8B yellow (not the green flyer)")

    vey = fn_span(ent, "static void spawn_veybar(Slot *e, u8 type)")
    if not vey or "e->sat_col = fast ? 0x89 : 0x83" not in vey:
        return fail("veybar 22/23 stay sat_col 0x83 (also TMS 3 green)")
    print("  veybar 22/23: sat_col 0x83 (green stripe, also 44BA)")

    pf = fn_span(ent, "static u8 post_flags(u8 t)")
    if not pf:
        return fail("post_flags not found")
    # Type 44 must not sit on the 44CA POST_SHOT-only list.
    ca = re.search(
        r"if \(t == 69 \|\| t == 70 \|\| t == 71 \|\| t == 81 \|\| t == 82",
        pf,
    )
    if not ca:
        return fail("44CA list must start at 69/70/71 (type 44 is 44BA)")
    if re.search(r"if \(t == 44 \|\|", pf):
        return fail("post_flags must not 44CA-gate type 44")
    if "return (u8)(POST_SHOT | POST_SHIP);" not in pf:
        return fail("default post_flags must stay 44BA (shot+ship)")
    print("  post_flags: type 44 falls through to 44BA POST_SHOT|POST_SHIP")

    col = fn_span(ent, "static void collide_player(void)")
    if not col:
        return fail("collide_player not found")
    if "player_dead() || player_is_over()" not in col:
        return fail("collide_player must skip dead/over")
    if re.search(r"if\s*\(\s*e->kind == KIND_GROUND\s*\)", col):
        return fail("collide_player must not skip KIND_GROUND (82ff 44BA)")
    if "KIND_VEYBAR" in col:
        return fail("collide_player must not skip KIND_VEYBAR")
    if "KIND_LUSTER" in col:
        return fail("collide_player must not skip KIND_LUSTER")
    if "player_hit()" not in col:
        return fail("hostile overlap must still player_hit (453E)")
    print("  collide_player: type 44 / veybar / luster enter 4560")

    sizes = c_array(ent, "k_col_size")
    if not sizes or len(sizes) != 128:
        return fail("k_col_size must stay 128 bytes (45C9)")
    ship = hitbox(sizes, 0x38, 0x78, 0xA0)
    plane = hitbox(sizes, 0x40, 0x78, 0xA0)
    bar = hitbox(sizes, 0x84, 0x78, 0xA0)
    if ship[2:] != (8, 8):
        return fail(f"SAT 0x38 ship hitbox {ship[2:]} want 8x8")
    if plane[2:] != (14, 12):
        return fail(f"SAT 0x40 plane hitbox {plane[2:]} want 14x12")
    if bar[2:] != (16, 12):
        return fail(f"SAT 0x84 veybar hitbox {bar[2:]} want 16x12")
    if not aabb(*ship, *plane):
        return fail("ship 0x38 vs type44 0x40 at same SAT XY must overlap")
    if not aabb(*ship, *bar):
        return fail("ship 0x38 vs veybar 0x84 at same SAT XY must overlap")
    print("  4560: ship 8x8 overlaps type44 14x12 and veybar 16x12")

    # EC is draw-only — collision stays SAT vs SAT
    hit = fn_span(ent, "static int hit_overlap_slot(s16 x1, s16 y1, u8 sat1, const Slot *e)")
    if not hit:
        return fail("hit_overlap_slot not found")
    if "mode_draw_x" in hit:
        return fail("4560 must stay SAT vs SAT (no mode_draw_x / EC)")
    if "e->x, e->y" not in hit:
        return fail("hit_overlap_slot must use stored SAT X/Y")
    print("  hit_overlap_slot: SAT vs SAT (EC is draw-only)")

    asm_path = next((p for p in ASM_CANDIDATES if p.is_file()), None)
    if asm_path:
        asm = asm_path.read_text(encoding="utf-8", errors="replace")
        t44 = asm.split("handler_type44_ground_structure:", 1)
        if len(t44) < 2:
            return fail("zanac.asm missing handler_type44_ground_structure")
        body = t44[1].split("handler_type61_large_descender:", 1)[0]
        if "JP	 0x44ba" not in body and "JP     0x44ba" not in body:
            return fail("Japan type 44 must JP 44BA (82ff)")
        if "0x83" not in body:
            return fail("Japan type 44 must write +04=0x83")
        if "CALL	 0x44ca" in body or "CALL     0x44ca" in body:
            return fail("Japan type 44 must not CALL 44CA")
        print("  zanac.asm: type 44 +04=0x83 JP 44BA (not 44CA)")
        t22 = asm.split("handler_type22_veybar:", 1)
        if len(t22) > 1:
            vbody = t22[1].split("handler_type24_veybar_fast:", 1)[0]
            if "JP	 0x44ba" not in vbody and "JP     0x44ba" not in vbody:
                return fail("Japan veybar must JP 44BA (7d89)")
            print("  zanac.asm: veybar 22 JP 44BA")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    print("ok: green flyer type 44 0x83 is 44BA; ship overlap hits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
