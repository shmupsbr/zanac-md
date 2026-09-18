#include <genesis.h>
#include "game.h"
#include "title.h"
#include "mode.h"
#include "sound.h"
#include "map_script.h"

/* MSX vblank_isr 0x43DA calls psg_sound_tick 0x4E7B after SAT DMA and
 * scroll_vram_write — once per vblank, never gated on the game loop.
 * MD VSRAM is a vblank port: latch the 1px camera in the sim tick and
 * commit it here so the plane does not stair-step on 8px cell writes. */
static void vint_psg(void)
{
    map_script_apply_vscroll();
    sound_tick();
}

int main(bool hardReset)
{
    (void)hardReset;

    VDP_setScreenWidth320();
    /* Dual-layer 16x16 (primary + 71f6 complement) is 8 tiles each.
     * Default SPR_init is 420 tiles; raise so 24 enemy slots + shots
     * + ship still AUTO_VRAM_ALLOC when the SAT is full. addSprite
     * NULL is an invisible box -- do not invent extra type 4/5/6. */
    SPR_initEx(512);
    /* wait_one_frame 0x4306 is one GINT (E1F8>=1). gameplay_frame_loop
     * 0x407A LD B,1. SGDK DMA auto-flush waits another VBlank when the
     * queue fills -- that is a second retrace and halves the tick rate.
     * Keep autoflush off. Raise the queue/buffer so the 68000 prepares
     * every SAT/complement/tile in the active frame; one flush after
     * the wait copies them in that vblank. Do not drop work. */
    DMA_setAutoFlush(FALSE);
    DMA_setMaxQueueSize(192);       /* default 80; SAT remap + NT + HUD */
    DMA_setBufferSize(16384);       /* default 8192 NTSC; sat_col remap */
    /* NTSC vblank ~7200 B (SGDK default). 0 = unlimited: leftover VRAM
     * DMA runs into the next active display and snows the top ~40px
     * (≈1/5 of 224) — Filipe's chiado. Cap so the flush stays in
     * vblank; remainder waits in the queue (soft colour defer already
     * does this above 4096). Autoflush stays off (extra wait = 30Hz). */
    DMA_setMaxTransferSize(7200);
    DMA_setIgnoreOverCapacity(FALSE);
    mode_init();
    sound_init();
    SYS_setVIntCallback(vint_psg);

    app_state = APP_TITLE;
    title_enter();

    while (TRUE)
    {
        if (app_state == APP_TITLE)
            title_update();
        else
            game_update();

        /* One tick = one GINT. Do not wait before SPR_update (that
         * would hide DMA prep in a second retrace) and do not flush
         * before the wait (autoflush-on / mid-frame flush = 30 Hz).
         * Remaining worst-case (hardware, not a second wait):
         *  20 sprites/line MD SAT flicker (not a dropped logic tick);
         *  type 67/45 SAT-name walk still DMA 128 B/tick (shape, not
         *  colour); kinds that miss the shared XOR CRAM nibble defer
         *  colour DMA when the queue is >=4096 B. Shot/lead/bar tiles
         *  share a VRAM bank after the first upload. Empty-screen
         *  leftover-4 no longer double-assembles (R+1 on leftover
         *  2/3); wrap/peek 24-col rows queue for vblank (not CPU OUT).
         *  Sim never skips a vblank. */
        SPR_update();
        SYS_doVBlankProcess();  /* one wait_one_frame 0x4306 */
        DMA_flushQueue();       /* flush in THAT vblank; never before */
    }

    return 0;
}
