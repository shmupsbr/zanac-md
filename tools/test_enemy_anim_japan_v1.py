#!/usr/bin/env python3
"""Enemy animation paths vs Japan v1 after PR #100 CRAM bind.

Japan v1 SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2.

Colour-only +04 XOR / 84d1 colour may CRAM-bind (slowdown KEEP).
SAT-name walkers must remap per frame — binding them rotates CRAM
like fire 0 and freezes / skips poses (open-close).

Japan locks:
  83d8 type 67: SAT ^=0x34 (0x20<->0x14) AND colour ^=0x0c. Not CRAM.
  8625 type 45: SAT 0x18+((+0x1c&1)<<3) bar/med. Not CRAM.
  81c3 56/59/57/58: colour ^=0x09, SAT name fixed. CRAM ok.
  829c type 36: colour ^=0x0e, SAT 0x34. CRAM ok.
  7f73 30-33: colour ^=0x06. CRAM ok.
  8659 type 21: R-nibble|0x80. CRAM ok.
  7e68/7e70 swoop: 4912 write-then-inc pats 43-46, colour fixed.
  84d1 leftover SAT + marker KEEP (death yellow).

Ship: stored Y 0x1E..0xB8 (7640). Draw sits on the 192 letterbox.
Complement white Y+2 (7735) KEEP.

Usage (from zanac-md):
    python tools/test_enemy_anim_japan_v1.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
PLY = ROOT / "src" / "player.c"
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


def find_asm() -> Path | None:
    for p in ASM_CANDIDATES:
        if p.is_file():
            return p
    return None


def main() -> int:
    ent = ENT.read_text(encoding="utf-8")
    ply = PLY.read_text(encoding="utf-8")

    wanted = fn_span(ent, "static int xor_cram_wanted(const Slot *s)")
    if not wanted:
        return fail("xor_cram_wanted not found")

    for kind in (
        "KIND_FLASH",
        "KIND_SIG",
        "KIND_GSWOOP",
        "KIND_TRACKER",
        "KIND_PAIRDESC",
        "KIND_EXPL",
        "KIND_PDEAD",
        "KIND_HUSK",
    ):
        if kind not in wanted:
            return fail("%s must stay a colour-only CRAM walker" % kind)
    if "variant == 21" not in wanted:
        return fail("type 21 8659 must stay a CRAM walker")
    if "KIND_CIRCLE" in wanted:
        return fail("type 67 83d8 SAT^=0x34 must not CRAM-bind")
    if "KIND_VEYBAR" in wanted or "KIND_SWOOP" in wanted:
        return fail("veybar/swoop SAT-name walk must not CRAM-bind")
    if "KIND_ORB" in wanted:
        return fail("KEEP: orb 8a16 stays remap/japan-pat, not XOR CRAM")
    print("  CRAM pool: colour-only (no 67/45/veybar/swoop/orb)")

    circ = fn_span(ent, "static void circle_step(Slot *e)")
    if not circ:
        return fail("circle_step not found")
    if "e->sat ^= 0x34" not in circ:
        return fail("83d8 SAT name must XOR 0x34")
    if "sat_col ^ 0x0c" not in circ:
        return fail("83e0 colour must XOR 0x0c")
    if "frame_from_sat" not in circ or "spr_place" not in circ:
        return fail("83d8 must spr_place the XOR'd SAT name")
    print("  type 67: SAT^=0x34 + colour^=0x0c + spr_place")

    ebullet = fn_span(ent, "void entity_update(void)")
    if not ebullet:
        # entity_update may be named differently
        ebullet = ent
    if "FRAME_MED_CIRCLE : FRAME_LIGHT_BAR" not in ent:
        return fail("type 45 8625 must pulse bar/med from clock LSB")
    print("  type 45: 8625 bar/med SAT pulse")

    swoop = fn_span(ent, "static void swoop_step(Slot *e)")
    if not swoop:
        return fail("swoop_step not found")
    if "FRAME_SPINNER_0 + fi" not in swoop:
        return fail("swoop 7e68/7e70 must walk pats 43-46")
    if "FRAME_SPINNER_C0 + fi" not in swoop:
        return fail("swoop 71f6 marker must be sat+0x10")
    if "s_swoop_atim[si] = 4" not in ent:
        return fail("swoop +0D/+0E=4 (4912 reload)")
    print("  swoop: 4912 pats 43-46 + marker +0x10")

    place = fn_span(ent, "static void spr_place(Slot *s, u16 frame)")
    if not place:
        return fail("spr_place not found")
    if "xor_cram_paint" not in place:
        return fail("CRAM-bound SAT-name change must re-paint tiles")
    print("  spr_place: re-paint bound nibble on frame change")

    become = fn_span(ent, "static void become_expl(Slot *e, u8 score_t)")
    if not become or "e->dest = leftover" not in become:
        return fail("KEEP: flyer death leftover SAT")
    print("  KEEP: leftover death SAT")

    if "max_y = 0xB8" not in ply or "min_y = 0x1E" not in ply:
        return fail("KEEP: ship stored Y 0x1E..0xB8 (7640)")
    if "dy = (s16)(y1 - SHIP_H)" not in ply:
        return fail("ship draw must stop at the 192 letterbox")
    if "cdy = (s16)(dy + 2)" not in ply:
        return fail("KEEP: ship black Y+2 (7735)")
    print("  ship: stored 0xB8; draw on letterbox; Y+2 KEEP")

    if "FIRE7_CRAM_NIB  13" not in ent and "FIRE7_CRAM_NIB 13" not in ent:
        return fail("KEEP: fire 7 CRAM nibble 13")
    print("  KEEP: fire7 nibble 13")

    asm = find_asm()
    if asm:
        text = asm.read_text(encoding="utf-8", errors="replace")
        if "XOR	 0x34" not in text and "XOR	 0x34" not in text:
            # allow either tab style
            if "XOR" not in text or "0x34" not in text:
                return fail("zanac.asm 83db is not XOR 0x34")
        if "0x83db" in text or "0x83d8" in text:
            print("  zanac.asm: type 67 XOR present")
        if "0xac, 0x8e, 0xb0, 0x8e, 0xb4, 0x8e, 0xb8, 0x8e" not in text.replace(" ", ""):
            # original has spaces after commas
            if "0xac, 0x8e, 0xb0, 0x8e" not in text:
                print("  (swoop 7e68 bytes not matched; C locks only)")
            else:
                print("  zanac.asm: 7e68 spinner table")
        else:
            print("  zanac.asm: 7e68 spinner table")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    print("ok: enemy anim vs Japan — CRAM colour-only; 67/45 remap; ship letterbox")
    return 0


if __name__ == "__main__":
    sys.exit(main())
