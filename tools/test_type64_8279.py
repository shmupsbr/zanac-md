#!/usr/bin/env python3
"""Type 64 8279 re-rolls a 64 lookup; does not invent force-44.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  handler_type64_proto_structure 0x8279:
    LD A,(E130) / SRL A / LD E,A
    LD A,R / AND 0x03 / ADD A,E
    CP 0x60 / JR C,828a / LD A,0x5F
    HL = 0xBECC+A / LD A,(HL) / LD (IX+00),A / RET

  0xBECC has 0x40 at idx 0, 23, 51. A 64 result leaves the slot as type 64
  so the same handler runs next frame. Windows:

    E130>>1 ==  0 -> 64, 44, 44, 44
    E130>>1 == 23 -> 64, 18, 24, 16
    E130>>1 == 51 -> 64, 58, 28, 23

  Force-44 on a 64 lookup substitutes a plane for 18/24/16/58/28/23.
  Port has no persistent type-64 slot (same-frame convert already). Re-roll
  until the byte is not 64 matches the eventual MSX type.

  Types 21/41/45 stay child-only in spawn_type_list.

Usage (from zanac-md):
    python tools/test_type64_8279.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTITY = ROOT / "src" / "entity.c"
SPAWN = ROOT / "src" / "data" / "spawn_table.c"
MAPC = ROOT / "src" / "map_script.c"
PLAYER = ROOT / "src" / "player.c"
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
    vals = [int(x, 0) for x in re.findall(r"0x[0-9A-Fa-f]+|\d+", m.group(1))]
    return vals


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8")
    spawn = SPAWN.read_text(encoding="utf-8")
    mapc = MAPC.read_text(encoding="utf-8")
    ply = PLAYER.read_text(encoding="utf-8")

    vals = parse_spawn_list(spawn)
    if not vals or len(vals) < 96:
        fail("spawn_type_list missing or short")
        return 1
    if vals[0] != 0x40 or vals[23] != 0x40 or vals[51] != 0x40:
        fail(f"0xBECC 0x40 slots: [0]={vals[0]:#x} [23]={vals[23]:#x} [51]={vals[51]:#x}")
        fails += 1
    else:
        print("  spawn_type_list: 0x40 at idx 0/23/51")
    if vals[1:4] != [0x2C, 0x2C, 0x2C]:
        fail(f"idx 1-3 must be 44,44,44 not {vals[1:4]}")
        fails += 1
    else:
        print("  window 0: 64, 44, 44, 44")
    if vals[24:27] != [0x12, 0x18, 0x10]:
        fail(f"idx 24-26 must be 18,24,16 not {vals[24:27]}")
        fails += 1
    else:
        print("  window 23: 64, 18, 24, 16")
    if vals[52:55] != [0x3A, 0x1C, 0x17]:
        fail(f"idx 52-54 must be 58,28,23 not {vals[52:55]}")
        fails += 1
    else:
        print("  window 51: 64, 58, 28, 23")

    # Child-only KEEP: 21/41/45 must not appear in the table.
    for t, name in ((21, "21"), (41, "41"), (45, "45")):
        if t in vals:
            fail(f"spawn_type_list must keep type {name} child-only")
            fails += 1
        else:
            print(f"  KEEP: type {name} child-only in spawn_type_list")

    asm = load_asm()
    if asm:
        if not re.search(r"handler_type64_proto_structure:", asm):
            fail("zanac.asm missing handler_type64_proto_structure")
            fails += 1
        else:
            print("  ASM: handler_type64_proto_structure")
        if not re.search(r"LD\s+A,\s*\(0xe130\)\s*;\s*0x8279", asm, re.I):
            fail("zanac.asm 8279 is not LD A,(E130)")
            fails += 1
        else:
            print("  ASM 8279: LD A,(E130)")
        if not re.search(r"SRL\s+A\s*;\s*0x827c", asm, re.I):
            fail("zanac.asm 827c is not SRL A")
            fails += 1
        else:
            print("  ASM 827c: SRL A")
        if not re.search(r"LD\s+A,\s*R\s*;\s*0x827f", asm, re.I):
            fail("zanac.asm 827f is not LD A,R")
            fails += 1
        else:
            print("  ASM 827f: LD A,R")
        if not re.search(r"AND\s+0x03\s*;\s*0x8281", asm, re.I):
            fail("zanac.asm 8281 is not AND 0x03")
            fails += 1
        else:
            print("  ASM 8281: AND 0x03")
        if not re.search(r"CP\s+0x60\s*;\s*0x8284", asm, re.I):
            fail("zanac.asm 8284 is not CP 0x60")
            fails += 1
        else:
            print("  ASM 8284: CP 0x60 clamp")
        if not re.search(r"LD\s+HL,\s*0xbecc\s*;\s*0x828d", asm, re.I):
            fail("zanac.asm 828d is not LD HL,0xBECC")
            fails += 1
        else:
            print("  ASM 828d: HL = 0xBECC")
        if not re.search(r"LD\s+\(IX\+0x00\),\s*A\s*;\s*0x8292", asm, re.I):
            fail("zanac.asm 8292 is not LD (IX+00),A")
            fails += 1
        else:
            print("  ASM 8292: write type, RET (retry if 64)")
        # Table bytes at 0xBECC / 0xBEE3 / 0xBEFF.
        if not re.search(
            r"0x40,\s*0x2[Cc],\s*0x2[Cc],\s*0x2[Cc].*0xbecc",
            asm,
            re.I,
        ) and "0x40, 0x2C, 0x2C, 0x2C" not in asm.replace("\t", " "):
            # extract_map_scripts dumps C; asm listing may be DB form.
            if not re.search(r"DB\s+0x40,\s*0x2c,\s*0x2c,\s*0x2c", asm, re.I):
                print("  (asm 0xBECC listing form not matched; C table locked)")
            else:
                print("  ASM 0xBECC: 40 2C 2C 2C")
        else:
            print("  ASM 0xBECC: 40 2C …")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    conv = fn_span(ent, "static int spawn_from_type(u8 t)")
    if not conv:
        fail("spawn_from_type not found")
        return 1
    t64 = re.search(r"if \(t == 64\)\s*\{(.*?)\n    \}", conv, re.S)
    if not t64:
        fail("spawn_from_type(64) block missing")
        return 1
    body = t64.group(1)
    if re.search(
        r"nt = spawn_type_list\[idx\];\s*\n\s*if \(nt == 64 \|\| !is_port_type\(nt\)\)\s*\n\s*nt = 44;",
        body,
    ):
        fail("spawn_from_type(64) still force-44 on the first 64 lookup")
        fails += 1
    elif "while (nt == 64" not in body and "while (nt == 64 &&" not in body:
        fail("spawn_from_type(64) must re-roll while the lookup is 64")
        fails += 1
    else:
        print("  spawn_from_type(64): re-roll until byte != 64")
    if "rnd() & 3" not in body:
        fail("8279 jitter must still be R&3")
        fails += 1
    else:
        print("  spawn_from_type(64): E130/2 + R&3")
    if "0x5F" not in body:
        fail("8279 clamp 0x5F missing")
        fails += 1
    else:
        print("  spawn_from_type(64): clamp 0x5F")

    # KEEP: type 21 8659; init 863b no +04; lead discs stay 0x8F white
    # (no 8659 / no CRAM). Type 45 stays 0x8F size-pulse.
    if not re.search(
        r"e->variant == 21\)\s*\n\s*spr_set_sat_col\(\s*e,\s*"
        r"\(u8\)\(0x80\s*\|\s*\(rnd\(\)\s*&\s*0x0F\)\)\)",
        ent,
    ):
        fail("type 21 8659 was reverted")
        fails += 1
    else:
        print("  KEEP: type 21 8659 R-nibble|0x80")
    init = fn_span(ent, "static void init_frag(Slot *e, s16 x, s16 y, u8 dir, u8 variant)")
    if not init or "variant != 21" not in init:
        fail("init_frag type 21 no +04 (863b) was reverted")
        fails += 1
    else:
        print("  KEEP: type 21 init still no +04")
    if len(re.findall(
        r"if \(e->variant == 21\)\s*\n\s*spr_set_sat_col\(\s*e,\s*"
        r"\(u8\)\(0x80\s*\|\s*\(rnd\(\)\s*&\s*0x0F\)\)\)",
        ent,
    )) != 1:
        fail("type 21 8659 must stay a single write")
        fails += 1
    elif re.search(
        r"if \(e->variant == 45\)\s*\n\s*spr_set_sat_col\(\s*e,\s*"
        r"\(u8\)\(0x80\s*\|\s*\(rnd\(\)\s*&\s*0x0F\)\)\)",
        ent,
    ):
        fail("do not apply 8659 to type 45 (size pulse, colour 0x8F)")
        fails += 1
    elif re.search(
        r"ebullet_lead_disc\(\s*e\s*\)\s*\)\s*\n\s*spr_set_sat_col\(\s*e,\s*"
        r"\(u8\)\(0x80\s*\|\s*\(rnd\(\)\s*&\s*0x0F\)\)\)",
        ent,
    ) and "options_bullet_high" not in ent:
        fail("lead discs must not 8659-walk in default (white lock)")
        fails += 1
    else:
        print("  KEEP: type 21 8659; lead discs white; type 45 no 8659")

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

    if "player_fireup_latch" not in ply:
        fail("KIND_FIREUP player_fireup_latch was reverted")
        fails += 1
    else:
        latch = fn_span(ply, "void player_fireup_latch(void)")
        if not latch or "s_invuln = 0" not in latch or "s_if_latch = 1" not in latch:
            fail("player_fireup_latch must be +1B=0 + SET 7")
            fails += 1
        else:
            print("  KEEP: player_fireup_latch +1B=0 + SET 7")

    if "player_grant_iframes" not in ply:
        fail("chip 78d0 i-frames was reverted")
        fails += 1
    else:
        print("  KEEP: chip/spawn SET latch + +1B=0x40")

    if "0xBFD6" in ent or "0xbfd6" in ent:
        fail("must not CALL 0xBFD6")
        fails += 1
    else:
        print("  KEEP: no 0xBFD6")

    if "e->sat_col = 0x89" not in ent:
        fail("type 10 sat_col 0x89 was reverted")
        fails += 1
    else:
        print("  KEEP: type 10 sat_col 0x89")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
