#!/usr/bin/env python3
"""Title continue mirrors MSX E701 including 0 after LAB_92af.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  E701 writers:
    0x403F  cold boot = 1
    0x4256  title_screen_init: ESC up -> E701=1; ESC held keeps E701
    0x4118  40DA: LD (E701),A from resolve_round_from_ptr
    0x9439  init_credits_stream: LD (E701),A from resolve

  resolve_round_from_ptr 0x9444 walks 8 entries at 0x945C high-to-low.
  dest 0xA6F4 (LAB_92af / ending stream) is below 0xA751 -> A=0.

  title_screen_init 0x425A:
    LD A,8 / SUB (IX+1) / ... table 0x945C + 2*(8-E701)
    E701=0 -> index 8 -> 0xA65C (9th word at 0x946C)

  0xA65C is a playable lead-in (cmd 8 banner, spawn_ctrl, place_tiles)
  that cmd-9 jumps to 0xB7A5 (round 8) at row 3000.

  Port s_continue_round used to skip 0 (only copied for rounds 1-8), so
  C+START after credits booted ptrs[0] (0xB7A5) instead of ptrs[8]
  (0xA65C). write_e701 now stores 0..8 like E701.

Usage (from zanac-md):
    python tools/test_continue_e701_round0.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPC = ROOT / "src" / "map_script.c"
MAPH = ROOT / "inc/map_scripts.h"
MAPSC = ROOT / "src/data/map_scripts.c"
TITLE = ROOT / "src/title.c"
BLOB = ROOT / "res/map_blob.bin"
BLOB_BASE = 0x9B64
ASM_CANDIDATES = [
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    Path.home() / "zanac-re" / "source" / "zanac.asm",
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
]

PTRS = [0xB7A5, 0xB61A, 0xB3FD, 0xB1DE, 0xAF1F, 0xAD61, 0xAAEF, 0xA751, 0xA65C]


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


def blob_u16(addr: int) -> int:
    off = addr - BLOB_BASE
    data = BLOB.read_bytes()
    return data[off] | (data[off + 1] << 8)


def main() -> int:
    fails = 0
    mapc = MAPC.read_text(encoding="utf-8")
    maph = MAPH.read_text(encoding="utf-8")
    mapsc = MAPSC.read_text(encoding="utf-8")
    title = TITLE.read_text(encoding="utf-8")

    asm = load_asm()
    if asm:
        if not re.search(r"LD\s+\(0xe701\),\s*A\s*;\s*0x9439", asm, re.I):
            fail("init_credits_stream 9439 must write E701")
            fails += 1
        else:
            print("  ASM 9439: init_credits_stream writes E701")
        if not re.search(r"LD\s+\(HL\),\s*A\s*;\s*0x4118", asm, re.I):
            fail("40DA 4118 must write E701")
            fails += 1
        else:
            print("  ASM 4118: 40DA writes E701 from resolve")
        if not re.search(r"SUB\s+\(IX\+0x1\)\s*;\s*0x425c", asm, re.I):
            fail("title 425A must index 8-E701")
            fails += 1
        else:
            print("  ASM 425C: title index is 8-E701")
        if not re.search(r"0x5C,\s*0xA6\s*;\s*0x946c", asm, re.I):
            fail("ptr table 0x946C must be 0xA65C")
            fails += 1
        else:
            print("  ASM 946C: 9th ptr is 0xA65C")
    else:
        print("  ASM: not found (blob + C checks only)")

    if "0xA65C" not in mapsc or "map_script_ptrs[9]" not in mapsc:
        fail("map_script_ptrs must have 9 entries ending at 0xA65C")
        fails += 1
    else:
        print("  map_scripts.c: ptrs[8] = 0xA65C")

    if "MAP_SCRIPT_COUNT   9" not in maph:
        fail("MAP_SCRIPT_COUNT must be 9")
        fails += 1
    else:
        print("  map_scripts.h: MAP_SCRIPT_COUNT 9")

    if not BLOB.is_file():
        fail("res/map_blob.bin missing")
        fails += 1
    else:
        # 0xA65C stream: row 3000 cmd 9 dest 0xB7A5 at 0xA6E7
        trig = blob_u16(0xA6E7)
        cmd = BLOB.read_bytes()[0xA6E7 + 2 - BLOB_BASE]
        dest = blob_u16(0xA6E7 + 3)
        if trig != 3000 or (cmd & 0x0F) != 9 or dest != 0xB7A5:
            fail(
                f"0xA6E7 must be row 3000 cmd9 -> 0xB7A5 "
                f"(got row={trig} cmd={cmd:02X} dest={dest:04X})"
            )
            fails += 1
        else:
            print("  blob 0xA6E7: row 3000 cmd 9 -> 0xB7A5")
        start_cmd = BLOB.read_bytes()[0xA65C + 2 - BLOB_BASE]
        if (start_cmd & 0x0F) != 6:
            fail(f"0xA65C must start with cmd 6 (got {start_cmd:02X})")
            fails += 1
        else:
            print("  blob 0xA65C: round-0 stream start (cmd 6)")

    write = fn_span(mapc, "static void write_e701(u8 round)")
    if not write or "s_continue_round = round" not in write:
        fail("write_e701 must copy 0..8 into s_continue_round")
        fails += 1
    else:
        print("  write_e701: s_continue_round = round (includes 0)")

    arm = fn_span(mapc, "static void arm_ending_stream(void)")
    if not arm or "write_e701(0)" not in arm:
        fail("arm_ending_stream must write_e701(0)")
        fails += 1
    else:
        print("  arm_ending_stream: write_e701(0)")

    jump = fn_span(mapc, "static void cmd_script_jump(u8 cmd, const u8 *ops)")
    if not jump or "write_e701" not in jump:
        fail("cmd_script_jump must write_e701(resolve)")
        fails += 1
    elif "round >= 1 &&" in jump or "round <= 8" in jump:
        fail("cmd_script_jump must not skip E701=0")
        fails += 1
    else:
        print("  cmd_script_jump: write_e701(resolve) including 0")

    setup = fn_span(mapc, "static void ending_setup_91fd(void)")
    if not setup or "write_e701" not in setup:
        fail("ending_setup_91fd must write_e701(resolve 0xBBB4)")
        fails += 1
    else:
        print("  ending_setup_91fd: write_e701(resolve 0xBBB4)")

    boot = fn_span(mapc, "static void script_boot(u8 round, u16 pc)")
    if not boot or "write_e701(round)" not in boot:
        fail("script_boot must write_e701(round)")
        fails += 1
    elif "round >= 1 &&" in boot:
        fail("script_boot must not skip E701=0")
        fails += 1
    else:
        print("  script_boot: write_e701(round) including 0")

    init = fn_span(mapc, "void map_script_init_round(u8 round)")
    if not init or "8 - round" not in init:
        fail("map_script_init_round must index 8-round")
        fails += 1
    else:
        print("  map_script_init_round: idx = 8 - round (0 -> 8)")

    if "map_script_continue_round()" not in title:
        fail("title C+START must use map_script_continue_round")
        fails += 1
    else:
        print("  title.c: C+START uses map_script_continue_round")

    # KEEP: dest 0xA6F4 is still a 941b jump, not a special-case credits arm
    if "MAP_ENDING_STREAM" in (jump or ""):
        fail("cmd_script_jump must not special-case 0xA6F4")
        fails += 1
    else:
        print("  KEEP: cmd 9 dest 0xA6F4 is a 941b jump")

    if fails:
        print(f"{fails} FAIL(S)")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
