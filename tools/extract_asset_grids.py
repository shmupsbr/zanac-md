from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

root = Path(r"C:\Users\Filipe\GitRepos\zanac-md")
out = root / "docs" / "asset-grids"
out.mkdir(parents=True, exist_ok=True)
frames_dir = out / "objs_frames"
frames_dir.mkdir(exist_ok=True)
ship_frames = out / "ship_frames"
ship_frames.mkdir(exist_ok=True)

NAMES = {
0:"SHOT",1:"DUSTER",2:"TERUZO",3:"LUSTER",4:"BOX",5:"CHIP",6:"LEAD",7:"SIG",
8:"SHOT_D",9:"SHOT_T",10:"FIRE",11:"CIRCLE",12:"COMET",13:"DEGID_L",14:"DEGID_R",15:"DEGID",
16:"VEYBAR_0",17:"VEYBAR_1",18:"VEYBAR_2",19:"VEYBAR_3",20:"VEYBAR_4",
21:"VEYBAR_C0",22:"VEYBAR_C1",23:"VEYBAR_C2",24:"VEYBAR_C3",25:"VEYBAR_C4",
26:"DUSTER_C",27:"TERUZO_C",28:"BOX_C",29:"LUSTER_C",30:"UMBER",31:"UMBER_C",
32:"STEALTH",33:"STEALTH_C",34:"SPINNER_0",35:"SPINNER_1",36:"SPINNER_2",37:"SPINNER_3",
38:"SPINNER_C0",39:"SPINNER_C1",40:"SPINNER_C2",41:"SPINNER_C3",
42:"SART",43:"SART_C",44:"LOGA",45:"LOGA_C",46:"PLANE",47:"PLANE_C",
48:"BOLT",49:"LIGHT_BAR",50:"SIG_TRIPLE",51:"SIG_DOUBLE",52:"MED_CIRCLE",
53:"LUSTER_A",54:"LUSTER_A_C",55:"UMBER_B",56:"UMBER_B_C",57:"LOGA_B",58:"LOGA_D",
59:"SNOW",60:"SMALL_STAR",
}

def nearest_font(size):
    for p in [
        r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\cour.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def sheet_grid(src_path, cell_w, cell_h, cols, label_h, scale, names, out_path, save_frames_dir=None):
    src = Image.open(src_path).convert("RGBA")
    n = src.width // cell_w
    rows = (n + cols - 1) // cols
    cell_draw_w = cell_w * scale
    cell_draw_h = cell_h * scale + label_h
    grid = Image.new("RGBA", (cols * cell_draw_w, rows * cell_draw_h), (30, 30, 36, 255))
    draw = ImageDraw.Draw(grid)
    font = nearest_font(max(10, label_h - 4))
    for i in range(n):
        r = i // cols
        c = i % cols
        x0 = c * cell_draw_w
        y0 = r * cell_draw_h
        tile = src.crop((i * cell_w, 0, (i + 1) * cell_w, cell_h))
        if save_frames_dir is not None:
            name = names.get(i, f"F{i:02d}")
            save_frames_dir.mkdir(parents=True, exist_ok=True)
            tile.resize((cell_w * 4, cell_h * 4), Image.NEAREST).save(save_frames_dir / f"{i:02d}_{name}.png")
        big = tile.resize((cell_draw_w, cell_h * scale), Image.NEAREST)
        for yy in range(0, cell_h * scale, 8):
            for xx in range(0, cell_draw_w, 8):
                col = (60, 60, 70, 255) if ((xx // 8) + (yy // 8)) % 2 == 0 else (45, 45, 55, 255)
                draw.rectangle([x0 + xx, y0 + yy, x0 + xx + 7, y0 + yy + 7], fill=col)
        grid.paste(big, (x0, y0), big)
        label = f"{i:02d} {names.get(i, '')}"
        draw.rectangle([x0, y0 + cell_h * scale, x0 + cell_draw_w - 1, y0 + cell_draw_h - 1], fill=(20, 20, 24, 255))
        draw.text((x0 + 2, y0 + cell_h * scale + 1), label[:18], fill=(220, 220, 230, 255), font=font)
        draw.rectangle([x0, y0, x0 + cell_draw_w - 1, y0 + cell_draw_h - 1], outline=(90, 90, 100, 255))
    grid.save(out_path)
    print("wrote", out_path, "frames", n)

sheet_grid(root / "res/sprites/objs.png", 16, 16, 8, 14, 4, NAMES, out / "objs_grid.png", frames_dir)
sheet_grid(root / "res/sprites/ship.png", 16, 16, 4, 14, 8, {0: "SHIP_0", 1: "SHIP_1"}, out / "ship_grid.png", ship_frames)

ship = Image.open(root / "res/sprites/ship.png").convert("RGBA")
ship.resize((ship.width * 8, ship.height * 8), Image.NEAREST).save(out / "ship_full_x8.png")

extras = [
    "res/hud_zanac_md.png",
    "res/title_zanac.png",
    "res/title_mdmark.png",
    "res/title_logo.png",
    "res/title_md_logo.png",
]
for rel in extras:
    p = root / rel
    if not p.exists():
        continue
    im = Image.open(p).convert("RGBA")
    sc = 4 if max(im.size) < 200 else 2
    big = im.resize((im.width * sc, im.height * sc), Image.NEAREST)
    canvas = Image.new("RGBA", (big.width + 2, big.height + 2), (30, 30, 36, 255))
    canvas.paste(big, (1, 1), big)
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, canvas.width - 1, canvas.height - 1], outline=(120, 120, 130, 255))
    canvas.save(out / f"{p.stem}_x{sc}.png")
    print("wrote", p.stem)

raw = (root / "res/charset_tiles.bin").read_bytes()
banks = len(raw) // 2048
cols, tw, th, sc = 32, 8, 8, 3
tiles_per_bank = 256
rows = tiles_per_bank // cols
grid = Image.new("RGB", (cols * tw * sc * banks + (banks - 1) * 8, rows * th * sc + 20), (30, 30, 36))
dr = ImageDraw.Draw(grid)
font = nearest_font(11)
for b in range(min(banks, 4)):
    ox = b * (cols * tw * sc + 8)
    dr.text((ox, 2), f"bank {b}", fill=(200, 200, 210), font=font)
    base = b * 2048
    for t in range(tiles_per_bank):
        if base + t * 8 + 8 > len(raw):
            break
        pat = raw[base + t * 8 : base + t * 8 + 8]
        tile = Image.new("RGB", (8, 8), (0, 0, 0))
        px = tile.load()
        for y in range(8):
            byte = pat[y]
            for x in range(8):
                on = (byte >> (7 - x)) & 1
                px[x, y] = (220, 220, 230) if on else (20, 20, 28)
        big = tile.resize((tw * sc, th * sc), Image.NEAREST)
        r = t // cols
        c = t % cols
        grid.paste(big, (ox + c * tw * sc, 18 + r * th * sc))
grid.save(out / "charset_tiles_grid.png")
print("charset banks", banks)
print("DONE", out)
