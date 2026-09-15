#!/usr/bin/env python3
"""Type 65 first volley 7ff0: +0D reload 0x20, +1D stays 0x30.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  7fc9  LD (IX+0x0d), 0x30     ; reload
  7fcd  LD (IX+0x1d), 0x30     ; first countdown
  ...
  7fe8  CP 0xc1                ; type 65 (running bit set)
  7fec  LD (IX+0x04), 0x85
  7ff0  LD (IX+0x0d), 0x20     ; reload ONLY
  7ff4  LD (IX+0x1e), 0x01
  7ff8  LD (IX+0x1f), 0x14
  7ffc  LD (IX+0x19), 0x04
  8000  JR 0x8012              ; same-frame DEC; no +1D write
  8012  DEC (IX+0x1d)
  8015  JR NZ, 0x8073
  8017  LD A,(IX+0x0d)         ; reload from +0D
  801a  LD (IX+0x1d), A

  Type 65 never writes +1D on the 7fec-8000 patch.
  First lead (type 20) after 48 DEC-Z ticks; later volleys every 32.

  Old port: e->clock = (type == 65) ? 32 : 48
  seeded +0D instead of +1D. First type-20 ~16 frames early.

Usage (from zanac-md):
    python tools/test_type65_7ff0.py
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


def port_ifelse_first_fire(clock0: int, period: int, frames: int = 80) -> int | None:
    """Port stealth_step: if(clock)--; else { clock=period; fire }.

    spawn_tick then update_enemies means frame 0 already DECs.
    """
    clock = clock0
    for f in range(frames):
        if clock:
            clock -= 1
        else:
            return f
    return None


def msx_decz_first_fire(clock0: int, frames: int = 80) -> int | None:
    """MSX: spawn frame no handler; next frame init+DEC-Z from clock0."""
    clock = clock0
    for f in range(frames):
        if f == 0:
            continue
        clock = (clock - 1) & 0xFF
        if clock == 0:
            return f
    return None


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8", errors="replace")
    ply = PLAYER.read_text(encoding="utf-8", errors="replace")
    hdr = PLAYER_H.read_text(encoding="utf-8", errors="replace")
    mapc = MAPC.read_text(encoding="utf-8", errors="replace")
    spawn_src = SPAWN.read_text(encoding="utf-8", errors="replace")
    asm = load_asm()

    if asm:
        if not re.search(r"LD\s+\(IX\+0x0d\),\s*0x30\s*;\s*0x7fc9", asm, re.I):
            fail("zanac.asm 7fc9 is not LD (IX+0x0d), 0x30")
            fails += 1
        else:
            print("  ASM 7fc9: +0D reload = 0x30")
        if not re.search(r"LD\s+\(IX\+0x1d\),\s*0x30\s*;\s*0x7fcd", asm, re.I):
            fail("zanac.asm 7fcd is not LD (IX+0x1d), 0x30")
            fails += 1
        else:
            print("  ASM 7fcd: +1D first countdown = 0x30")
        if not re.search(r"CP\s+0xc1\s*;\s*0x7fe8", asm, re.I):
            fail("zanac.asm 7fe8 is not CP 0xC1 (type 65)")
            fails += 1
        else:
            print("  ASM 7fe8: CP 0xC1 type 65")
        if not re.search(r"LD\s+\(IX\+0x0d\),\s*0x20\s*;\s*0x7ff0", asm, re.I):
            fail("zanac.asm 7ff0 is not LD (IX+0x0d), 0x20")
            fails += 1
        else:
            print("  ASM 7ff0: type 65 +0D reload = 0x20")
        if re.search(r"LD\s+\(IX\+0x1d\),\s*0x20\s*;\s*0x7ff", asm, re.I):
            fail("type 65 7ff0 patch must not write +1D = 0x20")
            fails += 1
        else:
            print("  ASM 7ff0: no +1D write (stays 0x30)")
        if not re.search(r"JR\s+0x8012\s*;\s*0x8000", asm, re.I):
            fail("zanac.asm 8000 is not JR 8012")
            fails += 1
        else:
            print("  ASM 8000: JR 8012 same-frame DEC")
        if not re.search(r"DEC\s+\(IX\+0x1d\)\s*;\s*0x8012", asm, re.I):
            fail("zanac.asm 8012 is not DEC (IX+0x1d)")
            fails += 1
        else:
            print("  ASM 8012: DEC +1D")
        if not re.search(r"LD\s+A,\s*\(IX\+0x0d\)\s*;\s*0x8017", asm, re.I):
            fail("zanac.asm 8017 is not LD A,(IX+0x0d)")
            fails += 1
        else:
            print("  ASM 8017: reload +1D from +0D")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    # Frame math: seed 48 + if/else first fire == MSX DEC-Z first fire.
    msx_first = msx_decz_first_fire(48)
    new_first = port_ifelse_first_fire(48, 32)
    old_first = port_ifelse_first_fire(32, 32)
    if msx_first != 48:
        fail(f"MSX DEC-Z first fire {msx_first} want 48")
        fails += 1
    elif new_first != 48:
        fail(f"port seed-48 first fire {new_first} want 48")
        fails += 1
    elif old_first != 32:
        fail(f"old seed-32 first fire {old_first} want 32 (sanity)")
        fails += 1
    else:
        print("  first volley: seed 48 -> frame 48 (old seed 32 was frame 32)")

    spawn = fn_span(ent, "static void spawn_stealth(Slot *e, u8 type)")
    if not spawn:
        fail("spawn_stealth not found")
        fails += 1
    elif re.search(r"e->clock\s*=\s*\(type\s*==\s*65\)\s*\?\s*32", spawn):
        fail("type 65 must not seed clock from +0D (7ff0 is reload only)")
        fails += 1
    elif "e->clock = 48" not in spawn:
        fail("spawn_stealth must seed clock=+1D 0x30 for all stealth types")
        fails += 1
    elif "e->clock = 32" in spawn:
        fail("spawn_stealth must not write clock=32 (that is +0D reload)")
        fails += 1
    else:
        print("  spawn_stealth: clock=48 (+1D stays 0x30)")

    if spawn and "k_stealth_dir[si]" not in spawn:
        fail("spawn_stealth must keep 807C dir[0]=2 via k_stealth_dir")
        fails += 1
    else:
        print("  KEEP: stealth dir[0]=2")

    step = fn_span(ent, "static void stealth_step(Slot *e)")
    if not step:
        fail("stealth_step not found")
        fails += 1
    elif '(e->variant == 65) ? 32 : 48' not in step:
        fail("stealth_step must reload +0D 0x20 for type 65, 0x30 else")
        fails += 1
    elif "spawn_lead20" not in step:
        fail("type 65 volley must stay spawn_lead20")
        fails += 1
    else:
        print("  stealth_step: type 65 reload 32 (+0D); 34/66 stay 48")

    vals = parse_spawn_list(spawn_src)
    if vals:
        if 65 not in vals:
            fail("spawn_type_list must include type 65 (0x41)")
            fails += 1
        else:
            print("  spawn_type_list: type 65 live")
        for t, name in ((21, "21"), (41, "41"), (45, "45")):
            if t in vals:
                fail(f"spawn_type_list must keep type {name} child-only")
                fails += 1
            else:
                print(f"  KEEP: type {name} child-only")

    # KEEP: E140 wrap just shipped.
    shot = fn_span(ent, "bool entity_spawn_shot(s16 x, s16 y)")
    if not shot or "s_alc_shots++" not in shot:
        fail("E140 76e8 wrap was reverted")
        fails += 1
    elif re.search(r"s_alc_shots\s*<\s*255", shot):
        fail("E140 must not saturate at 255")
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

    rst = fn_span(ply, "static void fire_reset(void)")
    if not rst or "s_e14f = 0" not in rst or "fire_select(0)" not in rst:
        fail("fire_reset 7544 E14F wipe was reverted")
        fails += 1
    else:
        print("  KEEP: fire_reset 7544 zeroes E14F then fire_select(0)")

    add = fn_span(ply, "void player_add_shot_level(void)")
    if not add or "fire_reset" in add or "fire_select(s_fire_num)" not in add:
        fail("78f2 must stay fire_select(E14B)")
        fails += 1
    else:
        print("  KEEP: 78f2 overflow still fire_select(E14B)")

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

    init = fn_span(ent, "static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)")
    if not init or "variant != 21" not in init:
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
            print("  KEEP: k_stealth_dir [2, 6, 4, 4]")

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
