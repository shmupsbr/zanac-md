#!/usr/bin/env python3
"""Gswoop 30/32 use 4898 unsigned wrap Y>=0xD0 / X>=0xD1, not playfield X>256.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  handler_type30_ground_swooper 0x7e9c (type 32 shares; CP 0x1E):
    init +0c=1 Y then 2 X; type30 X=0x30 Xvel/Yvel 0x0180
    type32 Y=0xD0 Yvel FF00 Xvel 0100 sense BIT6
    pair child type+1 at X=0xC0
    armed 0x7f20 merge then
    7f73 XOR +04 0x06
    CALL 0x4898                  ; 0x7f7b  same epilogue as tracker
    JP 0x44ba                    ; 0x7f7e

  Jump table type 30/32 at 0x70B7+30*2 / +32*2 = 0x70F3 / 0x70F7
  is 9C 7E = 7E9C.

  +0c=1 Y_motion_sub 0x48de: ADD HL,DE / LD A,H / CP 0xD0 / RET C
  +0c=2 X_motion_sub 0x48f8: ADD HL,DE / LD A,H / CP 0xD1 / RET C

  Original playfield_w=256; port max_x+16 = 256.
  Old gswoop_step added X/Y vel as signed s32. +0c=2 had no X>=0xD1
  check; playfield kept X=0xD1..0xFF (X>256 is false).
  Type30 parent after the pair is gone: X=0x30 + 0x0180 reaches 0xD1
  and must clear. Signed s32 stored 209 and stayed live.

  7f54 unsigned merge stays. Pairdesc 57/58 81cb stays signed
  (Y ends ~80, in-range on both). Do not re-ship those.

Usage (from zanac-md):
    python tools/test_gswoop_4898_wrap.py
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
HUD = ROOT / "src" / "hud.c"
MAIN = ROOT / "src" / "main.c"
ASM_CANDIDATES = [
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    Path.home() / "zanac-re" / "source" / "zanac.asm",
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
]
JAPAN_V1_SHA1 = "46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2"
CALL_4898 = bytes.fromhex("cd9848")
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


def step_y_4898(y: int, yf: int, vy: int) -> tuple[int, bool]:
    """u8 8.8 ADD then unsigned Y>=0xD0."""
    ypos = ((((y & 0xFF) << 8) | (yf & 0xFF)) + (vy & 0xFFFF)) & 0xFFFF
    y = (ypos >> 8) & 0xFF
    return y, y >= 0xD0


def step_x_4898(x: int, xf: int, vx: int) -> tuple[int, bool]:
    """u8 8.8 ADD then unsigned X>=0xD1."""
    xpos = ((((x & 0xFF) << 8) | (xf & 0xFF)) + (vx & 0xFFFF)) & 0xFFFF
    x = (xpos >> 8) & 0xFF
    return x, x >= 0xD1


def old_signed_then_playfield(
    x: int, y: int, xf: int, yf: int, vx: int, vy: int, max_y: int = 200
) -> tuple[int, int, bool]:
    """Old port: signed s32, no X>=0xD1; playfield X>256 / Y>200."""
    xpos = (x << 8) | (xf & 0xFF)
    ypos = (y << 8) | (yf & 0xFF)
    vx_s = vx if vx < 0x8000 else vx - 0x10000
    vy_s = vy if vy < 0x8000 else vy - 0x10000
    xpos += vx_s
    ypos += vy_s
    x = xpos >> 8
    y = ypos >> 8
    culled = x < -16 or x > 256 or y > max_y or y < -24
    return x, y, culled


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8", errors="replace")
    ply = PLAYER.read_text(encoding="utf-8", errors="replace")
    hdr = PLAYER_H.read_text(encoding="utf-8", errors="replace")
    mapc = MAPC.read_text(encoding="utf-8", errors="replace")
    spawn_src = SPAWN.read_text(encoding="utf-8", errors="replace")
    hud = HUD.read_text(encoding="utf-8", errors="replace")
    main_c = MAIN.read_text(encoding="utf-8", errors="replace")
    asm = load_asm()
    rom = load_japan_v1()

    if asm:
        t30 = asm.split("handler_type30_ground_swooper:", 1)
        if len(t30) < 2:
            fail("zanac.asm missing handler_type30_ground_swooper")
            fails += 1
        else:
            body = t30[1].split("LAB_ram_7f99:", 1)[0]
            if not re.search(r"CALL\s+0x4898\s*;\s*0x7f7b", body, re.I):
                fail("gswoop epilogue must CALL 4898 at 7f7b")
                fails += 1
            else:
                print("  ASM 7f7b: CALL 4898 (Z80 CD 98 48)")
            if not re.search(r"XOR\s+0x06\s*;\s*0x7f76", body, re.I):
                fail("7f73 must XOR +04 0x06 before 4898")
                fails += 1
            else:
                print("  ASM 7f76: XOR +04 0x06")
            if not re.search(r"LD\s+\(IX\+0x0c\),\s*0x01\s*;\s*0x7ea6", body, re.I):
                fail("7ea6 must set +0c=1 Y_motion")
                fails += 1
            else:
                print("  ASM 7ea6: +0c=1 Y_motion")
            if not re.search(r"LD\s+\(IX\+0x02\),\s*0x30\s*;\s*0x7eba", body, re.I):
                fail("7eba must write parent X=0x30")
                fails += 1
            else:
                print("  ASM 7eba: parent X=0x30")
            if not re.search(r"LD\s+\(IY\+0x02\),\s*0xc0\s*;\s*0x7ef5", body, re.I):
                fail("7ef5 must write child X=0xC0")
                fails += 1
            else:
                print("  ASM 7ef5: child X=0xC0")
            if not re.search(r"LD\s+\(IX\+0x0c\),\s*0x02\s*;\s*0x7f49", body, re.I):
                fail("7f49 must set +0c=2 (X_motion)")
                fails += 1
            else:
                print("  ASM 7f49: +0c=2 X_motion")
            if not re.search(r"SUB\s+\(IX\+0x02\)\s*;\s*0x7f54", body, re.I):
                fail("7f54 unsigned merge must stay")
                fails += 1
            else:
                print("  ASM 7f54: SUB (IX+02) unsigned merge stays")
        if not re.search(r"CP\s+0xd0\s*;\s*0x48f2", asm, re.I):
            fail("Y_motion_sub 48f2 is not CP 0xD0")
            fails += 1
        else:
            print("  ASM 48f2: Y_motion_sub CP 0xD0")
        if not re.search(r"CP\s+0xd1\s*;\s*0x490c", asm, re.I):
            fail("X_motion_sub 490c is not CP 0xD1")
            fails += 1
        else:
            print("  ASM 490c: X_motion_sub CP 0xD1")
        # Jump table type 30 at 0x70B7+30*2 = 0x70F3 is 9C 7E.
        if not re.search(r"SBC\s+A,\s*H\s*;\s*0x70f3", asm, re.I):
            fail("jump table 70f3 is not 0x9C (type 30 lo)")
            fails += 1
        elif not re.search(r"LD\s+A,\s*\(HL\)\s*;\s*0x70f4", asm, re.I):
            fail("jump table 70f4 is not 0x7E (type 30 hi = 7E9C)")
            fails += 1
        else:
            print("  ASM 70f3: type 30 handler 0x7E9C")
        if not re.search(r"SBC\s+A,\s*H\s*;\s*0x70f7", asm, re.I):
            fail("jump table 70f7 is not 0x9C (type 32 lo)")
            fails += 1
        elif not re.search(r"LD\s+A,\s*\(HL\)\s*;\s*0x70f8", asm, re.I):
            fail("jump table 70f8 is not 0x7E (type 32 hi = 7E9C)")
            fails += 1
        else:
            print("  ASM 70f7: type 32 handler 0x7E9C")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    if rom:
        if rom[0x7F7B : 0x7F7B + 3] != CALL_4898:
            fail(
                f"Japan v1 7f7b is {rom[0x7F7B:0x7F7B+3].hex()}, want cd9848"
            )
            fails += 1
        else:
            print("  ROM 7f7b: CD 98 48 CALL 4898")
        if rom[0x48F2] != 0xD0:
            fail(f"Japan v1 48f2 CP imm is {rom[0x48F2]:#x}, want 0xD0")
            fails += 1
        else:
            print("  ROM 48f2: CP 0xD0")
        if rom[0x490C] != 0xD1:
            fail(f"Japan v1 490c CP imm is {rom[0x490C]:#x}, want 0xD1")
            fails += 1
        else:
            print("  ROM 490c: CP 0xD1")
    else:
        print("  (Japan v1 ROM not on this machine; ASM + C locks)")

    # Type30 parent +0c=2: X=0xD0 + 0x0180 -> 0xD1 clears.
    x, culled = step_x_4898(0xD0, 0, 0x0180)
    ox, oy, old = old_signed_then_playfield(0xD0, 0x80, 0, 0, 0x0180, 0)
    if (x, culled) != (0xD1, True):
        fail(f"4898 0xD0+0x0180 -> X={x:#x} cull={culled}, want 0xD1 True")
        fails += 1
    elif ox != 0xD1:
        fail(f"old signed 0xD0+0x0180 -> X={ox}, want 209")
        fails += 1
    elif old:
        fail("old playfield cull must keep signed X=209 (<= 256)")
        fails += 1
    else:
        print("  sim: type30 0xD0+0x0180 -> 0xD1 clear; old playfield keeps")

    # Walk type30 parent from X=0x30 / 0x0180 until 4898 clears.
    run = 0x30
    frac = 0
    n = 0
    culled = False
    while n < 200:
        run, culled = step_x_4898(run, frac, 0x0180)
        frac = (frac + 0x80) & 0xFF
        n += 1
        if culled:
            break
    if not culled or run < 0xD1:
        fail(f"type30 walk from 0x30+0x0180 ended X={run:#x} cull={culled}")
        fails += 1
    elif n < 2:
        fail("type30 walk must take more than one frame to reach 0xD1")
        fails += 1
    else:
        print(f"  sim: type30 parent X=0x30+0x0180 hits X={run:#x} (>=0xD1) at frame {n}")

    # X=0xD1..0xFF: 4898 clears; old playfield X>256 does not.
    for xv in range(0xD1, 0x100):
        _, culled = step_x_4898(xv, 0, 0)
        if not culled:
            fail(f"4898 must clear X={xv:#x} (>= 0xD1)")
            fails += 1
        _, _, old = old_signed_then_playfield(xv, 0x80, 0, 0, 0, 0)
        if old:
            fail(f"old playfield cull must keep X={xv:#x} (<= 256)")
            fails += 1
    print("  sim: X=0xD1..0xFF clears on 4898; old playfield keeps")

    # Type32 first rise: Y=0xD0 + 0xFF00 -> 0xCF live on both.
    y, culled = step_y_4898(0xD0, 0, 0xFF00)
    oy_s = old_signed_then_playfield(0x30, 0xD0, 0, 0, 0, 0xFF00)[1]
    if (y, culled) != (0xCF, False):
        fail(f"4898 0xD0+0xFF00 -> Y={y:#x} cull={culled}, want 0xCF False")
        fails += 1
    elif oy_s != 0xCF:
        fail(f"signed 0xD0+0xFF00 -> Y={oy_s}, want 207")
        fails += 1
    else:
        print("  sim: type32 0xD0+0xFF00 -> 0xCF live (same as signed)")

    step = fn_span(ent, "static void gswoop_step(Slot *e)")
    if not step:
        fail("gswoop_step not found")
        fails += 1
    elif "ypos +=" in step or "s32 ypos" in step or "s32 xpos" in step:
        fail("gswoop_step must not keep signed s32 X/Y")
        fails += 1
    elif re.search(r"e->y\s*>\s*max_y|e->x\s*>\s*max_x", step):
        fail("gswoop_step must not invent a playfield cull")
        fails += 1
    elif "step_88_y_4898" not in step:
        fail("gswoop_step +0c=1 must use step_88_y_4898")
        fails += 1
    elif "(u8)e->x >= 0xD1" not in step:
        fail("gswoop_step +0c=2 must unsigned-cull X>=0xD1")
        fails += 1
    elif "(u8)((u8)e->x)" not in step and "((u8)e->x)" not in step:
        fail("gswoop_step X add must be unsigned u8 8.8")
        fails += 1
    elif "(u8)((u8)sib->x - (u8)e->x) < 0x0B" not in step:
        fail("gswoop 7f54 unsigned merge was reverted")
        fails += 1
    elif "sib->variant = 40" not in step or "e->x + 5" not in step:
        fail("merge must still write pair type 0x28 and X+=5")
        fails += 1
    else:
        print("  gswoop_step: Y step_88_y_4898 / X u8 wrap X>=0xD1")
        print("  KEEP: gswoop 7f54 unsigned (pair.X-self.X)<0x0B")

    if step:
        if "e->clock & 0x40" not in step:
            fail("gswoop BIT6 sense was reverted")
            fails += 1
        elif "e->clock & (u8)~3) | 2" not in step:
            fail("gswoop +0c=2 switch was reverted")
            fails += 1
        elif "e->sat_col ^ 0x06" not in step:
            fail("gswoop 7f73 XOR 0x06 was reverted")
            fails += 1
        else:
            print("  KEEP: gswoop Y-then-X / BIT6 / XOR 0x06")

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
    elif "e->y = 0xD0" not in spawn or "e->bind = 0xFF00" not in spawn:
        fail("type32 rise Y=0xD0 / Yvel FF00 was reverted")
        fails += 1
    elif "c->kind = KIND_TRACKER" not in child:
        fail("gswoop child must stay KIND_TRACKER")
        fails += 1
    elif "c->dest = (type == 30) ? 0xFE80 : 0xFF00" not in child:
        fail("gswoop child Xvel FE80/FF00 was reverted")
        fails += 1
    else:
        print("  KEEP: spawn_gswoop X=0x30/0xC0 type30 vel 0x0180")

    upd = fn_span(ent, "static void update_enemies(void)")
    if not upd:
        fail("update_enemies not found")
        fails += 1
    else:
        if not re.search(
            r"e->kind != KIND_GSWOOP\s*"
            r"&&\s*e->kind != KIND_TRACKER",
            upd,
        ):
            fail("KIND_GSWOOP must be excluded from playfield cull before TRACKER")
            fails += 1
        else:
            print("  update_enemies: KIND_GSWOOP excluded from max_y cull")
        if not re.search(
            r"else if \(e->kind == KIND_GSWOOP\)\s*\{\s*"
            r"gswoop_step\(e\);\s*"
            r"if \(!e->alive\)\s*continue;",
            upd,
        ):
            fail("KIND_GSWOOP must continue after 4898 clear")
            fails += 1
        else:
            print("  update_enemies: gswoop_step then continue if dead")
        if "gswoop 30/32" not in upd:
            fail("cull comment must list gswoop 30/32 with 4898 wrap set")
            fails += 1
        else:
            print("  update_enemies: gswoop 30/32 in 4898 wrap set")
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
        if "box 4/5/6 / chip 63" not in upd:
            fail("cull comment must keep box 4/5/6 / chip 63")
            fails += 1
        else:
            print("  update_enemies: box 4/5/6 / chip 63 still in 4898 set")
        if "4898 Y-only 36/61/62/72/83" not in upd:
            fail("cull comment must keep type 36 with 61/62/72/83")
            fails += 1
        else:
            print("  update_enemies: type 36 still in 4898 Y-only set")
        if re.search(
            r"e->kind != KIND_VEYBAR\s*"
            r"&&\s*e->kind != KIND_UMBER\s*"
            r"&&\s*!\(e->kind == KIND_EBULLET\)\s*"
            r"&&\s*\(e->variant == 20",
            upd,
        ):
            fail(
                "playfield cull must not split !(KIND_EBULLET) from variants"
            )
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

    y4898 = fn_span(ent, "static int step_88_y_4898(Slot *e)")
    if not y4898 or "(u8)e->y >= 0xD0" not in y4898:
        fail("step_88_y_4898 must still unsigned-cull Y>=0xD0")
        fails += 1
    else:
        print("  KEEP: step_88_y_4898 unsigned Y>=0xD0")

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

    box = fn_span(ent, "static void box_step(Slot *e)")
    if not box or "step_88_y_4898" not in box:
        fail("box 4/5/6 4898 stay was reverted")
        fails += 1
    elif "e->bind = 0x00C0" not in box:
        fail("box reveal bind=0x00C0 was reverted")
        fails += 1
    else:
        print("  KEEP: box_step step_88_y_4898 bind=0x00C0")

    chip = fn_span(ent, "static void chip_step(Slot *e)")
    if not chip or "step_88_y_4898" not in chip:
        fail("chip 63 4898 stay was reverted")
        fails += 1
    else:
        print("  KEEP: chip_step step_88_y_4898")

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

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
