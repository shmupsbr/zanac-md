#!/usr/bin/env python3
"""Skill scales boss/base clear / TIME-window bonuses only.

0x9302 base_clear_award_index_table → 0x4AEA via 0x91C1 (map_script_base_cleared).
Easy = 50% of Normal. Hard = +100% (double). Normal unchanged.

Scaled:
  - map_script_base_cleared / 0x91C1 (cmd-B TIME-window clear, ending
    E157 0x10/0x11/>=0x12 awards, any 0x9302 index)

Not scaled:
  - per-kill 4a6a / k_struct_award / player_add_score
  - timeout 9325 (no award)

Default Normal + EVERY X must leave the 0x4AEA table and 0x9302 path
unchanged (200 for R1 first base).

Usage (from zanac-md):
    python tools/test_skill_clear_bonus.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPT_C = ROOT / "src" / "options.c"
OPT_H = ROOT / "inc" / "options.h"
PLY = ROOT / "src" / "player.c"
PLY_H = ROOT / "inc" / "player.h"
MAPC = ROOT / "src" / "map_script.c"
ENT = ROOT / "src" / "entity.c"

K_CLEAR = [
    0x0A, 0x0C, 0x0D, 0x10, 0x0E, 0x0F, 0x0E, 0x0F,
    0x0F, 0x10, 0x11, 0x11, 0x00, 0x00, 0x00, 0x11,
    0x12, 0x13, 0x14,
]
K_AWARD = (
    0, 1, 6, 10, 17, 20, 30, 50, 80, 100,
    200, 400, 800, 1000, 1500, 2000, 3000, 4000, 5000, 10000, 200000,
)


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


def scale_clear(pts: int, skill: str) -> int:
    if skill == "easy":
        return pts // 2
    if skill == "hard":
        return pts * 2
    return pts


def main() -> int:
    fails = 0
    opt_c = OPT_C.read_text(encoding="utf-8")
    opt_h = OPT_H.read_text(encoding="utf-8")
    ply = PLY.read_text(encoding="utf-8")
    ply_h = PLY_H.read_text(encoding="utf-8")
    mapc = MAPC.read_text(encoding="utf-8")
    ent = ENT.read_text(encoding="utf-8")

    if "options_scale_clear_bonus" not in opt_h or "options_scale_clear_bonus" not in opt_c:
        fail("options_scale_clear_bonus must exist")
        fails += 1
    scale = fn_span(opt_c, "u32 options_scale_clear_bonus(u32 pts)") or ""
    if "pts / 2UL" not in scale and "pts / 2" not in scale:
        fail("Easy clear bonus must be half")
        fails += 1
    if "pts * 2UL" not in scale and "pts * 2" not in scale:
        fail("Hard clear bonus must be double")
        fails += 1
    if "SKILL_EASY" not in scale or "SKILL_HARD" not in scale:
        fail("clear bonus scale must branch on Easy / Hard")
        fails += 1
    else:
        print("  options_scale_clear_bonus: Easy /2, Hard *2, Normal passthrough")

    # Sim: R1 first base 0x0A → 200
    if K_CLEAR[0] != 0x0A or K_AWARD[0x0A] != 200:
        fail("R1 first-base table must stay 200")
        fails += 1
    if scale_clear(200, "normal") != 200:
        fail("Normal must leave 200 unchanged")
        fails += 1
    if scale_clear(200, "easy") != 100:
        fail("Easy 200 → 100")
        fails += 1
    if scale_clear(200, "hard") != 400:
        fail("Hard 200 → 400")
        fails += 1
    if scale_clear(200000, "easy") != 100000:
        fail("Easy 200000 → 100000")
        fails += 1
    if scale_clear(200000, "hard") != 400000:
        fail("Hard 200000 → 400000")
        fails += 1
    print("  sim: 200 → 100 / 200 / 400; 200000 → 100000 / 200000 / 400000")

    cleared = fn_span(mapc, "void map_script_base_cleared(void)") or ""
    if "player_add_clear_bonus" not in cleared:
        fail("map_script_base_cleared must player_add_clear_bonus (skill+extend)")
        fails += 1
    else:
        print("  0x91C1: player_add_clear_bonus")

    addc = fn_span(ply, "void player_add_clear_bonus(u8 award_idx)") or ""
    if "options_scale_clear_bonus" not in addc:
        fail("player_add_clear_bonus must apply options_scale_clear_bonus")
        fails += 1
    else:
        print("  player_add_clear_bonus: skill scale")

    if "player_clear_bonus_points" not in ply_h:
        fail("player.h must expose player_clear_bonus_points for the banner")
        fails += 1
    draw = fn_span(mapc, "static void bonus_draw(u8 award_idx)") or ""
    if "player_clear_bonus_points" not in draw:
        fail("BONUS banner must print the scaled placar value")
        fails += 1
    else:
        print("  bonus_draw: scaled placar value")

    # Kills stay on player_add_score (no skill scale).
    adds = fn_span(ply, "void player_add_score(u8 award_idx)") or ""
    if "options_scale_clear_bonus" in adds:
        fail("player_add_score must not skill-scale every kill")
        fails += 1
    award_sub = fn_span(ent, "static void award_subtype(u8 t)") or ""
    if "player_add_score" not in award_sub:
        fail("kills must still player_add_score (4a6a)")
        fails += 1
    if "player_add_clear_bonus" in award_sub:
        fail("do not skill-scale per-kill 4a6a")
        fails += 1
    else:
        print("  KEEP: per-kill 4a6a unscaled by skill")

    tick = fn_span(mapc, "static void base_timer_tick(void)") or ""
    if "player_add_clear_bonus" in (tick or "") or "player_add_score" in (tick or ""):
        fail("timeout 9325 must stay no-award")
        fails += 1
    else:
        print("  KEEP: TIME 00:00 still no award")

    if "s_skill = SKILL_NORMAL" not in opt_c:
        fail("default skill must stay Normal")
        fails += 1
    else:
        print("  defaults: Normal skill → clear bonuses unchanged")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
