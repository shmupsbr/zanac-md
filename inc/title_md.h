#ifndef TITLE_MD_H
#define TITLE_MD_H

#include <genesis.h>

#define TITLE_MD_W          224
#define TITLE_MD_IMG_H      80
#define TITLE_MD_X          16
#define TITLE_MD_Y          40
#define TITLE_MD_TILE_X     (16 >> 3)
#define TITLE_MD_TILE_Y     (40 >> 3)
#define TITLE_MD_TILE_W     (224 >> 3)
#define TITLE_MD_TILE_H     (80 >> 3)
#define TITLE_MD_PRESS_ROW  17

/* Blue wordmark, scrolled up out of the groove on BG_B. */
#define TITLE_ZANAC_TILE_X  (16 >> 3)
#define TITLE_ZANAC_TILE_Y  (40 >> 3)
#define TITLE_ZANAC_TILE_W  (224 >> 3)
#define TITLE_ZANAC_TILE_H  (56 >> 3)
#define TITLE_ZANAC_TRAVEL  56

/* Static MD mark on BG_A, drawn over the blue. */
#define TITLE_MDMARK_TILE_X ((16 >> 3) + 18)
#define TITLE_MDMARK_TILE_Y ((40 >> 3) + 5)
#define TITLE_MDMARK_TILE_W (72 >> 3)
#define TITLE_MDMARK_TILE_H (40 >> 3)

/* First BG_A row that stays opaque black: the lip of the groove. */
#define TITLE_GROOVE_ROW    ((40 + 56) >> 3)

extern const u16 title_md_palette[16];

#endif
