#!/usr/bin/env python3
"""Colour-cycling ebullets must run check_hit_player / player_hit.

Japan v1 (zanac-re SHA1 46e9ed7b7f6dfda8eee266476c9ebc4dd9d8fcc2):

  44A6 ship-only: type 20 (869b), 37 (84fe), 38/41 (85c9), 42/43 after
  they become 0xA5/0xA6. CALL 45A0 then CALL 44D4 (check_hit_player).
  44BA full: type 21 (8659) and 45 (8608) — ship AND shots.

  post_flags already marks 20/37/38/41/42/43 POST_SHIP (no POST_SHOT)
  and 21/45 POST_SHOT|POST_SHIP. Colour-cycle +04 (21 8659 R-nibble|0x80,
  xor_cram), spr_vis_playfield letterbox hide, and s_ebullet_init_ret
  (spawn-visit 4898 skip) are draw / init only. They must not drop the
  ship AABB.

  4560 SAT vs SAT: ship 0x38 is 8x8; lead 0x1C is 4x4; bar 0x18 is 16x6.
  Same SAT XY overlaps. Collision never uses mode_draw_x / sat_col EC.
  Player shots still pass through 44A6 leads and still hit 21/45.

KEEP: type44 44BA; HUD #126; letterbox clip #128; TITLE_MD_Y=40;
fire ABC defaults.

Usage (from zanac-md):
    python tools/test_ebullet_ship_hit.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENT = ROOT / "src" / "entity.c"
PLY = ROOT / "src" / "player.c"
TITLE = ROOT / "inc" / "title_md.h"
OPT = ROOT / "src" / "options.c"
HUD = ROOT / "inc" / "hud.h"
HUD_C = ROOT / "src" / "hud.c"
ASM_CANDIDATES = (
    Path("/tmp/zanac-re/source/zanac.asm"),
    Path("/tmp/refs/zanac-re/source/zanac.asm"),
    Path.home() / "zanac-re" / "source" / "zanac.asm",
    ROOT.parent / "zanac-re" / "source" / "zanac.asm",
)

SHIP_ONLY = (20, 37, 38, 41, 42, 43)
BARS = (21, 45)
ALL_EB = SHIP_ONLY + BARS


def fail(msg: str) -> int:
    print("FAIL:", msg)
    return 1


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


def c_array(src: str, name: str) -> list[int] | None:
    m = re.search(rf"static const u8 {name}\[128\] = \{{([^}}]+)\}}", src)
    if not m:
        return None
    return [int(x, 0) for x in m.group(1).split(",") if x.strip()]


def hitbox(col: list[int], sat: int, x: int, y: int) -> tuple[int, int, int, int]:
    idx = sat >> 1
    hy = min(col[idx], 7)
    hx = min(col[idx + 1] if idx + 1 < len(col) else 7, 7)
    return (x + hx, y + hy, 16 - 2 * hx, 16 - 2 * hy)


def aabb(ax, ay, aw, ah, bx, by, bw, bh) -> bool:
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def post_flags_sim(t: int) -> int:
    """Mirror src/entity.c post_flags (ship/shot bits only)."""
    t &= 0x7F
    post_shot, post_ship = 0x01, 0x02
    if t in (62, 63, 72, 83):
        return post_ship
    if t in SHIP_ONLY:
        return post_ship
    if t in (11, 69, 35, 60, 80, 39, 40, 0):
        return 0
    if t in (70, 71, 81, 82) or 73 <= t <= 79 or 84 <= t <= 89:
        return post_shot
    return post_shot | post_ship


def main() -> int:
    ent = ENT.read_text(encoding="utf-8")
    ply = PLY.read_text(encoding="utf-8")

    for t in SHIP_ONLY:
        pf = post_flags_sim(t)
        if pf != 0x02:
            return fail(f"type {t} must be POST_SHIP only (44A6), got {pf:#x}")
    for t in BARS:
        pf = post_flags_sim(t)
        if pf != 0x03:
            return fail(f"type {t} must be 44BA POST_SHOT|POST_SHIP, got {pf:#x}")
    print("  sim post_flags: 20/37/38/41/42/43 = 44A6; 21/45 = 44BA")

    pf = fn_span(ent, "static u8 post_flags(u8 t)")
    if not pf:
        return fail("post_flags not found")
    if "t == 20 || t == 37 || t == 38 || t == 41 || t == 42 || t == 43" not in pf:
        return fail("post_flags must keep 20/37/38/41/42/43 on POST_SHIP")
    if re.search(r"if \(t == 21 \|\|", pf):
        return fail("type 21 is 44BA; do not 44A6-gate it in post_flags")
    print("  post_flags: 44A6 list is leads/fragments only")

    hits = fn_span(ent, "static int ebullet_hits_player(const Slot *e)")
    if not hits:
        return fail("ebullet_hits_player must exist (44A6/44BA ship gate)")
    for t in ALL_EB:
        if f"t == {t}" not in hits:
            return fail(f"ebullet_hits_player must include type {t}")
    if "KIND_EBULLET" not in hits:
        return fail("ebullet_hits_player is KIND_EBULLET only")
    print("  ebullet_hits_player: 20/21/37/38/41/42/43/45")

    col = fn_span(ent, "static void collide_player(void)")
    if not col:
        return fail("collide_player not found")
    if "ebullet_hits_player" not in col:
        return fail("collide_player must consult ebullet_hits_player")
    if "player_hit()" not in col:
        return fail("hostile overlap must still player_hit (453E / 44D4)")
    if "player_dead() || player_is_over()" not in col:
        return fail("collide_player must skip only dead/over")
    if re.search(r"player_invincible", col):
        return fail("collide_player must not skip on s_invuln")
    if re.search(r"if\s*\(\s*e->kind == KIND_GROUND\s*\)", col):
        return fail("KEEP: type 44 is 44BA; do not skip KIND_GROUND")
    before_hit = col.split("player_hit()")[0]
    if re.search(r"if\s*\(.*HIDDEN", before_hit) or re.search(
        r"if\s*\(.*spr_vis_playfield", before_hit
    ):
        return fail("letterbox / sprite hide must not gate collide_player")
    if re.search(r"if\s*\(.*sat_col", before_hit):
        return fail("sat_col cycle must not skip check_hit_player")
    if re.search(r"if\s*\(.*s_ebullet_init_ret", col):
        return fail("init-RET is update-only; collide_player must still run")
    print("  collide_player: ebullet ship gate; no vis/sat_col/init-ret skip")

    satn = fn_span(ent, "static u8 ebullet_sat_name(const Slot *e)")
    if not satn:
        return fail("ebullet_sat_name not found")
    if "0x18" not in satn or "0x1C" not in satn:
        return fail("ebullet SAT names must stay 0x18 bar / 0x1C lead")
    hit = fn_span(ent, "static int hit_overlap_slot(s16 x1, s16 y1, u8 sat1, const Slot *e)")
    if not hit:
        return fail("hit_overlap_slot not found")
    if "ebullet_sat_name" not in hit:
        return fail("KIND_EBULLET AABB must use ebullet_sat_name, not leftover sat")
    if "mode_draw_x" in hit:
        return fail("4560 must stay SAT vs SAT (no mode_draw_x / EC)")
    print("  hit_overlap_slot: ebullet SAT names; EC is draw-only")

    sizes = c_array(ent, "k_col_size")
    if not sizes or len(sizes) != 128:
        return fail("k_col_size must stay 128 bytes (45C9)")
    ship = hitbox(sizes, 0x38, 0x78, 0xA0)
    lead = hitbox(sizes, 0x1C, 0x78, 0xA0)
    bar = hitbox(sizes, 0x18, 0x78, 0xA0)
    if ship[2:] != (8, 8):
        return fail(f"SAT 0x38 ship hitbox {ship[2:]} want 8x8")
    if lead[2:] != (4, 4):
        return fail(f"SAT 0x1C lead hitbox {lead[2:]} want 4x4")
    if bar[2:] != (16, 6):
        return fail(f"SAT 0x18 bar hitbox {bar[2:]} want 16x6")
    if not aabb(*ship, *lead):
        return fail("ship 0x38 vs lead 0x1C at same SAT XY must overlap")
    if not aabb(*ship, *bar):
        return fail("ship 0x38 vs bar 0x18 at same SAT XY must overlap")
    print("  4560: ship 8x8 overlaps lead 4x4 and bar 16x6")

    takes_s = fn_span(ent, "static int enemy_takes_shots(const Slot *e)")
    if not takes_s:
        return fail("enemy_takes_shots not found")
    if "et == 20 || et == 37 || et == 38 || et == 41 || et == 42 || et == 43" not in takes_s:
        return fail("player shots must still pass through 44A6 ebullets")
    if "return 0" not in takes_s:
        return fail("44A6 ebullets must not take shots")
    print("  KEEP: player shots pass through 20/37/38/41/42/43")

    takes_f = fn_span(ent, "static int enemy_takes_fire(const Slot *e)")
    if not takes_f or "et == 20" not in takes_f:
        return fail("E14E 44A6 fire gate was reverted")
    print("  KEEP: E14E fire vs 44A6")

    vis = fn_span(
        ent, "static void spr_vis_playfield(Sprite *sp, s16 dx, s16 dy, int want_vis)"
    )
    if not vis or "Collision / SAT stay on sim Y" not in vis:
        return fail("letterbox hide must stay draw-only (collision on sim Y)")
    print("  KEEP: letterbox sprite clip is draw-only")

    hitp = fn_span(ply, "void player_hit(void)")
    if not hitp or "s_invuln" not in hitp:
        return fail("player_hit must still no-op on s_invuln (86a4)")
    print("  player_hit: still 86a4 no-op on i-frames")

    asm_path = next((p for p in ASM_CANDIDATES if p.is_file()), None)
    if asm_path:
        asm = asm_path.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"JP\s+0x44a6\s*;\s*0x84fe", asm, re.I):
            return fail("Japan type 37 must JP 44A6 (84fe)")
        if not re.search(r"JP\s+0x44a6\s*;\s*0x869b", asm, re.I):
            return fail("Japan type 20 must JP 44A6 (869b)")
        if "0x44ba" not in asm.lower() and "0x44BA" not in asm:
            return fail("Japan type 21 must reach 44BA")
        print("  zanac.asm: type 37/20 44A6; 44BA present")
    else:
        print("  (zanac.asm not on this machine; C locks only)")

    hud_h = HUD.read_text(encoding="utf-8")
    hud_c = HUD_C.read_text(encoding="utf-8")
    if "HUD_CLOSE_HBAR_ROW   25" in hud_h:
        return fail("KEEP HUD #126: closing hbar must not sit in the letterbox")
    if "hud_hbar(HUD_CLOSE_HBAR_ROW)" not in hud_c and "hud_hbar(23)" not in hud_c:
        return fail("KEEP HUD #126: closing gray hbar at MSX 23")
    print("  KEEP: HUD #126")

    title = TITLE.read_text(encoding="utf-8")
    if "#define TITLE_MD_Y          40" not in title:
        return fail("KEEP: TITLE_MD_Y=40")
    print("  KEEP: TITLE_MD_Y=40")

    opt = OPT.read_text(encoding="utf-8")
    if not re.search(
        r"s_bind\[3\]\s*=\s*\{\s*FIRE_ROLE_BOTH\s*,\s*FIRE_ROLE_PRIMARY\s*,\s*FIRE_ROLE_SECONDARY",
        opt,
    ):
        return fail("KEEP: fire ABC defaults A=both B=primary C=secondary")
    print("  KEEP: fire ABC defaults")

    print("ok: cycling ebullets still run check_hit_player / player_hit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
