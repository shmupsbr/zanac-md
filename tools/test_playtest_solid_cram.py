#!/usr/bin/env python3
"""Solid enemies must not share fire7 / XOR CRAM palette slots.

Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  type 65 7f99 +04 = 0x85 (light blue). No XOR.
  type 66 +04 = 0x8b. No XOR.
  type 34 +04 = 0x88. No XOR.
  type 67 83b8 +04 = 0x86; 83e0 XOR 0x0c (0x86 <-> 0x8A);
           840a +04 = 0x8d then XOR continues (0x8d <-> 0x81).
  type 61 8347 +04 from 8eaf[E149&7]: 81 83 84 86 87 89 8A 8D
           (0x81 becomes 0x8F). One colour per spawn, not a walk.
  type 18 7ccd +04 = 0x8B. No XOR.

MD fire 0/1/2/7 72de owns PAL2[13]. XOR CRAM walkers bind a dedicated
nibble and cycle it. If a solid enemy remaps onto 5/6/13 it flashes
through the walker's / fire-0 colours.

Usage (from zanac-md):
    python tools/test_playtest_solid_cram.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
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


def main() -> int:
    ent = ENT.read_text(encoding="utf-8")

    pool = re.search(
        r"static const u8 k_xor_cram_nib\[XOR_CRAM_N\] = \{([^}]+)\}",
        ent,
    )
    if not pool:
        return fail("k_xor_cram_nib not found")
    nibs = [int(x, 0) for x in re.findall(r"0x[0-9A-Fa-f]+|\d+", pool.group(1))]
    for hot in (5, 6, 13):
        if hot in nibs:
            return fail("XOR CRAM pool must not include nibble %d" % hot)
    if 2 not in nibs:
        return fail("XOR CRAM walker nibble must be unused sat_col 2")
    print("  XOR CRAM pool:", nibs, "(not 5/6/13)")

    if "NIB_8D_ALIAS    12" not in ent and "NIB_8D_ALIAS 12" not in ent:
        return fail("0x8D must alias off fire7 nibble 13")
    alias = fn_span(ent, "static u8 sat_col_tile_nibble(const Slot *s, u8 want)")
    if not alias:
        return fail("sat_col_tile_nibble not found")
    if "FIRE7_CRAM_NIB" not in alias or "KIND_FIRE" not in alias:
        return fail("nibble 13 alias must spare the fire weapon")
    if "NIB_8D_ALIAS" not in alias:
        return fail("0x8D tiles must go to NIB_8D_ALIAS")
    print("  0x8D -> nibble 12; fire 7 keeps 13")

    wanted = fn_span(ent, "static int xor_cram_wanted(const Slot *s)")
    if not wanted:
        return fail("xor_cram_wanted not found")
    for kind in ("KIND_LUSTER", "KIND_STEALTH", "KIND_DESCEND"):
        if kind not in wanted:
            return fail("%s must be excluded from XOR CRAM" % kind)
    if "KIND_FLASH" not in wanted or "KIND_SIG" not in wanted:
        return fail("KEEP: colour-only walkers still CRAM")
    print("  solid 18/65/61 excluded; walkers 36/56 KEEP")

    stealth = fn_span(ent, "static void spawn_stealth")
    if stealth is None:
        stealth = ent
    if "e->sat_col = 0x85" not in ent:
        return fail("type 65 +04 must stay 0x85 (7f99)")
    if "e->sat_col = 0x8B" not in ent:
        return fail("type 18/66 +04 0x8B must stay")
    print("  type 65 0x85; type 18 0x8B")

    if "0x81, 0x83, 0x84, 0x86, 0x87, 0x89, 0x8A, 0x8D" not in ent:
        return fail("KEEP: type 61 8eaf table")
    print("  type 61 8eaf one colour per spawn")

    asm_path = next((p for p in ASM_CANDIDATES if p.is_file()), None)
    if asm_path:
        asm = asm_path.read_text(encoding="utf-8", errors="replace")
        if "LD	 (IX+0x04), 0x86" not in asm and "0x83b8" not in asm:
            print("  (type 67 +04 0x86 not matched; C locks only)")
        else:
            print("  zanac.asm: type 67 +04 0x86")
        if "0x81, 0x83, 0x84, 0x86" in asm.replace(" ", "") or "0x8eaf" in asm:
            print("  zanac.asm: 8eaf table present")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    print("ok: solid enemies keep one TMS colour; fire7 nibble 13 KEEP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
