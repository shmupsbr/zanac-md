#!/usr/bin/env python3
"""40DA loads the destination after wait_frames(0x64), not before.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  9480  BIT 5,E102 / RET NZ          ; freeze scroll while SET 5 pending
  40DA  CALL 40BA                    ; reset_entities (E150=0, E132=0)
        E722==0 -> 414d              ; skip stop/ev11/load
        stop_all / LD A,0x0B / 5189  ; ev11
        ... LDIR E800 blank ...
        LD B,0x64 / CALL 5BEC        ; wait_frames: VBlank only, no 9480/9393
        CALL 940c                    ; load dest stream  AFTER the wait
        4163 / ev10
  414d  RES 5 / E132 += 0x20

  SET 5 writers: type72 8A11, award 0x0F 91FA (E722=0xB7A5), 92af 92B8 (0xA6F4).

  wait_frames 5BEC does not CALL 9480 or 9393. Old port script_boot'd the
  destination then waited, so cruise E710=0x34 advanced ~20 dest rows
  during ev11. Signed-vs-unsigned 4898 is unrelated; do not invent culls.

Usage (from zanac-md):
    python tools/test_level_complete_40da.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPC = ROOT / "src" / "map_script.c"
GAME = ROOT / "src" / "game.c"
ENTITY = ROOT / "src" / "entity.c"
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


def dest_rows_during_wait(load_first: bool, e710: int = 0x34, wait: int = 0x64) -> int:
    """9480 carry rows the destination would gain if it were already loaded."""
    rows = 0
    e711 = 0
    if not load_first:
        return 0
    for _ in range(wait):
        total = e711 + e710
        e711 = total & 0xFF
        if total > 255:
            rows += 1
    return rows


def main() -> int:
    fails = 0
    mapc = MAPC.read_text(encoding="utf-8")
    game = GAME.read_text(encoding="utf-8")
    ent = ENTITY.read_text(encoding="utf-8")
    hud = HUD.read_text(encoding="utf-8")
    main_c = MAIN.read_text(encoding="utf-8")

    asm = load_asm()
    if asm:
        if not re.search(r"BIT\s+0x5,\s*A\s*;\s*0x9483", asm, re.I):
            fail("zanac.asm 9480 is not BIT 5,E102")
            fails += 1
        else:
            print("  ASM 9483: BIT 5 RET NZ freezes 9480")
        if not re.search(r"LD\s+B,\s*0x64\s*;\s*0x4108", asm, re.I):
            fail("zanac.asm 40DA is not wait_frames 0x64")
            fails += 1
        else:
            print("  ASM 4108: wait_frames 0x64 before load")
        if not re.search(r"CALL\s+0x940c\s*;\s*0x413e", asm, re.I):
            fail("zanac.asm 413e is not CALL 940c")
            fails += 1
        else:
            print("  ASM 413e: 940c after wait")
        if not re.search(r"LD\s+A,\s*0xb\s*;\s*0x40e8", asm, re.I):
            fail("zanac.asm 40EA is not ev11")
            fails += 1
        else:
            print("  ASM 40e8: ev11 before wait")
        if not re.search(r"LD\s+HL,\s*0xb7a5\s*;\s*0x91f1", asm, re.I):
            fail("zanac.asm 91F1 is not E722=0xB7A5")
            fails += 1
        else:
            print("  ASM 91f1: award 0x0F E722=0xB7A5")
        if not re.search(r"wait_frames:\s*\n\s*SUB\s+A\s*;\s*0x5bec", asm, re.I):
            fail("zanac.asm 5BEC is not wait_frames")
            fails += 1
        else:
            print("  ASM 5bec: wait_frames is VBlank only")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    old_rows = dest_rows_during_wait(True)
    new_rows = dest_rows_during_wait(False)
    if old_rows < 10:
        fail(f"sim: load-first should gain dest rows during 0x64 (got {old_rows})")
        fails += 1
    else:
        print(f"  sim: load-first cruise gains {old_rows} dest rows in 0x64")
    if new_rows != 0:
        fail("sim: wait-then-load must gain 0 dest rows")
        fails += 1
    else:
        print("  sim: wait-then-load gains 0 dest rows")

    warp = fn_span(mapc, "void map_script_warp(u16 dest)")
    if not warp:
        fail("map_script_warp not found")
        return 1
    if "script_boot" in warp or "map_script_start_ending" in warp:
        fail("map_script_warp loads dest before wait_frames (broken 40DA order)")
        fails += 1
    else:
        print("  map_script_warp: no load before wait")
    if "SND_EV_CLEARJING" not in warp:
        fail("map_script_warp must still play ev11")
        fails += 1
    else:
        print("  map_script_warp: ev11 still armed")
    if "MAP_ENDING_STREAM" not in warp:
        fail("map_script_warp must still special-case 0xA6F4")
        fails += 1
    else:
        print("  map_script_warp: 0xA6F4 still ending dest")
    if "entity_clear_enemies" not in warp:
        fail("40BA must entity_clear_enemies (no type 0x28 punch)")
        fails += 1
    elif re.search(r"(variant|kind)\s*=\s*0x28", warp):
        fail("40BA must not write type 0x28 (totem punch KEEP)")
        fails += 1
    else:
        print("  map_script_warp: 40BA clear, no type 0x28 punch")

    commit = fn_span(mapc, "static void warp_commit_load(void)")
    if not commit:
        fail("warp_commit_load not found")
        fails += 1
    else:
        if "script_boot" not in commit and "map_script_start_ending" not in commit:
            fail("warp_commit_load must 940c / ending after wait")
            fails += 1
        else:
            print("  warp_commit_load: dest load after wait")
        if "entity_alc_complete" not in commit:
            fail("warp_commit_load must LAB_414d E132+=0x20")
            fails += 1
        else:
            print("  warp_commit_load: alc_complete after load")

    tick = fn_span(mapc, "static void warp_jingle_tick(void)")
    if not tick or "warp_commit_load" not in tick:
        fail("warp_jingle_tick must commit load when wait hits 0")
        fails += 1
    else:
        print("  warp_jingle_tick: commit after 0x64")
    if "dump4177_begin" not in mapc:
        fail("40DA 4177 walk (blank/reveal) was omitted")
        fails += 1
    else:
        print("  KEEP: 4177 transition walk")
    if tick and tick.find("warp_commit_load") > tick.find("SND_EV_THEME"):
        fail("4163/ev10 must run after 940c, not before")
        fails += 1
    else:
        print("  warp_jingle_tick: 4163 after load")

    upd = fn_span(mapc, "void map_script_update(void)")
    if not upd or "if (s_warp_jingle)" not in upd:
        fail("map_script_update must skip 9480 while SET-5 wait is live")
        fails += 1
    else:
        print("  map_script_update: 9480 BIT 5 freeze")
    if upd:
        freeze = re.search(r"if \(s_warp_jingle\)\s*\{(.*?)\}", upd, re.S)
        if not freeze:
            fail("s_warp_jingle freeze block missing")
            fails += 1
        elif "scroll_precompute" in freeze.group(1) or "fire_pending" in freeze.group(1):
            fail("warp wait must not 97e3 / fire_pending (wait_frames)")
            fails += 1
        else:
            print("  map_script_update: wait has no 97e3")

    finish = fn_span(mapc, "static void base_clear_finish(void)")
    m0f = re.search(r"if \(mode == 0x0F\)\s*\{(.*?)\}", finish or "", re.S)
    if not m0f or "map_script_warp" not in m0f.group(1):
        fail("award 0x0F must SET 5 via map_script_warp, not instant script_boot")
        fails += 1
    elif "script_boot" in m0f.group(1):
        fail("award 0x0F still script_boot's R8 before 40DA wait")
        fails += 1
    else:
        print("  base_clear_finish 0x0F: 40DA warp")

    if "map_script_warp_waiting" not in game:
        fail("game_update must skip 9393 during 40DA wait")
        fails += 1
    else:
        print("  game.c: warp_waiting skips 9393")
    gu = fn_span(game, "void game_update(void)")
    if gu:
        wait = re.search(
            r"if \(map_script_warp_waiting\(\)\)\s*\{(.*?)\}", gu, re.S
        )
        if not wait:
            fail("game_update warp_waiting block missing")
            fails += 1
        elif "entity_update" in wait.group(1) or "player_update" in wait.group(1):
            fail("40DA wait_frames must not 9393 entity/player")
            fails += 1
        else:
            print("  game_update: wait has no entity_update")

    go = re.search(
        r"if \(!s_over_cleared\)\s*\{(.*?)\}", game, re.S
    )
    if not go or "entity_base_set(0)" not in go.group(1):
        fail("GO 40BA must zero E150 (9480 AND 0x3)")
        fails += 1
    else:
        print("  game.c: GO 40BA E150=0")

    # KEEP
    if "0xBFD6" in ent or "0xbfd6" in ent or "0xBFD6" in mapc:
        fail("must not CALL 0xBFD6")
        fails += 1
    else:
        print("  KEEP: no 0xBFD6")
    if "sat_x_964c" not in mapc and "964c" not in mapc.lower():
        fail("964C 8-bit SAT X wrap was reverted")
        fails += 1
    else:
        print("  KEEP: 964C present")
    if "s_fire7_col" not in ent or "0x8F" not in ent:
        fail("fire7 INC+AND 0x8F was reverted")
        fails += 1
    else:
        print("  KEEP: fire7 CRAM")
    if "(u8)e->y >= 0xD0" not in ent or "(u8)e->x >= 0xD1" not in ent:
        fail("4898 unsigned wrap was reverted")
        fails += 1
    else:
        print("  KEEP: 4898 Y>=0xD0 / X>=0xD1")
    if "KIND_GROUND" not in ent or "ship AABB ignores ground" not in ent:
        fail("ship AABB skip KIND_GROUND was reverted")
        fails += 1
    else:
        print("  KEEP: ship AABB skips KIND_GROUND")
    if "pre-carry" not in mapc and "pre-carry pixel" not in mapc:
        fail("#92 pre-carry wrap comment/path missing")
        fails += 1
    else:
        print("  KEEP: 97e3 pre-carry wrap")
    if "s_skip_precompute" not in mapc:
        fail("cmd-9 skip peek was reverted")
        fails += 1
    else:
        print("  KEEP: cmd 9 no peek")
    if "0x4BDF" not in hud and "4BDF" not in hud:
        fail("4BDF HUD border comment missing")
        fails += 1
    else:
        print("  KEEP: 4BDF")
    if "SYS_doVBlankProcess" not in main_c:
        fail("60fps vblank loop was reverted")
        fails += 1
    else:
        print("  KEEP: 60fps")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
