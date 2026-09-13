#!/usr/bin/env python3
"""Type 4/5/6 flying boxes: death must not keep leftover white crate SAT.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  handler_type68_proto_box 0x77a1 emits three type 4/5/6 from 0x77ea.

  handler_type4_box 0x7826 (shared):
    reveal 7839 +03=0xD4 (pat 53 box) / 783d +04=0x8F / 71da +03=0xD8
    last-HP 7860: type4 0x89, type5 0x8A, else 0x87

  7878 after 7904 Z:
    CP 5 / RET Z          ; type 5 stays 0x23; 849c / 4912 next tick
    CP 4 / JR Z,788f      ; type 4 -> three type 38
    7882 LD (IX+03),0x04  ; type 6 -> SAT 0x04 pat 1 power chip
    7886 LD (IX+04),0x8F
    788a LD (IX+00),0xBF  ; type 63 | bit7

  4912 writes 84d1[+0F]. 84d1[1] is SAT 0x1C / 0x8A. Japan replaces
  leftover +03=0xD4; it does not keep the crate as the yellow pose.

  gfx pat 1 = power chip (barrel / capsule). SAT name = pat*4 = 0x04.
  gfx pat 53 = box crate. SAT 0xD4.

Port leftover_flyer_sat used to keep SAT 0xD4. KIND_EXPL disc paint
then remapped every nonzero nibble of FRAME_BOX (baked 15) to 0x8F —
a solid white crate instead of the chip / 84d1 discs.

Usage (from zanac-md):
    python tools/test_box_death_chip_7882.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
ASM_CANDIDATES = [
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    Path.home() / "zanac-re" / "source" / "zanac.asm",
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


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


def load_asm() -> str | None:
    for p in ASM_CANDIDATES:
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    return None


def main() -> int:
    fails = 0
    ent = ENT.read_text(encoding="utf-8")
    asm = load_asm()

    if asm:
        if not re.search(r"LD\s+\(IX\+0x03\),\s*0x04\s*;\s*0x7882", asm, re.I):
            fail("zanac.asm 7882 is not LD (IX+03),0x04")
            fails += 1
        else:
            print("  ASM 7882: type 6 SAT 0x04 (pat 1 power chip)")
        if not re.search(r"LD\s+\(IX\+0x04\),\s*0x8f\s*;\s*0x7886", asm, re.I):
            fail("zanac.asm 7886 is not LD (IX+04),0x8F")
            fails += 1
        else:
            print("  ASM 7886: chip colour 0x8F")
        if not re.search(r"LD\s+\(IX\+0x00\),\s*0xbf\s*;\s*0x788a", asm, re.I):
            fail("zanac.asm 788a is not type 0xBF")
            fails += 1
        else:
            print("  ASM 788a: type 63 | bit7")
        if not re.search(r"LD\s+\(IX\+0x03\),\s*0xd4\s*;\s*0x7839", asm, re.I):
            fail("zanac.asm 7839 is not SAT 0xD4")
            fails += 1
        else:
            print("  ASM 7839: live box SAT 0xD4 (crate)")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    leftover = fn_span(ent, "static int leftover_flyer_sat(u8 sat)")
    if not leftover:
        fail("leftover_flyer_sat not found")
        fails += 1
    else:
        if "0xD4" not in leftover or "0xD8" not in leftover:
            fail("leftover_flyer_sat must reject box SAT 0xD4 / complement 0xD8")
            fails += 1
        else:
            print("  leftover_flyer_sat: SAT 0xD4 / 0xD8 rejected")
        if "FRAME_BOX" not in leftover:
            fail("leftover_flyer_sat must reject FRAME_BOX")
            fails += 1
        else:
            print("  leftover_flyer_sat: FRAME_BOX rejected")
        if "FRAME_CHIP" not in leftover:
            fail("KEEP: FRAME_CHIP leftover still rejected")
            fails += 1
        else:
            print("  KEEP: FRAME_CHIP leftover rejected")

    become = fn_span(ent, "static void become_chip(Slot *e)")
    if not become:
        fail("become_chip not found")
        fails += 1
    else:
        if "spr_detach(e)" not in become:
            fail("become_chip must spr_detach leftover crate / complement")
            fails += 1
        else:
            print("  become_chip: spr_detach drops SAT 0xD4 pair")
        place = become.find("spr_place(e, FRAME_CHIP)")
        sat = become.find("e->sat = 0x04")
        if place < 0 or sat < 0 or sat < place:
            fail("become_chip must set sat=0x04 after FRAME_CHIP")
            fails += 1
        else:
            print("  become_chip: FRAME_CHIP then SAT 0x04")
        if "0x8F" not in become:
            fail("become_chip must keep 7886 colour 0x8F")
            fails += 1
        else:
            print("  become_chip: sat_col 0x8F")

    kill = fn_span(ent, "static void box_kill_7878(Slot *e)")
    if not kill:
        fail("box_kill_7878 not found")
        fails += 1
    else:
        if "become_expl(e, drop)" not in kill or "drop == 5" not in kill:
            fail("type 5 must still become_expl (787d RET)")
            fails += 1
        else:
            print("  box_kill_7878: type 5 stay 0x23")
        if "become_chip(e)" not in kill:
            fail("type 6 must become_chip (7882)")
            fails += 1
        else:
            print("  box_kill_7878: type 6 become_chip")
        if "box_death_drop" not in kill or "drop == 4" not in kill:
            fail("type 4 must still drop three type 38")
            fails += 1
        else:
            print("  box_kill_7878: type 4 three type 38")

    if "0xD0, 0x1C, 0x20, 0x24, 0x20, 0x1C" not in ent:
        fail("KEEP: k_t35_sat 84d1 names")
        fails += 1
    else:
        print("  KEEP: 84d1 SAT names")

    wanted = fn_span(ent, "static int xor_cram_wanted(const Slot *s)")
    if not wanted:
        fail("xor_cram_wanted not found")
        fails += 1
    else:
        for kind in ("KIND_LUSTER", "KIND_STEALTH", "KIND_DESCEND"):
            if kind not in wanted:
                fail(f"KEEP: {kind} must stay excluded from XOR CRAM")
                fails += 1
        else:
            print("  KEEP: solid 18/65/61 still excluded from XOR CRAM")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
