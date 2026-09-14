#!/usr/bin/env python3
"""Title logo drop, SHMUPSBR port credit, mode-select copy, HUD mini-logo.

Usage (from zanac-md):
    python tools/test_title_hud_branding.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TITLE_MD = ROOT / "inc" / "title_md.h"
TITLE_C = ROOT / "src" / "title.c"
HUD_C = ROOT / "src" / "hud.c"
HUD_H = ROOT / "inc" / "hud.h"
HUD_LOGO_H = ROOT / "inc" / "hud_logo.h"
HUD_LOGO_C = ROOT / "src" / "data" / "hud_logo.c"
BUILD = ROOT / "tools" / "build_title_md.py"
HUD_BUILD = ROOT / "tools" / "build_hud_logo.py"

# #119 6x1 smeared MD's M into Zanac via an all-blue bbox. Do not reuse.
BROKEN_119 = (
    0x00055555, 0x00444455, 0x00000055, 0x00000555,
    0x00005555, 0x00055555, 0x00555555, 0x45555555,
    0x55555555, 0x55555555, 0x55555555, 0x55045550,
    0x54055550, 0x55555550, 0x55555554, 0x55555555,
    0x00550455, 0x50554555, 0x55555555, 0x55555055,
    0x05554055, 0x45555555, 0x55555555, 0x55555555,
    0x05555550, 0x55544400, 0x55000000, 0x55000000,
    0x55400000, 0x45555550, 0x45555540, 0x555CC550,
    0x55555555, 0x55558555, 0x44488448, 0x00688088,
    0x00888088, 0x06888688, 0x08888888, 0x88888888,
    0x55CC5555, 0x55CC5C55, 0x8CCCCCC2, 0x62CC02CC,
    0x62CC0CCC, 0x62CC2CCC, 0x62CCCCC0, 0x62CCCC00,
)

# First longs of the good #121 6x2 (Zanac band). The #122 6x1 clip starts
# 0x05555555 and is only 48 words.
GOOD_121_HEAD = (0x00005555, 0x00055555, 0x00000000, 0x00000000)


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


def consts(path: Path) -> dict:
    out = {}
    for name, expr in re.findall(r"#define\s+(\w+)\s+(.+)", path.read_text()):
        expr = expr.split("/*")[0].strip()
        try:
            out[name] = eval(expr, {}, dict(out))
        except Exception:
            out[name] = expr
    return out


def unpack_tiles(words: list[int], tw: int, th: int) -> list[int]:
    idx = [0] * (tw * 8 * th * 8)
    for ti, base in enumerate(range(0, len(words), 8)):
        ty, tx = divmod(ti, tw)
        for row in range(8):
            w32 = words[base + row]
            bs = [(w32 >> 24) & 0xFF, (w32 >> 16) & 0xFF, (w32 >> 8) & 0xFF, w32 & 0xFF]
            pix = []
            for b in bs:
                pix.append((b >> 4) & 0xF)
                pix.append(b & 0xF)
            for i, p in enumerate(pix):
                idx[(ty * 8 + row) * (tw * 8) + tx * 8 + i] = p
    return idx


def main() -> int:
    md = consts(TITLE_MD)
    if md.get("TITLE_MD_Y") != 40:
        return fail("TITLE_MD_Y must be 40 (two 8x8 rows below Y=24)")
    if md.get("TITLE_ZANAC_TILE_Y") != 5:
        return fail("TITLE_ZANAC_TILE_Y must follow TITLE_MD_Y (40>>3 == 5)")
    if md.get("TITLE_MDMARK_TILE_Y") != 10:
        return fail("TITLE_MDMARK_TILE_Y must stay mark-relative (+5 tiles)")
    if md.get("TITLE_GROOVE_ROW") != 12:
        return fail("TITLE_GROOVE_ROW must move with the wordmark (12)")
    if md.get("TITLE_ZANAC_TRAVEL") != 56:
        return fail("do not change swirl travel")
    if "LOGO_Y = 40" not in BUILD.read_text():
        return fail("tools/build_title_md.py LOGO_Y must stay 40")

    title = TITLE_C.read_text()
    if 'draw_str_pal("MD PORT BY SHMUPSBR @ 2026.", 3, (u16)(TITLE_NT0 + 19), PAL3)' not in title:
        return fail("port credit must sit under COPYRIGHT at NT0+19, col 3, PAL3")
    if "MD Conversion by SHMUPSBR" in title or "MD CONVERSION BY SHMUPSBR" in title:
        return fail("old MD Conversion by SHMUPSBR credit must be gone")
    if "MD PORT BY SHMUPSBR (c)" in title or "MD PORT BY SHMUPSBR (C)" in title:
        return fail("(c) is not a glyph; use @ like COPYRIGHT @ 1986 (pink © / year)")
    for line in (
        'draw_str_pal("GAME DESIGNED BY COMPILE", 3, (u16)(TITLE_NT0 + 15), PAL3)',
        'draw_str_pal("PRODUCED      BY AII", 3, (u16)(TITLE_NT0 + 16), PAL3)',
        'draw_str_pal("PRESENTED     BY PONY INC.", 3, (u16)(TITLE_NT0 + 17), PAL3)',
        'draw_str_pal("COPYRIGHT @ 1986 PONY INC.", 3, (u16)(TITLE_NT0 + 18), PAL3)',
    ):
        if line not in title:
            return fail("do not rewrite MSX credit lines (%s)" % line)
    if "draw_score_top" not in title or "TITLE_NT0" not in title:
        return fail("SCORE/TOP must stay on TITLE_NT0")

    ct = (ROOT / "res" / "charset_ct.bin").read_bytes()
    at_ct = ct[0x40 * 8:0x40 * 8 + 8]
    year_ct = ct[0x32 * 8:0x32 * 8 + 8]
    if at_ct != bytes([0x90] * 8) or year_ct != bytes([0x90] * 8):
        return fail("@ and year digits must stay CT 0x90 (COPYRIGHT pink / TMS 9)")
    if 't == \' \' || t == \'.\' || t == \'@\'' not in title:
        return fail("charset_tile must still pass @ so the port credit © matches COPYRIGHT")

    hint = title.split("static void draw_mode_hint(void)", 1)
    if len(hint) < 2:
        return fail("draw_mode_hint missing")
    hint_body = hint[1].split("static void enter_wait(void)", 1)[0]
    if 'draw_str_cx_pal("PLEASE SELECT:"' not in hint_body:
        return fail("mode select prompt must be PLEASE SELECT:")
    if "FIRE START" in hint_body:
        return fail("old FIRE START prompt must be gone")
    if 'draw_str_cx_pal("MSX ENHANCED"' not in hint_body:
        return fail("MODE_ORIGINAL entry must be labeled MSX ENHANCED")
    if 'draw_str_cx_pal("ORIGINAL"' in hint_body:
        return fail("old ORIGINAL mode label must be gone")
    if 'draw_str_cx_pal("ZANAC MD"' not in hint_body:
        return fail("second mode entry must stay ZANAC MD")
    confirm = title.split("static void confirm_start(void)", 1)
    if len(confirm) < 2:
        return fail("confirm_start missing")
    confirm_body = confirm[1].split("static void ", 1)[0]
    if "MODE_ORIGINAL" not in confirm_body or "MODE_ZANAC_MD" not in confirm_body:
        return fail("keep MODE_ORIGINAL / MODE_ZANAC_MD (s_sel 0 / 1)")
    if "s_sel == 0" not in confirm_body:
        return fail("s_sel 0 must still start MODE_ORIGINAL")

    hud = HUD_C.read_text()
    hud_h = HUD_H.read_text()
    if "hud_draw_logo();" not in hud:
        return fail("hud_draw_static_labels must stamp the mini logo")
    if "hud_load_logo();" not in hud:
        return fail("hud_init must load hud_logo_tiles")
    if "0x03, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20, 0x03" not in hud:
        return fail("0x4BDF border must stay 8 tiles")
    if "recolor_charset_tile_opaque_bg" in hud:
        return fail("do not opaque-recolor 0x20")
    if 'hud_str_win(HUD_TEXT, hud_y(18), "FIRE ")' not in hud:
        return fail("FIRE must stay MSX row 18")
    if "HUD_TIME_MSX_ROW     24" not in hud_h:
        return fail("TIME must sit at MSX row 24 (moved down for the 6x2)")
    if "HUD_CLOSE_HBAR_ROW   25" not in hud_h:
        return fail("gray closing hbar must sit at MSX row 25")
    if "hud_y(HUD_TIME_MSX_ROW)" not in hud:
        return fail("hud_draw_time must use HUD_TIME_MSX_ROW")
    if "hud_hbar(HUD_CLOSE_HBAR_ROW)" not in hud:
        return fail("closing gray bar must be HUD_CLOSE_HBAR_ROW")
    if "hud_hbar(23)" in hud:
        return fail("do not leave the closing hbar on MSX 23 (that is the gap below the 6x2)")
    if "hud_y(21)" in hud:
        return fail("do not leave TIME on MSX 21 (overlaps the 6x2 MD band)")

    time_fn = hud.split("void hud_draw_time(u8 on, u8 e155)", 1)
    if len(time_fn) < 2:
        return fail("hud_draw_time missing")
    time_body = time_fn[1].split("void hud_draw_player", 1)[0]
    if "hud_draw_logo();" in time_body:
        return fail("TIME no longer overlaps the 6x2 — do not restamp the logo")
    if "hud_border_row(HUD_TIME_MSX_ROW)" not in time_body:
        return fail("TIME off must restore 0x4BDF on TIME's row only")
    if "hud_fill_tile(WINDOW, HUD_TEXT, row, ' ', 6)" in hud:
        return fail("do not space-fill TIME's row — that would erase the logo")

    layout = consts(HUD_H)
    logo_defs = consts(HUD_LOGO_H)
    time_row = layout.get("HUD_TIME_MSX_ROW")
    close_row = layout.get("HUD_CLOSE_HBAR_ROW")
    logo_row = logo_defs.get("HUD_LOGO_MSX_ROW")
    logo_hgt = logo_defs.get("HUD_LOGO_TILE_H")
    if not isinstance(time_row, int) or not isinstance(close_row, int):
        return fail("HUD_TIME_MSX_ROW / HUD_CLOSE_HBAR_ROW must be integers")
    if close_row - time_row > 2 or close_row - time_row < 1:
        return fail("TIME must sit 1 or 2 MSX rows above the gray closing border")
    # Playfield is 192px = screen rows 2-25 (MSX 0-23). Letterbox is 26-27.
    # Do not stamp opaque letter tiles on screen 25 (that steals the last
    # playfield row). TIME/hbar live in the letterbox HUD corner.
    mode = (ROOT / "src" / "mode.c").read_text()
    if "VDP_fillTileMapRect(BG_A, attr, 0, 25," in mode:
        return fail("letterbox must not stamp BG_A screen row 25 (last playfield row)")
    if "VDP_fillTileMapRect(BG_A, attr, 0, 26, MODE_H32_COLS, 2)" not in mode:
        return fail("bottom letterbox stays BG_A screen 26-27 (16px, not playfield)")
    if "VDP_fillTileMapRect(WINDOW, attr, MODE_BAR_COL, 26, MODE_BAR_W, 2)" in mode:
        return fail("do not letterbox-stamp WINDOW over TIME/hbar (screen 26-27)")
    if not isinstance(logo_row, int) or not isinstance(logo_hgt, int):
        return fail("HUD_LOGO_MSX_ROW / HUD_LOGO_TILE_H must be integers")
    fire_last = 19
    gap_above = logo_row - fire_last - 1
    gap_below = time_row - (logo_row + logo_hgt - 1) - 1
    if gap_above != 1 or gap_below != 1:
        return fail("logo must be equidistant: 1 blank above and below the 6x2")

    logo_h = HUD_LOGO_H.read_text()
    # FIRE 18-19, blank 20, 6x2 at 21-22, blank 23, TIME 24, hbar 25.
    if "HUD_LOGO_MSX_ROW    21" not in logo_h:
        return fail("mini logo must sit at MSX row 21 (gap below FIRE, gap above TIME)")
    if "HUD_LOGO_MSX_ROW    17" in logo_h:
        return fail("do not leave the #122 6x1 clip at MSX 17 (ROUND pocket)")
    if "HUD_LOGO_MSX_ROW    16" in logo_h:
        return fail("MSX 16 is the ROUND digit")
    if "HUD_LOGO_MSX_ROW    18" in logo_h:
        return fail("MSX 18 is FIRE")
    if "HUD_LOGO_MSX_ROW    20" in logo_h:
        return fail("MSX 20 is the blank gap above the 6x2, not the logo")
    if "HUD_LOGO_MSX_ROW    22" in logo_h:
        return fail("do not start the 6x2 on MSX 22 (unequal gap / hits TIME)")
    if "HUD_LOGO_MSX_ROW    21" not in HUD_BUILD.read_text():
        return fail("build_hud_logo.py must emit HUD_LOGO_MSX_ROW 21")
    if "TITLE_MD_Y" in logo_h:
        return fail("do not touch title constants from the HUD logo header")
    if "HUD_LOGO_TILE_W     6" not in logo_h or "HUD_LOGO_TILE_H     2" not in logo_h:
        return fail("mini logo must stay 6x2 (HUD interior cols 25-30)")
    if "HUD_LOGO_TILE_H     1" in logo_h:
        return fail("do not leave the #122 6x1 clip as the final mark")
    if "HUD_TILE_BASE + 256" not in logo_h:
        return fail("logo VRAM must sit after the 256-tile charset")
    if "title_md_logo.png" not in logo_h and "title_md_logo.png" not in HUD_BUILD.read_text():
        return fail("mini logo must be derived from res/title_md_logo.png")

    tiles = HUD_LOGO_C.read_text()
    if "const u32 hud_logo_tiles" not in tiles:
        return fail("hud_logo_tiles must be u32 (u8 can start odd → Address error)")
    if "const u8 hud_logo_tiles" in tiles:
        return fail("do not revert hud_logo_tiles to u8")
    m = re.search(r"hud_logo_tiles\[(\d+)\]", tiles)
    if not m or int(m.group(1)) != 96:
        return fail("hud_logo_tiles must be 12*8 = 96 longs (384 bytes, word-aligned)")
    words = [int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{8})", tiles)]
    if len(words) != 96:
        return fail("hud_logo_tiles must list 96 u32 values")
    if tuple(words[:48]) == BROKEN_119 or tuple(words) == BROKEN_119:
        return fail("do not reuse the broken #119 6x1 tile words")
    if tuple(words[:4]) != GOOD_121_HEAD:
        return fail("restore the good #121 6x2 tile data (Zanac band head)")
    if "extern const u32 hud_logo_tiles" not in logo_h:
        return fail("hud_logo.h must export u32 hud_logo_tiles")
    if not (ROOT / "res" / "hud_zanac_md.png").is_file():
        return fail("res/hud_zanac_md.png missing")

    pix = unpack_tiles(words, 6, 2)
    z_blue = md_red = md_green = 0
    for y in range(8):
        row = pix[y * 48:(y + 1) * 48]
        z_blue += sum(1 for v in row if v in (4, 5))
    for y in range(8, 16):
        row = pix[y * 48:(y + 1) * 48]
        md_red += sum(1 for v in row[24:] if v in (6, 8))
        md_green += sum(1 for v in row[24:] if v in (2, 12))
    if z_blue < 80:
        return fail("6x2 top band must carry the Zanac word (blue ink)")
    if md_red < 8 or md_green < 8:
        return fail("6x2 bottom band must carry the MD mark (red + green)")

    print("ok: title Y=40 / groove 12; MD PORT BY SHMUPSBR @ 2026.; "
          "PLEASE SELECT: / MSX ENHANCED / ZANAC MD; 6x2 HUD @ MSX 21")
    return 0


if __name__ == "__main__":
    sys.exit(main())
