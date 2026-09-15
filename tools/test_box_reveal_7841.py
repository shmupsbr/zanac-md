#!/usr/bin/env python3
"""Box reveal 7841 writes +08=0xC0 only (Yvel 8.8 00C0).

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  handler_type4_box 0x7826 (types 4/5/6 share):
    BIT 7,(IX+00) / JR NZ,784d
    DEC (IX+03) / RET NZ
    CALL 71da / (HL)=0xD8
    +19=5 / +03=0xD4 / +04=0x8F
    7841  LD (IX+0x08), 0xC0     ; vy_frac only
    7845  LD (IX+0x0c), 0x01     ; Y-motion
    SET 7,(IX+00) / CALL 4898

  Reveal never writes +09. entity_clear 48d0 zeros +00..+17;
  cold 42AF zeros the 0x20-byte slots; stream BF79 writes type into
  a type-0 slot. Leftover +09 is 0 → Yvel 8.8 = 0x00C0 (0.75 px/frame).

  Old port invented bind=0x01C0 (1.75 px/frame) — ~2.3× too fast.

  Type 64 8279 re-roll and type 21 8659 stay. Types 21/41/45 child-only.

Usage (from zanac-md):
    python tools/test_box_reveal_7841.py
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
    return [int(x, 0) for x in re.findall(r"0x[0-9A-Fa-f]+|\d+", m.group(1))]


def main() -> int:
    fails = 0
    ent = ENTITY.read_text(encoding="utf-8")
    spawn = SPAWN.read_text(encoding="utf-8")
    mapc = MAPC.read_text(encoding="utf-8")
    ply = PLAYER.read_text(encoding="utf-8")

    asm = load_asm()
    if asm:
        if not re.search(r"handler_type4_box:", asm):
            fail("zanac.asm missing handler_type4_box")
            fails += 1
        else:
            print("  ASM: handler_type4_box")
        if not re.search(r"LD\s+\(IX\+0x08\),\s*0xc0\s*;\s*0x7841", asm, re.I):
            fail("zanac.asm 7841 is not LD (IX+08),0xC0")
            fails += 1
        else:
            print("  ASM 7841: LD (IX+08),0xC0")
        if not re.search(r"LD\s+\(IX\+0x0c\),\s*0x01\s*;\s*0x7845", asm, re.I):
            fail("zanac.asm 7845 is not LD (IX+0c),0x01")
            fails += 1
        else:
            print("  ASM 7845: +0c=1 Y-only")
        # Reveal 7826-7849 must not write +09 (integer Yvel).
        reveal = re.search(
            r"handler_type4_box:.*?CALL\s+0x4898\s*;\s*0x784d",
            asm,
            re.S | re.I,
        )
        if not reveal:
            fail("zanac.asm reveal span 7826-784d not found")
            fails += 1
        elif re.search(r"IX\+0x09", reveal.group(0), re.I):
            fail("7841 path must not write +09")
            fails += 1
        else:
            print("  ASM 7826-784d: no +09 write")
        if not re.search(r"LD\s+\(HL\),\s*0x00\s*;\s*0x48d3", asm, re.I):
            fail("zanac.asm 48d3 entity_clear type=0 missing")
            fails += 1
        else:
            print("  ASM 48d3: entity_clear zeros +00..+17")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    box = fn_span(ent, "static void box_step(Slot *e)")
    if not box:
        fail("box_step not found")
        return 1
    if "e->bind = 0x01C0" in box or "e->bind = 0x01c0" in box:
        fail("box_step still invents Yvel 0x01C0")
        fails += 1
    elif "e->bind = 0x00C0" not in box:
        fail("box_step must set bind=0x00C0 on reveal")
        fails += 1
    else:
        print("  box_step reveal: bind=0x00C0")
    if re.search(r"e->bind\s*=\s*0x01C0", ent):
        fail("entity.c still has invented box Yvel 0x01C0")
        fails += 1
    else:
        print("  entity.c: no leftover 0x01C0 box Yvel")

    spawn_box = fn_span(ent, "static void spawn_box(Slot *e, u8 type, s16 x, s16 y, u8 sat_cd)")
    if not spawn_box or "e->bind = 0" not in spawn_box:
        fail("spawn_box must still leave bind=0 until reveal")
        fails += 1
    else:
        print("  spawn_box: bind=0 until 7841")
    if not spawn_box or "spr_detach(e)" not in spawn_box:
        fail("spawn_box must spr_detach (not orphan spr=NULL)")
        fails += 1
    else:
        print("  spawn_box: spr_detach leftover SAT")
    if "if (!e->spr)" not in box or "spr_place(e, FRAME_BOX)" not in box:
        fail("box_step must retry spr_place after reveal if addSprite failed")
        fails += 1
    else:
        print("  box_step: retry spr_place when spr is NULL")

    # KEEP: type 64 re-roll, not force-44 on first 64.
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
        fail("spawn_from_type(64) force-44 on first 64 lookup")
        fails += 1
    elif "while (nt == 64" not in body:
        fail("spawn_from_type(64) must re-roll while lookup is 64")
        fails += 1
    else:
        print("  KEEP: type 64 8279 re-roll")

    vals = parse_spawn_list(spawn)
    if not vals or len(vals) < 96:
        fail("spawn_type_list missing or short")
        return 1
    if vals[0] != 0x40 or vals[23] != 0x40 or vals[51] != 0x40:
        fail("0xBECC 0x40 at idx 0/23/51 was changed")
        fails += 1
    else:
        print("  KEEP: table 0x40 at idx 0/23/51")
    for t, name in ((21, "21"), (41, "41"), (45, "45")):
        if t in vals:
            fail(f"spawn_type_list must keep type {name} child-only")
            fails += 1
        else:
            print(f"  KEEP: type {name} child-only")

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
