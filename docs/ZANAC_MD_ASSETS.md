# Zanac MD — assets e o que podes fazer no Mega Drive

Guia prático para fechar a arte do modo **ZANAC MD**. Números alinhados com `inc/mode_md.h` e `res/resources.res` em `main` (após o cenário 1:1 centrado).

A simulação e o modo **MSX Enhanced** (`MODE_ORIGINAL`) não mudam. Este ficheiro descreve só o que podes redesenhar e como o hardware MD limita o pack.

---

## Objectivo

- Fechar a arte do modo **ZANAC MD** **sem** level design novo.
- **MSX Enhanced / Original não se mexe.** Os packs actuais de `res/sprites/` continuam a servir o Enhanced.
- A simulação continua em espaço MSX **256×192** (eventos, spawns, SAT, E800 de 24 colunas, culls). Só o **desenho** MD muda: H40 320×224, sprites no sítio certo, tileset opcional depois.

Fonte de verdade no código: `inc/mode_md.h` (de/para e constantes), `src/mode.c` (`mode_draw_x` / `mode_draw_y` / `mode_map_dest_cols`), `res/resources.res` (o que o ROM carrega hoje).

---

## Ecrã

| | MSX Enhanced | Zanac MD |
| --- | --- | --- |
| Playfield | 256×192 + HUD à direita (cols 24–31) + letterbox 16px cima/baixo | 320×224 H40 (`MODE_MD_W` × `MODE_MD_H`) |
| Simulação | 256×192 | **igual** — `playfield_w/h` ficam 256×192 |
| Mapa NT | 24 cols de playfield | 24 cols **1:1** centradas (`MODE_MD_X0 = 8`; dest = 8 + col MSX); gutters 0–7 e 32–39 = céu charset **0x28** |
| Plane | H32 (32 de largo) | **64-wide** (`MODE_PLANE_COLS`, `VDP_setPlaneSize(64, 32, TRUE)`) — obrigatório em H40 |
| `y_off` | 16 (letterbox) | 0 (1:1 com a grelha 8px) |
| Window | HUD direita | desligada (`VDP_setWindowOff`) |

Um plano de 32 colunas em H40 enrola as cols 32–39 sobre 0–7: o fill das gutters pinta o lado esquerdo do estágio e as 8 colunas da direita repetem a esquerda. Por isso o modo MD usa plano de 64.

Não duplicar colunas 24→30. Isso alongava o cenário (lixo repetido). Cada coluna MSX ocupa **uma** coluna H40, centrada.

---

## De/para posição

A colisão continua em SAT vs SAT. Só o **desenho** passa por `mode_draw_x` / `mode_draw_y`.

### X (sprites)

1. Aplicar **Early Clock** (bit 7 da cor SAT): hardware TMS desenha em `SAT_X − 32`.
2. Depois escalar **×320/256** (×5/4).

Exemplo (nave): SAT `0x78` com EC (`0x8F`) → visual MSX **88** → MD **110**.

```
x_md ≈ x_msx * 320 / 256
MSX SAT X=0x78 EC → 88 → MD 110
```

### Y (sprites e mapa)

**1:1** com a grelha de 8px. `y_off` MD = 0.

Não fazer ×224/192 no mapa. Isso + duplicar linhas partia o cenário a meio do ecrã (filas do wrap saltadas, overwrite de células vivas). E800 / wrap / peek / VSCROLL ficam na grelha Original de 24 linhas × 8px.

---

## De/para tamanho sprite

A arte actual ainda é placeholder MSX 16×16 (`SPRITE … 2 2` em `resources.res`). O pack MD deve ocupar ~a mesma fracção de ecrã e **snap** a células 8×8 (SGDK 1–4 tiles). Sem escala em runtime.

| MSX E×F | Exacto (C/A , D/B) | Snap sugerido (tiles 8×8) |
| --- | --- | --- |
| 16×16 | 20×18.67 | **24×16** (3×2) ou **24×24** (3×3) |
| 16×8 | 20×9.33 | **24×8** (3×1) |
| 8×8 | 10×9.33 | **16×8** (2×1) ou **8×8** (1×1) |
| 8×16 | 10×18.67 | **16×16** (2×2) |

Constantes: `MODE_MD_SPR_W_EXACT 20`, `MODE_MD_SPR_H_EXACT 18`, snap placeholder `24×16`.

### Nave (ship bank)

