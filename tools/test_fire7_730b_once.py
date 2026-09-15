#!/usr/bin/env python3
"""Fire 7 730B is once per frame: 7253 BIT 7 mutex.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  fire_weapon_handler 0x7253:
    BIT 7,(IX+0x00)
    JP NZ, 0x7279          ; update dispatch only
    SET 7,(IX+0x00)
    ... init dispatch ...
  fire_init_dispatch[7] = 0x728F
    CALL 0x730B            ; life timer
    ... 4cf7 ...
    falls into 72de + 4898
  fire_update_dispatch[7] = 0x7306
    CALL 0x730B
    JR 0x72de

  728F and 7306 are mutually exclusive. Init frame ticks 730B once.

  Old port: entity_try_spawn_fire (728F) AND update_fire (7306)
  both called player_fire_life_tick() on the spawn frame
  (player_update then entity_update; s_fire.alive is already 1).
  E14C/E14D advanced twice vs MSX once. If E14C was 1, spawn
  wrapped and DEC E14D, then update DECd the reloaded 0x3C.

Usage (from zanac-md):
    python tools/test_fire7_730b_once.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTITY = ROOT / "src" / "entity.c"
PLAYER = ROOT / "src" / "player.c"
PLAYER_H = ROOT / "inc" / "player.h"
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


def old_port_ticks(n_frames: int) -> int:
    """Spawn-frame: 728F tick then 7306 tick (alive already)."""
    ticks = 0
    alive = False
    for f in range(n_frames):
        if not alive and f == 0:
            alive = True
            ticks += 1
        if alive:
            ticks += 1
    return ticks


def new_port_ticks(n_frames: int) -> int:
    """Spawn-frame: 728F tick; 7306 skipped via s_fire7_life_ticked."""
    ticks = 0
    alive = False
    skip = False
    for f in range(n_frames):
        if not alive and f == 0:
            alive = True
            ticks += 1
            skip = True
        if alive:
            if skip:
                skip = False
            else:
                ticks += 1
    return ticks


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8", errors="replace")
    ply = PLAYER.read_text(encoding="utf-8", errors="replace")
    hdr = PLAYER_H.read_text(encoding="utf-8", errors="replace")
    mapc = MAPC.read_text(encoding="utf-8", errors="replace")
    spawn_src = SPAWN.read_text(encoding="utf-8", errors="replace")
    asm = load_asm()

    if asm:
        if not re.search(r"BIT\s+7,\s*\(IX\+0x00\)\s*;\s*0x7253", asm, re.I):
            fail("zanac.asm 7253 is not BIT 7,(IX+00)")
            fails += 1
        else:
            print("  ASM 7253: BIT 7 init/update mutex")
        if not re.search(r"JP\s+NZ,\s*0x7279\s*;\s*0x7257", asm, re.I):
            fail("zanac.asm 7257 is not JP NZ 7279")
            fails += 1
        else:
            print("  ASM 7257: JP NZ 7279 (update only when bit7)")
        if not re.search(r"CALL\s+0x730b\s*;\s*0x728f", asm, re.I):
            fail("zanac.asm 728F is not CALL 730B")
            fails += 1
        else:
            print("  ASM 728F: init CALL 730B")
        if not re.search(r"CALL\s+0x730b\s*;\s*0x7306", asm, re.I):
            fail("zanac.asm 7306 is not CALL 730B")
            fails += 1
        else:
            print("  ASM 7306: update CALL 730B")
        if not re.search(r"JR\s+0x72de\s*;\s*0x7309", asm, re.I):
            fail("zanac.asm 7309 is not JR 72de")
            fails += 1
        else:
            print("  ASM 7309: JR 72de after update 730B")
        if not re.search(r"LD\s+HL,\s*0xe14c\s*;\s*0x730b", asm, re.I):
            fail("zanac.asm 730B is not LD HL,E14C")
            fails += 1
        else:
            print("  ASM 730B: DEC E14C life timer")
        # Init table slot 7 is 728F; update slot 7 is 7306.
        init = re.search(
            r"fire_init_dispatch:.*?DW\s+([^\n]+);\s*0x7269", asm, re.S
        )
        upd = re.search(
            r"fire_update_dispatch:.*?DW\s+([^\n]+);\s*0x727f", asm, re.S
        )
        if not init or "0x728f" not in init.group(1).lower():
            fail("fire_init_dispatch[7] must be 0x728F")
            fails += 1
        else:
            print("  ASM 7269[7]: 728F")
        if not upd or "0x7306" not in upd.group(1).lower():
            fail("fire_update_dispatch[7] must be 0x7306")
            fails += 1
        else:
            print("  ASM 727F[7]: 7306")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    old = old_port_ticks(3)
    new = new_port_ticks(3)
    if old != 4:
        fail(f"old spawn+update ticks {old} want 4 (2+1+1)")
        fails += 1
    elif new != 3:
        fail(f"new mutex ticks {new} want 3 (1+1+1)")
        fails += 1
    else:
        print("  frame math: spawn frame 1 tick (old was 2); 3 frames -> 3")

    spawn = fn_span(ent, "void entity_try_spawn_fire(s16 x, s16 y, u8 xvel_sel)")
    if not spawn:
        fail("entity_try_spawn_fire not found")
        fails += 1
    elif "player_fire_life_tick()" not in spawn:
        fail("728F must still CALL 730B on fire 7 init")
        fails += 1
    elif "s_fire7_life_ticked = 1" not in spawn:
        fail("728F must set s_fire7_life_ticked so 7306 does not re-tick")
        fails += 1
    else:
        print("  728F: player_fire_life_tick + s_fire7_life_ticked=1")

    upd_fn = fn_span(ent, "static void update_fire(void)")
    if not upd_fn:
        fail("update_fire not found")
        fails += 1
    else:
        # Fire 7 update must honor the skip; must still tick when skip is 0.
        if "s_fire7_life_ticked" not in upd_fn:
            fail("7306 must honor s_fire7_life_ticked")
            fails += 1
        elif not re.search(
            r"if\s*\(\s*!skip\s*&&\s*player_fire_life_tick\(\)\s*\)", upd_fn
        ):
            fail("7306 must skip player_fire_life_tick when spawn already ticked")
            fails += 1
        elif upd_fn.count("player_fire_life_tick()") < 2:
            # fire 3 (73c2) + fire 7 (7306)
            fail("update_fire must keep 73c2 fire-3 life tick")
            fails += 1
        else:
            print("  7306: skip 730B when s_fire7_life_ticked")
        if "s_fire7_life_ticked = 0" not in upd_fn:
            fail("update_fire must clear s_fire7_life_ticked")
            fails += 1
        else:
            print("  update_fire: clears s_fire7_life_ticked")

    if "static u8  s_fire7_life_ticked" not in ent and (
        "static u8 s_fire7_life_ticked" not in ent
    ):
        fail("s_fire7_life_ticked must be a slot-local flag")
        fails += 1
    else:
        print("  s_fire7_life_ticked declared")

    life = fn_span(ply, "u8 player_fire_life_tick(void)")
    if not life or "s_fire_timer--" not in life or "fire_reset()" not in life:
        fail("player_fire_life_tick 730B body was reverted")
        fails += 1
    else:
        print("  730B: DEC E14C / underflow fire_reset")

    # Fire 3 update-only 730B must stay (73c2); init 7331 has no 730B.
    if not spawn or spawn.count("player_fire_life_tick()") != 1:
        fail("only fire 7 init (728F) ticks 730B in spawn")
        fails += 1
    else:
        print("  spawn: only fire 7 ticks 730B (not fire 3 7331)")

    # KEEP: type 65 first volley just shipped.
    stealth = fn_span(ent, "static void spawn_stealth(Slot *e, u8 type)")
    if not stealth or "e->clock = 48" not in stealth:
        fail("type 65 7ff0 +1D=0x30 seed was reverted")
        fails += 1
    elif re.search(r"e->clock\s*=\s*\(type\s*==\s*65\)", stealth):
        fail("type 65 must not seed clock from +0D")
        fails += 1
    else:
        print("  KEEP: spawn_stealth clock=48 (+1D stays 0x30)")

    step = fn_span(ent, "static void stealth_step(Slot *e)")
    if not step or "(e->variant == 65) ? 32 : 48" not in step:
        fail("stealth_step +0D reload 32/48 was reverted")
        fails += 1
    else:
        print("  KEEP: stealth_step reload 32 for 65, 48 for 34/66")

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
        print("  KEEP: E141 still saturates (76bc)")

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

    if not re.search(
        r"e->variant == 21(?:\s*&&\s*options_bullet_high\(\))?\)\s*\n\s*spr_set_sat_col\(\s*e,\s*"
        r"\(u8\)\(0x80\s*\|\s*\(rnd\(\)\s*&\s*0x0F\)\)\)",
        ent,
    ):
        fail("type 21 8659 was reverted")
        fails += 1
    else:
        print("  KEEP: type 21 8659 R-nibble|0x80")

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

    if "0xBFD6" in ent or "0xbfd6" in ent:
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
