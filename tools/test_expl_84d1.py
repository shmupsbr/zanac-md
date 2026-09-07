#!/usr/bin/env python3
"""Type 35 / 80 explosion SAT is 84d1 (sat,col) x6. Frame 0 is JP 48D0.

0x84d1: D0 48 / 1C 8A / 20 8E / 24 8F / 20 8D / 1C 89
Init +0F=1 skips SAT 0xD0. 86F3 player death stays 11 pairs.

Usage (from zanac-md):
    python tools/test_expl_84d1.py
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
    if "e->clock = 1" not in ent or "e->aux = 1" not in ent:
        return fail("type35 init +0D=1 +0F=1 skips 84d1[0]")
    if "e->vx = 0" not in ent:
        return fail("become_expl must zero leftover vel (type-35 only)")
    if "e->ground = hide" in ent:
        return fail("do not force become_expl ground=1 on 4898 type44/guns")
    if "sat_space" not in ent:
        return fail("become_expl must treat KIND_GROUND/GUN as SAT-space")
    if "e->dest = leftover" not in ent:
        return fail("become_expl must stash leftover SAT for the yellow pose")

    print("ok: 84d1 / 86F3 SAT; leftover vel; ground hide")
    return 0


if __name__ == "__main__":
    sys.exit(main())
