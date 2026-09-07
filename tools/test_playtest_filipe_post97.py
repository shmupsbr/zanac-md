#!/usr/bin/env python3
"""Filipe playtest after PR #97 (49c8650) — left-edge blue notch at coast.

Japan v1 SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2 (no VSCROLL).

Screenshot: blue water / green land, hard horizontal line across most of
the width, jagged **blue notch on the far left** several pixels into the
green — leftover sky column at playfield col 0.

Japan 9a79 (scroll_vram_write): SETWRT nametable col 0, B=0x18 OUT from
E800, then HL+=0x20 (HUD 24-31 untouched). Assemble commits EA48 skip 8
into that 24-col row. MD wrap/peek DMA_QUEUE'd 32 H32 cols (HUD pad)
then restored 24-31. The 32-word queued burst dropped word 0, so
playfield col 0 kept leftover 0x28 sky. Invisible over water; at a
coast it is the left-edge notch. Do not invent shore tiles.

#97 KEEP: wrap DMA after entity (9a79 after 87e2/88ed). This PR keeps
that handshake and writes the 24-col stream with CPU so col 0 lands.

KEEP: #91 peek only after real 97e3; #92 wrap(pre) RAW; #96 tile_wrap
stamps; fire7; 964C; ship Y+2; no 0x28 punch; orb; 4898; ebullet; 4BDF;
60fps; no letter fill; no opaque 0x20; no BFD6. Ignore enemy black mask.

Usage (from zanac-md):
    python tools/test_playtest_filipe_post97.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "src" / "map_script.c"
ENT = ROOT / "src" / "entity.c"
GAME = ROOT / "src" / "game.c"
HDR = ROOT / "inc" / "map_script.h"
MAIN = ROOT / "src" / "main.c"
PLY = ROOT / "src" / "player.c"
SPAWN = ROOT / "src" / "data" / "spawn_table.c"


def src(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"ok: {msg}")


def fn_span(text: str, sig: str) -> str | None:
    m = re.search(rf"{re.escape(sig)}\s*\{{", text)
    if not m:
        return None
    i = m.end() - 1
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i : j + 1]
    return None


def hidden_wrap_nt_at(scroll_px: int) -> int:
    off = (scroll_px + 16) & 0xFF
    py = (16 - off) & 0xFF
    return py >> 3


def tile_wrap_nt_at(scroll_px: int) -> int:
    return hidden_wrap_nt_at(scroll_px & ~7)


def check_japan_24col_not_32queue() -> None:
    """Main 49c8650 hole: 32-col DMA_QUEUE dropped playfield col 0."""
    m = src(MAP)
    dma = fn_span(m, "static void dma_nt_row(u8 nt_y, const u8 *src, TransferMethod tm)")
    if not dma:
        fail("dma_nt_row not found")
    if "width = MODE_H32_COLS" in dma:
        fail(
            "32-col wrap/peek DMA is the left-edge 0x28 notch; "
            "Japan 9a79 writes BC=0x18 playfield cols at nametable col 0"
        )
    if "VDP_setTileMapDataRow(BG_B, dst, nt_y, 0, width, tm)" in dma:
        fail("playfield row must not DMA `width` (32 H32) — that skipped col 0")
    if "VDP_setTileMapDataRow(BG_B, dst, nt_y, 0, PF_COLS, play_tm)" not in dma:
        fail("playfield must be 24 cols at x=0 (Japan 9a79 B=0x18)")
    if "play_tm = (tm == DMA_QUEUE) ? CPU : tm" not in dma:
        fail("queued wrap/peek must CPU the 24 playfield tiles so col 0 lands")
    # HUD restore KEEP (WINDOW punch-through), after the 24-col write.
    if "VDP_setTileMapDataRow(BG_B, dst + MODE_BAR_COL, nt_y" not in dma:
        fail("KEEP: restore HUD BG_B cols 24-31")
    row_at = dma.find("VDP_setTileMapDataRow(BG_B, dst, nt_y, 0, PF_COLS, play_tm)")
    rest_at = dma.find("VDP_setTileMapDataRow(BG_B, dst + MODE_BAR_COL, nt_y")
    if rest_at < 0 or row_at < 0 or rest_at < row_at:
        fail("HUD restore must come after the 24-col playfield write")
    if "mode_letter_attr()" not in dma:
        fail("KEEP: pad HUD dst[24-31] with letter_attr")
    flip_at = dma.find("s_dma_flip ^= 1")
    if flip_at >= 0 and rest_at >= 0 and flip_at < rest_at:
        fail("do not flip the DMA_QUEUE buffer before the HUD restore")
    if "VDP_fillTileMapRect(BG_A" in dma or "mode_draw_letterbox" in dma:
        fail("dma_nt_row must not playfield/letterbox fill (60fps)")
    if "do not invent" not in m.lower() and "do not invent" not in dma.lower():
        fail("coast stays Japan column streams; no invented art")
    ok("9a79 24-col CPU playfield at x=0; HUD restore KEEP")


def check_e800_includes_col0() -> None:
    m = src(MAP)
    if "#define ASM_SKIP        8" not in m and not re.search(
        r"#define\s+ASM_SKIP\s+8\b", m
    ):
        fail("KEEP EA48 skip 8")
    if "#define PF_COLS         24" not in m and not re.search(
        r"#define\s+PF_COLS\s+24\b", m
    ):
        fail("97e3 row width is 24 playfield cols")
    pre = fn_span(m, "static void scroll_precompute(u16 map_row)")
    peek = fn_span(m, "static void peek_assemble_row(u16 map_row)")
    if not pre or "s_rowbuf[ASM_SKIP + x]" not in pre:
        fail("97e3 must copy e800 from EA48 (ASM_SKIP)")
    if "for (x = 0; x < PF_COLS; x++)" not in pre:
        fail("97e3 must copy all 24 cols including col 0")
    if not peek or "s_rowbuf[ASM_SKIP + x]" not in peek:
        fail("peek must copy 24 cols from EA48 including col 0")
    # First-word-drop model: 32-col queue leaves dst[0] unwritten in VRAM.
    # e800[0] is rowbuf[8]; that cell must still be in the 24-col write.
    if "s_e800[s_e714][x] = s_rowbuf[ASM_SKIP + x]" not in pre:
        fail("e800[e714][0] is playfield col 0 (EA48)")
    ok("e800/peek 24 cols from EA48 including col 0")


def check_keep_97e3_commit_peek() -> None:
    m, g, h = src(MAP), src(GAME), src(HDR)
    pre = fn_span(m, "static void scroll_precompute(u16 map_row)")
    if not pre:
        fail("scroll_precompute (97e3) not found")
    if "hidden_wrap_nt_at(s_scroll_px)" not in pre:
        fail("KEEP #92: 97e3 latches wrap(pre) RAW")
    if "tile_wrap_nt_at" in pre:
        fail("KEEP #92: 97e3 must not switch to tile_wrap")
    if "s_wrap_pending = 1" not in pre:
        fail("KEEP #97: DMA_QUEUE path defers to commit_wrap")
    if re.search(r"dma_nt_row\(hidden_wrap_nt_at\(s_scroll_px\)", pre):
        fail("KEEP #97: 97e3 must not DMA the wrap row before 87e2/88ed")
    if "void map_script_commit_wrap(void)" not in h:
        fail("KEEP #97 commit_wrap in header")
    commit = fn_span(m, "void map_script_commit_wrap(void)")
    if not commit or "dma_nt_row(s_wrap_nt, s_e800[s_e714]" not in commit:
        fail("KEEP #97: commit DMA e800[e714] at wrap(pre)")
    if "s_peek_line" not in commit:
        fail("commit_wrap must also flush the deferred peek row")
    if not re.search(
        r"entity_update\s*\(\s*\)\s*;[\s\S]{0,80}?map_script_commit_wrap\s*\(\s*\)\s*;",
        g,
    ):
        fail("KEEP #97: entity_update before commit_wrap")
    sat = fn_span(m, "static int sat_to_nt(s16 x, s16 y, u8 *col, u8 *row)")
    if not sat or "tile_wrap_nt_at(s_scroll_px)" not in sat:
        fail("KEEP #96 sat_to_nt tile_wrap")
    leftover = 0xE9
    if tile_wrap_nt_at(leftover) == hidden_wrap_nt_at(leftover):
        fail("leftover tile wrap must differ from wrap(raw) peek")
    upd = fn_span(m, "void map_script_update(void)")
    skip = upd.split("if (!s_skip_precompute)") if upd else []
    if len(skip) < 2:
        fail("KEEP s_skip_precompute")
    body = skip[1]
    i = body.find("{")
    depth = 0
    end = i
    for j, ch in enumerate(body[i:], i):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = j
                break
    block = body[i : end + 1]
    if "s_scroll_px =" in block:
        fail("must not write s_scroll_px before 97e3")
    if "peek_next_row" not in block:
        fail("KEEP #91: peek only after real 97e3")
    peek = fn_span(m, "static void peek_next_row(u16 map_row)")
    if not peek or "s_scroll_px + 8" not in peek:
        fail("KEEP peek wrap(scroll+8)")
    ok("KEEP #91/#92/#96/#97 wrap/peek/commit")


def check_keep_rest() -> None:
    m, e, p, main = src(MAP), src(ENT), src(PLY), src(MAIN)
    if "mdy = dy" not in e:
        fail("KEEP 71f6 complement Y = parent (ignore horns)")
    if "ADD 0xF1" not in p:
        fail("KEEP ship black Y+2")
    if "k_orb_sat" not in e:
        fail("KEEP orb")
    if re.search(r"VDP_setTileMapXY\([^,]+,\s*0x20\s*,", m):
        fail("no 0x20 opaque")
    if "recolor_charset_tile_opaque_bg" in m:
        fail("no 0x20 opaque")
    if "BFD6" in m or "0xBFD6" in e or "0xbfd6" in e:
        fail("no BFD6")
    if "SYS_doVBlankProcess" not in main:
        fail("KEEP 60fps")
    spawn = src(SPAWN)
    types = re.findall(
        r"0x[0-9A-Fa-f]{2}", spawn.split("spawn_type_list")[1].split(";")[0]
    )
    if len(types) < 51 or types[50].lower() != "0x44":
        fail("KEEP proto_box type 68")
    if "VDP_fillTileMapRect(BG_A, mode_letter_attr(), 0, 2, MODE_BAR_COL, 24)" in m:
        fail("no letter fill")
    st = fn_span(m, "void map_script_stamp_82_digit(s16 x, s16 y, u8 fire_num)")
    if not st or "punch_cell(" not in st or "0x30 + fire_num" not in st:
        fail("KEEP 87e2 punch_cell 0x30+fire")
    if "u8 hx = (u8)((u8)sat_x - 0x20)" not in m and "sat_x_964c" not in m:
        fail("KEEP 964C")
    if "punch_cell(col, srow, 0x28)" in m:
        fail("no 0x28 punch")
    ok("KEEP fire7/964C/orb/4898/60fps/no 0x28/no BFD6")


def main() -> None:
    check_japan_24col_not_32queue()
    check_e800_includes_col0()
    check_keep_97e3_commit_peek()
    check_keep_rest()
    print("test_playtest_filipe_post97: all checks passed")


if __name__ == "__main__":
    main()
