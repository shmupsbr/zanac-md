#!/usr/bin/env python3
"""Respawn zeroes E130 (player_ship_handler 0x7606).

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  player_ship_handler first frame (bit7 clear), every 4068 ship spawn:
    75ff  CALL 0x7544          ; fire_reset
    7602  SUB A
    7603  LD (0xe10b), A       ; shot_level = 0
    7606  LD (0xe130), A       ; encounter B = 0
    7609  CALL 0xbfd6          ; HUD readout only — do not port
    760c  CALL 0x4c4d          ; update_status_bar
    760f  CALL 0x7771          ; load_shot_params

  Readers of E130:
    7ad4  type 11  RRCA x3 / AND 0x0E -> pair (E130>>4)&7
    8279  type 64  SRL A -> spawn_type_list[E130/2 + R&3]

  BFC8 INCs E130 on chip / fire-up / idol death. After a late-credit
  death the old port kept that leftover, so the next life opened the
  wrong type-11 pair and the wrong type-64 slice. First life is fine
  (entity_init zeroes E130 after player_init).

  7609 CALL BFD6 is the encounter HUD tail. Do not add it.

Usage (from zanac-md):
    python tools/test_respawn_e130_7606.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTITY = ROOT / "src" / "entity.c"
PLAYER = ROOT / "src" / "player.c"
PLAYER_H = ROOT / "inc" / "player.h"
ENTITY_H = ROOT / "inc" / "entity.h"
SPAWN = ROOT / "src" / "data" / "spawn_table.c"
MAPC = ROOT / "src" / "map_script.c"
ASM_CANDIDATES = [
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    Path.home() / "zanac-re" / "source" / "zanac.asm",
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def load_asm() -> str | None:
    for p in ASM_CANDIDATES:
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    return None


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


def parse_spawn_list(src: str) -> list[int] | None:
    m = re.search(
        r"const u8 spawn_type_list\[SPAWN_TYPE_LEN\] = \{([^}]+)\}", src
    )
    if not m:
        return None
    return [int(x, 0) for x in re.findall(r"0x[0-9A-Fa-f]+|\d+", m.group(1))]


def type11_pair(e130: int) -> int:
    """7ad4: RRCA x3 / AND 0x0E as byte offset -> (E130>>4)&7."""
    return (e130 >> 4) & 7


def type64_base(e130: int) -> int:
    """8279: SRL A -> E130>>1 (R&3 added by the caller)."""
    return e130 >> 1


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8", errors="replace")
    ply = PLAYER.read_text(encoding="utf-8", errors="replace")
    hdr = PLAYER_H.read_text(encoding="utf-8", errors="replace")
    eh = ENTITY_H.read_text(encoding="utf-8", errors="replace")
    mapc = MAPC.read_text(encoding="utf-8", errors="replace")
    spawn_src = SPAWN.read_text(encoding="utf-8", errors="replace")
    asm = load_asm()

    if asm:
        if not re.search(r"LD\s+\(0xe10b\),\s*A\s*;\s*0x7603", asm, re.I):
            fail("zanac.asm 7603 is not LD (E10B),A")
            fails += 1
        else:
            print("  ASM 7603: LD (E10B),A")
        if not re.search(r"LD\s+\(0xe130\),\s*A\s*;\s*0x7606", asm, re.I):
            fail("zanac.asm 7606 is not LD (E130),A")
            fails += 1
        else:
            print("  ASM 7606: LD (E130),A")
        if not re.search(r"CALL\s+0xbfd6\s*;\s*0x7609", asm, re.I):
            fail("zanac.asm 7609 is not CALL BFD6")
            fails += 1
        else:
            print("  ASM 7609: CALL BFD6 (HUD-only; do not port)")
        if not re.search(r"LD\s+A,\s*\(0xe130\)\s*;\s*0x7ad4", asm, re.I):
            fail("zanac.asm 7ad4 is not LD A,(E130)")
            fails += 1
        else:
            print("  ASM 7ad4: type 11 reads E130")
        if not re.search(r"LD\s+A,\s*\(0xe130\)\s*;\s*0x8279", asm, re.I):
            fail("zanac.asm 8279 is not LD A,(E130)")
            fails += 1
        else:
            print("  ASM 8279: type 64 reads E130")
    else:
        print("  (no zanac.asm; ASM checks skipped)")

    # Stale E130=0x20 (BFC8 after chips) vs 7606 zero.
    if type11_pair(0x20) == type11_pair(0):
        fail("E130=0x20 must change type 11 pair vs 0")
        fails += 1
    elif type11_pair(0x20) != 2 or type11_pair(0) != 0:
        fail(f"type11 pairs: leftover {type11_pair(0x20)} want 2; zero {type11_pair(0)} want 0")
        fails += 1
    else:
        print("  type 11 pair: leftover 0x20 -> 2; respawn 0 -> 0")

    if type64_base(0x20) == type64_base(0):
        fail("E130=0x20 must change type 64 base vs 0")
        fails += 1
    elif type64_base(0x20) != 16 or type64_base(0) != 0:
        fail(f"type64 base: leftover {type64_base(0x20)} want 16; zero {type64_base(0)} want 0")
        fails += 1
    else:
        print("  type 64 index: leftover 0x20 -> 16; respawn 0 -> 0")

    zero = fn_span(ent, "void entity_zero_e130(void)")
    if not zero or "s_e130 = 0" not in zero:
        fail("entity_zero_e130 must assign s_e130 = 0")
        fails += 1
    else:
        print("  entity_zero_e130: s_e130 = 0")

    if "void entity_zero_e130(void)" not in eh:
        fail("entity.h must declare entity_zero_e130")
        fails += 1
    else:
        print("  entity.h: entity_zero_e130")

    resp = fn_span(ply, "static void respawn(void)")
    if not resp:
        fail("respawn not found")
        fails += 1
    elif "entity_zero_e130()" not in resp:
        fail("respawn must call entity_zero_e130 (7606)")
        fails += 1
    elif "s_shot_level = 0" not in resp:
        fail("respawn must still zero E10B (7603)")
        fails += 1
    elif "fire_reset()" not in resp:
        fail("respawn must still fire_reset (75ff)")
        fails += 1
    elif re.search(r"CALL\s+0xBFD6|base_encounter_ctrl", resp, re.I):
        fail("respawn must not invoke the 7609 HUD tail")
        fails += 1
    else:
        print("  respawn: 7603 E10B + 7606 E130; no BFD6")

    init = fn_span(ent, "void entity_init(void)")
    if not init or "s_e130 = 0" not in init:
        fail("entity_init must still seed E130=0 (first life)")
        fails += 1
    else:
        print("  entity_init: first-life E130=0")

    spawn11 = fn_span(ent, "static void spawn_spawner(Slot *e)")
    if not spawn11 or "(s_e130 >> 4) & 7" not in spawn11:
        fail("type 11 must still index (E130>>4)&7")
        fails += 1
    else:
        print("  type 11: (E130>>4)&7")

    if "s_e130 >> 1" not in ent:
        fail("type 64 must still index E130/2")
        fails += 1
    else:
        print("  type 64: E130/2")

    # KEEP: just-merged type 80 / 8A26 and the standing KEEP list.
    husk = fn_span(ent, "static void husk_step(Slot *e)")
    if not husk or "tick_e124_84bc()" not in husk:
        fail("husk_step 849c E124 was reverted")
        fails += 1
    else:
        print("  KEEP: husk_step 849c ticks E124")

    boom = fn_span(ent, "void entity_explode_airborne(void)")
    if not boom or "become_expl" not in boom:
        fail("8A26 become_expl was reverted")
        fails += 1
    elif re.search(r"KIND_EXPL|KIND_PDEAD", boom.split("slot_msx_type", 1)[0]
                   if "slot_msx_type" in boom else ""):
        fail("8A26 must not skip KIND_EXPL / KIND_PDEAD")
        fails += 1
    else:
        print("  KEEP: 8A26 still reconverts live type 35")

    if "s_fire7_life_ticked" not in ent:
        fail("fire 7 730B-once flag was reverted")
        fails += 1
    else:
        print("  KEEP: fire 7 730B once (s_fire7_life_ticked)")

    stealth = fn_span(ent, "static void spawn_stealth(Slot *e, u8 type)")
    if not stealth or "e->clock = 48" not in stealth:
        fail("type 65 7ff0 +1D=0x30 seed was reverted")
        fails += 1
    else:
        print("  KEEP: spawn_stealth clock=48")

    step = fn_span(ent, "static void stealth_step(Slot *e)")
    if not step or "(e->variant == 65) ? 32 : 48" not in step:
        fail("stealth_step +0D reload 32/48 was reverted")
        fails += 1
    else:
        print("  KEEP: stealth_step reload 32/48")

    md = re.search(r"static const u8 k_stealth_dir\[4\] = \{([^}]+)\}", ent)
    if not md:
        fail("k_stealth_dir not found")
        fails += 1
    else:
        ds = [int(x, 0) for x in re.findall(r"0x[0-9A-Fa-f]+|\d+", md.group(1))]
        if ds != [2, 6, 4, 4]:
            fail(f"k_stealth_dir {ds} want [2, 6, 4, 4]")
            fails += 1
        else:
            print("  KEEP: stealth dir[0]=2")

    if stealth and "e->sat_col = 0x85" not in stealth:
        fail("type 65 SAT 0x85 was reverted")
        fails += 1
    elif stealth and "e->hp = (type == 65) ? 4 : 7" not in stealth:
        fail("type 65 HP 4 was reverted")
        fails += 1
    else:
        print("  KEEP: type 65 SAT 0x85 HP 4")

    rst = fn_span(ply, "static void fire_reset(void)")
    if not rst or "s_e14f = 0" not in rst or "fire_select(0)" not in rst:
        fail("fire_reset 7544 E14F wipe was reverted")
        fails += 1
    else:
        print("  KEEP: fire_reset 7544 zeroes E14F then fire_select(0)")

    sel = fn_span(ply, "static void fire_select(u8 n)")
    if not sel or "s_e14f" in sel:
        fail("7548 fire_select must not touch E14F")
        fails += 1
    else:
        print("  KEEP: player_fire_select is 7548")

    shot = fn_span(ent, "bool entity_spawn_shot(s16 x, s16 y)")
    if not shot or "s_alc_shots++" not in shot or re.search(
        r"s_alc_shots\s*<\s*255", shot
    ):
        fail("E140 76e8 wrap was reverted")
        fails += 1
    else:
        print("  KEEP: E140 76e8 still wraps")

    alc = fn_span(ent, "void entity_on_shot_fired(u8 cadence)")
    if not alc or "s_e141++" not in alc or "s_e141--" not in alc:
        fail("E141 76bc saturate was reverted")
        fails += 1
    else:
        print("  KEEP: E141 still saturates")

    gate = fn_span(ent, "static int descender_on_death(Slot *e)")
    if not gate or "(s_alc_shots & 0x3F) == (player_score_lo() & 0x3F)" not in gate:
        fail("type 61 gate 8374 was reverted")
        fails += 1
    else:
        print("  KEEP: type 61 gate 8374")

    box = fn_span(ent, "static void box_step(Slot *e)")
    if not box or "e->bind = 0x00C0" not in box:
        fail("box reveal 7841 00C0 was reverted")
        fails += 1
    else:
        print("  KEEP: box reveal bind=0x00C0")

    if "while (nt == 64 && guard < 8)" not in ent:
        fail("type 64 8279 re-roll was reverted")
        fails += 1
    else:
        print("  KEEP: type 64 8279 re-roll")

    if "ebullet_apply_vis" not in ent:
        fail("type 21 8659 was reverted")
        fails += 1
    else:
        print("  KEEP: type 21 8659 via ebullet_apply_vis")

    initf = fn_span(ent, "static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)")
    if not initf or "variant != 21" not in initf:
        fail("init_frag type 21 no +04 (863b) was reverted")
        fails += 1
    else:
        print("  KEEP: type 21 init still no +04")

    jump = fn_span(mapc, "static void cmd_script_jump(u8 cmd, const u8 *ops)")
    if not jump:
        fail("cmd_script_jump not found")
        fails += 1
    elif "MAP_ENDING_STREAM" in jump:
        fail("cmd_script_jump must not special-case 0xA6F4")
        fails += 1
    elif "entity_alc_reset" in jump:
        fail("cmd 9 must still never alc_reset")
        fails += 1
    else:
        print("  KEEP: cmd 9 dest 0xA6F4 is a 941b jump; no alc_reset")

    latch = fn_span(ply, "void player_fireup_latch(void)")
    if not latch or "s_invuln = 0" not in latch or "s_if_latch = 1" not in latch:
        fail("player_fireup_latch must stay +1B=0 + SET 7")
        fails += 1
    else:
        print("  KEEP: player_fireup_latch +1B=0")

    grant = fn_span(ply, "void player_grant_iframes(void)")
    if not grant or "s_invuln = PLAYER_IFRAMES" not in grant:
        fail("chip/spawn +1B=0x40 was reverted")
        fails += 1
    else:
        print("  KEEP: chip/spawn SET latch + +1B=0x40")

    collide = fn_span(ent, "static void collide_player(void)")
    fireup = None
    if collide:
        m = re.search(r"if \(e->kind == KIND_FIREUP\)\s*\{", collide)
        if m:
            i = m.end() - 1
            depth = 0
            for j in range(i, len(collide)):
                if collide[j] == "{":
                    depth += 1
                elif collide[j] == "}":
                    depth -= 1
                    if depth == 0:
                        fireup = collide[i : j + 1]
                        break
    if not fireup or "player_fire_select" not in fireup or "player_fire_reset" in fireup:
        fail("KIND_FIREUP must still player_fire_select (8eaf JP 7548)")
        fails += 1
    else:
        print("  KEEP: type 83 still player_fire_select (7548)")

    riser = fn_span(ent, "static void become_riser(Slot *e)")
    grant_life = fn_span(ply, "void player_grant_life(void)")
    if not riser or "player_fire_select" in riser or "fire_select" in riser:
        fail("type 62 must stay lives-only")
        fails += 1
    elif grant_life and ("fire_select" in grant_life or "player_fire_select" in grant_life):
        fail("player_grant_life must stay lives-only")
        fails += 1
    else:
        print("  KEEP: type 62 lives-only")

    if not collide or "if (player_dead() || player_is_over())" not in collide:
        fail("collide_player must skip only dead/over")
        fails += 1
    elif re.search(r"if\s*\(\s*player_invincible", collide):
        fail("collide_player must not skip on s_invuln")
        fails += 1
    else:
        print("  KEEP: collide_player skips only dead/over")

    complete = fn_span(ent, "void entity_alc_complete(void)")
    if not complete or "0x20" not in complete:
        fail("entity_alc_complete E132+=0x20 was reverted")
        fails += 1
    else:
        print("  KEEP: warp entity_alc_complete E132+=0x20")
    alc_reset = fn_span(ent, "void entity_alc_reset(void)")
    if not alc_reset or "0x20" in alc_reset:
        fail("entity_alc_reset must not bake +0x20")
        fails += 1
    else:
        print("  KEEP: alc_reset no +0x20")

    if "e->sat_col = 0x89" not in ent:
        fail("type 10 sat_col 0x89 was reverted")
        fails += 1
    else:
        print("  KEEP: type 10 sat_col 0x89")

    if "0xBFD6" in ent or "0xbfd6" in ent or "0xBFD6" in ply or "0xbfd6" in ply:
        fail("must not CALL 0xBFD6")
        fails += 1
    else:
        print("  KEEP: no 0xBFD6")

    vals = parse_spawn_list(spawn_src)
    if vals:
        for t, name in ((21, "21"), (41, "41"), (45, "45")):
            if t in vals:
                fail(f"spawn_type_list must keep type {name} child-only")
                fails += 1
            else:
                print(f"  KEEP: type {name} child-only")

    add = fn_span(ply, "void player_add_shot_level(void)")
    if not add or "fire_reset" in add or "fire_select(s_fire_num)" not in add:
        fail("78f2 must stay fire_select(E14B)")
        fails += 1
    else:
        print("  KEEP: 78f2 overflow still fire_select(E14B)")

    if "player_fire_reset" not in hdr or "player_fire_select" not in hdr:
        fail("player.h must keep fire_reset / fire_select split")
        fails += 1
    else:
        print("  KEEP: player.h fire_reset + fire_select")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