Hoje `res/sprites/ship.png` é **32×16**: dois frames 16×16 (pat 14 branco + pat 15 preto). Enhanced desenha os dois (preto no mesmo X, Y+2).

Pack MD: **32×32** (4×4) ou o snap da tabela (24×16 / 24×24). Plano antigo de frames: **neutro + 2 tilt à direita**; no MD usa **flip horizontal** para a esquerda. Não precisas de 2 tilt à esquerda no sheet.

---

## Limites Mega Drive (o que podes usar)

- **80 sprites/frame** de hardware; **~20 por scanline** em H40 (16 em H32). Cuidado com chuva de tiros / bolinhas: o 21.º sprite na linha cai.
- Sprites em células **8×8** até **4×4 tiles (32×32)**. SGDK `SpriteDefinition` (`SPRITE name "…" W H` em tiles 1–4).
- **4 paletas × 16 cores** (CRAM). Índice **0 é transparente** nos sprites. Um sprite = uma paleta.
- Planos **A/B + window**; scroll **por pixel** (já usamos: VSCROLL do mapa + HSCROLL). MD desliga a window; Enhanced usa-a para o HUD.
- **VRAM ~64KB** partilhada entre tiles, mapas e sprites. Packs MD grandes precisam de bank / não carregar tudo de uma vez.
- **Sem `VDP_allocateTiles` para scale em runtime** — o SGDK 2.11 deste projecto nem expõe isso. Arte **pré-sized** no PNG; o ROM só faz upload.

Complementos MSX (`_C`, segundo SAT preto) no Enhanced são um segundo sprite. No pack MD podes **fundir** o preto no mesmo 4bpp (poupa SAT e scanline) — RetroDev liga isso; tu redesenha o par na mesma folha até lá.

---

## Ficheiros actuais (editares estes / clones MD)

`resources.res` hoje aponta **os dois modos** para os mesmos `spr_ship` / `spr_objs` (células 16×16). O pack MD entra por paths **novos** (ver Workflow); o Enhanced fica com estes.

| Ficheiro | Agora | Função | Acção MD |
| --- | --- | --- | --- |
| `res/sprites/objs.png` | **976×16** (61 frames × 16×16). `SPRITE spr_objs … 2 2` | inimigos / tiros / FX | Redesenhar pack MD no snap da tabela. **Não tocar** neste pack Original se o MD for um clone separado |
| `res/sprites/ship.png` | **32×16** (2 frames × 16×16). `SPRITE spr_ship … 2 2` | nave (pat 14 + compl 15) | Pack MD 32×32 ou snap da tabela |
| `res/charset_tiles.bin` + `charset_ct.bin` | charset MSX (256 tiles 4bpp + CT) | tiles do cenário | Tileset MD **opcional depois**; o cenário hoje é **1:1 tiles MSX centrados** |
| `res/map_blob.bin` | mapa / scripts | level | **Não redesenhar o level** — só um tileset novo, se houver |
| `res/hud_zanac_md.png` | **48×16** (preview; não está no `.res`) | logo HUD MD (`tools/build_hud_logo.py` → `hud_logo.c`) | Podes retocar |
| `res/title_*.png` | vários (ver abaixo) | title | Retocar OK |
| `res/sound_blob.bin` | 27 eventos AY | som | Depois (XGM/PCM); Enhanced fica no interpretador PSG |

Title no disco (retocar OK):

| Ficheiro | Tamanho | No `resources.res`? |
| --- | --- | --- |
| `res/title_zanac.png` | 224×56 | sim — `IMAGE title_zanac` |
| `res/title_mdmark.png` | 72×40 | sim — `IMAGE title_mdmark` |
| `res/title_logo.png` | 144×40 | fonte / preview |
| `res/title_md_logo.png` | 224×80 | fonte do logo |
| `res/title_md_source.png` / `title_md_source_old.png` | fontes | não ligar directo |

`logo_tiles.bin` e `bg_late.bin` são overlays MSX do charset (title / fases tardias). Não são o mapa. Não redesenhes `map_blob.bin`.

---

## Frames em objs (lista `FRAME_*` principais)

Definição em `src/entity.c`. `FRAME_N = 61`. O strip é horizontal: frame *i* = pixels `[i*16 .. i*16+16) × 16`.

