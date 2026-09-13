#!/usr/bin/env python3
"""Type 61 ship-ram death gate, dest-0 40D6, respawn keeps E13F/E110.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  handler_type61 0x8368:
    CALL 0x44BA                 ; ship then shots (44D4 / 44F9)
    LD A,(IX+00) / CP 0x23 / RET NZ
    CALL 0xBFB3                 ; dec E12E
    LD A,(E140) / AND 0x3F
    LD A,(E103) / AND 0x3F / CP B
    JR NZ,838A
    CALL 0x4A6A / LD (IX+00),0x3E / RET   ; type 62
    LD HL,E148 / CP 05 / RET C
    CALL 0x4A6A / LD (IX+00),0x53         ; type 83
    LD A,(IX+1D) / LD (IX+1C),A / RET

  44BA remaps a ship ram to 0x23; the same visit still runs 8371-839E.
  Port shot path already called descender_on_death; ship CLS_EXPL used
  to become_expl only and skip the gate / one E12E decrement.

  level_complete 0x40DA:
    CALL 0x40BA                 ; 40D6 LD (E132),A only (A=0)
    E722==0 JP 414d             ; then E132 += 0x20 -> 0x20
  Dest 0 must 40D6-zero E132 before 414d. Do not wipe E12E (KEEP 40DA
  still alc_reset on script_boot / arm_ending).

  player_ship_handler 0x75D5 first frame:
    7544 / E10B=0 / E130=0 / 7771. No store to E13F or E110.
  Those freeze while the slot is type 60. player_init still zeros them.

Usage (from zanac-md):
    python tools/test_type61_ship_ram_alc.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTITY = ROOT / "src" / "entity.c"
ENTITY_H = ROOT / "inc" / "entity.h"
PLAYER = ROOT / "src" / "player.c"
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


def brace_after(src: str, needle: str) -> str | None:
    m = re.search(needle, src)
    if not m:
        return None
    i = src.find("{", m.end() - 1)
    if i < 0:
        return None
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i : j + 1]
    return None


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8", errors="replace")
    eh = ENTITY_H.read_text(encoding="utf-8", errors="replace")
    ply = PLAYER.read_text(encoding="utf-8", errors="replace")
    mapc = MAPC.read_text(encoding="utf-8", errors="replace")
    asm = load_asm()

    if asm:
        if not re.search(r"CALL\s+0x44ba\s*;\s*0x8368", asm, re.I):
            fail("zanac.asm 8368 is not CALL 44BA")
            fails += 1
        else:
            print("  ASM 8368: type 61 CALL 44BA (ship then shots)")
        if not re.search(r"CALL\s+0xbfb3\s*;\s*0x8371", asm, re.I):
            fail("zanac.asm 8371 is not CALL BFB3")
            fails += 1
        else:
            print("  ASM 8371: BFB3 after remap to 0x23")
        if not re.search(r"LD\s+A,\s*\(0xe140\)\s*;\s*0x8374", asm, re.I):
            fail("zanac.asm 8374 is not LD A,(E140)")
            fails += 1
        else:
            print("  ASM 8374: score gate vs E140")
        if not re.search(r"LD\s+HL,\s*0xe148\s*;\s*0x838a", asm, re.I):
            fail("zanac.asm 838A is not LD HL,E148")
            fails += 1
        else:
            print("  ASM 838A: E148>=5 fire-up")
        if not re.search(r"LD\s+\(0xe132\),\s*A\s*;\s*0x40d6", asm, re.I):
            fail("zanac.asm 40D6 is not LD (E132),A")
            fails += 1
        else:
            print("  ASM 40D6: reset_entities zeros E132 only")
        if not re.search(r"JP\s+Z,\s*0x414d\s*;\s*0x40e2", asm, re.I):
            fail("zanac.asm 40E2 is not JP Z,414d")
            fails += 1
        else:
            print("  ASM 40E2: dest 0 still 414d")
        if not re.search(r"LD\s+\(0xe10b\),\s*A\s*;\s*0x7603", asm, re.I):
            fail("zanac.asm 7603 is not LD (E10B),A")
            fails += 1
        else:
            print("  ASM 7603: spawn zeros E10B")
        if not re.search(r"LD\s+\(0xe130\),\s*A\s*;\s*0x7606", asm, re.I):
            fail("zanac.asm 7606 is not LD (E130),A")
            fails += 1
        else:
            print("  ASM 7606: spawn zeros E130")
        first = re.search(
            r"player_ship_handler:[\s\S]{0,700}player_ship_update:",
            asm,
        )
        if not first:
            fail("zanac.asm player_ship_handler first-frame span missing")
            fails += 1
        elif re.search(r"0xe13f|0xe110", first.group(0), re.I):
            fail("75D5 first frame must not store E13F or E110")
            fails += 1
        else:
            print("  ASM 75D5: no E13F / E110 store on spawn")
    else:
        print("  (no zanac.asm; ASM checks skipped)")

    gate = fn_span(ent, "static int descender_on_death(Slot *e)")
    if not gate or "(s_alc_shots & 0x3F) == (player_score_lo() & 0x3F)" not in gate:
        fail("descender_on_death must keep 8374 score gate")
        fails += 1
    elif "player_e148() >= 5" not in gate:
        fail("descender_on_death must keep 838A E148>=5")
        fails += 1
    elif "entity_dec_encounter_a" not in gate:
        fail("descender_on_death must CALL BFB3 first")
        fails += 1
    else:
        print("  descender_on_death: BFB3 + 8374 + 838A")

    collide = fn_span(ent, "static void collide_player(void)")
    expl = brace_after(collide or "", r"else if \(cls == CLS_EXPL\)")
    if not expl:
        fail("collide_player CLS_EXPL arm missing")
        fails += 1
    elif "KIND_DESCEND" not in expl or "descender_on_death" not in expl:
        fail("ship ram CLS_EXPL must descender_on_death for KIND_DESCEND")
        fails += 1
    elif "become_expl(e, 61)" not in expl:
        fail("ship ram gate miss must become_expl(e, 61)")
        fails += 1
    else:
        print("  collide_player CLS_EXPL: type 61 still runs 8371 gate")

    shot = fn_span(ent, "static void collide_bolt_enemies(Slot *bolt, u8 persist)")
    if not shot or "KIND_DESCEND" not in shot or "descender_on_death" not in shot:
        fail("shot path must still descender_on_death")
        fails += 1
    else:
        print("  shot path: type 61 gate still live")

    zero = fn_span(ent, "void entity_alc_zero_e132(void)")
    if not zero or "s_e132 = 0" not in zero:
        fail("entity_alc_zero_e132 must assign s_e132 = 0")
        fails += 1
    elif "s_spawn_pos_hi" in zero or "s_e131" in zero:
        fail("40D6 must not wipe E12E/E12F/E131")
        fails += 1
    else:
        print("  entity_alc_zero_e132: E132 only")

    if "void entity_alc_zero_e132(void)" not in eh:
        fail("entity.h must declare entity_alc_zero_e132")
        fails += 1
    else:
        print("  entity.h: entity_alc_zero_e132")

    complete = fn_span(ent, "void entity_alc_complete(void)")
    if not complete or "0x20" not in complete:
        fail("entity_alc_complete E132+=0x20 was reverted")
        fails += 1
    else:
        print("  KEEP: entity_alc_complete E132+=0x20")

    warp = fn_span(mapc, "void map_script_warp(u16 dest)")
    dest0 = brace_after(warp or "", r"if \(!dest\)")
    if not dest0:
        fail("map_script_warp dest==0 arm missing")
        fails += 1
    elif "entity_alc_zero_e132" not in dest0:
        fail("dest==0 must 40D6-zero E132 before 414d")
        fails += 1
    elif "entity_alc_complete" not in dest0:
        fail("dest==0 must still LAB_414d entity_alc_complete")
        fails += 1
    elif "entity_alc_reset" in dest0:
        fail("dest==0 must not wipe E12E (alc_reset)")
        fails += 1
    else:
        print("  map_script_warp dest 0: 40D6 then 414d")

    resp = fn_span(ply, "static void respawn(void)")
    if not resp:
        fail("respawn not found")
        fails += 1
    elif "s_alc_cadence = 0" in resp or "s_shot_cd = 0" in resp:
        fail("respawn must leave E13F / E110 (75D5 has no store)")
        fails += 1
    elif "entity_zero_e130()" not in resp:
        fail("respawn must still entity_zero_e130 (7606)")
        fails += 1
    elif "s_shot_level = 0" not in resp:
        fail("respawn must still zero E10B (7603)")
        fails += 1
    elif "fire_reset()" not in resp:
        fail("respawn must still fire_reset (75ff)")
        fails += 1
    else:
        print("  respawn: keep E13F/E110; still 7603/7606/7544")

    init = fn_span(ply, "void player_init(void)")
    if not init or "s_alc_cadence = 0" not in init or "s_shot_cd = 0" not in init:
        fail("player_init must still zero E13F / E110 (title 4215)")
        fails += 1
    else:
        print("  player_init: still zeros E13F / E110")

    # KEEP: 40DA wipe on script_boot / ending; cmd 9 never resets.
    boot = fn_span(mapc, "static void script_boot(u8 round, u16 pc)")
    if not boot or "entity_alc_reset" not in boot:
        fail("script_boot must still entity_alc_reset (KEEP 40DA)")
        fails += 1
    elif "entity_alc_complete" in boot:
        fail("script_boot must not bake +0x20")
        fails += 1
    else:
        print("  KEEP: script_boot still alc_reset, no +0x20")

    ending = fn_span(mapc, "static void arm_ending_stream(void)")
    if not ending or "entity_alc_reset" not in ending:
        fail("arm_ending_stream must still entity_alc_reset")
        fails += 1
    else:
        print("  KEEP: arm_ending_stream still alc_reset")

    jump = fn_span(mapc, "static void cmd_script_jump(u8 cmd, const u8 *ops)")
    if not jump:
        fail("cmd_script_jump not found")
        fails += 1
    elif "entity_alc_reset" in jump or "entity_alc_complete" in jump:
        fail("cmd 9 must still never alc_reset / alc_complete")
        fails += 1
    else:
        print("  KEEP: cmd 9 no alc_reset")

    write = fn_span(mapc, "static void write_e701(u8 round)")
    if not write or "s_continue_round = round" not in write:
        fail("write_e701 must copy 0..8 into s_continue_round")
        fails += 1
    else:
        print("  KEEP: write_e701 stores 0..8")

    clr = fn_span(mapc, "static void bonus_clear(void)")
    if not clr or "hud_fill_tile(BG_A, 6, mode_text_row(11), 0, 12)" not in clr:
        fail("bonus_clear must wipe 12 BG_A tiles at col 6 row 11 with tile 0")
        fails += 1
    else:
        print("  KEEP: BONUS clear tile 0")

    if "s_warp_jwait = 0x64" not in mapc:
        fail("40DA wait_frames 0x64 was reverted")
        fails += 1
    else:
        print("  KEEP: 40DA wait 0x64")

    rst = fn_span(ply, "static void fire_reset(void)")
    if not rst or "s_e14f = 0" not in rst or "fire_select(0)" not in rst:
        fail("fire_reset 7544 E14F wipe was reverted")
        fails += 1
    else:
        print("  KEEP: fire_reset 7544")

    sel = fn_span(ply, "static void fire_select(u8 n)")
    if not sel or "s_e14f" in sel:
        fail("7548 fire_select must not touch E14F")
        fails += 1
    else:
        print("  KEEP: fire_select is 7548")

    if "0x47AA" not in mapc and "0x47aa" not in mapc:
        fail("credits 47AA skip-N was reverted")
        fails += 1
    else:
        print("  KEEP: credits 47AA")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
