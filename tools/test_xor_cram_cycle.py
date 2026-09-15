#!/usr/bin/env python3
"""XOR leftover colour cycle is CRAM after bind, like fire 7.

Japan +04 XOR / 72de is one SAT-colour byte. MD tile remap every tick
(type 36/56/59/67, gswoop/tracker, type 21, 84d1 colour walk) was the
remaining hitch after fire 0/1/2/7 shared PAL2[13].

Bind body pixels to an unused PAL2 nibble (2 -- not type 65/67/61
sat_col 5/6, not fire7 13, not LIGHT_BAR baked 4). 0x8D (type 67 840a
/ type 61 table) aliases to nibble 12 so fire 0/1/2/7 cannot rainbow
those bodies.
Share nibble 2 among all walkers of the same kind (refcount). Exclusive
per-sprite left a full SIG wave on remap+DMA every tick.
Later spr_set_sat_col only writes CRAM. Other kinds miss the pool and
hit remap_cache + dma_nibble_defer.

Type 67 (SAT ^=0x34 every tick) is not a walker -- shape + colour.
Type 45 bar/med is not a walker.

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
    if "k_xor_cram_nib" not in ent:
        return fail("XOR CRAM pool must exist")
    if "s_xor_cram_kind" not in ent or "s_xor_cram_refs" not in ent:
        return fail("XOR CRAM must be shared by kind (refcount)")
    if re.search(r"k_xor_cram_nib\[XOR_CRAM_N\] = \{[^}]*\b4\b", ent):
        return fail("XOR CRAM must not own nibble 4 (FRAME_LIGHT_BAR baked 4)")
    if re.search(r"k_xor_cram_nib\[XOR_CRAM_N\] = \{[^}]*\b5\b", ent):
        return fail("XOR CRAM must not own nibble 5 (type 65 0x85)")
    if re.search(r"k_xor_cram_nib\[XOR_CRAM_N\] = \{[^}]*\b6\b", ent):
        return fail("XOR CRAM must not own nibble 6 (type 67 0x86 / type 61 0x86)")
    if "FIRE7_CRAM_NIB" in ent and "NIB_8D_ALIAS" not in ent:
        return fail("0x8D enemies must alias off fire7 nibble 13")
    if "NIB_8D_ALIAS    12" not in ent and "NIB_8D_ALIAS 12" not in ent:
        return fail("type 67 840a / type 61 0x8D tiles sit on nibble 12")
    if "FIRE7_CRAM_NIB  13" not in ent and "FIRE7_CRAM_NIB 13" not in ent:
        return fail("KEEP: fire 7 CRAM nibble 13")

    setc = fn_span(ent, "static void spr_set_sat_col(Slot *s, u8 col)")
    if not setc:
        return fail("spr_set_sat_col not found")
    if "xor_cram_cycle" not in setc or "xor_cram_bind" not in setc:
        return fail("spr_set_sat_col must CRAM-cycle after bind")
    print("  spr_set_sat_col: bind once, then CRAM")

    alloc = fn_span(ent, "static u8 xor_cram_alloc(const Slot *s)")
    if not alloc:
        return fail("xor_cram_alloc must take the slot (share by kind)")
    if "s_xor_cram_kind" not in alloc or "s_xor_cram_refs" not in alloc:
        return fail("xor_cram_alloc must refcount the owner kind")
    print("  xor_cram_alloc: shared by kind")

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
    ):
        if kind not in wanted:
            return fail("%s must be a CRAM walker" % kind)
    if "KIND_CIRCLE" in wanted:
        return fail("type 67 83d8 SAT^=0x34 is not a colour-only walker")
    if "variant == 21" not in wanted:
        return fail("type 21 8659 random colour must CRAM")
    if "LIGHTBAR_CRAM_NIB" not in ent:
        return fail("type 21 must own a dedicated CRAM nibble (not XOR pool 2)")
    if not re.search(r"LIGHTBAR_CRAM_NIB\s+4", ent):
        return fail("type 21 CRAM must be PAL2[4] (FRAME_LIGHT_BAR bake)")
    alloc = fn_span(ent, "static u8 xor_cram_alloc(const Slot *s)")
    if not alloc or "LIGHTBAR_CRAM_NIB" not in alloc:
        return fail("xor_cram_alloc must always return LIGHTBAR_CRAM_NIB for type 21")
    bind = fn_span(ent, "static int xor_cram_bind(Slot *s, u8 col)")
    if not bind:
        return fail("xor_cram_bind not found")
    if "variant == 21" not in bind:
        return fail("type 21 must CRAM-bind even without a hardware sprite")
    if "xor_cram_cycle" not in setc:
        return fail("spr_set_sat_col must CRAM-cycle after bind")
    if "variant == 45" in wanted:
        return fail("type 45 8625 bar/med must not CRAM")
    if "KIND_LUSTER" not in wanted or "KIND_STEALTH" not in wanted:
        return fail("solid dual-SAT flyers must be excluded from CRAM")
    print("  walkers: 36/56/59/gswoop/tracker/21/expl (not 67/65/18)")

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
