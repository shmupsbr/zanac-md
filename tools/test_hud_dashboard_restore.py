#!/usr/bin/env python3
"""Wrap/peek DMA must not punch map through the Original dashboard.

Japan v1 (SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2) 0x4BDF:
  CALL 0x5C28 then INC BC + three JR NZ (disp 0x20) + INC BC + NOP
  = 03 20 20 20 20 20 20 03 at nametable cols 24-31.
Tile 0x20 CT is 70 (bg nibble 0). SCREEN2 bg 0 is R7 black; MD color 0
is transparent, so WINDOW spaces punch to BG_B.

dma_nt_row writes Japan 9a79's 24 playfield cols at x=0 (CPU when
queued, so col 0 cannot drop). Pad dst[24-31] with letter_attr and
restore cols 24-31 AFTER the playfield write (same TransferMethod).
One row x 8 tiles -- not a playfield fill, not a per-tick letterbox.

4898 unsigned X=192..208 (0xC0..0xD0) stays live (< 0xD1). Those
sprites overlap the bar; spr_vis_playfield must hide primary AND
marker on mode_hud_overlap. Do not revert type 36/44/67/umber/veybar
4898 to playfield max_y.

Known-good HUD path (41fd7f9 stripe / 45fc22f 8-tile 4BDF /
92e75c0 charset-0 wipe) stays: WPV=2, wipe from WINDOW row 2,
BG_B cols 24-31, no opaque-recolor 0x20, no playfield-wide letter fill.

Usage (from zanac-md):
    python tools/test_hud_dashboard_restore.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HUD = ROOT / "src" / "hud.c"
MODE = ROOT / "src" / "mode.c"
MAPC = ROOT / "src" / "map_script.c"
ENT = ROOT / "src" / "entity.c"
CT = ROOT / "res" / "charset_ct.bin"
ASM_CANDIDATES = [
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    Path.home() / "zanac-re" / "source" / "zanac.asm",
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
]
JAPAN_V1_SHA1 = "46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2"
BORDER_8 = bytes((0x03, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20, 0x03))
HUD_BAR = 192
SPR_W = 16


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def jr_disp(pc: int, target: int) -> int:
    return (target - (pc + 2)) & 0xFF


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


def load_asm() -> str | None:
    for p in ASM_CANDIDATES:
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    return None


def step_4898_x(x: int, vx: int) -> tuple[int, bool]:
    xpos = ((x & 0xFF) << 8) + (vx & 0xFFFF)
    x = (xpos >> 8) & 0xFF
    return x, x >= 0xD1


def hud_overlap(draw_x: int, width: int = SPR_W) -> bool:
    if draw_x >= HUD_BAR:
        return True
    return draw_x + width > HUD_BAR


def main() -> int:
    fails = 0
    hud = HUD.read_text(encoding="utf-8")
    mode = MODE.read_text(encoding="utf-8")
    map_c = MAPC.read_text(encoding="utf-8")
    ent = ENT.read_text(encoding="utf-8")

    # --- Japan v1 0x4BDF / SCREEN2 CT ---
    inline = bytes(
        (
            0x03,
            0x20,
            jr_disp(0x4BE3, 0x4C05),
            0x20,
            jr_disp(0x4BE5, 0x4C07),
            0x20,
            jr_disp(0x4BE7, 0x4C09),
            0x03,
            0x00,
        )
    )
    if inline != BORDER_8 + b"\x00":
        fail(f"0x4BE2 JR offsets must be 03+six 20+03 00, got {inline.hex(' ')}")
        fails += 1
    else:
        print("  0x4BE2 assembles 03 20 20 20 20 20 20 03 00")

    asm = load_asm()
    if asm:
        if not re.search(r"CALL\s+0x5c28\s*;\s*0x4bdf", asm, re.I):
            fail("zanac.asm 4BDF is not CALL 0x5C28")
            fails += 1
        else:
            print("  ASM 4BDF: CALL 0x5C28 (inline tiles until 00)")
        if not re.search(r"INC\s+BC\s*;\s*0x4be2", asm, re.I):
            fail("zanac.asm 4BE2 is not INC BC")
            fails += 1
        if not re.search(r"JR\s+NZ,\s*LAB_ram_4c05\s*;\s*0x4be3", asm, re.I):
            fail("zanac.asm 4BE3 is not JR NZ 4C05 (disp 0x20)")
            fails += 1
        if not re.search(r"NOP\s*;\s*0x4bea", asm, re.I):
            fail("zanac.asm 4BEA is not NOP terminator")
            fails += 1
        if fails == 0:
            print("  ASM 4BE2..4BEA: INC BC + JR 20 20 x3 + INC BC + NOP")
    else:
        print("  (zanac.asm not on this machine; assembled 4BE2 + C locks)")

    if not CT.is_file():
        fail("res/charset_ct.bin missing")
        fails += 1
    else:
        ct = CT.read_bytes()
        space = ct[0x20 * 8 : 0x20 * 8 + 8]
        if space != bytes([0x70] * 8):
            fail(f"charset 0x20 CT must stay 70 (bg nibble 0), got {space.hex()}")
            fails += 1
        else:
            print("  SCREEN2 CT 0x20 = 70 70 70 70 70 70 70 70 (bg=0)")
        border_ct = ct[0x03 * 8 : 0x03 * 8 + 8]
        if border_ct != bytes([0xE0] * 8):
            fail(f"charset 0x03 CT must stay E0, got {border_ct.hex()}")
            fails += 1
        else:
            print("  SCREEN2 CT 0x03 = E0 (gray on 0)")

    # --- Known-good HUD path (41fd7f9 / 45fc22f / 92e75c0) ---
    if "0x03, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20, 0x03" not in hud:
        fail("hud_draw_border must stay assembled 8-tile 0x4BDF")
        fails += 1
    else:
        print("  hud.c: 8-tile 4BDF 03+six 20+03")
    if "hud_put_win((u16)(HUD_COL + 4), y, 0x03)" in hud:
        fail("do not restore the 5-tile 03 20 20 20 03 border")
        fails += 1
    if "VDP_fillTileMapRect(BG_B, blank, HUD_COL, 0, MODE_BAR_W, 32)" not in hud:
        fail("HUD stripe must still back BG_B cols 24-31")
        fails += 1
    else:
        print("  hud.c: BG_B cols 24-31 letter backing")
    if "VDP_fillTileMapRect(WINDOW, trans, 0, 0, MODE_H32_COLS, 28)" in hud:
        fail("do not write charset 0 into WINDOW letterbox rows 0-1")
        fails += 1
    if "VDP_fillTileMapRect(WINDOW, trans, 0, 2, MODE_H32_COLS, 26)" not in hud:
        fail("hud_wipe WINDOW charset 0 must start at row 2")
        fails += 1
    else:
        print("  hud.c: charset-0 wipe starts at WINDOW row 2")
    if "VDP_setWindowVPos(FALSE, 2)" not in mode:
        fail("WPV must stay 2")
        fails += 1
    else:
        print("  mode.c: WPV=2")
    if "VDP_loadTileData(clear0, 0, 1, CPU)" not in mode:
        fail("tile 0 must stay empty")
        fails += 1
    if "recolor_charset_tile_opaque_bg" in map_c:
        fail("do not opaque-recolor shared 0x20")
        fails += 1
    else:
        print("  KEEP: no opaque-recolor 0x20")
    if "recolor_charset_tile(0x20, charset_ct + 0x20 * 8)" not in map_c:
        fail("space 0x20 must keep ROM CT (bg nibble 0)")
        fails += 1
    if re.search(
        r"VDP_fillTileMapRect\(\s*BG_A\s*,\s*mode_letter_attr\(\)",
        map_c,
    ):
        fail("do not playfield-wide fill BG_A with letter tiles")
        fails += 1
    else:
        print("  KEEP: no playfield-wide letter fill")

    # --- Playfield is Japan 9a79 24 cols at x=0; HUD restore AFTER ---
    dma = fn_span(map_c, "static void dma_nt_row(u8 nt_y, const u8 *src, TransferMethod tm)")
    if not dma:
        fail("dma_nt_row not found")
        fails += 1
    else:
        row_dma = "VDP_setTileMapDataRow(BG_B, dst, nt_y, 0, PF_COLS, play_tm)"
        restore = (
            "VDP_setTileMapDataRow(BG_B, dst + MODE_BAR_COL, nt_y,\n"
            "                              MODE_BAR_COL, MODE_BAR_W, tm)"
        )
        restore_alt = "VDP_setTileMapDataRow(BG_B, dst + MODE_BAR_COL, nt_y"
        if "width = MODE_H32_COLS" in dma:
            fail("32-col wrap DMA left playfield col 0 as leftover 0x28 sky")
            fails += 1
        else:
            print("  dma_nt_row: 24 playfield cols (Japan 9a79 B=0x18)")
        if "mode_letter_attr()" not in dma:
            fail("dma_nt_row must pad HUD cols with mode_letter_attr")
            fails += 1
        else:
            print("  dma_nt_row: pad dst[24-31] with letter_attr")
        if row_dma not in dma:
            fail("dma_nt_row must write 24 playfield cols at x=0")
            fails += 1
        if restore_alt not in dma or "MODE_BAR_COL, MODE_BAR_W, tm)" not in dma:
            fail(
                "dma_nt_row must restore BG_B HUD cols 24-31 AFTER the row DMA "
                "(same tm; 8 tiles, not a playfield fill)"
            )
            fails += 1
        else:
            row_at = dma.find(row_dma)
            rest_at = dma.find(restore_alt)
            if rest_at < 0 or row_at < 0 or rest_at < row_at:
                fail("HUD restore must come after the 24-col playfield write")
                fails += 1
            else:
                print("  dma_nt_row: restore BG_B cols 24-31 after playfield write")
        flip_at = dma.find("s_dma_flip ^= 1")
        rest_at = dma.find(restore_alt)
        if flip_at >= 0 and rest_at >= 0 and flip_at < rest_at:
            fail("do not flip the DMA_QUEUE buffer before the HUD restore")
            fails += 1
        if "VDP_fillTileMapRect(BG_A" in dma:
            fail("dma_nt_row must not fill playfield / letterbox rects")
            fails += 1
        if "mode_draw_letterbox" in dma:
            fail("dma_nt_row must not restamp letterbox (60Hz hitch)")
            fails += 1
        else:
            print("  dma_nt_row: no playfield/letterbox fill (60fps)")
        _ = restore  # documented shape for reviewers

    # --- Sprites: 4898 X 192-208 live, hide on HUD overlap ---
    for x in range(0xC0, 0xD1):
        nx, culled = step_4898_x(x, 0)
        if culled or nx != x:
            fail(f"4898 must keep X={x:#x} (HUD overlap, < 0xD1)")
            fails += 1
            break
    else:
        print("  sim: 4898 X=192..208 live (do not playfield-cull the bar)")
    nx, culled = step_4898_x(0xD0, 0x0100)
    if nx != 0xD1 or not culled:
        fail(f"4898 X 0xD0+1 -> {nx:#x} cull={culled}, want 0xD1 True")
        fails += 1
    else:
        print("  sim: 4898 X>=0xD1 still clears")

    if not hud_overlap(192) or not hud_overlap(177) or hud_overlap(176):
        fail("mode_hud_overlap: x>=192 or x+16>192; x=176 occupies 176-192")
        fails += 1
    else:
        print("  mode_hud_overlap: X=192..208 and X=177..191 overlap the bar")

    vis = fn_span(ent, "static void spr_vis_playfield(Sprite *sp, s16 dx, s16 dy, int want_vis)")
    if not vis or "mode_hud_overlap(dx, MODE_SPR_W)" not in vis:
        fail("spr_vis_playfield must hide on mode_hud_overlap")
        fails += 1
    else:
        print("  spr_vis_playfield: hide on mode_hud_overlap")

    sync = fn_span(ent, "static void spr_sync(Slot *s)")
    if not sync:
        fail("spr_sync not found")
        fails += 1
    else:
        if "spr_vis_playfield(s->spr, dx, dy, 1)" not in sync:
            fail("spr_sync must clip the primary on its own draw box")
            fails += 1
        else:
            print("  spr_sync: primary uses spr_vis_playfield(dx)")
        if "spr_vis_playfield(s->mspr, mdx, mdy, 1)" not in sync:
            fail("spr_sync must clip the marker on its own draw box")
            fails += 1
        else:
            print("  spr_sync: marker uses spr_vis_playfield(mdx)")
        if re.search(r"spr_vis_playfield\(\s*s->mspr,\s*dx,\s*dy", sync):
            fail("complement vis must not use the primary draw box")
            fails += 1

    # --- Do not revert 4898 wrap / KEEP HUD-adjacent ---
    xy = fn_span(ent, "static int step_88_4898(Slot *e)")
    if not xy or "(u8)e->y >= 0xD0" not in xy or "(u8)e->x >= 0xD1" not in xy:
        fail("step_88_4898 must stay unsigned Y>=0xD0 / X>=0xD1")
        fails += 1
    else:
        print("  KEEP: step_88_4898 unsigned Y>=0xD0 / X>=0xD1")
    yonly = fn_span(ent, "static int step_88_y_4898(Slot *e)")
    if not yonly or "(u8)e->y >= 0xD0" not in yonly:
        fail("step_88_y_4898 must stay unsigned Y>=0xD0")
        fails += 1
    else:
        print("  KEEP: step_88_y_4898 unsigned Y>=0xD0")

    upd = fn_span(ent, "static void update_enemies(void)")
    if not upd:
        fail("update_enemies not found")
        fails += 1
    else:
        if "KIND_GROUND" not in upd or "step_88_4898" not in upd:
            fail("type 44 KIND_GROUND 4898 wrap was reverted")
            fails += 1
        else:
            print("  KEEP: type 44 4898 wrap")
        if "KIND_FLASH" not in upd:
            fail("type 36 KIND_FLASH was reverted")
            fails += 1
        else:
            print("  KEEP: type 36 flash group")
        if "KIND_CIRCLE" not in upd:
            fail("type 67 KIND_CIRCLE was reverted")
            fails += 1
        else:
            print("  KEEP: type 67 circle group")
        if "KIND_UMBER" not in upd or "KIND_VEYBAR" not in upd:
            fail("umber/veybar 4898 groups were reverted")
            fails += 1
        else:
            print("  KEEP: umber / veybar 4898 groups")
        if re.search(
            r"if\s*\(\s*!\s*\(\s*e->kind\s*==\s*KIND_EBULLET\s*&&",
            upd,
        ):
            fail("do not close !(KIND_EBULLET && variants) early")
            fails += 1
        else:
            print("  KEEP: ebullet variants stay in the shared tail")

    if "16 - off" not in map_c:
        fail("hidden_wrap_nt_at must be playfield top (screen Y 16 / SAT Y 0)")
        fails += 1
    elif re.search(r"u8 py = \(u8\)\(8 - off\)", map_c):
        fail("hidden_wrap Y=8 is the letterbox row (seam / south lens)")
        fails += 1
    else:
        print("  KEEP: wrap SAT Y=16 == sat_to_nt(0)")
    if "peek_next_row_at((u16)(s_ms.row + 1), (u16)(s_scroll_px + 8))" not in map_c:
        fail("boot peek must be hidden_wrap_nt_at(scroll_px+8) = NT 31")
        fails += 1
    else:
        print("  KEEP: boot peek NT 31 via +8")
    if "0xBFD6" in ent or "0xbfd6" in ent:
        fail("must not CALL 0xBFD6")
        fails += 1
    else:
        print("  KEEP: no 0xBFD6")
    collide = re.search(
        r"static void collide_player\(void\)\s*\{(.*?)^\}",
        ent,
        re.S | re.M,
    )
    if not collide or re.search(r"if\s*\(\s*e->kind == KIND_GROUND\s*\)", collide.group(1)):
        fail("type 44 is 44BA; collide_player must not skip KIND_GROUND")
        fails += 1
    else:
        print("  type 44 44BA: collide_player does not skip KIND_GROUND")

    if fails:
        print(f"{fails} HUD dashboard restore check(s) failed", file=sys.stderr)
        return 1
    print("ok: 4BDF 8-tile + CT bg=0; wrap DMA pads+restores HUD; spr hide")
    return 0


if __name__ == "__main__":
    sys.exit(main())
