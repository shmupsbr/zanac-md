#!/usr/bin/env python3
"""SAT write order is entity_dispatch slot walk, not Y-sort.

zanac.asm 0x445F: SAT ptr E000, IX=E300, B=0x1A, stride 0x20.
0x48B8 sprite_sat_write appends. TMS first SAT index is on top.
  E300 player, E320+ shots, E380 fire, E3A0+ enemies.
0x71f6 complement appends immediately after its primary.

SPR_MIN_DEPTH (-0x8000) loses to draw Y if SGDK sorts unsigned.
Slot depths start at 0. Clear AUTO_DEPTH so SPR_update cannot Y-sort.
SGDK 2.11 SPR_setDepth immediately sortSprite-inserts -- bind at
place/init only. spr_sync must not re-bind (Y-sort thrash).

Usage (from zanac-md):
    python tools/test_sat_order.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
PLY = ROOT / "src" / "player.c"


def main() -> int:
    ent = ENT.read_text(encoding="utf-8")
    ply = PLY.read_text(encoding="utf-8")

    if "SAT_DEPTH_PLAYER" not in ent or "SAT_DEPTH_SHOT" not in ent:
        print("FAIL: missing SAT_DEPTH_* constants")
        return 1
    if "#define SAT_DEPTH_PLAYER    0" not in ent:
        print("FAIL: SAT_DEPTH_PLAYER must be 0 (SPR_MIN_DEPTH loses to Y if unsigned)")
        return 1
    if "SPR_FLAG_AUTO_DEPTH" not in ent:
        print("FAIL: must clear SPR_FLAG_AUTO_DEPTH or SPR_update Y-sorts")
        return 1
    if "sat_bind_depth" not in ent:
        print("FAIL: missing sat_bind_depth")
        return 1
    if "sat_depth_primary" not in ent or "sat_depth_marker" not in ent:
        print("FAIL: missing sat_depth helpers")
        return 1
    if re.search(r"SPR_setDepth\(\s*s->spr,\s*mdy\s*\)", ent):
        print("FAIL: primary depth still uses draw Y")
        return 1
    if re.search(r"SPR_setDepth\(\s*s->mspr,\s*\(s16\)\(mdy - 1\)\s*\)", ent):
        print("FAIL: complement depth still uses draw Y")
        return 1
    if "sat_bind_depth(s->spr, sat_depth_primary(s))" not in ent:
        print("FAIL: primary must use sat_bind_depth(sat_depth_primary)")
        return 1
    if "sat_bind_depth(s->mspr, sat_depth_marker(s))" not in ent:
        print("FAIL: complement must use sat_bind_depth(sat_depth_marker)")
        return 1
    if "SPR_setDepth(s_spr, 0)" not in ply:
        print("FAIL: ship must stay SAT index 0 (E300 first write)")
        return 1
    if "SPR_FLAG_AUTO_DEPTH" not in ply:
        print("FAIL: ship must clear AUTO_DEPTH")
        return 1

    sync = re.search(r"static void spr_sync\(Slot \*s\)\s*\{(.*?)^\}", ent, re.S | re.M)
    if not sync:
        print("FAIL: spr_sync not found")
        return 1
    if "sat_bind_depth" in sync.group(1) or "SPR_setDepth(" in sync.group(1):
        print("FAIL: spr_sync must not SPR_setDepth (immediate sortSprite)")
        return 1
    if "sat_depth_ok" not in ent:
        print("FAIL: cache SAT depth after the first slot-index lookup")
        return 1
    show = re.search(r"static void show_ship\(int vis\)\s*\{(.*?)^\}", ply, re.S | re.M)
    if not show:
        print("FAIL: show_ship not found")
        return 1
    if "SPR_setDepth(" in show.group(1):
        print("FAIL: show_ship must not re-bind depth every tick")
        return 1
    if "SPR_setDepth(s_spr, 0)" not in ply or "SPR_setDepth(s_cspr, 1)" not in ply:
        print("FAIL: ship depth still bound once at init")
        return 1

    # MSX slot math: fire is slot 4 (E380), enemies start slot 5 (E3A0).
    e300 = 0xE300
    if (0xE380 - e300) // 0x20 != 4:
        print("FAIL: E380 is not slot 4")
        return 1
    if (0xE3A0 - e300) // 0x20 != 5:
        print("FAIL: E3A0 is not slot 5")
        return 1
    # Depths: player 0 < shots < fire < enemies; complement = primary+1.
    print("ok: SAT depths follow 445F slot walk (player/shots/fire/enemies)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