| Idx | `FRAME_*` | Notas |
| ---: | --- | --- |
| 0 | `SHOT` | tiro nível 0–1 |
| 1 | `DUSTER` | + `DUSTER_C` (26) |
| 2 | `TERUZO` | + `TERUZO_C` (27) |
| 3 | `LUSTER` | Luster B; + `LUSTER_C` (29) |
| 4 | `BOX` | + `BOX_C` (28) |
| 5 | `CHIP` | power chip / type 83 |
| 6 | `LEAD` | bolinha / projéctil pequeno |
| 7 | `SIG` | |
| 8 | `SHOT_D` | tiro duplo |
| 9 | `SHOT_T` | tiro triplo |
| 10 | `FIRE` | alvo fire 0 |
| 11 | `CIRCLE` | círculo grande |
| 12 | `COMET` | |
| 13–15 | `DEGID_L` / `DEGID_R` / `DEGID` | |
| 16–20 | `VEYBAR_0` .. `VEYBAR_4` | + `VEYBAR_C0` .. `C4` (21–25) |
| 26 | `DUSTER_C` | |
| 27 | `TERUZO_C` | |
| 28 | `BOX_C` | |
| 29 | `LUSTER_C` | |
| 30 | `UMBER` | + `UMBER_C` (31) |
| 32 | `STEALTH` | + `STEALTH_C` (33) |
| 34–37 | `SPINNER_0` .. `SPINNER_3` | + `SPINNER_C0` .. `C3` (38–41) |
| 42 | `SART` | + `SART_C` (43) |
| 44 | `LOGA` | + `LOGA_C` (45), `LOGA_B` (57), `LOGA_D` (58) |
| 46 | `PLANE` | + `PLANE_C` (47) |
| 48 | `BOLT` | |
| 49 | `LIGHT_BAR` | |
| 50 | `SIG_TRIPLE` | |
| 51 | `SIG_DOUBLE` | |
| 52 | `MED_CIRCLE` | |
| 53 | `LUSTER_A` | + `LUSTER_A_C` (54) |
| 55 | `UMBER_B` | + `UMBER_B_C` (56) |
| 59 | `SNOW` | fire 3/4 |
| 60 | `SMALL_STAR` | |
| 61 | `FRAME_N` | contagem, não é um gráfico |

Lista curta: `SHOT`, `DUSTER(+C)`, `TERUZO(+C)`, `LUSTER(+C)`, `BOX(+C)`, `CHIP`, `LEAD`, `SIG`, `SHOT_D/T`, `FIRE`, `CIRCLE`, `COMET`, `DEGID_L/R/DEGID`, `VEYBAR_0..4` + `C0..`, `UMBER(+C)`, `STEALTH(+C)`, `SPINNER_0..3` + `C`, `SART(+C)`, `PLANE(+C)`, `LOGA(+C/B/D)`, `BOLT`, `LIGHT_BAR`, `SIG_TRIPLE/DOUBLE`, `MED_CIRCLE`, `LUSTER_A(+C)`, `UMBER_B(+C)`, `SNOW`, `SMALL_STAR`. **`FRAME_N = 61`.**

Muitos voadores = par **colorido + preto** (`_C`). Redesenhar **os dois** (mesmo que o MD depois os funda num 4bpp).

---

## Workflow

1. Copiar/criar `res/sprites/md/` (ou um sheet MD) **sem partir** os paths Original (`res/sprites/ship.png`, `res/sprites/objs.png`).
2. Desenhar na **grelha 8×8**, PNG indexado, **paleta índice 0 = transparente**.
3. Avisar o RetroDev para ligar o pack **só** no modo `MODE_ZANAC_MD` (`ModeAssets` / `mode_init`). Linhas novas no `resources.res` (`SPRITE spr_md_ship` / `spr_md_objs`, `W H` em tiles).
4. Enhanced continua com `objs` / `ship` actuais.

Quando o PNG MD existir, a linha SGDK é do género:

```
SPRITE spr_md_ship "sprites/md/ship.png" 3 2 NONE 0
SPRITE spr_md_objs "sprites/md/objs.png" 3 2 NONE 0
```

(`3 2` = 24×16 se fores no snap 16×16→24×16. Ajusta W H ao tamanho real.)

---

## Fora de âmbito agora

- **Aleste 2**
- Mudar **MSX Enhanced** (lógica, sprites, charset, mapa)
- **Level design novo** (`map_blob.bin` / scripts de ronda)

Tileset MD do cenário pode vir depois; até lá o modo MD mostra os tiles MSX 1:1, centrados, com céu 0x28 nas gutters.
