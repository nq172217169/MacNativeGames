/* Two GameController snapshots through Kirby's host mapping and the guest Npad API. */
#include "../../runtime/gamepad.m"
#include "../../runtime/input.c"
#include <assert.h>
#include <string.h>

_Noreturn void runtime_fail(const char *message) { fprintf(stderr, "%s\n", message); abort(); }
static int handheld;
uint64_t runtime_now_ns(void) { return 1000000000; }
int runtime_handheld_mode(void) { return handheld; }
void runtime_feedback_attach(GCController *c) { (void)c; }
void runtime_feedback_detach(GCController *c) { (void)c; }
void runtime_feedback_quiet(void) {}
void runtime_autoload_user_input(void) {}
void runtime_survey_cancel_user(void) {}
int runtime_survey_command(const char *line) { (void)line; return 0; }
int runtime_output_mode_cycle(void) { return 0; }
int runtime_aspect_toggle(void) { return 0; }
void runtime_shortcut_help_toggle(void) {}
void *runtime_hid_feedback_override(const char *name) { (void)name; return NULL; }
int runtime_hid_feedback_flag(const char *name, int value) { (void)name; (void)value; return 0; }
void dm_gfx_set_flag(const char *name, int value) { (void)name; (void)value; }
void runtime_front_request_close(void) {}
void runtime_swkbd_selftest(void) {}
void runtime_front_text_test(const char *op, const char *text) { (void)op; (void)text; }
void runtime_hle_trace_set(int mode) { (void)mode; }
void runtime_frame_step_pin(double ms) { (void)ms; }
void runtime_dump_threads(void) {}
void dm_gfx_shot_at(long frames, const char *path) { (void)frames; (void)path; }
void dm_gfx_passdump_next(long n) { (void)n; }
void dm_gfx_gpucapture_next(const char *path) { (void)path; }
void dm_gfx_anomdump(void) {}
void dm_gfx_querylog_next(long n) { (void)n; }
void dm_gfx_texdump_next(const char *path) { (void)path; }
void dm_gfx_window_shot(const char *path) { (void)path; }

static NpadState read_pad(uint32_t id) {
    NpadState state;
    full_states(&state, 1, &id);
    return state;
}

int main(int argc, char **argv) { @autoreleasepool {
    unsetenv("TOTK_CONTROLS");
    unsetenv("TOTK_INPUT_LOG");
    unsetenv("TOTK_INPUT_TRACE");
    int fallback = argc > 1 && !strcmp(argv[1], "fallback");
    if (!fallback) unsetenv("TOTK_TWO_PLAYERS");
    controller_map_default(controllerMap, controllerModes);
    GCController *one = [GCController controllerWithExtendedGamepad];
    GCController *two = [GCController controllerWithExtendedGamepad];
    attach_gamepad(one);
    attach_gamepad(two);
    uint32_t ids[] = {0, 1}, handheldID = 0x20;
    initialize();
    supported_ids(ids, 2);
    supported_styles(3);

    ControllerSupportResult result;
    if (fallback) {
        assert(!runtime_gamepad_player2_connected());
        assert(!style(&ids[1]));
        [two.extendedGamepad.leftThumbstick setValueForXAxis:-1 yAxis:0];
        refresh_gamepads();
        assert(read_pad(0).lx == -32767);                  /* every controller still merges into player 1 */
        show_controller_support(&result, NULL);
        assert(result.players == 1 && result.selected == 0);
        puts("pass: TOTK_TWO_PLAYERS=0 fallback");
        return 0;
    }

    assert(runtime_gamepad_player2_connected());
    assert(style(&ids[0]) == 1 && style(&ids[1]) == 1);
    assert(!style(&handheldID));                           /* player 1 must not flicker between ids 0 and 0x20 */

    [two.extendedGamepad.leftThumbstick setValueForXAxis:-1 yAxis:0];
    refresh_gamepads();
    assert(read_pad(0).lx == 0 && read_pad(1).lx == -32767);
    [one.extendedGamepad.leftThumbstick setValueForXAxis:0 yAxis:1];
    refresh_gamepads();
    NpadState p1 = read_pad(0), p2 = read_pad(1);
    assert(p1.ly == 32767 && p2.lx == -32767);

    runtime_input_key_synthetic(38, 1);                    /* keyboard drives player 1 only */
    p1 = read_pad(0); p2 = read_pad(1);
    assert((p1.buttons & 1) && !(p2.buttons & 1));
    runtime_input_key_synthetic(38, 0);
    read_pad(0); read_pad(1);

    RuntimeGamepadState touch = {.connected = 1, .buttons = 8};
    runtime_touch_pad_set(&touch); touch.buttons = 0; runtime_touch_pad_set(&touch);
    p1 = read_pad(0); p2 = read_pad(1);
    assert((p1.buttons & 8) && !(p2.buttons & 8));

    show_controller_support(&result, NULL);
    assert(result.players == 2 && result.selected == 0);

    [two.extendedGamepad.leftShoulder setValue:1]; refresh_gamepads();
    [two.extendedGamepad.leftShoulder setValue:0]; refresh_gamepads();
    p2 = read_pad(1);
    assert(p2.buttons & 64);                               /* L1 -> Switch L on player 2's layout */

    disconnect(&ids[1]);
    assert(!style(&ids[1]) && style(&ids[0]));
    p1 = read_pad(0);
    assert(p1.ly == 32767);                                /* disconnecting P2 leaves P1's stick alone */
    show_controller_support(&result, NULL);                /* the applet reconnects the still-attached controller */
    assert(result.players == 2 && style(&ids[1]));
    supported_ids(ids, 2);
    assert(style(&ids[1]));

    disconnect(&ids[0]);
    assert(!style(&ids[0]) && style(&ids[1]));
    assert(read_pad(1).lx == -32767);                      /* disconnecting P1 leaves P2's stick alone */
    supported_ids(ids, 2);
    assert(style(&ids[0]) && style(&ids[1]));

    puts("pass: Kirby two-player Npad routing");
    return 0;
}}
