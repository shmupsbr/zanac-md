#!/usr/bin/env python3
"""Title GAME START / OPTIONS + session skill / autofire / keys / ships.

Usage (from zanac-md):
    python tools/test_title_options.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TITLE = ROOT / "src" / "title.c"
OPT_C = ROOT / "src" / "options.c"
OPT_H = ROOT / "inc" / "options.h"
PLY = ROOT / "src" / "player.c"
ENT = ROOT / "src" / "entity.c"
MAPC = ROOT / "src" / "map_script.c"
PLY_H = ROOT / "inc" / "player.h"
ENT_H = ROOT / "inc" / "entity.h"
TITLE_MD = ROOT / "inc" / "title_md.h"


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
    title = TITLE.read_text(encoding="utf-8")
    opt_c = OPT_C.read_text(encoding="utf-8")
    opt_h = OPT_H.read_text(encoding="utf-8")
    ply = PLY.read_text(encoding="utf-8")
    ent = ENT.read_text(encoding="utf-8")
    mapc = MAPC.read_text(encoding="utf-8")
    ply_h = PLY_H.read_text(encoding="utf-8")
    ent_h = ENT_H.read_text(encoding="utf-8")
    title_md = TITLE_MD.read_text(encoding="utf-8")

    # --- title flow -------------------------------------------------
    for name, val in (
        ("PHASE_MAIN", 2),
        ("PHASE_MODE", 3),
        ("PHASE_OPTIONS", 4),
        ("PHASE_KEYS", 5),
    ):
        if f"#define {name}" not in title or f"{val}" not in title.split(f"#define {name}", 1)[1][:20]:
            fail(f"title must define {name} = {val}")
            fails += 1
        else:
            print(f"  title: {name} = {val}")

    if "PHASE_WAIT" in title and "PHASE_MAIN" not in title:
        fail("PHASE_WAIT is obsolete; use PHASE_MAIN")
        fails += 1

    if "Do not open an SGDK START/OPTIONS menu" in title:
        fail("obsolete SGDK START/OPTIONS veto must be gone")
        fails += 1
    else:
        print("  title: obsolete SGDK menu veto gone")

    main_fn = fn_span(title, "static void draw_main_menu(void)") or ""
    if '"GAME START"' not in main_fn or '"OPTIONS"' not in main_fn:
        fail("draw_main_menu must show GAME START / OPTIONS")
        fails += 1
    else:
        print("  title: GAME START / OPTIONS")

    hint = fn_span(title, "static void draw_mode_hint(void)") or ""
    if '"PLEASE SELECT:"' not in hint or '"MSX ENHANCED"' not in hint or '"ZANAC MD"' not in hint:
        fail("mode pick must stay PLEASE SELECT: / MSX ENHANCED / ZANAC MD")
        fails += 1
    else:
        print("  title: PLEASE SELECT / MSX ENHANCED / ZANAC MD")

    wait = fn_span(title, "static void enter_wait(void)") or ""
    if "show_main" not in wait:
        fail("swirl settle must land on GAME START / OPTIONS (show_main)")
        fails += 1
    else:
        print("  title: swirl settle → PHASE_MAIN")

    upd_main = fn_span(title, "static void update_main(u16 joy, u16 pressed)") or ""
    if "enter_mode" not in upd_main or "enter_options" not in upd_main:
        fail("GAME START must enter mode pick; OPTIONS must enter options")
        fails += 1
    else:
        print("  title: GAME START → mode; OPTIONS → options")

    upd_mode = fn_span(title, "static void update_mode(u16 joy, u16 pressed)") or ""
    if "confirm_start" not in upd_mode:
        fail("mode pick must still confirm_start")
        fails += 1
    if "BUTTON_B" not in upd_mode or "show_main" not in upd_mode:
        fail("B on mode pick must return to GAME START / OPTIONS")
        fails += 1
    else:
        print("  title: mode pick B back + confirm_start")

    confirm = fn_span(title, "static void confirm_start(void)") or ""
    if "MODE_ORIGINAL" not in confirm or "MODE_ZANAC_MD" not in confirm:
        fail("confirm_start must keep MODE_ORIGINAL / MODE_ZANAC_MD")
        fails += 1
    if "map_script_continue_round" not in confirm or "game_start_ending" not in confirm:
        fail("KEEP: START-held debug warps")
        fails += 1
    else:
        print("  title: START-held debug warps kept")

    opt_ui = fn_span(title, "static void draw_options_menu(void)") or ""
    for s in ('"REDEFINE KEYS"', '"SKILL LEVEL"', '"AUTOFIRE"', '"PLAYER SHIPS"'):
        if s not in opt_ui:
            fail(f"OPTIONS must list {s}")
            fails += 1
    if '"EASY"' not in opt_ui or '"NORMAL"' not in opt_ui or '"HARD"' not in opt_ui:
        fail("Skill Level must list Easy / Normal / Hard")
        fails += 1
    if '"X2"' not in opt_ui or '"X5"' not in opt_ui:
        fail("Autofire must list X2..X5")
        fails += 1
    else:
        print("  title: OPTIONS rows + values")

    keys_ui = fn_span(title, "static void draw_keys_menu(void)") or ""
    if '"BOTH"' not in keys_ui or '"PRIMARY"' not in keys_ui or '"SECONDARY"' not in keys_ui:
        fail("redefine keys must show BOTH / PRIMARY / SECONDARY")
        fails += 1
    else:
        print("  title: redefine keys roles")

    if "TITLE_MD_Y          40" not in title_md:
        fail("KEEP TITLE_MD_Y = 40")
        fails += 1
    if 'draw_str_pal("MD PORT BY SHMUPSBR @ 2026."' not in title:
        fail("KEEP port credit")
        fails += 1
    if "ROW_CRED0" not in title or "ROW_PICK0" not in title:
        fail("options/main rows must sit in the lower title area")
        fails += 1
    else:
        print("  KEEP: TITLE_MD_Y 40 / credits / lower-area rows")

    # --- ALC 0x50 ---------------------------------------------------
    if "#define ALC_HALF_RANK           0x50" not in opt_h:
        fail("ALC_HALF_RANK must be 0x50")
        fails += 1
    else:
        print("  ALC_HALF_RANK = 0x50 (50% of 0xA0 clamp)")
    if "0xA0" not in opt_h or "50%" not in opt_h:
        fail("document 0x50 as 50% of the 0xA0 clamp threshold")
        fails += 1

    alc_eff = fn_span(opt_c, "u16 options_alc_effective(u16 pos)") or ""
    if "SKILL_EASY" not in alc_eff or "ALC_HALF_RANK" not in alc_eff:
        fail("Easy must cap effective ALC at ALC_HALF_RANK")
        fails += 1
    if "SKILL_HARD" in alc_eff:
        fail("Hard must not floor in options_alc_effective (start seed only)")
        fails += 1
    else:
        print("  Easy: cap only; Hard: no per-frame floor")

    seed = fn_span(opt_c, "u8 options_alc_start_e12e(void)") or ""
    if "SKILL_HARD" not in seed or "ALC_HALF_RANK" not in seed:
        fail("Hard must seed E12E to ALC_HALF_RANK")
        fails += 1
    else:
        print("  Hard: start E12E = 0x50")

    recom = fn_span(ent, "static void alc_recompute(void)") or ""
    if "options_alc_effective" not in recom:
        fail("alc_recompute must apply options_alc_effective to pos")
        fails += 1
    if re.search(r"SKILL_HARD|pos\s*<\s*ALC_HALF_RANK|pos\s*<\s*0x50", recom):
        fail("alc_recompute must not floor Hard at 0x50")
        fails += 1
    else:
        print("  alc_recompute: Easy cap, no Hard floor")

    reset = fn_span(ent, "void entity_alc_reset(void)") or ""
    if "options_alc_start_e12e" not in reset:
        fail("entity_alc_reset must seed E12E from options_alc_start_e12e")
        fails += 1
    else:
        print("  entity_alc_reset: Hard start seed")

    # --- TIME ±50% --------------------------------------------------
    scale = fn_span(opt_c, "u8 options_scale_time(u8 e155)") or ""
    if "* 3u" not in scale and "* 3" not in scale:
        fail("Easy TIME must be ×1.5 (bin * 3 / 2)")
        fails += 1
    if "/ 2u" not in scale and "/ 2" not in scale:
        fail("Hard TIME must be ×0.5")
        fails += 1
    if "bin = 1" not in scale:
        fail("Hard TIME must keep min 1 if the script value was non-zero")
        fails += 1
    if "SKILL_NORMAL" not in scale:
        fail("Normal TIME must pass E155 through")
        fails += 1
    else:
        print("  TIME: Easy ×1.5 / Hard ×0.5 min 1 / Normal passthrough")

    wide = fn_span(mapc, "static void cmd_wide_slot(u8 cmd, const u8 *ops)") or ""
    if "options_scale_time(ops[0])" not in wide:
        fail("cmd B must scale armed E155, not the per-frame tick")
        fails += 1
    else:
        print("  cmd_wide_slot: scale armed E155")

    tick = fn_span(mapc, "static void base_timer_tick(void)") or ""
    if "options_scale_time" in (tick or ""):
        fail("do not scale every TIME tick")
        fails += 1

    # --- autofire periods ------------------------------------------
    if "SHOT_PERIOD     20" not in ent_h and "SHOT_PERIOD     20" not in ply_h:
        if "#define SHOT_PERIOD     20" not in ent_h:
            fail("SHOT_PERIOD must stay 20 (Normal)")
            fails += 1
    periods = fn_span(opt_c, "u8 options_shot_period(void)") or opt_c
    if "k_shot_period" not in opt_c:
        fail("autofire period table missing")
        fails += 1
    if "SHOT_PERIOD / 2" not in opt_c:
        fail("x2 period must be 10 (SHOT_PERIOD/2)")
        fails += 1
    if "(SHOT_PERIOD + 2) / 3" not in opt_c:
        fail("x3 period must be 7 ((20+2)/3)")
        fails += 1
    if "SHOT_PERIOD / 4" not in opt_c:
        fail("x4 period must be 5")
        fails += 1
    if re.search(r"\b4\s*/\*\s*x5", opt_c, re.I) is None and "4                       /* x5 */" not in opt_c:
        fail("x5 period must be 4")
        fails += 1
    else:
        print("  autofire: 20 / 10 / 7 / 5 / 4")

    pupd = fn_span(ply, "void player_update(void)") or ""
    if "options_shot_period()" not in pupd:
        fail("primary reload must use options_shot_period")
        fails += 1
    if "s_alc_cadence = 0" not in pupd:
        fail("E13F must still reset on shot")
        fails += 1
    else:
        print("  primary reload + E13F reset")

    # --- lives ------------------------------------------------------
    init = fn_span(ply, "void player_init(void)") or ""
    if "options_player_ships()" not in init:
        fail("player_init must take starting lives from OPTIONS")
        fails += 1
    if "PLAYER_LIVES_INIT   3" not in ply_h:
        fail("PLAYER_LIVES_INIT must stay 3 (default ships)")
        fails += 1
    if "PLAYER_LIVES_INIT" not in opt_c:
        fail("default ships must be PLAYER_LIVES_INIT")
        fails += 1
    else:
        print("  lives: init from options, default 3")

    # --- default remap ---------------------------------------------
    if not re.search(
        r"s_bind\[3\]\s*=\s*\{\s*FIRE_ROLE_BOTH\s*,\s*FIRE_ROLE_PRIMARY\s*,\s*FIRE_ROLE_SECONDARY",
        opt_c,
    ):
        fail("default remap A=BOTH B=PRIMARY C=SECONDARY")
        fails += 1
    else:
        print("  default remap: A both / B primary / C secondary")
    if "options_cycle_bind" not in opt_c:
        fail("redefine keys must swap roles without duplicates")
        fails += 1

    if "s_skill = SKILL_NORMAL" not in opt_c:
        fail("default skill must be Normal")
        fails += 1
    if "s_autofire = AUTOFIRE_NORMAL" not in opt_c:
        fail("default autofire must be Normal")
        fails += 1
    else:
        print("  defaults: Normal skill / Normal autofire / 3 ships")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
