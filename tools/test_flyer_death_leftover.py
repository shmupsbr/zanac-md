#!/usr/bin/env python3
"""Flyer death yellow pose is leftover SAT, not a shared FRAME_LEAD triangle.

Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):
  453E writes type 0x23 only. +03 leftover SAT and type39 stay until
  8446 + 84c9 4912. 84d1[1] is SAT 0x1C / colour 0x8A (pat 7).
  FRAME_LEAD is that pat cropped to an 8x8 UL shard -- every flyer
  then showed the same triangular yellow.

Port:
  become_expl stashes leftover SAT in dest and keeps the marker.
  First 84d1 write (aux==1, SAT 0x1C) keeps leftover SAT + 0x8A.
  Later 0x20/0x24 encode Japan pats 8/9 into the FRAME_CIRCLE vehicle
  (same as type 72). spawn_expl dest=0 uses discs only.
  pdeath dest=0; 86F3 still 11 pairs.

Usage (from zanac-md):
    python tools/test_flyer_death_leftover.py
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

    become = fn_span(ent, "static void become_expl(Slot *e, u8 score_t)")
    if not become:
        return fail("become_expl not found")
    if "e->dest = leftover" not in become:
        return fail("become_expl must stash leftover SAT in dest")
    if "marker_kill(e)" in become and "if (nt_locked)" not in become:
        return fail("become_expl must not marker_kill flyers")
    # NT-locked still hide; flyers keep leftover SAT / marker.
    if "nt_locked" not in become:
        return fail("NT-locked leftovers still hide (8f25)")
    if "e->vx = 0" not in become or "e->vy = 0" not in become:
        return fail("KEEP: become_expl still zeros leftover vel")
    print("  become_expl: leftover SAT stashed; flyer marker kept")

    spawn = fn_span(ent, "static void spawn_expl(s16 x, s16 y)")
    if not spawn:
        return fail("spawn_expl not found")
    if "e->dest = 0" not in spawn:
        return fail("scatter spawn_expl dest=0 (no leftover yellow pose)")
    if re.search(r"spr_place\s*\(", spawn):
        return fail("spawn_expl must not spr_place (leftover SAT stays empty)")
    print("  spawn_expl: dest=0, no FRAME_LEAD")

    pdeath = fn_span(ent, "void entity_spawn_pdeath(s16 x, s16 y)")
    if not pdeath:
        return fail("entity_spawn_pdeath not found")
    if "e->dest = 0" not in pdeath:
        return fail("pdeath dest=0 (86F3 discs, no flyer leftover)")
    print("  pdeath: dest=0")

    if "static int leftover_flyer_sat(u8 sat)" not in ent:
        return fail("leftover_flyer_sat not found")
    i = ent.rfind("static void anim_sub_4912")
    if i < 0:
        return fail("anim_sub_4912 not found")
    anim = ent[i : i + 2200]
    if "leftover_flyer_sat" not in anim:
        return fail("4912 must keep leftover SAT on the first 84d1 0x1C write")
    if "e->aux == 1" not in anim:
        return fail("yellow pose is table[1] only (84d1[1] 0x1C/0x8A)")
    if "FRAME_CIRCLE" not in anim:
        return fail("later 84d1 discs use FRAME_CIRCLE vehicle + Japan pats")
    if "orb_japan_pat" not in anim:
        return fail("84d1/86F3 SAT 1C/20/24 must encode Japan pats 7/8/9")
    print("  4912: leftover yellow pose then Japan discs")

    if "0xD0, 0x1C, 0x20, 0x24, 0x20, 0x1C" not in ent:
        return fail("k_t35_sat must stay 84d1 names")
    if "0x48, 0x8A, 0x8E, 0x8F, 0x8D, 0x89" not in ent:
        return fail("k_t35_col must stay 84d1 colors")

    japan = fn_span(ent, "static int orb_upload_japan(Slot *s, u8 want)")
    if not japan:
        return fail("orb_upload_japan not found")
    if "KIND_EXPL" not in japan or "KIND_PDEAD" not in japan:
        return fail("84d1/86F3 must share type-72 Japan pat encoder")
    print("  orb_upload_japan: EXPL/PDEAD/HUSK encode pats 7/8/9")

    print("ok: flyer death leftover SAT + Japan discs; no shared triangle")
    return 0


if __name__ == "__main__":
    sys.exit(main())
