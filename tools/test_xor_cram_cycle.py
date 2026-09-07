#!/usr/bin/env python3
"""XOR leftover colour cycle is CRAM after bind, like fire 7.

Japan +04 XOR / 72de is one SAT-colour byte. MD tile remap every tick
(type 36/56/59/67, gswoop/tracker, type 21, 84d1 colour walk) was the
remaining hitch after fire 0/1/2/7 shared PAL2[13].

Bind body pixels to an unused PAL2 nibble (5/6/12 -- not flyer greens
2/3, not fire7 13) once. Later spr_set_sat_col only writes CRAM.
Pool miss still hits remap_cache.

KEEP: fire7 PAL2[13]; orb variant cache; 816d gun primary remap.

Usage (from zanac-md):
    python tools/test_xor_cram_cycle.py
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


def main() -> int:
    ent = ENT.read_text(encoding="utf-8")

    if "xor_cram_bind" not in ent or "xor_cram_cycle" not in ent:
        return fail("XOR leftovers must CRAM-bind like fire 7")
    if "5, 6, 12" not in ent and "5,6,12" not in ent:
        return fail("XOR CRAM nibbles must be 5/6/12 (not 2/3 greens, not 13)")
    if "FIRE7_CRAM_NIB  13" not in ent and "FIRE7_CRAM_NIB 13" not in ent:
        return fail("KEEP: fire 7 CRAM nibble 13")

    setc = fn_span(ent, "static void spr_set_sat_col(Slot *s, u8 col)")
    if not setc:
        return fail("spr_set_sat_col not found")
    if "xor_cram_cycle" not in setc or "xor_cram_bind" not in setc:
        return fail("spr_set_sat_col must CRAM-cycle after bind")
    print("  spr_set_sat_col: bind once, then CRAM")

    wanted = fn_span(ent, "static int xor_cram_wanted(const Slot *s)")
    if not wanted:
        return fail("xor_cram_wanted not found")
    for kind in (
        "KIND_FLASH",
        "KIND_SIG",
        "KIND_CIRCLE",
        "KIND_GSWOOP",
        "KIND_TRACKER",
        "KIND_PAIRDESC",
        "KIND_EXPL",
    ):
        if kind not in wanted:
            return fail("%s must be a CRAM walker" % kind)
    if "variant == 21" not in wanted:
        return fail("type 21 8659 random colour must CRAM")
    print("  walkers: 36/56/59/67/gswoop/tracker/21/expl")

    cyc = fn_span(ent, "static void xor_cram_cycle(Slot *s, u8 col)")
    if not cyc:
        return fail("xor_cram_cycle not found")
    if "spr_upload_color" in cyc or "remap_cache_get" in cyc:
        return fail("cycle must not remap tiles")
    if "PAL_setColor" not in cyc:
        return fail("cycle is a CRAM write")
    print("  xor_cram_cycle: PAL_setColor only")

    rel = fn_span(ent, "static void spr_detach(Slot *s)")
    if not rel or "xor_cram_release" not in rel:
        return fail("spr_detach must release the CRAM nibble")

    fire = fn_span(ent, "static void fire7_cycle_cram(Slot *f)")
    if not fire or "spr_set_sat_col" in fire:
        return fail("KEEP: fire 7 cycle stays CRAM-only")

    print("ok: XOR leftovers CRAM-bind; fire7 nibble 13 KEEP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
