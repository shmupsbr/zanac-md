#include <genesis.h>
#include "game.h"
#include "title.h"
#include "mode.h"
#include "sound.h"

/* MSX vblank_isr 0x43DA calls psg_sound_tick 0x4E7B after SAT DMA and
 * scroll_vram_write — once per vblank, never gated on the game loop. */
static void vint_psg(void)
{
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
    DMA_setMaxTransferSize(0);      /* 0 = no cap; ToDefault is 7200 */
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
         *  2/3); identical wrap/peek NT rows skip the 24-col CPU OUT.
         *  Sim never skips a vblank. */
        SPR_update();
        SYS_doVBlankProcess();  /* one wait_one_frame 0x4306 */
        DMA_flushQueue();       /* flush in THAT vblank; never before */
    }

    return 0;
}
