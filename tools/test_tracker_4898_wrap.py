#!/usr/bin/env python3
"""Types 31/33 stealth tracker use 4898 unsigned wrap, not playfield max_y.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  handler_type31_stealth_tracker entry 0x7f84 (type 33 shares):
    playerY CP entityY; BIT6 +05 CCF; NC keep +0c; CY +0c=2
    then fall into 7f73 XOR +04 0x06
    CALL 0x4898                  ; 0x7f7b
    JP 0x44ba                    ; 0x7f7e

  Jump table type 31/33 = 0x7F84. Gswoop 30/32 child is type+1
  (KIND_TRACKER) and also ends at 7f73/7f7b.

  Z80 CALL 0x4898 is bytes CD 98 48.

  +0c=1 Y_motion_sub 0x48de: ADD HL,DE / LD A,H / CP 0xD0 / RET C
  +0c=2 X_motion_sub 0x48f8: ADD HL,DE / LD A,H / CP 0xD1 / RET C

  Original playfield_h=192; port max_y = playfield_h+8 = 200.
  Old tracker_step added X/Y vel as signed s32 then the shared pass
  culled Y>200 / Y<-24 / X>256.
  Type32 child first rise: Y=0xD0 + 0xFF00 -> 0xCF (207) is live
  on MSX (unsigned < 0xD0) and died on playfield max_y=200.
  Type30 child left-wrap: X=0 + FE80 -> 0xFE >= 0xD1 clears;
  signed s32 sat at -1.5 then playfield x<-16.

Usage (from zanac-md):
    python tools/test_tracker_4898_wrap.py
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
    """Old port: signed s32 then Y>200 / X>256 / Y<-24."""
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
    asm = load_asm()
    rom = load_japan_v1()

    if asm:
        t31 = asm.split("handler_type31_stealth_tracker:", 1)
        if len(t31) < 2:
            fail("zanac.asm missing handler_type31_stealth_tracker")
            fails += 1
        else:
            body = t31[1].split("LAB_ram_7f99:", 1)[0]
            if not re.search(r"CALL\s+0x4898\s*;\s*0x7f7b", body, re.I):
                fail("tracker epilogue must CALL 4898 at 7f7b")
                fails += 1
            else:
                print("  ASM 7f7b: CALL 4898 (Z80 CD 98 48)")
            if not re.search(r"XOR\s+0x06\s*;\s*0x7f76", body, re.I):
                fail("7f73 must XOR +04 0x06 before 4898")
                fails += 1
            else:
                print("  ASM 7f76: XOR +04 0x06")
            if not re.search(r"LD\s+A,\s*\(0xe301\)\s*;\s*0x7f84", body, re.I):
                fail("7f84 is not LD A,(E301) player Y")
                fails += 1
            else:
                print("  ASM 7f84: LD A,(E301) player Y")
            if not re.search(r"LD\s+\(IX\+0x0c\),\s*0x02\s*;\s*0x7f93", body, re.I):
                fail("7f93 must set +0c=2 (X_motion)")
                fails += 1
            else:
                print("  ASM 7f93: +0c=2 X_motion")
            if not re.search(r"JR\s+0x7f73\s*;\s*0x7f97", body, re.I):
                fail("7f97 must JR 7f73 (shared 7f7b)")
                fails += 1
            else:
                print("  ASM 7f97: JR 7f73")
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
        # Jump table type 31 at 0x70B7+31*2 = 0x70F5 is 84 7F.
        if not re.search(r"ADD\s+A,\s*H\s*;\s*0x70f5", asm, re.I):
            fail("jump table 70f5 is not 0x84 (type 31 lo)")
            fails += 1
        elif not re.search(r"LD\s+A,\s*A\s*;\s*0x70f6", asm, re.I):
            fail("jump table 70f6 is not 0x7F (type 31 hi = 7F84)")
            fails += 1
        else:
            print("  ASM 70f5: type 31 handler 0x7F84")
        if not re.search(r"ADD\s+A,\s*H\s*;\s*0x70f9", asm, re.I):
            fail("jump table 70f9 is not 0x84 (type 33 lo)")
            fails += 1
        elif not re.search(r"LD\s+A,\s*A\s*;\s*0x70fa", asm, re.I):
            fail("jump table 70fa is not 0x7F (type 33 hi = 7F84)")
            fails += 1
        else:
            print("  ASM 70f9: type 33 handler 0x7F84")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    if rom is not None:
        if rom[0x7F7B : 0x7F7B + 3] != CALL_4898:
            fail(
                f"Japan v1 7f7b bytes {rom[0x7F7B:0x7F7B+3].hex()} "
                f"want {CALL_4898.hex()}"
            )
            fails += 1
        else:
            print("  ROM 7f7b: cd 98 48")
        if rom[0x70F5 : 0x70F7] != bytes.fromhex("847f"):
            fail(
                f"Japan v1 type31 handler {rom[0x70F5:0x70F7].hex()} "
                "want 84 7f"
            )
            fails += 1
        else:
            print("  ROM 70f5: type 31 -> 7f84")
    else:
        print("  (Japan v1 ROM not on this machine; ASM + C locks)")

    # Y=201..207: playfield max_y=200 kills; 4898 does not.
    for y in range(201, 208):
        _, culled = step_y_4898(y, 0, 0)
        if culled:
            fail(f"4898 must keep Y={y} (< 0xD0)")
            fails += 1
        _, _, old = old_signed_then_playfield(0x80, y, 0, 0, 0, 0)
        if not old:
            fail(f"old playfield cull must kill Y={y} (> 200)")
            fails += 1
    y, culled = step_y_4898(0xCF, 0, 0x0100)
    if (y, culled) != (0xD0, True):
        fail(f"4898 at 0xCF + 0x0100 -> Y={y:#x} cull={culled}, want 0xD0 True")
        fails += 1
    else:
        print("  sim: Y=201..207 live on 4898; old max_y=200 kills; 0xD0 clears")

    # Type32 child first rise: Y=0xD0 + 0xFF00 -> 0xCF. Signed also 207.
    y, culled = step_y_4898(0xD0, 0, 0xFF00)
    ox, oy, old = old_signed_then_playfield(0xC0, 0xD0, 0, 0, 0, 0xFF00)
    if (y, culled) != (0xCF, False):
        fail(f"4898 type32 rise 0xD0+0xFF00 -> Y={y:#x} cull={culled}, want 0xCF False")
        fails += 1
    elif oy != 0xCF:
        fail(f"old signed 0xD0+0xFF00 -> Y={oy}, want 207")
        fails += 1
    elif not old:
        fail("old playfield cull must kill signed Y=207 (> 200)")
        fails += 1
    else:
        print("  sim: type32 child 0xD0+0xFF00 -> 0xCF live; old max_y kills")

    # Type30 child left wrap: X=0 + FE80 -> 0xFE >= 0xD1. Signed sits at -1.5.
    x, culled = step_x_4898(0, 0, 0xFE80)
    ox, oy, old = old_signed_then_playfield(0, 0x80, 0, 0, 0xFE80, 0)
    if (x, culled) != (0xFE, True):
        fail(f"4898 left wrap 0+FE80 -> X={x:#x} cull={culled}, want 0xFE True")
        fails += 1
    elif ox != -2:
        fail(f"old signed s32 0+FE80 -> X={ox}, want -2")
        fails += 1
    elif old:
        fail("old playfield cull must keep signed X=-2 (>-16)")
        fails += 1
    else:
        print("  sim: type30 child left wrap 0+FE80 -> 0xFE clear; s32 was -2 live")

    # X=0xD1..0xFF: 4898 clears; old playfield X>256 does not.
    for x in range(0xD1, 0x100):
        _, culled = step_x_4898(x, 0, 0)
        if not culled:
            fail(f"4898 must clear X={x:#x} (>= 0xD1)")
            fails += 1
        _, _, old = old_signed_then_playfield(x, 0x80, 0, 0, 0, 0)
        if old:
            fail(f"old playfield cull must keep X={x:#x} (<= 256)")
            fails += 1
    print("  sim: X=0xD1..0xFF clears on 4898; old playfield keeps")

    step = fn_span(ent, "static void tracker_step(Slot *e)")
    if not step:
        fail("tracker_step not found")
        fails += 1
    elif "ypos +=" in step or "s32 ypos" in step or "s32 xpos" in step:
        fail("tracker_step must not keep signed s32 X/Y")
        fails += 1
    elif re.search(r"e->y\s*>\s*max_y|e->x\s*>\s*max_x", step):
        fail("tracker_step must not invent a playfield cull")
        fails += 1
    elif "step_88_y_4898" not in step:
        fail("tracker_step +0c=1 must use step_88_y_4898")
        fails += 1
    elif "(u8)e->x >= 0xD1" not in step:
        fail("tracker_step +0c=2 must unsigned-cull X>=0xD1")
        fails += 1
    elif "(u8)((u8)e->x)" not in step and "((u8)e->x)" not in step:
        fail("tracker_step X add must be unsigned u8 8.8")
        fails += 1
    elif "0x0B" in step or "sib->x" in step:
        fail("tracker_step (7f84) must not grow a merge")
        fails += 1
    else:
        print("  tracker_step: Y step_88_y_4898 / X u8 wrap X>=0xD1")

    # Y-then-X stay. XOR +04 0x06 stay.
    if step:
        if "e->clock & 0x40" not in step:
            fail("tracker BIT6 sense was reverted")
            fails += 1
        elif "e->clock & (u8)~3) | 2" not in step:
            fail("tracker +0c=2 switch was reverted")
            fails += 1
        elif "e->sat_col ^ 0x06" not in step:
            fail("tracker 7f73 XOR 0x06 was reverted")
            fails += 1
        else:
            print("  KEEP: tracker Y-then-X / BIT6 / XOR 0x06")

    spawn = fn_span(ent, "static void spawn_tracker(Slot *e, u8 type)")
    if not spawn:
        fail("spawn_tracker not found")
        fails += 1
    elif "e->bind = 0x0200" not in spawn:
        fail("spawn_tracker must keep Yvel 8.8 0x0200")
        fails += 1
    elif "e->clock = 0x01" not in spawn:
        fail("spawn_tracker must keep +0c=1 Y-then-X")
        fails += 1
    elif "apply_dir_88(e, k_stealth_dir[si], 1)" not in spawn:
        fail("spawn_tracker must keep 807c dir speed 1")
        fails += 1
    elif "e->y = 0" not in spawn:
        fail("spawn_tracker must keep leftover Y=0")
        fails += 1
    else:
        print("  spawn_tracker: Y=0 bind=0x0200 +0c=1 807c dir")

    gs_spawn = fn_span(ent, "static void spawn_gswoop(Slot *e, u8 type)")
    if not gs_spawn:
        fail("spawn_gswoop not found")
        fails += 1
    elif "c->kind = KIND_TRACKER" not in gs_spawn:
        fail("gswoop child must stay KIND_TRACKER")
        fails += 1
    elif "e->y = 0xD0" not in gs_spawn or "e->bind = 0xFF00" not in gs_spawn:
        fail("type32 rise Y=0xD0 / Yvel FF00 was reverted")
        fails += 1
    elif "c->dest = (type == 30) ? 0xFE80 : 0xFF00" not in gs_spawn:
        fail("gswoop child Xvel FE80/FF00 was reverted")
        fails += 1
    else:
        print("  KEEP: gswoop child KIND_TRACKER type32 Y=0xD0 FF00")

    upd = fn_span(ent, "static void update_enemies(void)")
    if not upd:
        fail("update_enemies not found")
        fails += 1
    else:
        if "e->kind != KIND_TRACKER" not in upd:
            fail("KIND_TRACKER must be excluded from playfield max_y cull")
            fails += 1
        else:
            print("  update_enemies: KIND_TRACKER excluded from max_y cull")
        if not re.search(
            r"else if \(e->kind == KIND_TRACKER\)\s*\{\s*"
            r"tracker_step\(e\);\s*"
            r"if \(!e->alive\)\s*continue;",
            upd,
        ):
            fail("KIND_TRACKER must continue after 4898 clear")
            fails += 1
        else:
            print("  update_enemies: tracker_step then continue if dead")
        if "tracker 31/33" not in upd:
            fail("cull comment must list tracker 31/33 with 4898 wrap set")
            fails += 1
        else:
            print("  update_enemies: tracker 31/33 in 4898 wrap set")
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
        if "4898 Y-only 36/61/62/72/83" not in upd:
            fail("cull comment must keep type 36 with 61/62/72/83")
            fails += 1
        else:
            print("  update_enemies: type 36 still in 4898 Y-only set")
        # KIND_TRACKER is an extra != term before KIND_SWOOP.
        # The swoop/veybar/umber/ebullet grouping must stay intact:
        # && KIND_SWOOP && KIND_VEYBAR && KIND_UMBER && !(KIND_EBULLET && variants)
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
        print("  step_88_4898: unsigned Y>=0xD0 / X>=0xD1")

    y4898 = fn_span(ent, "static int step_88_y_4898(Slot *e)")
    if not y4898 or "(u8)e->y >= 0xD0" not in y4898:
        fail("step_88_y_4898 must still unsigned-cull Y>=0xD0")
        fails += 1
    else:
        print("  step_88_y_4898: unsigned Y>=0xD0")

    swoop = fn_span(ent, "static void swoop_step(Slot *e)")
    if not swoop or "step_88_4898" not in swoop:
        fail("swoop 26-29 4898 stay was reverted")
        fails += 1
    else:
        print("  KEEP: swoop_step step_88_4898")

    if upd and "e->kind != KIND_SWOOP" not in upd:
        fail("KIND_SWOOP playfield-cull exclude was reverted")
        fails += 1
    else:
        print("  KEEP: KIND_SWOOP excluded from playfield cull")

    vey = fn_span(ent, "static void veybar_step(Slot *e)")
    if not vey or "step_88_4898" not in vey or "step_88_y_4898" not in vey:
        fail("veybar 22-25 4898 stay was reverted")
        fails += 1
    else:
        print("  KEEP: veybar_step x_on ? step_88_4898 : step_88_y_4898")

    if upd and "e->kind != KIND_VEYBAR" not in upd:
        fail("KIND_VEYBAR playfield-cull exclude was reverted")
        fails += 1
    else:
        print("  KEEP: KIND_VEYBAR excluded from playfield cull")

    umber = fn_span(ent, "static void umber_step(Slot *e)")
    if not umber or "step_88_y_4898" not in umber:
        fail("umber 7/8/9 4898 stay was reverted")
        fails += 1
    else:
        print("  KEEP: umber_step step_88_y_4898")

    if upd and "e->kind != KIND_UMBER" not in upd:
        fail("KIND_UMBER playfield-cull exclude was reverted")
        fails += 1
    else:
        print("  KEEP: KIND_UMBER excluded from playfield cull")

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

    if "mode_letter_attr" in ent:
        fail("entity.c must not grow a playfield-wide mode_letter_attr fill")
        fails += 1
    else:
        print("  KEEP: no playfield-wide mode_letter_attr")

    if "dma_nt_row" not in mapc:
        fail("dma_nt_row HUD restore was reverted")
        fails += 1
    else:
        print("  KEEP: dma_nt_row HUD BG_B restore")

    vals = parse_spawn_list(spawn_src)
    if vals:
        for t, name in ((21, "21"), (41, "41"), (45, "45")):
            if t in vals:
                fail(f"spawn_type_list must keep type {name} child-only")
                fails += 1
            else:
                print(f"  KEEP: type {name} child-only")
        if 30 not in vals:
            fail("spawn_type_list must still include type 30 (tracker parent)")
            fails += 1
        else:
            print("  spawn_type_list still includes type 30")
        for t in (26, 27, 28, 29):
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

    # Leftover same-class CALL (one-PR: do not ship).
    pair = fn_span(ent, "static void pairdesc_step(Slot *e)")
    if not pair:
        fail("pairdesc_step not found")
        fails += 1
    elif "ypos +=" not in pair:
        fail("one-PR: pairdesc leftover signed s32 should remain")
        fails += 1
    else:
        print("  leftover: pairdesc_step still signed s32 (81cb, not this PR)")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
