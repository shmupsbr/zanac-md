#!/usr/bin/env python3
"""Type 62 8744 LDIRVM is SGT 0x1800, not a playfield nametable poke.

zanac.asm Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  init_vdp_regs 0x42CF: R2=0x0E -> nametable 0x3800
                         R6=0x03 -> SGT 0x1800

  handler_type62 0x8728 (armed, every 16 frames):
    LD HL,0x876b / ADD HL,DE     ; 876b or 878b (phase bit4<<1)
    LD DE,0x1800                 ; 0x873e  SGT pattern 0
    LD BC,0x0020                 ; 16x16 1bpp (4 x 8x8)
    CALL 0x42ed / CALL 0x005C    ; vdp_int_disable + LDIRVM

  SAT name 0 (8717) + colour 0x87 (871b, EC+cyan) draws that pattern.
  Writing those bytes as nametable tile IDs across PF_COLS parked a
  garbage charset row in E800; MD VSCROLL then dragged it across the
  192. Filipe: round 2 after 1st boss (cmd B 0xAB3B row 440) when a
  type-61 death becomes type 62.

KEEP: 8717 SAT 0 16x16; 8727 first-visit RET; lives-only; no NT poke;
no letter fill; no opaque 0x20; 4BDF; TITLE_MD_Y=40.

Usage (from zanac-md):
    python tools/test_type62_sgt_1800.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPC = ROOT / "src" / "map_script.c"
MAPH = ROOT / "inc" / "map_script.h"
ENTITY = ROOT / "src" / "entity.c"
PLAYER = ROOT / "src" / "player.c"
BLOB = ROOT / "res" / "map_blob.bin"
BLOB_BASE = 0x9B64
TITLE_MD = ROOT / "inc" / "title_md.h"
HUD = ROOT / "src" / "hud.c"
ASM_CANDIDATES = [
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    Path.home() / "zanac-re" / "source" / "zanac.asm",
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
]

# ROM 876b / 878b. Same bytes as Japan's LDIRVM source (data, not tile IDs).
JAPAN_876B = bytes((
    0x07, 0x1F, 0x3F, 0x7F, 0x43, 0x81, 0xE1, 0xE1,
    0x81, 0x43, 0x7F, 0x30, 0x1C, 0x17, 0xD0, 0x38,
    0xC0, 0xF0, 0xF8, 0xFC, 0x84, 0x02, 0xC2, 0xC2,
    0x02, 0x84, 0xFC, 0x18, 0x70, 0xD0, 0x16, 0x38,
))
JAPAN_878B = bytes((
    0x07, 0x1F, 0x3F, 0x7F, 0x43, 0x81, 0x87, 0x87,
    0x81, 0x43, 0x7F, 0x30, 0x9F, 0xA7, 0x40, 0x20,
    0xC0, 0xF0, 0xF8, 0xFC, 0x84, 0x02, 0x0E, 0x0E,
    0x02, 0x84, 0xFC, 0x18, 0xF2, 0xCA, 0x04, 0x08,
))


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


def c_u8_arrays(src: str, name: str) -> list[list[int]]:
    m = re.search(rf"{name}\s*\[[^\]]+\](?:\s*\[[^\]]+\])?\s*=\s*\{{", src)
    if not m:
        return []
    i = m.end() - 1
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                body = src[i : j + 1]
                frames = re.findall(r"\{([^}]+)\}", body)
                out = []
                for fr in frames:
                    vals = [int(x, 0) for x in re.findall(r"0x[0-9A-Fa-f]+|\d+", fr)]
                    if len(vals) == 32:
                        out.append(vals)
                return out
    return []


def main() -> int:
    fails = 0
    mapc = MAPC.read_text(encoding="utf-8", errors="replace")
    maph = MAPH.read_text(encoding="utf-8", errors="replace")
    ent = ENTITY.read_text(encoding="utf-8", errors="replace")
    ply = PLAYER.read_text(encoding="utf-8", errors="replace")
    hud = HUD.read_text(encoding="utf-8", errors="replace")
    title = TITLE_MD.read_text(encoding="utf-8", errors="replace")
    asm = load_asm()

    if asm:
        if not re.search(r"LD\s+DE,\s*0x1800\s*;\s*0x873e", asm, re.I):
            fail("zanac.asm 873e is not LD DE,0x1800")
            fails += 1
        else:
            print("  ASM 873e: LDIRVM dest 0x1800")
        if not re.search(r"LD\s+BC,\s*0x0020\s*;\s*0x8741", asm, re.I):
            fail("zanac.asm 8741 is not LD BC,0x0020")
            fails += 1
        else:
            print("  ASM 8741: BC=0x20 (one 16x16 SGT pattern)")
        if not re.search(r"CALL\s+0x005c\s*;\s*0x8747", asm, re.I):
            fail("zanac.asm 8747 is not CALL LDIRVM")
            fails += 1
        else:
            print("  ASM 8747: LDIRVM")
        if "0x0E" not in asm and "0x0e" not in asm:
            fail("init_vdp_regs R2 missing from tree")
            fails += 1
        r2 = re.search(r"0x0[eE].*name table|PN\s*=\s*14|R2.*0x0[eE]", asm)
        if "0x3800" in asm:
            print("  ASM: nametable 0x3800 is not 0x1800")
        if not re.search(r"LD\s+\(IX\+0x03\),\s*0x00\s*;\s*0x8717", asm, re.I):
            fail("zanac.asm 8717 SAT name 0 lost")
            fails += 1
        else:
            print("  ASM 8717: SAT name 0")
    else:
        print("  ASM: zanac.asm not in tree (bytes checked in port)")

    frames = c_u8_arrays(mapc, "k_riser_sgt")
    if len(frames) != 2:
        fail("k_riser_sgt must be two 32-byte SGT frames")
        fails += 1
    else:
        if bytes(frames[0]) != JAPAN_876B:
            fail("k_riser_sgt[0] must match ROM 876b")
            fails += 1
        else:
            print("  k_riser_sgt[0] = 876b")
        if bytes(frames[1]) != JAPAN_878B:
            fail("k_riser_sgt[1] must match ROM 878b")
            fails += 1
        else:
            print("  k_riser_sgt[1] = 878b")

    poke = fn_span(mapc, "void map_script_type62_poke(u8 phase)")
    if not poke:
        fail("map_script_type62_poke missing")
        fails += 1
    else:
        for bad in (
            "nt_put",
            "VDP_setTileMap",
            "PF_COLS",
            "hidden_wrap",
            "tile_wrap",
            "s_e800",
            "dma_nt_row",
        ):
            if bad in poke:
                fail(f"type62_poke must not write nametable ({bad})")
                fails += 1
                break
        else:
            print("  type62_poke: no nametable / wrap / E800 write")
        if "pack_riser_sgt" not in poke:
            fail("type62_poke must pack SGT 1bpp -> 4bpp (Japan LDIRVM dest)")
            fails += 1
        else:
            print("  type62_poke: SGT pack")

    if "k_riser_nt" in mapc:
        fail("do not keep the nametable-row interpretation (k_riser_nt)")
        fails += 1
    else:
        print("  no k_riser_nt")

    if "poke row0 24-col" in maph:
        fail("map_script.h must not describe type62 as a 24-col nametable poke")
        fails += 1
    if "SGT" not in maph and "0x1800" not in maph:
        fail("map_script.h must document SGT 0x1800")
        fails += 1
    else:
        print("  header: SGT 0x1800")

    dma = fn_span(ent, "static void riser_dma_sgt(Slot *s)")
    if not dma or "map_script_type62_sgt" not in dma:
        fail("riser_dma_sgt must upload packed SGT tiles to the sprite")
        fails += 1
    elif "nt_put" in dma:
        fail("riser_dma_sgt must not nt_put")
        fails += 1
    else:
        print("  entity: SGT tiles -> sprite VRAM")

    become = fn_span(ent, "static void become_riser(Slot *e)")
    if not become:
        fail("become_riser missing")
        fails += 1
    elif "e->sat = 0" not in become:
        fail("KEEP: 8717 SAT 0")
        fails += 1
    elif "e->sat_col = 0x87" not in become:
        fail("KEEP: 871b sat_col 0x87")
        fails += 1
    elif "step_88_y_4898" in become or "riser_step" in become:
        fail("KEEP: 8727 become_riser must not 4898 / riser_step")
        fails += 1
    else:
        print("  KEEP: 8717 SAT 0 / 871b 0x87 / 8727 no 4898")

    step = fn_span(ent, "static void riser_step(Slot *e)")
    if not step or "step_88_y_4898" not in step:
        fail("armed riser_step must still 4898")
        fails += 1
    elif "map_script_type62_poke" not in step:
        fail("8728 must still LDIRVM every 16f")
        fails += 1
    else:
        print("  KEEP: 8728 poke + 874a 4898")

    if "e->sat = 0" not in (step or ""):
        fail("riser_step must restore SAT 0 after FRAME_BOX vehicle alloc")
        fails += 1
    else:
        print("  riser_step: SAT 0 after sprite alloc")

    grant = fn_span(ply, "void player_grant_life(void)")
    if grant and ("fire_select" in grant or "player_fire_select" in grant):
        fail("KEEP: type 62 lives-only")
        fails += 1
    else:
        print("  KEEP: type 62 lives-only")

    if "recolor_charset_tile_opaque_bg" in mapc:
        fail("KEEP: no opaque 0x20")
        fails += 1
    else:
        print("  KEEP: no opaque 0x20")

    dma_nt = fn_span(mapc, "static void dma_nt_row(u8 nt_y, const u8 *src, TransferMethod tm)")
    if dma_nt and (
        "mode_draw_letterbox" in dma_nt
        or "VDP_fillTileMapRect(BG_A" in dma_nt
    ):
        fail("KEEP: no playfield letter fill")
        fails += 1
    else:
        print("  KEEP: no playfield letter fill")

    if 'hud_str_win(HUD_TEXT, hud_y(18), "FIRE ")' not in hud:
        fail("KEEP: FIRE stays MSX row 18")
        fails += 1
    else:
        print("  KEEP: FIRE MSX 18")
    if "0x03, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20, 0x03" not in hud:
        fail("KEEP: 0x4BDF 8-tile border")
        fails += 1
    else:
        print("  KEEP: 4BDF")
    if "#define TITLE_MD_Y          40" not in title:
        fail("KEEP: TITLE_MD_Y=40")
        fails += 1
    else:
        print("  KEEP: TITLE_MD_Y=40")

    blob = BLOB.read_bytes() if BLOB.is_file() else b""
    if len(blob) > (0xAB3B - BLOB_BASE) + 3:
        off = 0xAB3B - BLOB_BASE
        row = blob[off] | (blob[off + 1] << 8)
        cmd = blob[off + 2]
        if row != 440 or (cmd & 0x0F) != 0x0B:
            fail(f"R2 first boss 0xAB3B must be row 440 cmd B, got row {row} cmd {cmd:#x}")
            fails += 1
        else:
            print("  blob 0xAB3B: R2 1st boss row 440 cmd B")

    if fails:
        print(f"{fails} FAIL(s)", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
