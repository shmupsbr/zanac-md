#!/usr/bin/env python3
"""Mega Drive A/B/C fire split. Intentional MD control change, not MSX 1:1.

MSX E100 bit4 = SPACE (primary shot + fire-weapon together).
MD buttons (Filipe):
  A = current both (primary + secondary)
  B = primary only (type-2 shots; do not spawn type 3)
  C = secondary only (depleting fire-weapon)
Secondary ammo (E14D) decreases when the fire-weapon is live and that
path calls fire_dec_ammo — A or C spawn type 3; B does not.

In-play BUTTON_B must not return to title (old port convenience).
Fire 2 Field Shutter stays auto (fire_select writes E380=3).

Usage (from zanac-md):
    python tools/test_md_fire_abc.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLY = ROOT / "src" / "player.c"
GAME = ROOT / "src" / "game.c"
MAPC = ROOT / "src" / "map_script.c"
README = ROOT / "README.md"


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


def main() -> int:
    fails = 0
    ply = PLY.read_text(encoding="utf-8")
    game = GAME.read_text(encoding="utf-8")
    mapc = MAPC.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")

    upd = fn_span(ply, "void player_update(void)")
    if not upd:
        fail("player_update not found")
        fails += 1
        upd = ply

    # Primary: A or B.
    if not re.search(
        r"if \(joy & \(BUTTON_A \| BUTTON_B\)\)",
        upd,
    ):
        fail("primary shot must be A|B")
        fails += 1
    else:
        print("  player_update: primary shot on A|B")

    if "entity_spawn_shot" not in upd or "entity_on_shot_fired" not in upd:
        fail("KEEP: primary still ALC + spawn_shot")
        fails += 1
    else:
        print("  KEEP: ALC + spawn_shot on primary")

    # Secondary: A or C, or fire 2 auto. B must not be in this mask.
    sec = re.search(
        r"if \(\(joy & \(([^)]+)\)\) \|\| s_fire_num == 2\)",
        upd,
    )
    if not sec:
        fail("secondary spawn gate not found")
        fails += 1
    else:
        mask = sec.group(1)
        if "BUTTON_A" not in mask or "BUTTON_C" not in mask:
            fail("secondary must be A|C")
            fails += 1
        elif "BUTTON_B" in mask:
            fail("B must not spawn the fire-weapon")
            fails += 1
        else:
            print("  player_update: secondary on A|C; B excluded")

    if "entity_try_spawn_fire" not in upd:
        fail("KEEP: entity_try_spawn_fire still the type-3 spawn")
        fails += 1
    else:
        print("  KEEP: type 3 via entity_try_spawn_fire")

    if "s_fire_num == 2" not in upd:
        fail("KEEP: fire 2 Field stays auto")
        fails += 1
    else:
        print("  KEEP: fire 2 auto")

    # In-play B must not go_title. Game-over skip includes B.
    play = fn_span(game, "void game_update(void)")
    if not play:
        # game.c uses a different name?
        play = game
    if re.search(
        r"if \(joy & BUTTON_B\)\s*\{\s*go_title\(\);",
        game,
    ):
        fail("in-play BUTTON_B must not go_title")
        fails += 1
    else:
        print("  game_update: B is not title-return in play")

    if "BUTTON_A | BUTTON_B | BUTTON_C" not in game:
        fail("game-over skip must accept A/B/C")
        fails += 1
    else:
        print("  game-over: A/B/C skip wait")

    if "BUTTON_A | BUTTON_B | BUTTON_C" not in mapc:
        fail("credits wait_fire must accept A/B/C")
        fails += 1
    else:
        print("  credits wait_fire: A/B/C")

    if "Primary shot only" not in readme and "primary only" not in readme.lower():
        fail("README must document B = primary only")
        fails += 1
    else:
        print("  README: B primary-only documented")
    if "Back to title" in readme and "| Game   | B |" in readme:
        fail("README must not keep Game B = Back to title")
        fails += 1
    else:
        print("  README: in-play B is no longer title-return")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
