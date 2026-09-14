#!/usr/bin/env python3
"""Box 4/5/6 and chip 63 use 4898 unsigned Y>=0xD0, not playfield max_y.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  handler_type4_box 0x7826 (types 4/5/6 share):
    BIT 7 / JR NZ,784d
    DEC +03 / RET NZ                 ; hidden: no 4898
    7841 +08=0xC0 +0c=1 SET 7
    CALL 0x4898                      ; 0x784d Y_motion

  handler_type63_power_chip:
    CALL 0x4898                      ; 0x78af Y_motion (inherits +0c=1)

  proto_box 0x44 (type 68) is in spawn_type_list; it emits types 4/5/6
  at Y=0. Box-6 death 7882 converts in-place to type 63 (keeps 00C0).

  Y_motion_sub 0x48de:
    ADD HL,DE
    LD A,H / CP 0xD0 / RET C
    JP 0x48d0                        ; entity_clear

  Original playfield_h=192; port max_y = playfield_h+8 = 200.
  Old box_step / chip_step added Yvel as signed s32 then the shared
  pass culled Y>200. Y=201..207 is still live on MSX (unsigned < 0xD0).
  Yvel 0x00C0 from Y=0 first mismatches at frame 268 (Y=201).

  Pairdesc 57/58 81cb CALL 4898 stays signed s32: dir 4 speed 5 for
  +1f=0x20 frames is Y=80 / Xvel=0, in-range on both.

Usage (from zanac-md):
    python tools/test_box_chip_4898_yd0.py
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
HUD = ROOT / "src" / "hud.c"
MAIN = ROOT / "src" / "main.c"
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
    ypos = ((y & 0xFF) << 8) | (yf & 0xFF)
    ypos = (ypos + (vy & 0xFFFF)) & 0xFFFF
    y = ypos >> 8
    yf = ypos & 0xFF
    return y, yf, y >= 0xD0


def old_playfield_cull(y: int) -> bool:
    return y > 200 or y < -24


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8")
    ply = PLAYER.read_text(encoding="utf-8")
    hdr = PLAYER_H.read_text(encoding="utf-8")
    spawn_src = SPAWN.read_text(encoding="utf-8")
    mapc = MAPC.read_text(encoding="utf-8")
    hud = HUD.read_text(encoding="utf-8")
    main_c = MAIN.read_text(encoding="utf-8")

    asm = load_asm()
    if asm:
        if not re.search(r"CALL\s+0x4898\s*;\s*0x784d", asm, re.I):
            fail("zanac.asm 784d is not CALL 4898")
            fails += 1
        else:
            print("  ASM 784d: CALL 4898")
        if not re.search(r"LD\s+\(IX\+0x0c\),\s*0x01\s*;\s*0x7845", asm, re.I):
            fail("zanac.asm 7845 is not +0c=1")
            fails += 1
        else:
            print("  ASM 7845: +0c=1 Y-only")
        if not re.search(r"CALL\s+0x4898\s*;\s*0x78af", asm, re.I):
            fail("zanac.asm 78af is not CALL 4898")
            fails += 1
        else:
            print("  ASM 78af: chip CALL 4898")
        if not re.search(r"CP\s+0xd0\s*;\s*0x48f2", asm, re.I):
            fail("zanac.asm 48f2 is not CP 0xD0")
            fails += 1
        else:
            print("  ASM 48f2: Y_motion_sub CP 0xD0")
        if not re.search(r"CALL\s+0x4898\s*;\s*0x81cb", asm, re.I):
            fail("zanac.asm 81cb is not CALL 4898")
            fails += 1
        else:
            print("  ASM 81cb: pairdesc/sig still CALL 4898")
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
    y, yf, culled = step_y_4898(0xCF, 0x40, 0x00C0)
    if (y, culled) != (0xD0, True):
        fail(f"4898 at 0xCF.40 + 0x00C0 -> Y={y:#x} cull={culled}, want 0xD0 True")
        fails += 1
    else:
        print("  sim: Y=201..207 live on 4898; old max_y=200 kills; 0xD0 clears")

    # Box 00C0 from Y=0 first mismatches at frame 268 (Y=201).
    y = yf = 0
    mismatch = None
    for i in range(1, 400):
        y, yf, u_cull = step_y_4898(y, yf, 0x00C0)
        s_cull = old_playfield_cull(y)
        if u_cull != s_cull:
            mismatch = (i, y, u_cull, s_cull)
            break
    if mismatch != (268, 201, False, True):
        fail(f"box 00C0 from Y=0 mismatch {mismatch}, want (268, 201, False, True)")
        fails += 1
    else:
        print("  sim: box 00C0 from Y=0 first mismatch frame 268 Y=201")

    # Pairdesc 32-frame dir4 speed5 stays in-range (do not ship 81cb).
    yvel = 128 * 5
    y = yf = 0
    x = 0xC6
    pair_bad = False
    for _ in range(32):
        ypos = ((y & 0xFF) << 8) | yf
        ypos = (ypos + (yvel & 0xFFFF)) & 0xFFFF
        yf = ypos & 0xFF
        y = ypos >> 8
        if y >= 0xD0 or x >= 0xD1 or old_playfield_cull(y):
            pair_bad = True
            break
    if pair_bad or y != 80:
        fail(f"pairdesc 32f must stay Y=80 in-range, got Y={y} bad={pair_bad}")
        fails += 1
    else:
        print("  sim: pairdesc 32f dir4/spd5 ends Y=80 (in-range both)")

    box = fn_span(ent, "static void box_step(Slot *e)")
    if not box:
        fail("box_step not found")
        fails += 1
    elif "step_88_y_4898" not in box:
        fail("box_step must use step_88_y_4898 (4898 Y-only CP 0xD0)")
        fails += 1
    elif "e->bind = 0x00C0" not in box:
        fail("box_step reveal must still set bind=0x00C0")
        fails += 1
    elif "ypos +=" in box or "ypos >> 8" in box:
        fail("box_step must not keep signed s32 Y")
        fails += 1
    else:
        print("  box_step: step_88_y_4898 (unsigned Y>=0xD0), bind=0x00C0")

    chip = fn_span(ent, "static void chip_step(Slot *e)")
    if not chip:
        fail("chip_step not found")
        fails += 1
    elif "step_88_y_4898" not in chip:
        fail("chip_step must use step_88_y_4898 (4898 Y-only CP 0xD0)")
        fails += 1
    elif "ypos +=" in chip or "ypos >> 8" in chip:
        fail("chip_step must not keep signed s32 Y")
        fails += 1
    else:
        print("  chip_step: step_88_y_4898 (unsigned Y>=0xD0)")

    upd = fn_span(ent, "static void update_enemies(void)")
    if not upd:
        fail("update_enemies not found")
        fails += 1
    else:
        if "e->kind != KIND_BOX" not in upd:
            fail("KIND_BOX must be excluded from playfield max_y cull")
            fails += 1
        else:
            print("  update_enemies: KIND_BOX excluded from max_y cull")
        if "e->kind != KIND_CHIP" not in upd:
            fail("KIND_CHIP must be excluded from playfield max_y cull")
            fails += 1
        else:
            print("  update_enemies: KIND_CHIP excluded from max_y cull")
        if not re.search(
            r"else if \(e->kind == KIND_BOX\)\s*\{\s*"
            r"box_step\(e\);\s*"
            r"if \(!e->alive\)\s*continue;",
            upd,
        ):
            fail("KIND_BOX must continue after 4898 clear")
            fails += 1
        else:
            print("  update_enemies: box_step then continue if dead")
        if not re.search(
            r"else if \(e->kind == KIND_CHIP\)\s*\{\s*"
            r"chip_step\(e\);\s*"
            r"if \(!e->alive\)\s*continue;",
            upd,
        ):
            fail("KIND_CHIP must continue after 4898 clear")
            fails += 1
        else:
            print("  update_enemies: chip_step then continue if dead")
        if "box 4/5/6 / chip 63" not in upd:
            fail("cull comment must list box 4/5/6 / chip 63")
            fails += 1
        else:
            print("  update_enemies: box 4/5/6 / chip 63 in 4898 Y-only set")
        if "4898 Y-only 36/61/62/72/83" not in upd:
            fail("cull comment must keep type 36 with 61/62/72/83")
            fails += 1
        else:
            print("  update_enemies: type 36 still in 4898 Y-only set")
        if "tracker 31/33" not in upd:
            fail("cull comment must keep tracker 31/33")
            fails += 1
        else:
            print("  update_enemies: tracker 31/33 still in 4898 wrap set")
        if "swoop 26-29" not in upd:
            fail("cull comment must keep swoop 26-29")
            fails += 1
        else:
            print("  update_enemies: swoop 26-29 still in 4898 wrap set")
        if "veybar 22-25" not in upd:
            fail("cull comment must keep veybar 22-25")
            fails += 1
        else:
            print("  update_enemies: veybar 22-25 still in 4898 wrap set")
        if re.search(
            r"e->kind != KIND_VEYBAR\s*"
            r"&&\s*e->kind != KIND_UMBER\s*"
            r"&&\s*!\(e->kind == KIND_EBULLET\)\s*"
            r"&&\s*\(e->variant == 20",
            upd,
        ):
            fail("playfield cull must not split !(KIND_EBULLET) from variants")
            fails += 1
        elif not re.search(
            r"e->kind != KIND_TRACKER\s*"
            r"&&\s*e->kind != KIND_SWOOP\s*"
            r"&&\s*e->kind != KIND_VEYBAR\s*"
            r"&&\s*e->kind != KIND_UMBER\s*"
            r"&&\s*!\(e->kind == KIND_EBULLET\s*"
            r"&&\s*\(e->variant == 20",
            upd,
        ):
            fail(
                "playfield cull must keep "
                "KIND_TRACKER then KIND_SWOOP then "
                "!(KIND_EBULLET && variants) after KIND_VEYBAR/UMBER"
            )
            fails += 1
        else:
            print("  update_enemies: ebullet exclude is !(KIND_EBULLET && variants)")
        if re.search(
            r"e->x > max_x \+ 16\)\s*"
            r"\|\|\s*\(e->kind != KIND_GSWOOP && e->y > max_y\)",
            upd,
        ):
            fail("playfield (x || y) group must not close after max_x+16")
            fails += 1
        else:
            print("  update_enemies: playfield (x || y) group intact")

    y4898 = fn_span(ent, "static int step_88_y_4898(Slot *e)")
    if not y4898 or "(u8)e->y >= 0xD0" not in y4898:
        fail("step_88_y_4898 must still unsigned-cull Y>=0xD0")
        fails += 1
    else:
        print("  step_88_y_4898: unsigned Y>=0xD0")

    # Leftover: pairdesc 81cb stays signed (32-frame descent in-range).
    pair = fn_span(ent, "static void pairdesc_step(Slot *e)")
    if not pair:
        fail("pairdesc_step not found")
        fails += 1
    elif "ypos +=" not in pair:
        fail("one-PR: pairdesc leftover signed s32 should remain")
        fails += 1
    elif "step_88_4898" in pair or "step_88_y_4898" in pair:
        fail("one-PR: do not convert pairdesc 81cb in this PR")
        fails += 1
    else:
        print("  leftover: pairdesc_step still signed s32 (81cb in-range)")

    tracker = fn_span(ent, "static void tracker_step(Slot *e)")
    if not tracker or "step_88_y_4898" not in tracker:
        fail("tracker 31/33 4898 stay was reverted")
        fails += 1
    else:
        print("  KEEP: tracker_step step_88_y_4898")

    if upd and "e->kind != KIND_TRACKER" not in upd:
        fail("KIND_TRACKER playfield-cull exclude was reverted")
        fails += 1
    else:
        print("  KEEP: KIND_TRACKER excluded from playfield cull")

    swoop = fn_span(ent, "static void swoop_step(Slot *e)")
    if not swoop or "step_88_4898" not in swoop:
        fail("swoop 26-29 4898 stay was reverted")
        fails += 1
    else:
        print("  KEEP: swoop_step step_88_4898")

    vey = fn_span(ent, "static void veybar_step(Slot *e)")
    if not vey or "step_88_4898" not in vey or "step_88_y_4898" not in vey:
        fail("veybar 22-25 4898 stay was reverted")
        fails += 1
    else:
        print("  KEEP: veybar_step x_on ? step_88_4898 : step_88_y_4898")

    umber = fn_span(ent, "static void umber_step(Slot *e)")
    if not umber or "step_88_y_4898" not in umber:
        fail("umber 7/8/9 4898 stay was reverted")
        fails += 1
    else:
        print("  KEEP: umber_step step_88_y_4898")

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

    if "dma_nt_row" not in mapc:
        fail("dma_nt_row HUD restore was reverted")
        fails += 1
    else:
        print("  KEEP: dma_nt_row HUD BG_B restore")

    if "0x03, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20, 0x03" not in hud:
        fail("8-tile 0x4BDF HUD border was reverted")
        fails += 1
    else:
        print("  KEEP: 8-tile 0x4BDF HUD border")

    if "DMA_setAutoFlush(FALSE)" not in main_c:
        fail("60fps: DMA auto-flush must stay off")
        fails += 1
    elif main_c.count("SYS_doVBlankProcess()") != 1:
        fail("60fps: exactly one SYS_doVBlankProcess per tick")
        fails += 1
    else:
        print("  KEEP: 60fps one VBlank / DMA auto-flush off")

    if "mode_letter_attr" in ent:
        fail("entity.c must not grow a playfield-wide mode_letter_attr fill")
        fails += 1
    else:
        print("  KEEP: no playfield-wide mode_letter_attr")

    if "opaque" in hud.lower() and "0x20" in hud and "CT" not in hud:
        fail("do not opaque-recolor charset 0x20")
        fails += 1
    if "hud_put_win((u16)(HUD_COL + 4), y, 0x03)" in hud:
        fail("do not restore the 5-tile 03 20 20 20 03 border")
        fails += 1
    else:
        print("  KEEP: charset 0x20 is not opaque-recolored")

    if "0xBFD6" in ent or "0xbfd6" in ent:
        fail("must not CALL 0xBFD6")
        fails += 1
    else:
        print("  KEEP: no 0xBFD6")

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

    if "while (nt == 64 && guard < 8)" not in ent:
        fail("type 64 8279 re-roll was reverted")
        fails += 1
    else:
        print("  KEEP: type 64 8279 re-roll")

    if not re.search(
        r"e->variant == 21\)\s*\n\s*spr_set_sat_col\(\s*e,\s*"
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
        if 68 not in vals:
            fail("spawn_type_list must still include type 68 (proto_box)")
            fails += 1
        else:
            print("  spawn_type_list still includes type 68 (proto_box)")

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
