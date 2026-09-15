#!/usr/bin/env python3
"""explode_enemies 0x8A26 reconverts live type 35 (does not skip 0x23).

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  8a37  LD A,(IY+0)
  8a3a  AND 0x7F
  8a3c  JR Z, 8a4d            ; empty
  8a3e  CP 0x46
  8a40  JR NC, 8a4d           ; type >= 70
  8a42  CP 0x28
  8a44  JR Z, 8a4d            ; type 40 clear only
  8a46  LD (IY+0), 0x23       ; bit7 CLEAR
  8a4a  LD (IY+0x18), A       ; +0x18 = unmasked type (0x23 if already 35)

  handler_type35 8446 BIT 7: clear -> ALC dump, ev17, 4a6a(+0x18),
  E124 DEC / E125, 84d1 arm. Writing 0x23 on a live 0xA3 restarts that.

  Old port: skip KIND_EXPL / KIND_PDEAD. Mid-anim discs stayed put;
  type 60 was also skipped (0x3C is in [1,0x45]). Yellow-orb / fire-6
  / 90fe 8A26 therefore missed ALC / E124 / anim restart.

  become_expl script=0 is the bit7-clear. +0x18 is the current type
  (35), not the leftover source variant.

Usage (from zanac-md):
    python tools/test_explode_8a26_live.py
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


def msx_8a26(type_byte: int) -> tuple[int, int] | None:
    """Return (new_type, plus18) or None if skipped."""
    a = type_byte & 0x7F
    if a == 0:
        return None
    if a >= 0x46:
        return None
    if a == 0x28:
        return None
    return (0x23, a)


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8")
    ply = PLAYER.read_text(encoding="utf-8")
    hdr = PLAYER_H.read_text(encoding="utf-8")
    spawn_src = SPAWN.read_text(encoding="utf-8")
    mapc = MAPC.read_text(encoding="utf-8")
    asm = load_asm()

    if asm:
        chunk = asm
        if "explode_enemies:" not in chunk:
            fail("zanac.asm missing explode_enemies")
            fails += 1
        else:
            body = chunk.split("explode_enemies:", 1)[1].split(
                "handler_type73_base_segment:", 1
            )[0]
            checks = (
                ("AND\t 0x7f", "8a3a AND 0x7F"),
                ("CP\t 0x46", "8a3e CP 0x46"),
                ("CP\t 0x28", "8a42 CP 0x28"),
                ("LD\t (IY+0x0), 0x23", "8a46 write type 0x23"),
                ("LD\t (IY+0x18), A", "8a4a +0x18 = unmasked type"),
            )
            for needle, label in checks:
                if needle not in body and needle.replace("\t", " ") not in body:
                    # tolerate spacing variants
                    compact = re.sub(r"\s+", "", body.upper())
                    key = re.sub(r"\s+", "", needle.upper())
                    if key not in compact:
                        fail(f"ASM {label} not in explode_enemies")
                        fails += 1
                        continue
                print(f"  ASM: {label}")
            # Live 0x23 is not in the skip set.
            if re.search(r"CP\s+0x23", body):
                fail("ASM 8A26 must not special-case CP 0x23")
                fails += 1
            else:
                print("  ASM 8A26: no CP 0x23 skip")
    else:
        print("  (zanac.asm not in tree; filter math still checked)")

    # Filter math: live type 35 / 60 convert; 40 and 70+ do not.
    cases = (
        (0x00, None, "empty"),
        (0x23, (0x23, 0x23), "type 35"),
        (0xA3, (0x23, 0x23), "type 35 running"),
        (0x3C, (0x23, 0x3C), "type 60"),
        (0xBC, (0x23, 0x3C), "type 60 running"),
        (0x28, None, "type 40"),
        (0xA8, None, "type 40 running"),
        (0x0A, (0x23, 0x0A), "type 10"),
        (0x45, (0x23, 0x45), "type 69"),
        (0x46, None, "type 70"),
        (0x50, None, "type 80"),
    )
    for raw, want, name in cases:
        got = msx_8a26(raw)
        if got != want:
            fail(f"8A26 {name} (0x{raw:02X}): {got} want {want}")
            fails += 1
        else:
            print(f"  8A26 {name}: {got}")

    expl = fn_span(ent, "void entity_explode_airborne(void)")
    if not expl:
        fail("entity_explode_airborne not found")
        fails += 1
        expl = ""

    if re.search(r"kind\s*==\s*KIND_EXPL", expl):
        fail("8A26 must not skip KIND_EXPL (live type 35 is converted)")
        fails += 1
    else:
        print("  port: no KIND_EXPL skip")

    if re.search(r"kind\s*==\s*KIND_PDEAD", expl):
        fail("8A26 must not skip KIND_PDEAD (type 60 is in [1,0x45])")
        fails += 1
    else:
        print("  port: no KIND_PDEAD skip")

    if "0x28" not in expl and "t == 40" not in expl:
        fail("8A26 must still skip type 0x28")
        fails += 1
    else:
        print("  port: skip type 0x28")

    if "0x46" not in expl and ">= 70" not in expl:
        fail("8A26 must still skip type >= 0x46")
        fails += 1
    else:
        print("  port: skip type >= 0x46")

    if "become_expl" not in expl:
        fail("8A26 must become_expl survivors")
        fails += 1
    else:
        print("  port: become_expl survivors")

    become = fn_span(ent, "static void become_expl(Slot *e, u8 score_t)")
    if not become or "e->script = 0" not in become:
        fail("become_expl must clear script (bit7-clear / 8446 init)")
        fails += 1
    elif "e->variant = score_t" not in become:
        fail("become_expl must store +0x18 = score_t")
        fails += 1
    else:
        print("  become_expl: script=0 + variant=+0x18")

    # +0x18 is the current type (slot_msx_type), not leftover e->variant.
    if expl and "slot_msx_type" not in expl:
        fail("8A26 +0x18 must be slot_msx_type (current type), not leftover variant")
        fails += 1
    else:
        print("  8A26 +0x18: slot_msx_type (0x23 on live expl)")

    # Flash wait_frames B=5 stays (visual overlay; not a freeze).
    flash = fn_span(ent, "static void flash_begin(void)")
    if not flash or "s_flash_left = 5" not in flash:
        fail("8A26 wait_frames B=5 flash was reverted")
        fails += 1
    else:
        print("  KEEP: 8A26 5-frame flash")

    if "mode_backdrop_flash(1)" not in (flash or ""):
        fail("flash_begin must still mode_backdrop_flash(1)")
        fails += 1

    # KEEP: fire 7 730B once (just shipped).
    if "s_fire7_life_ticked" not in ent:
        fail("fire 7 730B-once flag was reverted")
        fails += 1
    else:
        print("  KEEP: fire 7 730B once (s_fire7_life_ticked)")

    spawn = fn_span(ent, "void entity_try_spawn_fire(s16 x, s16 y, u8 xvel_sel)")
    upd = fn_span(ent, "static void update_fire(void)")
    if not spawn or not upd:
        fail("fire spawn/update not found")
        fails += 1
    elif spawn.count("player_fire_life_tick()") != 1:
        fail("only fire 7 init (728F) ticks 730B in spawn")
        fails += 1
    elif "s_fire7_life_ticked" not in upd:
        fail("update_fire must still honor the 7306 skip flag")
        fails += 1
    else:
        print("  KEEP: 728F still ticks; 7306 skipped that frame")

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

    husk = fn_span(ent, "static void husk_step(Slot *e)")
    if not husk or "tick_e124_84bc()" not in husk:
        fail("type 80 8e2a JP 849c must tick E124")
        fails += 1
    else:
        print("  KEEP: husk_step 849c ticks E124")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
