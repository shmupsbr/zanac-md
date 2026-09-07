#!/usr/bin/env python3
"""84d1 / 86F3 discs share the type-72 leftover-nibble sanitizer.

Same SAT 0x1C/0x20/0x24 as 8a16 (lead / med / lg). Frame 0 of 84d1 is
JP 48D0 (0xD0,0x48) and stays skipped. 86F3 stays 11 pairs. Do not
invent frames. KIND_ORB path stays; explosions paint every nonzero
nibble then keep 0/sat_col. A 4-tile VRAM pad wrote past 1-2 tile
AUTO_VRAM slots and composited FRAME_SHOT into the next flyer.

Usage (from zanac-md):
    python tools/test_expl_disc_sanitize.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


def main() -> int:
    ent = ENT.read_text(encoding="utf-8")

    if "0xD0, 0x1C, 0x20, 0x24, 0x20, 0x1C" not in ent:
        return fail("k_t35_sat must stay 84d1 names")
    if "0x48, 0x8A, 0x8E, 0x8F, 0x8D, 0x89" not in ent:
        return fail("k_t35_col must stay 84d1 colors")
    if "0x00, 0x1C, 0x1C, 0x20, 0x20, 0x24, 0x24, 0x20, 0x20, 0x1C, 0x1C" not in ent:
        return fail("k_t60_sat must stay 86F3 names")
    if "0xC9, 0x86, 0x8F, 0x88, 0x8F, 0x89, 0x8F, 0x88, 0x89, 0x86, 0x8F" not in ent:
        return fail("k_t60_col must stay 86F3 colors")
    if "e->clock = 1" not in ent or "e->aux = 1" not in ent:
        return fail("type35 init +0D=1 +0F=1 skips 84d1[0]")
    if "orb_keep_body_nibbles" not in ent:
        return fail("disc upload must sanitize leftover PAL2 nibbles")
    if "orb_paint_body_nibbles" not in ent:
        return fail("disc upload must paint every nonzero nibble (not from==15)")
    if "u16 out = 128" in ent:
        return fail("do not re-ship 4-tile pad; it overruns flyer VRAM")
    if "s->kind == KIND_EXPL" not in ent or "KIND_PDEAD" not in ent:
        return fail("84d1/86F3 kinds must use the disc paint path")
    if "s->kind == KIND_HUSK" not in ent:
        return fail("type 80 849c 84d1 must use the disc paint path")
    if "s->kind == KIND_ORB" not in ent:
        return fail("KIND_ORB sanitizer must stay")
    if "orb_upload_japan" not in ent:
        return fail("84d1/86F3 SAT 0x1C/0x20/0x24 must encode Japan pats 7/8/9")
    if "leftover_flyer_sat" not in ent:
        return fail("become_expl leftover SAT is the yellow pose, not FRAME_LEAD")
    if "static const u8 k_orb_mid_pal = 7" not in ent:
        return fail("k_orb_mid_pal must stay 7")
    if "FRAME_SMALL_STAR" not in ent:
        return fail("FRAME_SMALL_STAR must stay")

    print("ok: 84d1/86F3 tables locked; expl/pdead/husk share disc paint")
    return 0


if __name__ == "__main__":
    sys.exit(main())
