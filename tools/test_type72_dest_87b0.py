#!/usr/bin/env python3
"""Type 70/71 dest is E720[cursor] as-is; no R7->R8 rewrite.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  9654  LD A,(IX+0x1D) / LD (HL),A     ; stuff cursor into +0x03
  87b0  LD A,(IX+0x03) / LD C,A / B=0
  87b6  LD HL,(E720) / ADD HL,BC
  87ba  LD (IX+0x1C),A / INC HL / LD (IX+0x1D),A
  87c3  LD (IX+0x03),0x24
  8a05  LD L,(IX+0x1C) / LD H,(IX+0x1D) / LD (E722),HL / SET 5
  40E2  E722==0 -> 414d (skip stop/ev11/load)

  No CP E701 / no force 0xB7A5. Cmd 8 at R7 row 0x1E sets E720=0xB787.
  Table words (byte cursor; 9654 stuffs IX+0x1D then INC 1 or 2):
    +0  = 0x0000  (40DA skip)   +3/+0x0A = 0xB7A5 (R8)
    +6/+0x0C/+0x14 = 0xB61A (R7)

  Old port rewrote type 70/71 dest on round 7 when resolve was not 7/8,
  and map_script_warp invented 0xB7A5 when dest==0 on R7. Cursor 0
  therefore warped to R8; Japan stores 0x0000 and 40DA skips the load.

Usage (from zanac-md):
    python tools/test_type72_dest_87b0.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPC = ROOT / "src" / "map_script.c"
ENTITY = ROOT / "src" / "entity.c"
GAME = ROOT / "src" / "game.c"
HUD = ROOT / "src" / "hud.c"
MAIN = ROOT / "src" / "main.c"
BLOB = ROOT / "res" / "map_blob.bin"
BLOB_BASE = 0x9B64
TABLE = 0xB787
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


def resolve_round(dest: int) -> int:
    ptrs = [0xB7A5, 0xB61A, 0xB3FD, 0xB1DE, 0xAF1F, 0xAD61, 0xAAEF, 0xA751]
    for i, p in enumerate(ptrs):
        if dest >= p:
            return 8 - i
    return 0


def invented_r7_rewrite(dest: int, round_: int, typ: int) -> int:
    """The port hole: force 0xB7A5 when R7 70/71 dest is not R7/R8."""
    if typ in (70, 71) and round_ == 7:
        wr = resolve_round(dest)
        if wr not in (7, 8):
            return 0xB7A5
    if dest == 0 and round_ == 7:
        return 0xB7A5
    return dest


def main() -> int:
    fails = 0
    mapc = MAPC.read_text(encoding="utf-8")
    ent = ENTITY.read_text(encoding="utf-8")
    game = GAME.read_text(encoding="utf-8")
    hud = HUD.read_text(encoding="utf-8")
    main_c = MAIN.read_text(encoding="utf-8")

    asm = load_asm()
    if asm:
        if not re.search(r"LD\s+HL,\s*\(0xe720\)\s*;\s*0x87b6", asm, re.I):
            fail("zanac.asm 87b6 is not LD HL,(E720)")
            fails += 1
        else:
            print("  ASM 87b6: dest = word at E720[+0x03]")
        if not re.search(r"LD\s+\(IX\+0x1c\),\s*A\s*;\s*0x87bb", asm, re.I):
            fail("zanac.asm 87bb is not LD (IX+0x1C),A")
            fails += 1
        else:
            print("  ASM 87bb: +0x1c/+0x1d = table word")
        if re.search(
            r"0x87b0[\s\S]{0,400}CP\s+.*E701|0x87b0[\s\S]{0,400}0xb7a5",
            asm,
            re.I,
        ):
            fail("zanac.asm 87b0 must not CP round or force 0xB7A5")
            fails += 1
        else:
            print("  ASM 87b0: no round filter")
        if not re.search(r"LD\s+\(0xe722\),\s*HL\s*;\s*0x8a0b", asm, re.I):
            fail("zanac.asm 8a0b is not LD (E722),HL")
            fails += 1
        else:
            print("  ASM 8a0b: E722 = +0x1c/+0x1d as-is")
        if not re.search(r"JP\s+Z,\s*0x414d\s*;\s*0x40e2", asm, re.I):
            fail("zanac.asm 40E2 is not JP Z,414d")
            fails += 1
        else:
            print("  ASM 40e2: E722==0 skips load")
        if not re.search(r"0x88,\s*0x87,\s*0xB7", asm, re.I):
            fail("R7 cmd 8 dest 0xB787 missing")
            fails += 1
        else:
            print("  ASM: R7 cmd 8 E720=0xB787")
    else:
        print("  (zanac.asm not on this machine; C/blob locks only)")

    blob = BLOB.read_bytes() if BLOB.is_file() else None
    table = None
    if blob:
        off = TABLE - BLOB_BASE
        table = blob[off : off + 24]
        w0 = table[0] | (table[1] << 8)
        w3 = table[3] | (table[4] << 8)
        w6 = table[6] | (table[7] << 8)
        w10 = table[10] | (table[11] << 8)
        w12 = table[12] | (table[13] << 8)
        w20 = table[20] | (table[21] << 8)
        if w0 != 0x0000:
            fail(f"0xB787+0 must be 0x0000, got 0x{w0:04X}")
            fails += 1
        else:
            print("  blob 0xB787+0: 0x0000 (40DA skip)")
        if w3 != 0xB7A5 or w10 != 0xB7A5:
            fail("0xB787+3/+0x0A must be 0xB7A5")
            fails += 1
        else:
            print("  blob 0xB787+3/+0x0A: 0xB7A5 R8")
        if w6 != 0xB61A or w12 != 0xB61A or w20 != 0xB61A:
            fail("0xB787+6/+0x0C/+0x14 must be 0xB61A")
            fails += 1
        else:
            print("  blob 0xB787+6/+0x0C/+0x14: 0xB61A R7")

        # Sim: Japan dest vs invented rewrite.
        for cur, want in ((0, 0x0000), (3, 0xB7A5), (6, 0xB61A), (10, 0xB7A5)):
            dest = table[cur] | (table[cur + 1] << 8)
            if dest != want:
                fail(f"cursor {cur}: table word 0x{dest:04X} != 0x{want:04X}")
                fails += 1
            rewritten = invented_r7_rewrite(dest, 7, 71)
            if want in (0xB7A5, 0xB61A):
                if rewritten != dest:
                    fail(f"aligned dest 0x{dest:04X} must stay")
                    fails += 1
                else:
                    print(f"  sim: cursor {cur} dest 0x{dest:04X} stays")
            else:
                if rewritten != 0xB7A5:
                    fail(f"sim: rewrite of 0x{dest:04X} -> 0x{rewritten:04X}")
                    fails += 1
                else:
                    print(
                        f"  sim: cursor {cur} dest 0x{dest:04X}; "
                        f"old rewrite -> R8 (hole)"
                    )
        print("  sim: Japan keeps table words; zero skips 40DA load")
        if resolve_round(0) != 0:
            fail("0 must resolve to round 0")
            fails += 1
        else:
            print("  sim: dest 0 resolve R0 (40DA 414d)")
    else:
        print("  (map_blob.bin missing; skip table census)")

    place = fn_span(mapc, "static void place_tile_group(StreamSlot *st, u16 *pptr)")
    if not place:
        fail("place_tile_group not found")
        fails += 1
    else:
        if re.search(r"round == 7", place) or "wr != 7" in place:
            fail("place_tile_group must not rewrite R7 dest to 0xB7A5")
            fails += 1
        else:
            print("  place_tile_group: no R7 dest rewrite")
        if "s_ms.idol_ptr + s_idol_cur" not in place:
            fail("place_tile_group must still read E720[cursor]")
            fails += 1
        else:
            print("  place_tile_group: dest = E720[cursor]")

    ctrl = fn_span(mapc, "static void place_ctrl_at(u16 ptr)")
    if not ctrl:
        fail("place_ctrl_at not found")
        fails += 1
    elif re.search(r"round == 7", ctrl) or "wr != 7" in ctrl:
        fail("place_ctrl_at must not rewrite R7 dest to 0xB7A5")
        fails += 1
    else:
        print("  place_ctrl_at: no R7 dest rewrite")

    warp = fn_span(mapc, "void map_script_warp(u16 dest)")
    if not warp:
        fail("map_script_warp not found")
        fails += 1
    else:
        if re.search(r"!dest && s_ms\.round == 7", warp) or (
            "round == 7" in warp and "map_script_ptrs[0]" in warp
        ):
            fail("map_script_warp must not invent 0xB7A5 when dest==0")
            fails += 1
        else:
            print("  map_script_warp: dest==0 is 414d, not R8")
        if "entity_alc_complete" not in warp:
            fail("E722==0 must still LAB_414d entity_alc_complete")
            fails += 1
        else:
            print("  map_script_warp: E722==0 still alc_complete")
        if "entity_clear_enemies" not in warp:
            fail("40BA must entity_clear_enemies")
            fails += 1
        elif re.search(r"(variant|kind)\s*=\s*0x28", warp):
            fail("40BA must not write type 0x28")
            fails += 1
        else:
            print("  KEEP: 40BA clear, no type 0x28 punch")
        if "s_warp_jwait = 0x64" not in mapc and "0x64" not in warp:
            fail("40DA wait_frames 0x64 was reverted")
            fails += 1
        else:
            print("  KEEP: 40DA wait 0x64")

    collect = fn_span(ent, "static void collide_player(void)")
    if not collect:
        fail("collide_player not found")
        fails += 1
    else:
        orb = re.search(
            r"if \(e->kind == KIND_ORB\)\s*\{(.*?)return;\s*\}",
            collect,
            re.S,
        )
        if not orb:
            fail("KIND_ORB collect block missing")
            fails += 1
        elif "map_script_warp(dest)" not in orb.group(1):
            fail("black orb must map_script_warp(+0x1c/+0x1d)")
            fails += 1
        elif "map_script_ptrs[0]" in orb.group(1) or "0xB7A5" in orb.group(1):
            fail("orb collect must not invent 0xB7A5")
            fails += 1
        else:
            print("  KIND_ORB: warp dest as-is")

    # Hunt #1 KEEP
    if "map_script_warp_waiting" not in game:
        fail("game_update 40DA 9393 skip was reverted")
        fails += 1
    else:
        print("  KEEP: 40DA skip 9393")
    if "entity_base_set(0)" not in game:
        fail("GO 40BA E150=0 was reverted")
        fails += 1
    else:
        print("  KEEP: GO E150=0")
    if "0xBFD6" in ent or "0xbfd6" in ent or "0xBFD6" in mapc:
        fail("must not CALL 0xBFD6")
        fails += 1
    else:
        print("  KEEP: no 0xBFD6")
    if "sat_x_964c" not in mapc:
        fail("964C 8-bit SAT X wrap was reverted")
        fails += 1
    else:
        print("  KEEP: 964C")
    if "(u8)e->y >= 0xD0" not in ent or "(u8)e->x >= 0xD1" not in ent:
        fail("4898 unsigned wrap was reverted")
        fails += 1
    else:
        print("  KEEP: 4898 Y>=0xD0 / X>=0xD1")
    if "s_fire7_col" not in ent or "0x8F" not in ent:
        fail("fire7 INC+AND 0x8F was reverted")
        fails += 1
    else:
        print("  KEEP: fire7 CRAM")
    if "s_skip_precompute" not in mapc:
        fail("cmd-9 skip peek was reverted")
        fails += 1
    else:
        print("  KEEP: cmd 9 no peek")
    if "pre-carry" not in mapc:
        fail("#92 pre-carry wrap missing")
        fails += 1
    else:
        print("  KEEP: 97e3 pre-carry wrap")
    if "0x4BDF" not in hud and "4BDF" not in hud:
        fail("4BDF HUD border missing")
        fails += 1
    else:
        print("  KEEP: 4BDF")
    if "SYS_doVBlankProcess" not in main_c:
        fail("60fps vblank loop was reverted")
        fails += 1
    else:
        print("  KEEP: 60fps")
    collide = fn_span(ent, "static void collide_player(void)")
    if not collide or re.search(r"if\s*\(\s*e->kind == KIND_GROUND\s*\)", collide):
        fail("type 44 is 44BA; collide_player must not skip KIND_GROUND")
        fails += 1
    else:
        print("  type 44 44BA: collide_player does not skip KIND_GROUND")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
