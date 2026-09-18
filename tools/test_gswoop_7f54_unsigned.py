#!/usr/bin/env python3
"""Gswoop 30/32 merge at 7f54 is unsigned (pair.X-self.X)<0x0B, not abs.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  handler_type30_ground_swooper armed 0x7f20:
    BIT 7, (IX+05) / JR NZ, 7f73          ; already locked
    IY = pair (+1b/+1c)
    A=(IX+00 & 0x7f)+1 / CP (IY+00)       ; pair must be type+1
    playerY CP ownY; type32 BIT6 CCF
    maybe +0c=2 on both
    LD A,(IY+02)                          ; 0x7f51 pair X
    SUB (IX+02)                           ; 0x7f54 A = pair.X - self.X
    CP 0x0B                               ; 0x7f57
    JR NC, 7f73                           ; 0x7f59 skip if A >= 11
    SET 7,(IX+05) / +03=0xf4 / pair type 0x28
    X+=5 / +0c=1

  Bytes at 7f54: DD 96 02 FE 0B 30 18
    SUB (IX+02); CP 0x0B; JR NC,7f73

  After the pair crosses left, SUB wraps (e.g. pair 5 left => A=0xFB)
  and CP 0x0B is NC, so MSX refuses merge. Old port used abs(dx)
  and still merged.

  Child 7f84 (type 31/33) has no merge.

Usage (from zanac-md):
    python tools/test_gswoop_7f54_unsigned.py
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


def msx_merge(pair_x: int, self_x: int) -> bool:
    """7f54: unsigned (pair.X - self.X) < 0x0B."""
    return ((pair_x - self_x) & 0xFF) < 0x0B


def old_abs_merge(pair_x: int, self_x: int) -> bool:
    """Old port: |pair.X - self.X| < 0x0B."""
    dx = pair_x - self_x
    if dx < 0:
        dx = -dx
    return dx < 0x0B


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8", errors="replace")
    ply = PLAYER.read_text(encoding="utf-8", errors="replace")
    hdr = PLAYER_H.read_text(encoding="utf-8", errors="replace")
    mapc = MAPC.read_text(encoding="utf-8", errors="replace")
    spawn_src = SPAWN.read_text(encoding="utf-8", errors="replace")
    asm = load_asm()

    if asm:
        t30 = asm.split("handler_type30_ground_swooper:", 1)
        if len(t30) < 2:
            fail("zanac.asm missing handler_type30_ground_swooper")
            fails += 1
        else:
            body = t30[1].split("LAB_ram_7f99:", 1)[0]
            if not re.search(r"LD\s+A,\s*\(IY\+0x02\)\s*;\s*0x7f51", body, re.I):
                fail("7f51 is not LD A,(IY+02) pair X")
                fails += 1
            else:
                print("  ASM 7f51: LD A,(IY+02) pair X")
            if not re.search(r"SUB\s+\(IX\+0x02\)\s*;\s*0x7f54", body, re.I):
                fail("7f54 is not SUB (IX+02)")
                fails += 1
            else:
                print("  ASM 7f54: SUB (IX+02) unsigned pair.X-self.X")
            if not re.search(r"CP\s+0x0b\s*;\s*0x7f57", body, re.I):
                fail("7f57 is not CP 0x0B")
                fails += 1
            else:
                print("  ASM 7f57: CP 0x0B")
            if not re.search(r"JR\s+NC,\s*0x7f73\s*;\s*0x7f59", body, re.I):
                fail("7f59 is not JR NC,7f73")
                fails += 1
            else:
                print("  ASM 7f59: JR NC,7f73 (skip merge if A>=11)")
            if "NEG" in body or "CPL" in body:
                fail("gswoop merge must not ABS the SUB")
                fails += 1
            else:
                print("  ASM: no NEG/CPL (unsigned, not abs)")
            if not re.search(r"SET\s+7,\s*\(IX\+0x05\)\s*;\s*0x7f5b", body, re.I):
                fail("7f5b is not SET lock")
                fails += 1
            else:
                print("  ASM 7f5b: SET lock")
        child = asm.split("LAB_ram_7f84:", 1)
        if len(child) < 2:
            fail("zanac.asm missing LAB_ram_7f84")
            fails += 1
        else:
            cbody = child[1].split("LAB_ram_7f99:", 1)[0]
            if "SUB" in cbody and "0x02" in cbody:
                fail("child 7f84 must not merge on X")
                fails += 1
            else:
                print("  ASM 7f84: child has no 7f54 merge")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    # pair 5 right: both merge
    if not msx_merge(0x55, 0x50) or not old_abs_merge(0x55, 0x50):
        fail("pair 5 right must merge on both predicates")
        fails += 1
    else:
        print("  sim: pair 5 right -> merge (MSX and old abs)")

    # pair 10 right: merge (10 < 11)
    if not msx_merge(0x5A, 0x50):
        fail("pair 10 right must merge (A=0x0A < 0x0B)")
        fails += 1
    else:
        print("  sim: pair 10 right A=0x0A -> merge")

    # pair 11 right: no merge
    if msx_merge(0x5B, 0x50) or old_abs_merge(0x5B, 0x50):
        fail("pair 11 right must not merge")
        fails += 1
    else:
        print("  sim: pair 11 right A=0x0B -> no merge")

    # same X: merge
    if not msx_merge(0x50, 0x50):
        fail("same X A=0 must merge")
        fails += 1
    else:
        print("  sim: same X A=0 -> merge")

    # pair 5 left: THE leftover. MSX wraps, old abs still merges.
    left5_msx = msx_merge(0x4B, 0x50)
    left5_old = old_abs_merge(0x4B, 0x50)
    if left5_msx:
        fail("pair 5 left must wrap A=0xFB and refuse merge")
        fails += 1
    elif not left5_old:
        fail("old abs must still merge pair 5 left (documents the hole)")
        fails += 1
    elif ((0x4B - 0x50) & 0xFF) != 0xFB:
        fail("pair 5 left wrap must be 0xFB")
        fails += 1
    else:
        print("  sim: pair 5 left A=0xFB -> MSX refuse; old abs merges")

    step = fn_span(ent, "static void gswoop_step(Slot *e)")
    if not step:
        fail("gswoop_step not found")
        fails += 1
    elif re.search(r"dx\s*<\s*0\s*;|dx\s*=\s*\(s16\)\(-dx\)|abs\s*\(", step):
        fail("gswoop_step must not abs() the 7f54 SUB")
        fails += 1
    elif "(u8)((u8)sib->x - (u8)e->x) < 0x0B" not in step:
        fail("gswoop_step must use unsigned (u8)(pair.X-self.X) < 0x0B")
        fails += 1
    elif "sib->variant = 40" not in step:
        fail("merge must still write pair type 0x28 / 40")
        fails += 1
    elif "e->x + 5" not in step:
        fail("merge must still X+=5")
        fails += 1
    elif "0x81" not in step:
        fail("merge must still SET lock | +0c=1")
        fails += 1
    else:
        print("  gswoop_step: unsigned (u8)(pair.X-self.X)<0x0B")

    tracker = fn_span(ent, "static void tracker_step(Slot *e)")
    if not tracker:
        fail("tracker_step not found")
        fails += 1
    elif "0x0B" in tracker or "sib->x" in tracker:
        fail("tracker_step (7f84) must not grow a merge")
        fails += 1
    else:
        print("  KEEP: tracker_step child has no merge")

    spawn = fn_span(ent, "static void spawn_gswoop(Slot *e, u8 type)")
    child = fn_span(ent, "static Slot *spawn_gswoop_pair_child(Slot *e)")
    if not spawn:
        fail("spawn_gswoop not found")
        fails += 1
    elif "e->x = 0x30" not in spawn:
        fail("spawn_gswoop must keep parent X=0x30")
        fails += 1
    elif not child or "c->x = 0xC0" not in child:
        fail("spawn_gswoop must keep parent X=0x30 child X=0xC0")
        fails += 1
    elif "e->bind = 0x0180" not in spawn or "e->dest = 0x0180" not in spawn:
        fail("type 30 Yvel/Xvel 0x0180 was reverted")
        fails += 1
    else:
        print("  KEEP: spawn_gswoop X=0x30/0xC0 type30 vel 0x0180")

    # Type 36 / 44 / 67 4898 KEEP (do not re-litigate)
    flash = fn_span(ent, "static void flash_step(Slot *e)")
    if not flash or "step_88_y_4898" not in flash:
        fail("type 36 flash_step step_88_y_4898 was reverted")
        fails += 1
    else:
        print("  KEEP: type 36 flash_step step_88_y_4898")

    circ = fn_span(ent, "static void circle_step(Slot *e)")
    if not circ or "step_88_4898" not in circ:
        fail("type 67 circle_step step_88_4898 was reverted")
        fails += 1
    else:
        print("  KEEP: type 67 circle_step step_88_4898")

    upd = fn_span(ent, "static void update_enemies(void)")
    if not upd:
        fail("update_enemies not found")
        fails += 1
    else:
        if "e->kind != KIND_GROUND" not in upd:
            fail("KIND_GROUND playfield-cull exclude was reverted")
            fails += 1
        else:
            print("  KEEP: KIND_GROUND excluded from playfield cull")
        if "e->kind != KIND_CIRCLE" not in upd:
            fail("KIND_CIRCLE playfield-cull exclude was reverted")
            fails += 1
        else:
            print("  KEEP: KIND_CIRCLE excluded from playfield cull")
        if "KIND_GSWOOP" not in upd:
            fail("KIND_GSWOOP update path missing")
            fails += 1
        else:
            print("  KEEP: KIND_GSWOOP still dispatched")

    xy4898 = fn_span(ent, "static int step_88_4898(Slot *e)")
    if (
        not xy4898
        or "(u8)e->y >= 0xD0" not in xy4898
        or "(u8)e->x >= 0xD1" not in xy4898
    ):
        fail("step_88_4898 must still unsigned-cull Y>=0xD0 / X>=0xD1")
        fails += 1
    else:
        print("  KEEP: step_88_4898 unsigned Y>=0xD0 / X>=0xD1")

    collide = fn_span(ent, "static void collide_player(void)")
    if not collide:
        fail("collide_player not found")
        fails += 1
    elif re.search(r"if\s*\(\s*e->kind == KIND_GROUND\s*\)", collide):
        fail("type 44 is 44BA (82ff); collide_player must not skip KIND_GROUND")
        fails += 1
    elif "if (player_dead() || player_is_over())" not in collide:
        fail("collide_player must skip only dead/over")
        fails += 1
    elif re.search(r"if\s*\(\s*player_invincible", collide):
        fail("collide_player must not skip on s_invuln")
        fails += 1
    else:
        print("  type 44 44BA: collide_player does not skip KIND_GROUND")

    if "s_ebullet_init_ret" not in ent:
        fail("s_ebullet_init_ret for 21/37/38/41/42/43 was reverted")
        fails += 1
    else:
        print("  KEEP: s_ebullet_init_ret still armed")

    if "s_shot_init_ret" not in ent:
        fail("s_shot_init_ret was reverted")
        fails += 1
    else:
        print("  KEEP: s_shot_init_ret")

    if "s_riser_init_ret" not in ent:
        fail("s_riser_init_ret was reverted")
        fails += 1
    else:
        print("  KEEP: s_riser_init_ret")

    if "s_fire7_life_ticked" not in ent:
        fail("fire 7 730B-once flag was reverted")
        fails += 1
    else:
        print("  KEEP: fire 7 730B once")

    stealth = fn_span(ent, "static void spawn_stealth(Slot *e, u8 type)")
    if not stealth or "e->clock = 48" not in stealth:
        fail("type 65 7ff0 +1D=0x30 seed was reverted")
        fails += 1
    else:
        print("  KEEP: spawn_stealth clock=48")

    ststep = fn_span(ent, "static void stealth_step(Slot *e)")
    if not ststep or "(e->variant == 65) ? 32 : 48" not in ststep:
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

    complete = fn_span(ent, "void entity_alc_complete(void)")
    if not complete or "0x20" not in complete:
        fail("entity_alc_complete E132+=0x20 was reverted")
        fails += 1
    else:
        print("  KEEP: warp entity_alc_complete E132+=0x20")

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
        if 30 not in vals:
            fail("spawn_type_list must still include type 30")
            fails += 1
        else:
            print("  spawn_type_list still includes type 30")

    if "player_fire_reset" not in hdr or "player_fire_select" not in hdr:
        fail("player.h must keep fire_reset / fire_select split")
        fails += 1
    else:
        print("  KEEP: player.h fire_reset + fire_select")

    husk = fn_span(ent, "static void husk_step(Slot *e)")
    if not husk or "tick_e124_84bc()" not in husk:
        fail("husk_step must still tick 84bc (8e2a JP 849c)")
        fails += 1
    else:
        print("  KEEP: type 80/35 tick_e124_84bc")

    zero = fn_span(ent, "void entity_zero_e130(void)")
    if not zero:
        fail("entity_zero_e130 missing")
        fails += 1
    else:
        print("  KEEP: respawn 7606 zeroes E130")

    if "enemy_takes_fire" not in ent:
        fail("E14E enemy_takes_fire was reverted")
        fails += 1
    else:
        print("  KEEP: E14E enemy_takes_fire")

    takes = fn_span(ent, "static int enemy_takes_shots(const Slot *e)")
    if not takes or "KIND_CIRCLE && !(e->aux & 0x40)" not in takes:
        fail("idle type 67 must still skip 44BA (83ee JP 48b8)")
        fails += 1
    else:
        print("  KEEP: idle type 67 no 44BA")

    if "mode_letter_attr" in ent:
        fail("entity.c must not grow a playfield-wide mode_letter_attr fill")
        fails += 1
    else:
        print("  KEEP: no playfield-wide mode_letter_attr")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
