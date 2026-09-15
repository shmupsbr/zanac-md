#!/usr/bin/env python3
"""BFA0 must not clear E125 until spawn_from_type(68) succeeds.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  ground_struct_spawn_ctrl 0xBF2C:
    BIT 0,(IX+0x25) / JR NZ, sub_bfa0     ; E125 bit0

  sub_bfa0 0xBFA0:
    CALL 0x4496                           ; alloc_entity_slot
    RET  C                                ; no slot → keep E125
    RES  0,(IX+0x25)                      ; clear spawn_trigger
    LD   (HL), 0x44                       ; write type 44
    RET

  Bytes at BFA0: CD 96 44 D8 DD CB 25 86
    CALL 4496 / RET C / RES 0,(IX+25)

  alloc_entity_slot 4496: walk E3A0 stride 0x20, B=0x15.
    OR A / RET Z on free; table full → SCF / RET.

  Old port: RES first, then spawn_from_type(68). A full table
  dropped the husk-latched type-44 forever.

Usage (from zanac-md):
    python tools/test_bfa0_e125_retc.py
"""
from __future__ import annotations

import hashlib
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
JAPAN_V1_SHA1 = "46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2"
BFA0_BYTES = bytes.fromhex("cd9644d8ddcb2586")
ROM_CANDIDATES = [
    Path("/tmp/zanac-japan-v1.rom"),
    Path("/tmp/refs/zanac-japan-v1.rom"),
    Path("/tmp/zanac.rom"),
    ROOT.parent / "zanac.rom",
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def load_asm() -> str | None:
    for p in ASM_CANDIDATES:
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    return None


def load_japan_v1() -> bytes | None:
    for p in ROM_CANDIDATES:
        if not p.is_file():
            continue
        data = p.read_bytes()
        if hashlib.sha1(data).hexdigest() == JAPAN_V1_SHA1:
            return data
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


def if_span(src: str, cond: str) -> str | None:
    m = re.search(rf"if\s*\(\s*{re.escape(cond)}\s*\)\s*\{{", src)
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


def old_bfa0(e125: int, slot_ok: bool) -> tuple[int, bool]:
    """Old port: RES first, then try spawn. Full table drops the latch."""
    e125 = e125 & ~0x01
    return e125, slot_ok


def new_bfa0(e125: int, slot_ok: bool) -> tuple[int, bool]:
    """BFA0: CALL 4496 / RET C / then RES 0,(E125)."""
    if slot_ok:
        e125 = e125 & ~0x01
    return e125, slot_ok


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8", errors="replace")
    ply = PLAYER.read_text(encoding="utf-8", errors="replace")
    hdr = PLAYER_H.read_text(encoding="utf-8", errors="replace")
    mapc = MAPC.read_text(encoding="utf-8", errors="replace")
    spawn_src = SPAWN.read_text(encoding="utf-8", errors="replace")
    asm = load_asm()
    rom = load_japan_v1()

    if asm:
        bfa0 = asm.split("sub_bfa0:", 1)
        if len(bfa0) < 2:
            fail("zanac.asm missing sub_bfa0")
            fails += 1
        else:
            body = bfa0[1].split("inc_encounter_a:", 1)[0]
            if not re.search(r"CALL\s+0x4496\s*;\s*0xbfa0", body, re.I):
                fail("BFA0 is not CALL 4496")
                fails += 1
            else:
                print("  ASM BFA0: CALL 4496")
            if not re.search(r"RET\s+C\s*;\s*0xbfa3", body, re.I):
                fail("BFA3 is not RET C")
                fails += 1
            else:
                print("  ASM BFA3: RET C (keep E125 on full table)")
            if not re.search(
                r"RES\s+0x0,\s*\(IX\+0x25\)\s*;\s*0xbfa4", body, re.I
            ):
                fail("BFA4 is not RES 0,(IX+25)")
                fails += 1
            else:
                print("  ASM BFA4: RES 0,(IX+25) after RET C")
            if body.find("RET\t C") > body.find("RES"):
                fail("RET C must precede RES 0,(E125)")
                fails += 1
            if not re.search(r"LD\s+\(HL\),\s*0x44\s*;\s*0xbfa8", body, re.I):
                fail("BFA8 is not LD (HL),0x44")
                fails += 1
            else:
                print("  ASM BFA8: LD (HL),0x44")
        if not re.search(r"BIT\s+0x0,\s*\(IX\+0x25\)\s*;\s*0xbf3c", asm, re.I):
            fail("BF3C is not BIT 0,(IX+25)")
            fails += 1
        else:
            print("  ASM BF3C: BIT 0,(E125) before stream")
        if not re.search(r"JR\s+NZ,\s*sub_bfa0\s*;\s*0xbf40", asm, re.I):
            fail("BF40 is not JR NZ,sub_bfa0")
            fails += 1
        else:
            print("  ASM BF40: JR NZ,sub_bfa0")
        alloc = asm.split("alloc_entity_slot:", 1)
        if len(alloc) < 2:
            fail("zanac.asm missing alloc_entity_slot")
            fails += 1
        else:
            abody = alloc[1].split("CALL\t 0x45a0", 1)[0]
            if "SCF" not in abody or "RET" not in abody:
                fail("4496 full table must SCF / RET")
                fails += 1
            else:
                print("  ASM 4496: full table SCF / RET (carry)")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    if rom is not None:
        if rom[0xBFA0 : 0xBFA0 + 8] != BFA0_BYTES:
            fail(
                f"Japan v1 BFA0 bytes {rom[0xBFA0:0xBFA0+8].hex()} "
                f"want {BFA0_BYTES.hex()}"
            )
            fails += 1
        else:
            print("  ROM BFA0: cd 96 44 d8 dd cb 25 86")
    else:
        print("  (Japan v1 ROM not on this machine; ASM + C locks)")

    if old_bfa0(1, False) != (0, False):
        fail("old full-table must drop E125")
        fails += 1
    elif new_bfa0(1, False) != (1, False):
        fail("new full-table must keep E125")
        fails += 1
    elif new_bfa0(1, True) != (0, True):
        fail("new success must RES E125 after spawn")
        fails += 1
    elif old_bfa0(1, True) != (0, True):
        fail("old success still spawned, but cleared first")
        fails += 1
    else:
        print("  sim: full table keeps latch; success clears after spawn")

    tick = fn_span(ent, "static void spawn_tick(void)")
    if not tick:
        fail("spawn_tick not found")
        fails += 1
    else:
        bfa0 = if_span(tick, "s_e125 & 0x01")
        if not bfa0:
            fail("spawn_tick must still test s_e125 bit0")
            fails += 1
        else:
            spawn_at = bfa0.find("spawn_from_type(68)")
            clear_at = bfa0.find("s_e125 =")
            if spawn_at < 0:
                fail("BFA0 must spawn_from_type(68) (LD (HL),0x44 = type 68, not decimal 44)")
                fails += 1
            elif clear_at < 0:
                fail("BFA0 must still RES 0,(E125) on success")
                fails += 1
            elif spawn_at > clear_at:
                fail("BFA0 must not clear s_e125 before spawn_from_type(68)")
                fails += 1
            elif "if (spawn_from_type(68))" not in bfa0:
                fail("BFA0 must gate RES on spawn_from_type(68) success")
                fails += 1
            elif "return;" not in bfa0:
                fail("BFA0 must RET after the latch attempt (skip stream)")
                fails += 1
            else:
                print("  spawn_tick: spawn_from_type(68) then RES on success")
            bit3_at = tick.find("s_spawn_ctrl & 0x08")
            e125_at = tick.find("s_e125 & 0x01")
            if bit3_at < 0 or e125_at < 0 or e125_at > bit3_at:
                fail("E125 bit0 must still be checked before the bit3 block")
                fails += 1
            else:
                print("  spawn_tick: E125 still before bit3 stream-block")

    helper = fn_span(ent, "static void tick_e124_84bc(void)")
    if not helper or "s_e125 = 1" not in helper:
        fail("tick_e124_84bc must still latch E125=1")
        fails += 1
    else:
        print("  KEEP: tick_e124_84bc still latches E125=1")

    husk = fn_span(ent, "static void husk_step(Slot *e)")
    if not husk or "tick_e124_84bc()" not in husk:
        fail("husk_step must still tick 84bc (8e2a JP 849c)")
        fails += 1
    else:
        print("  KEEP: type 80/35 tick_e124_84bc")

    gs = fn_span(ent, "static void gswoop_step(Slot *e)")
    if not gs or "(u8)((u8)sib->x - (u8)e->x) < 0x0B" not in gs:
        fail("gswoop 7f54 unsigned (pair.X-self.X)<0x0B was reverted")
        fails += 1
    elif "abs" in gs.lower() and "pair" in gs.lower():
        fail("gswoop 7f54 must not use abs")
        fails += 1
    else:
        print("  KEEP: gswoop 7f54 unsigned (pair.X-self.X)<0x0B")

    flash = fn_span(ent, "static void flash_step(Slot *e)")
    if not flash or "step_88_y_4898" not in flash:
        fail("type 36 flash_step step_88_y_4898 was reverted")
        fails += 1
    else:
        print("  KEEP: type 36 Y-only step_88_y_4898")

    xy4898 = fn_span(ent, "static int step_88_4898(Slot *e)")
    if (
        not xy4898
        or "(u8)e->y >= 0xD0" not in xy4898
        or "(u8)e->x >= 0xD1" not in xy4898
    ):
        fail("step_88_4898 must still unsigned-cull Y>=0xD0 / X>=0xD1")
        fails += 1
    else:
        print("  KEEP: type 44/67 X|Y step_88_4898")

    circ = fn_span(ent, "static void circle_step(Slot *e)")
    if not circ or "step_88_4898" not in circ:
        fail("type 67 armed circle_step step_88_4898 was reverted")
        fails += 1
    else:
        print("  KEEP: type 67 armed step_88_4898")

    takes = fn_span(ent, "static int enemy_takes_shots(const Slot *e)")
    if not takes or "KIND_CIRCLE && !(e->aux & 0x40)" not in takes:
        fail("idle type 67 must still skip 44BA (83ee JP 48b8)")
        fails += 1
    else:
        print("  KEEP: idle type 67 no 44BA")

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

    fire_spawn = fn_span(ent, "void entity_try_spawn_fire(s16 x, s16 y, u8 xvel_sel)")
    if not fire_spawn or fire_spawn.count("player_fire_life_tick()") != 1:
        fail("Fire 3 must stay update-only; only fire 7 init ticks 730B")
        fails += 1
    else:
        print("  KEEP: Fire 3 update-only (730B only on fire 7 init)")

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

    if "e->sat_col = 0x8F" not in ent:
        fail("20/37/38/41/42/43 sat_col 0x8F was reverted")
        fails += 1
    else:
        print("  KEEP: 20/37/38/41/42/43 sat_col 0x8F")

    if "0xBFD6" in ent or "0xbfd6" in ent:
        fail("must not CALL 0xBFD6")
        fails += 1
    else:
        print("  KEEP: no 0xBFD6")

    if "mode_letter_attr" in ent:
        fail("entity.c must not grow a playfield-wide mode_letter_attr fill")
        fails += 1
    else:
        print("  KEEP: no playfield-wide mode_letter_attr")

    vals = parse_spawn_list(spawn_src)
    if vals:
        for t, name in ((21, "21"), (41, "41"), (45, "45")):
            if t in vals:
                fail(f"spawn_type_list must keep type {name} child-only")
                fails += 1
            else:
                print(f"  KEEP: type {name} child-only")

    if "player_fire_reset" not in hdr or "player_fire_select" not in hdr:
        fail("player.h must keep fire_reset / fire_select split")
        fails += 1
    else:
        print("  KEEP: player.h fire_reset + fire_select")

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

    boom = fn_span(ent, "void entity_explode_airborne(void)")
    if not boom:
        fail("entity_explode_airborne not found")
        fails += 1
    elif "KIND_EXPL" in boom and "continue" in boom:
        if re.search(
            r"KIND_EXPL|KIND_PDEAD",
            boom.split("slot_msx_type", 1)[0] if "slot_msx_type" in boom else boom,
        ):
            fail("8A26 must not skip KIND_EXPL / KIND_PDEAD")
            fails += 1
        else:
            print("  KEEP: 8A26 still reconverts live type 35")
    elif "become_expl" not in (boom or ""):
        fail("8A26 must still become_expl")
        fails += 1
    else:
        print("  KEEP: 8A26 still become_expl")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
