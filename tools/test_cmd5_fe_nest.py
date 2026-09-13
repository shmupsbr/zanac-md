#!/usr/bin/env python3
"""Cmd 5 len 0xFE must not clobber the parent stream slot.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  stream stamp 0x9A38 LD A,(HL) = len; INC HL
  0x9A3E CP 0xFE / JR NC 0x9A68     ; both nest via load_stream_slots
  0x9A68 LD C,(IY+0) / CALL 0x95A8  ; C = parent ybase
  0x9A74 JR NZ,0x9A44               ; after POP AF (flags from CP 0xFE)
  0x9A44 LD (IY+2),L / DEC (IY+1)   ; 0xFF only
  0x9A76 POP BC / JR 0x9A54         ; 0xFE: leave parent ptr and count

Live blob (only 0xFE nest in the 9 scripts + ending + warp stub):

  R8 row 2992 cmd 5 @0xB8FA  01 01 08 50 B9  -> slot 1 ptr 0xB950
  stream 0xB950:
    01 00 FE 04
      02 00 3E BA   03 08 3E BA   04 10 3E BA
      09 00 04 50 B9              ; rebind parent slot 1, delay 4, ptr 0xB950

Port treated 0xFE like 0xFF: advanced ptr past the nest and DEC count,
then overwrote the rebind (ptr 0xB961, delay 4 -> 3, or used=0).

Also locks two ESC/STOP edges from the same hunt:
  40DA wait_frames 0x5BEC has no 4DA5 — pause_tick after warp_waiting.
  Credits 0x476C is a page-boundary ESC sample, not mid-page START.

Usage (from zanac-md):
    python tools/test_cmd5_fe_nest.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPC = ROOT / "src" / "map_script.c"
GAME = ROOT / "src" / "game.c"
BLOB = ROOT / "res" / "map_blob.bin"
BLOB_BASE = 0x9B64
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
    mapc = MAPC.read_text(encoding="utf-8", errors="replace")
    game = GAME.read_text(encoding="utf-8", errors="replace")
    asm = load_asm()

    if asm:
        if not re.search(r"CP\s+0xfe\s*;\s*0x9a3e", asm, re.I):
            fail("zanac.asm 9A3E is not CP 0xFE")
            fails += 1
        else:
            print("  ASM 9A3E: CP 0xFE")
        if not re.search(r"JR\s+NC,\s+\S+\s*;\s*0x9a40", asm, re.I):
            fail("zanac.asm 9A40 is not JR NC 9A68")
            fails += 1
        else:
            print("  ASM 9A40: nest on len>=0xFE")
        if not re.search(r"JR\s+NZ,\s+\S+\s*;\s*0x9a74", asm, re.I):
            fail("zanac.asm 9A74 is not JR NZ 9A44")
            fails += 1
        else:
            print("  ASM 9A74: 0xFF stores ptr+count; 0xFE skips")
        if not re.search(r"CALL\s+0x5bec\s*;\s*0x410a", asm, re.I):
            fail("zanac.asm 410A is not CALL wait_frames")
            fails += 1
        else:
            print("  ASM 410A: 40DA wait_frames 0x5BEC")
        if not re.search(r"CALL\s+0x43d2\s*;\s*0x476c", asm, re.I):
            fail("zanac.asm 476C is not CALL check_esc_key")
            fails += 1
        else:
            print("  ASM 476C: ESC after wait+settle")
    else:
        print("  (no zanac.asm; ASM checks skipped)")

    if BLOB.is_file():
        blob = BLOB.read_bytes()
        rec = blob[0xB8F8 - BLOB_BASE : 0xB8F8 - BLOB_BASE + 8]
        if rec != bytes([0xB0, 0x0B, 0x85, 0x01, 0x01, 0x08, 0x50, 0xB9]):
            fail(f"R8 row 2992 cmd 5: {rec.hex(' ')}")
            fails += 1
        else:
            print("  blob 0xB8F8: row 2992 cmd 5 -> 0xB950")
        st = blob[0xB950 - BLOB_BASE : 0xB950 - BLOB_BASE + 21]
        want = bytes(
            [
                0x01, 0x00, 0xFE, 0x04,
                0x02, 0x00, 0x3E, 0xBA,
                0x03, 0x08, 0x3E, 0xBA,
                0x04, 0x10, 0x3E, 0xBA,
                0x09, 0x00, 0x04, 0x50, 0xB9,
            ]
        )
        if st != want:
            fail(f"stream 0xB950: {st.hex(' ')}")
            fails += 1
        else:
            print("  blob 0xB950: 0xFE nest rebinds slot 1 delay 4")
    else:
        print("  (map_blob.bin missing; skip live FE census)")

    stamp = fn_span(mapc, "static void stream_stamp_buf(void)")
    nest = brace_after(stamp or "", r"else if \(len >= 0xFE\)")
    if not nest:
        fail("stream_stamp_buf nest arm missing")
        fails += 1
    elif "load_stream_slots_at" not in nest:
        fail("0xFE/0xFF must still load_stream_slots")
        fails += 1
    elif "if (len == 0xFE)" not in nest or "continue" not in nest:
        fail("0xFE must skip parent ptr/count write (9A74 Z)")
        fails += 1
    elif nest.find("if (len == 0xFE)") > nest.find("s->ptr ="):
        fail("0xFE continue must run before parent ptr advance")
        fails += 1
    else:
        print("  stream_stamp_buf: 0xFE leaves parent; 0xFF advances")

    cred = fn_span(mapc, "static void cred_tick(void)")
    if not cred:
        fail("cred_tick not found")
        fails += 1
    elif "s_cred_age" in cred or "s_cred_age" in mapc:
        fail("credits ESC must not use a start-of-credits age window")
        fails += 1
    elif "BUTTON_START" not in cred or "s_cred_exit = 1" not in cred:
        fail("credits START must still be ESC")
        fails += 1
    else:
        settle = brace_after(cred, r"if \(s_cred_settle\)")
        if not settle or "s_cred_exit = 1" not in settle:
            fail("0x476C ESC must sample when settle expires")
            fails += 1
        elif "cred_advance" not in settle:
            fail("settle expiry without START must still cred_advance")
            fails += 1
        else:
            print("  cred_tick: ESC at page-boundary settle, not mid-page")

    gu = fn_span(game, "void game_update(void)")
    if not gu:
        fail("game_update not found")
        fails += 1
    else:
        wpos = gu.find("map_script_warp_waiting()")
        ppos = gu.find("pause_tick(pressed)")
        # GO path also pause_tick's; play-path pause is the last one.
        ppos = gu.rfind("pause_tick(pressed)")
        if wpos < 0 or ppos < 0:
            fail("game_update must still pause_tick and warp_waiting")
            fails += 1
        elif ppos < wpos:
            fail("pause_tick must not run during 40DA wait_frames")
            fails += 1
        else:
            print("  game_update: warp wait skips 4DA5; play still pauses")
        creds = brace_after(gu, r"if \(map_script_credits_active\(\)\)")
        if creds and "pause_tick" in creds:
            fail("credits START must still not be STOP")
            fails += 1
        else:
            print("  KEEP: credits START is ESC, not pause")

    jump = fn_span(mapc, "static void cmd_script_jump(u8 cmd, const u8 *ops)")
    if not jump or "entity_alc_reset" in jump:
        fail("cmd 9 must still never alc_reset")
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
        fail("bonus_clear must wipe with tile 0")
        fails += 1
    else:
        print("  KEEP: BONUS clear tile 0")

    if "s_warp_jwait = 0x64" not in mapc:
        fail("40DA wait_frames 0x64 was reverted")
        fails += 1
    else:
        print("  KEEP: 40DA wait 0x64")

    if "0x47AA" not in mapc and "0x47aa" not in mapc:
        fail("credits 47AA skip-N was reverted")
        fails += 1
    else:
        print("  KEEP: credits 47AA")

    if "s_assemble_peek = 1" not in mapc:
        fail("peek assemble flag was reverted")
        fails += 1
    else:
        print("  KEEP: peek assemble still snap/restore")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
