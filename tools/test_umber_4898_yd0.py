#!/usr/bin/env python3
"""Types 7/8/9 umber use 4898 unsigned Y>=0xD0, not playfield max_y.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  handler_type7_umber 0x791d (shared 7/8/9 via 0x7923):
    init +0c=0x09 (Y_homing bit3 + Y_motion bit0)
    active 0x7954 morph/burst, then
    CALL 0x4898                  ; 0x79ae
    Type 9 7a12 / 7a15 / 7a27 also JP 79ae.

  Y_motion_sub 0x48de:
    ADD HL,DE
    LD A,H / CP 0xD0 / RET C
    JP 0x48d0                    ; entity_clear

  Original playfield_h=192; port max_y = playfield_h+8 = 200.
  Old umber_step added Yvel as signed s32 then the shared pass
  culled Y>200 / Y<-24.
  Y=201..207 is still live on MSX (unsigned < 0xD0).
  Rise wrap Y=0 + Yvel 0xFD00 is unsigned 0xFD >= 0xD0 clear,
  not signed Y=-3 then playfield y<-24.

Usage (from zanac-md):
    python tools/test_umber_4898_yd0.py
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


def step_y_4898(y: int, yf: int, vy: int) -> tuple[int, int, bool]:
    """u8 8.8 ADD then unsigned Y>=0xD0."""
    ypos = (((y & 0xFF) << 8) | (yf & 0xFF)) + (vy & 0xFFFF)
    ypos &= 0xFFFF
    y = (ypos >> 8) & 0xFF
    return y, ypos & 0xFF, y >= 0xD0


def old_signed_s32(y: int, yf: int, vy: int) -> int:
    """Old port: signed s32 Y then arithmetic >>8."""
    vel = vy & 0xFFFF
    if vel >= 0x8000:
        vel -= 0x10000
    ypos = ((y << 8) | (yf & 0xFF)) + vel
    return ypos >> 8


def old_playfield_cull(y: int, max_y: int = 200) -> bool:
    """Old port: shared pass e->y > playfield_h+8 or y < -24."""
    return y > max_y or y < -24


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8", errors="replace")
    ply = PLAYER.read_text(encoding="utf-8", errors="replace")
    hdr = PLAYER_H.read_text(encoding="utf-8", errors="replace")
    mapc = MAPC.read_text(encoding="utf-8", errors="replace")
    spawn_src = SPAWN.read_text(encoding="utf-8", errors="replace")
    asm = load_asm()

    if asm:
        t7 = asm.split("handler_type7_umber:", 1)
        if len(t7) < 2:
            fail("zanac.asm missing handler_type7_umber")
            fails += 1
        else:
            body = t7[1].split("handler_type10_duster:", 1)[0]
            if not re.search(r"CALL\s+0x4898\s*;\s*0x79ae", body, re.I):
                fail("umber armed must CALL 4898 at 79ae")
                fails += 1
            else:
                print("  ASM 79ae: CALL 4898")
            if not re.search(r"LD\s+\(IX\+0x0c\),\s*0x09\s*;\s*0x7938", body, re.I):
                fail("umber init must set +0c=0x09 (Y|Y-homing)")
                fails += 1
            else:
                print("  ASM 7938: +0c=0x09 Y|Y-homing")
            if not re.search(r"JP\s+NZ,\s*0x79ae\s*;\s*0x7a15", body, re.I):
                fail("type 9 7a15 must JP NZ 79ae")
                fails += 1
            else:
                print("  ASM 7a15: type 9 JP NZ 79ae")
            if not re.search(r"JP\s+0x79ae\s*;\s*0x7a27", body, re.I):
                fail("type 9 7a27 must JP 79ae")
                fails += 1
            else:
                print("  ASM 7a27: type 9 JP 79ae")
        if not re.search(r"CP\s+0xd0\s*;\s*0x48f2", asm, re.I):
            fail("Y_motion_sub 48f2 is not CP 0xD0")
            fails += 1
        else:
            print("  ASM 48f2: Y_motion_sub CP 0xD0")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    # Y=201..207: playfield max_y=200 kills; 4898 does not.
    for y in range(201, 208):
        _, _, culled = step_y_4898(y, 0, 0)
        if culled:
            fail(f"4898 must keep Y={y} (< 0xD0)")
            fails += 1
        if not old_playfield_cull(y):
            fail(f"old playfield cull must kill Y={y} (> 200)")
            fails += 1
    y, yf, culled = step_y_4898(0xCF, 0x00, 0x0100)
    if (y, culled) != (0xD0, True):
        fail(f"4898 at 0xCF + 0x0100 -> Y={y:#x} cull={culled}, want 0xD0 True")
        fails += 1
    else:
        print("  sim: Y=201..207 live on 4898; old max_y=200 kills; 0xD0 clears")

    # Rise wrap: Y=0 + 0xFD00 -> 0xFD >= 0xD0. Signed s32 sits at -3.
    y, yf, culled = step_y_4898(0, 0, 0xFD00)
    old_y = old_signed_s32(0, 0, 0xFD00)
    if (y, culled) != (0xFD, True):
        fail(f"4898 rise wrap 0+0xFD00 -> Y={y:#x} cull={culled}, want 0xFD True")
        fails += 1
    elif old_y != -3:
        fail(f"old signed s32 0+0xFD00 -> {old_y}, want -3")
        fails += 1
    elif old_playfield_cull(old_y):
        fail("old playfield cull must keep signed Y=-3 (>-24)")
        fails += 1
    else:
        print("  sim: rise wrap 0+0xFD00 -> 0xFD clear; s32 was -3 live")

    step = fn_span(ent, "static void umber_step(Slot *e)")
    if not step:
        fail("umber_step not found")
        fails += 1
    elif "step_88_y_4898" not in step:
        fail("umber_step must use step_88_y_4898 (4898 Y-only CP 0xD0)")
        fails += 1
    elif "playfield" in step or "max_y" in step:
        fail("umber_step must not invent a playfield cull")
        fails += 1
    elif "ypos +=" in step or "ypos >> 8" in step:
        fail("umber_step must not keep signed s32 Y")
        fails += 1
    else:
        print("  umber_step: step_88_y_4898 (unsigned Y>=0xD0)")

    spawn = fn_span(ent, "static void spawn_umber(Slot *e, u8 type)")
    if not spawn:
        fail("spawn_umber not found")
        fails += 1
    elif "e->bind = 0x0300" not in spawn:
        fail("spawn_umber must keep Yvel 8.8 0x0300")
        fails += 1
    elif "e->x = 120" not in spawn:
        fail("spawn_umber must keep X=0x78")
        fails += 1
    else:
        print("  spawn_umber: Yvel 0x0300 X=0x78")

    upd = fn_span(ent, "static void update_enemies(void)")
    if not upd:
        fail("update_enemies not found")
        fails += 1
    else:
        if "e->kind != KIND_UMBER" not in upd:
            fail("KIND_UMBER must be excluded from playfield max_y cull")
            fails += 1
        else:
            print("  update_enemies: KIND_UMBER excluded from max_y cull")
        if not re.search(
            r"else if \(e->kind == KIND_UMBER\)\s*\{\s*"
            r"umber_step\(e\);\s*"
            r"if \(!e->alive\)\s*continue;",
            upd,
        ):
            fail("KIND_UMBER must continue after 4898 clear")
            fails += 1
        else:
            print("  update_enemies: umber_step then continue if dead")
        if "4898 Y-only 36/61/62/72/83" not in upd:
            fail("cull comment must keep type 36 with 61/62/72/83")
            fails += 1
        else:
            print("  update_enemies: type 36 still in 4898 Y-only set")
        # KIND_UMBER is an extra != term. The ebullet exclude must stay
        # !(KIND_EBULLET && variants), not !(KIND_EBULLET) then a
        # separate variant AND (that would skip the cull for almost
        # every non-ebullet).
        if re.search(
            r"e->kind != KIND_UMBER\s*"
            r"&&\s*!\(e->kind == KIND_EBULLET\)\s*"
            r"&&\s*\(e->variant == 20",
            upd,
        ):
            fail(
                "playfield cull must not split !(KIND_EBULLET) from variants"
            )
            fails += 1
        elif not re.search(
            r"e->kind != KIND_UMBER\s*"
            r"&&\s*!\(e->kind == KIND_EBULLET\s*"
            r"&&\s*\(e->variant == 20",
            upd,
        ):
            fail(
                "playfield cull must keep "
                "!(KIND_EBULLET && variants) after KIND_UMBER"
            )
            fails += 1
        else:
            print("  update_enemies: ebullet exclude is !(KIND_EBULLET && variants)")

    y4898 = fn_span(ent, "static int step_88_y_4898(Slot *e)")
    if not y4898 or "(u8)e->y >= 0xD0" not in y4898:
        fail("step_88_y_4898 must still unsigned-cull Y>=0xD0")
        fails += 1
    else:
        print("  step_88_y_4898: unsigned Y>=0xD0")

    tick = fn_span(ent, "static void spawn_tick(void)")
    if not tick:
        fail("spawn_tick not found")
        fails += 1
    elif "spawn_from_type(68)" not in tick:
        fail("BFA0 spawn_from_type(68) was reverted")
        fails += 1
    elif not re.search(
        r"if \(spawn_from_type\(68\)\)\s*"
        r"s_e125 = \(u8\)\(s_e125 & \(u8\)~0x01\)",
        tick,
    ):
        fail("BFA0 must RES s_e125 only after spawn_from_type(68) succeeds")
        fails += 1
    else:
        print("  KEEP: BFA0 spawn_from_type(68) then RES s_e125 on success")

    gs = fn_span(ent, "static void gswoop_step(Slot *e)")
    if not gs or "(u8)((u8)sib->x - (u8)e->x) < 0x0B" not in gs:
        fail("gswoop 7f54 unsigned merge was reverted")
        fails += 1
    else:
        print("  KEEP: gswoop 7f54 unsigned (pair.X-self.X)<0x0B")

    flash = fn_span(ent, "static void flash_step(Slot *e)")
    if not flash or "step_88_y_4898" not in flash:
        fail("type 36 flash_step step_88_y_4898 was reverted")
        fails += 1
    else:
        print("  KEEP: type 36 flash_step step_88_y_4898")

    if upd and "e->kind != KIND_GROUND" not in upd:
        fail("KIND_GROUND playfield-cull exclude was reverted")
        fails += 1
    else:
        print("  KEEP: type 44 KIND_GROUND excluded from playfield cull")

    circle = fn_span(ent, "static void circle_step(Slot *e)")
    if not circle or "step_88_4898" not in circle:
        fail("type 67 armed 4898 stay was reverted")
        fails += 1
    else:
        print("  KEEP: type 67 circle_step step_88_4898")

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
        print("  KEEP: fire 7 730B once (s_fire7_life_ticked)")

    stealth = fn_span(ent, "static void spawn_stealth(Slot *e, u8 type)")
    if not stealth or "e->clock = 48" not in stealth:
        fail("type 65 7ff0 +1D=0x30 seed was reverted")
        fails += 1
    else:
        print("  KEEP: spawn_stealth clock=48")

    st = fn_span(ent, "static void stealth_step(Slot *e)")
    if not st or "(e->variant == 65) ? 32 : 48" not in st:
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

    collide = fn_span(ent, "static void collide_player(void)")
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

    husk = fn_span(ent, "static void husk_step(Slot *e)")
    if not husk or "tick_e124_84bc()" not in husk:
        fail("husk_step must still tick 84bc (8e2a JP 849c)")
        fails += 1
    else:
        print("  KEEP: type 80/35 tick_e124_84bc")

    vals = parse_spawn_list(spawn_src)
    if vals:
        for t, name in ((21, "21"), (41, "41"), (45, "45")):
            if t in vals:
                fail(f"spawn_type_list must keep type {name} child-only")
                fails += 1
            else:
                print(f"  KEEP: type {name} child-only")
        for t in (7, 8, 9):
            if t not in vals:
                fail(f"spawn_type_list must still include type {t}")
                fails += 1
            else:
                print(f"  spawn_type_list still includes type {t}")

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
