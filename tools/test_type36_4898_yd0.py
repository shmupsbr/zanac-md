#!/usr/bin/env python3
"""Type 36 flashing uses 4898 unsigned Y>=0xD0, not playfield max_y.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  handler_type36_flashing 0x8296:
    BIT 7, (IX+00)
    JR Z, 0x82b3                 ; init
    LD A, (IX+04) / XOR 0x0E     ; 0x829c
    CALL 0x4898                  ; 0x82a4 Y_motion (+0c=1)
    BIT 7 / RET Z
    CALL 0x44ba / CALL 0x7904

  init 0x82b3:
    CALL 0x71c5                  ; Y=0, random X
    LD (IX+0x0c), 0x01           ; Y-only
    LD (IX+0x08), 0x80           ; Yvel 8.8 0x0080
    +03=0x34 +04=0x8F +19=0x10
    SET 7 / JR 0x829c            ; same-frame XOR+4898

  Y_motion_sub 0x48de:
    ADD HL,DE
    LD A,H / CP 0xD0 / RET C
    JP 0x48d0                    ; entity_clear

  Original playfield_h=192; port max_y = playfield_h+8 = 200.
  Old flash_step added Yvel then the shared pass culled Y>200.
  Y=201..207 is still live on MSX (unsigned < 0xD0).

Usage (from zanac-md):
    python tools/test_type36_4898_yd0.py
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


def old_playfield_cull(y: int, max_y: int = 200) -> bool:
    """Old port: shared pass e->y > playfield_h+8."""
    return y > max_y


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8", errors="replace")
    ply = PLAYER.read_text(encoding="utf-8", errors="replace")
    hdr = PLAYER_H.read_text(encoding="utf-8", errors="replace")
    mapc = MAPC.read_text(encoding="utf-8", errors="replace")
    spawn_src = SPAWN.read_text(encoding="utf-8", errors="replace")
    asm = load_asm()

    if asm:
        t36 = asm.split("handler_type36_flashing:", 1)
        if len(t36) < 2:
            fail("zanac.asm missing handler_type36_flashing")
            fails += 1
        else:
            body = t36[1].split("handler_type44_ground_structure:", 1)[0]
            if not re.search(r"CALL\s+0x4898\s*;\s*0x82a4", body, re.I):
                fail("type36 armed must CALL 4898 at 82a4")
                fails += 1
            else:
                print("  ASM 82a4: CALL 4898")
            if not re.search(r"XOR\s+0x0e\s*;\s*0x829f", body, re.I):
                fail("type36 must XOR +04 with 0x0E")
                fails += 1
            else:
                print("  ASM 829f: XOR 0x0E")
            if not re.search(r"LD\s+\(IX\+0x0c\),\s*0x01\s*;\s*0x82b6", body, re.I):
                fail("type36 init must set +0c=1 (Y-only)")
                fails += 1
            else:
                print("  ASM 82b6: +0c=1 Y-only")
            if not re.search(r"LD\s+\(IX\+0x08\),\s*0x80\s*;\s*0x82ba", body, re.I):
                fail("type36 init must set Yvel lo=0x80")
                fails += 1
            else:
                print("  ASM 82ba: Yvel 0x0080")
            if not re.search(r"JR\s+0x829c\s*;\s*0x82ce", body, re.I):
                fail("type36 init must fall into 829c (same-frame 4898)")
                fails += 1
            else:
                print("  ASM 82ce: JR 829c same-frame 4898")
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
    y, yf, culled = step_y_4898(0xCF, 0x80, 0x0080)
    if (y, culled) != (0xD0, True):
        fail(f"4898 at 0xCF.80 + 0x0080 -> Y={y:#x} cull={culled}, want 0xD0 True")
        fails += 1
    else:
        print("  sim: Y=201..207 live on 4898; old max_y=200 kills; 0xD0 clears")

    flash = fn_span(ent, "static void flash_step(Slot *e)")
    if not flash:
        fail("flash_step not found")
        fails += 1
    elif "step_88_y_4898" not in flash:
        fail("flash_step must use step_88_y_4898 (4898 Y-only CP 0xD0)")
        fails += 1
    elif "playfield" in flash or "max_y" in flash:
        fail("flash_step must not invent a playfield cull")
        fails += 1
    elif "ypos +=" in flash or "ypos >> 8" in flash:
        fail("flash_step must not keep signed s32 Y (invented cull)")
        fails += 1
    else:
        print("  flash_step: step_88_y_4898 (unsigned Y>=0xD0)")

    spawn = fn_span(ent, "static void spawn_flash(Slot *e)")
    if not spawn:
        fail("spawn_flash not found")
        fails += 1
    elif "e->bind = 0x0080" not in spawn:
        fail("spawn_flash must keep Yvel 8.8 0x0080")
        fails += 1
    elif "e->hp = 16" not in spawn:
        fail("spawn_flash must keep HP 16")
        fails += 1
    else:
        print("  spawn_flash: Yvel 0x0080 HP 16")

    upd = fn_span(ent, "static void update_enemies(void)")
    if not upd:
        fail("update_enemies not found")
        fails += 1
    else:
        if "e->kind != KIND_FLASH" not in upd:
            fail("KIND_FLASH must be excluded from playfield max_y cull")
            fails += 1
        else:
            print("  update_enemies: KIND_FLASH excluded from max_y cull")
        if not re.search(
            r"else if \(e->kind == KIND_FLASH\)\s*\{\s*"
            r"flash_step\(e\);\s*"
            r"if \(!e->alive\)\s*continue;",
            upd,
        ):
            fail("KIND_FLASH must continue after 4898 clear")
            fails += 1
        else:
            print("  update_enemies: flash_step then continue if dead")
        if "4898 Y-only 36/61/62/72/83" not in upd:
            fail("cull comment must list type 36 with 61/62/72/83")
            fails += 1
        else:
            print("  update_enemies: type 36 in 4898 Y-only set")

    y4898 = fn_span(ent, "static int step_88_y_4898(Slot *e)")
    if not y4898 or "(u8)e->y >= 0xD0" not in y4898:
        fail("step_88_y_4898 must still unsigned-cull Y>=0xD0")
        fails += 1
    else:
        print("  step_88_y_4898: unsigned Y>=0xD0")

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

    vals = parse_spawn_list(spawn_src)
    if vals:
        for t, name in ((21, "21"), (41, "41"), (45, "45")):
            if t in vals:
                fail(f"spawn_type_list must keep type {name} child-only")
                fails += 1
            else:
                print(f"  KEEP: type {name} child-only")
        if 36 not in vals:
            fail("spawn_type_list must still include type 36")
            fails += 1
        else:
            print("  spawn_type_list still includes type 36")

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

    if "s_ebullet_init_ret" not in ent:
        fail("s_ebullet_init_ret for 21/37/38/41/42/43 was reverted")
        fails += 1
    else:
        print("  KEEP: s_ebullet_init_ret still armed")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
