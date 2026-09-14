#!/usr/bin/env python3
"""Type 62 8717 SAT 0 is a 16x16 pickup box, not leftover 0xF8 / 0x40.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  handler_type62 0x8709 init (bit7 clear):
    LD (IX+0x03), 0x00     ; 0x8717 SAT name 0
    LD (IX+0x04), 0x87     ; 0x871b EC + cyan (invisible; no SAT DMA)
    LD (IX+0x0c), 0x01
    SET 7 / RET 0x8727

  hitbox_setup_ix 0x45A0: sat>>1 into 0x45C9.
    SAT 0 → half 0,0 → 16x16 at stored XY.
    SAT 0xF8 (type 61 leftover FRAME_SART) → half 0,2 → 12x16 at X+2.
    SAT 0x40 (hit_overlap_slot unset fallback) → half 2,1 → 14x12.

  Type 61 death 8385 writes 0x3E on the same slot (SAT still 0xF8).
  Port become_riser must stamp 8717/871b so 44B0 uses 16x16.

KEEP: 8727 first-visit RET; type 62 lives-only; type 44 44BA;
s_riser_init_ret; no 0xBFD6.

Usage (from zanac-md):
    python tools/test_type62_sat0_8717.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTITY = ROOT / "src" / "entity.c"
PLAYER = ROOT / "src" / "player.c"
ASM_CANDIDATES = [
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    Path.home() / "zanac-re" / "source" / "zanac.asm",
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def load_asm() -> str | None:
    for p in ASM_CANDIDATES:
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    return None


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


def c_array(src: str, name: str) -> list[int]:
    m = re.search(rf"{name}\[[^\]]*\]\s*=\s*\{{([^}}]+)\}}", src, re.S)
    if not m:
        return []
    return [int(x, 0) for x in re.findall(r"0x[0-9A-Fa-f]+|\d+", m.group(1))]


def hitbox(col: list[int], sat: int) -> tuple[int, int, int, int]:
    idx = sat >> 1
    hy = col[idx]
    hx = col[idx + 1]
    return hx, hy, 16 - 2 * hx, 16 - 2 * hy


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8", errors="replace")
    ply = PLAYER.read_text(encoding="utf-8", errors="replace")
    asm = load_asm()

    if asm:
        if not re.search(r"LD\s+\(IX\+0x03\),\s*0x00\s*;\s*0x8717", asm, re.I):
            fail("zanac.asm 8717 is not LD (IX+03),0x00")
            fails += 1
        else:
            print("  ASM 8717: SAT name 0")
        if not re.search(r"LD\s+\(IX\+0x04\),\s*0x87\s*;\s*0x871b", asm, re.I):
            fail("zanac.asm 871b is not LD (IX+04),0x87")
            fails += 1
        else:
            print("  ASM 871b: SAT color 0x87")
        if not re.search(r"LD\s+HL,\s*0x45c9\s*;\s*0x45a8", asm, re.I):
            fail("zanac.asm 45A8 is not LD HL,0x45C9")
            fails += 1
        else:
            print("  ASM 45A8: hitbox table 0x45C9")
    else:
        print("  ASM: zanac.asm not in tree (bytes checked in port)")

    col = c_array(ent, "k_col_size")
    if len(col) < 128:
        fail("k_col_size must stay 128 bytes")
        fails += 1
        return 1

    ox, oy, w, h = hitbox(col, 0)
    if (ox, oy, w, h) != (0, 0, 16, 16):
        fail(f"SAT 0 must be 16x16 at +0,+0, got {w}x{h} at +{ox},+{oy}")
        fails += 1
    else:
        print("  SAT 0: 16x16 (Japan 8717)")

    ox, oy, w, h = hitbox(col, 0xF8)
    if (w, h) == (16, 16) and ox == 0 and oy == 0:
        fail("SAT 0xF8 must differ from SAT 0 (leftover type-61 must miss)")
        fails += 1
    else:
        print(f"  SAT 0xF8 leftover: {w}x{h} at +{ox},+{oy} (not 16x16)")

    ox, oy, w, h = hitbox(col, 0x40)
    if (w, h) == (16, 16) and ox == 0 and oy == 0:
        fail("SAT 0x40 fallback must differ from SAT 0")
        fails += 1
    else:
        print(f"  SAT 0x40 fallback: {w}x{h} at +{ox},+{oy} (not 16x16)")

    become = fn_span(ent, "static void become_riser(Slot *e)")
    if not become:
        fail("become_riser not found")
        fails += 1
    elif "e->sat = 0" not in become:
        fail("become_riser must write 8717 SAT 0")
        fails += 1
    elif "e->sat_col = 0x87" not in become:
        fail("become_riser must write 871b sat_col 0x87")
        fails += 1
    elif "step_88_y_4898" in become or "riser_step" in become:
        fail("become_riser must not 4898 / riser_step (KEEP 8727)")
        fails += 1
    else:
        print("  become_riser: SAT 0 / color 0x87, no 4898")

    hit = fn_span(ent, "static int hit_overlap_slot(s16 x1, s16 y1, u8 sat1, const Slot *e)")
    if not hit:
        fail("hit_overlap_slot not found")
        fails += 1
    elif "KIND_RISER" not in hit:
        fail("hit_overlap_slot must honor type 62 SAT 0 (not 0→0x40)")
        fails += 1
    elif not re.search(
        r"if\s*\(\s*e->kind\s*==\s*KIND_RISER\s*\)\s*\n\s*esat\s*=\s*0\s*;",
        hit,
    ):
        fail("KIND_RISER must force SAT 0 (16x16), not the 0x40 fallback")
        fails += 1
    else:
        print("  hit_overlap_slot: KIND_RISER SAT 0")

    # KEEP: 8727 first-visit RET; lives-only; type 44 44BA.
    if "s_riser_init_ret" not in ent:
        fail("KEEP: s_riser_init_ret was reverted")
        fails += 1
    else:
        print("  KEEP: s_riser_init_ret")

    grant = fn_span(ply, "void player_grant_life(void)")
    if grant and ("fire_select" in grant or "player_fire_select" in grant):
        fail("KEEP: player_grant_life must stay lives-only")
        fails += 1
    else:
        print("  KEEP: type 62 lives-only")

    collide = fn_span(ent, "static void collide_player(void)")
    if not collide:
        fail("collide_player not found")
        fails += 1
    elif re.search(r"if\s*\(\s*e->kind == KIND_GROUND\s*\)", collide):
        fail("type 44 is 44BA; collide_player must not skip KIND_GROUND")
        fails += 1
    else:
        print("  type 44 44BA: collide_player does not skip KIND_GROUND")

    if "0xBFD6" in ent or "0xbfd6" in ent:
        fail("KEEP: no 0xBFD6")
        fails += 1
    else:
        print("  KEEP: no 0xBFD6")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
