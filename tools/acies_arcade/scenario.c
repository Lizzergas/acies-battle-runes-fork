/* ARM64 extension for the fingerprinted Acies local client. */
#include <stdint.h>
#include <stdbool.h>

extern char arcade_image_start;
typedef struct {
    float frame[4];
    void (*draw)(void *, void *, void *);
    void (*click)(void *, void *);
} Control;

typedef void (*DrawControl)(void *, void *, void *);
typedef void (*ClickControl)(void *, void *);

extern void *arcade_add_control(void *owner, const Control *control);
extern void arcade_draw_control(void *owner, void *button, void *graphics, const char *caption);

#define EXTENSION_ADDRESS 0x991000
#define STATE_ADDRESS 0x980000
#define TYPES 56
#define LIMIT 24
#define CONTROLS 7
#define DEBUG_TAB 8
#define FN(offset, result, ...) ((result (*)(__VA_ARGS__))(base() + (offset)))

enum { PREVIOUS, NEXT, ADD_BLUE, ADD_RED, PLAY, RESET, CLEAR };
enum { SETUP, PLAY_PENDING, RUNNING, RESET_PENDING };

typedef struct {
    void *map;
    void *buttons[CONTROLS];
    unsigned selected;
    unsigned count[2];
    uint8_t lineup[2][LIMIT];
    unsigned phase;
} Scenario;

static uintptr_t base(void) {
    return (uintptr_t)&arcade_image_start - EXTENSION_ADDRESS;
}

static Scenario *state(void) {
    return (Scenario *)(base() + STATE_ADDRESS);
}

static bool is_range(void *map) {
    return map && *(const uint64_t *)((char *)map + 8) == UINT64_C(0x0000000100000006)
        && *((const uint8_t *)map + 0x2f0) == 30;
}

static void *layer_view(void *layer) {
    void **vtable = *(void ***)layer;
    return ((void *(*)(void *))vtable[0x38 / 8])(layer);
}

static unsigned control_index(Scenario *scenario, void *button) {
    for (unsigned i = 0; i < CONTROLS; ++i)
        if (scenario->buttons[i] == button)
            return i;
    return CONTROLS;
}

/* Generated from game[083].xmf in the same order as the scenario squads. */
#include "roster.h"

static const char *arcade_caption(void *button) {
    Scenario *scenario = state();
    unsigned index = control_index(scenario, button);
    switch (index) {
        case PREVIOUS: return "< Unit";
        case NEXT: return roster[scenario->selected];
        case ADD_BLUE: return team1_labels[scenario->count[0]];
        case ADD_RED: return team2_labels[scenario->count[1]];
        case PLAY:
            return __atomic_load_n(&scenario->phase, __ATOMIC_ACQUIRE) == SETUP ? "Play" : "Battle running";
        case RESET: return "Reset";
        case CLEAR: return "Clear teams";
        default: return "";
    }
}

static void draw_scenario_control(void *owner, void *button, void *graphics) {
    arcade_draw_control(owner, button, graphics, arcade_caption(button));
}

static void arcade_click(void *owner, void *button) {
    (void)owner;
    Scenario *scenario = state();
    unsigned phase = __atomic_load_n(&scenario->phase, __ATOMIC_ACQUIRE);
    switch (control_index(scenario, button)) {
        case PREVIOUS: scenario->selected = (scenario->selected + TYPES - 1) % TYPES; break;
        case NEXT: scenario->selected = (scenario->selected + 1) % TYPES; break;
        case ADD_BLUE:
        case ADD_RED: {
            unsigned side = control_index(scenario, button) - ADD_BLUE;
            if (phase == SETUP && scenario->count[side] < LIMIT)
                scenario->lineup[side][scenario->count[side]++] = (uint8_t)scenario->selected;
            break;
        }
        case PLAY:
            if (phase == SETUP && scenario->count[0] && scenario->count[1])
                __atomic_store_n(&scenario->phase, PLAY_PENDING, __ATOMIC_RELEASE);
            break;
        case RESET:
            if (phase == RUNNING)
                __atomic_store_n(&scenario->phase, RESET_PENDING, __ATOMIC_RELEASE);
            break;
        case CLEAR:
            if (phase == SETUP)
                scenario->count[0] = scenario->count[1] = 0;
            break;
    }
}

void arcade_start(void *map, void *layer) {
    if (is_range(map)) {
        void *view = layer_view(layer);
        if (view) {
            Scenario *scenario = state();
            scenario->map = map;
            scenario->selected = 11; /* Swordsman */
            scenario->count[0] = scenario->count[1] = 0;
            __atomic_store_n(&scenario->phase, SETUP, __ATOMIC_RELEASE);
            float width = FN(0x878100, float, void *)(view);
            float x = (width - 736.0f) * 0.5f;
            for (unsigned i = 0; i < CONTROLS; ++i) {
                Control control = {
                    { x + 184.0f * (float)(i % 4), 72.0f + 40.0f * (float)(i / 4), 180.0f, 37.0f },
                    draw_scenario_control, arcade_click
                };
                scenario->buttons[i] = arcade_add_control(layer, &control);
            }
        }
    }
    FN(0x872030, void, void *, void *)(map, layer);
}

static void show_map_test(void *view) {
    void *screen = FN(0x868a80, void *, unsigned)(0x258);
    FN(0x872630, void, void *)(screen);
    FN(0x868aa0, void *, void *)(screen);
    /* Match the top layer's order so the map picker opens above Options. */
    void *layers = *(void **)((char *)view + 0x28);
    unsigned count = *(unsigned *)((char *)layers + 0x20);
    if (count) {
        void **items = *(void ***)((char *)layers + 0x18);
        *(unsigned *)((char *)screen + 0x200) = *(unsigned *)((char *)items[count - 1] + 0x200);
    }
    FN(0x868ab0, void, void *, void *)(view, screen);
}

static void open_map_test(void *panel, void *button) {
    (void)button;
    void *view = layer_view(panel);
    if (view)
        show_map_test(view);
}

static void draw_arcade_entry(void *owner, void *button, void *graphics) {
    arcade_draw_control(owner, button, graphics, "Arcade");
}

static void draw_map_test_entry(void *owner, void *button, void *graphics) {
    arcade_draw_control(owner, button, graphics, "Map & AI");
}

/* Keep callback addresses out of compiler-generated absolute-address constants. */
static __attribute__((noinline)) void add_debug_action(void *panel, float y, DrawControl draw, ClickControl click) {
    Control control = {{330.0f, y, 180.0f, 37.0f}, draw, click};
    arcade_add_control(panel, &control);
}

static void select_debug(void *options, void *button) {
    (void)button;
    if (*(unsigned *)((char *)options + 0x250) == DEBUG_TAB)
        return;
    /* The native tab switch clears the previous panel even for an unassigned tab. */
    FN(0x875000, void, void *, unsigned)(options, DEBUG_TAB);
    void *panel = *(void **)((char *)options + 0x248);
    add_debug_action(panel, 76.0f, draw_arcade_entry, FN(0x990400, void, void *, void *));
    add_debug_action(panel, 126.0f, draw_map_test_entry, open_map_test);
}

void debug_add_tab(void *options) {
    Control tab = {{0.0f, 470.0f, 300.0f, 70.0f},
                   FN(0x996900, void, void *, void *, void *), select_debug};
    arcade_add_control(options, &tab);
}

void debug_return(void *view, void *map) {
    bool arcade = is_range(map);
    void *lobby = FN(0x868a80, void *, unsigned)(0x2b0);
    FN(0x872600, void, void *, int, int)(lobby, 0, 0);
    FN(0x868aa0, void *, void *)(lobby);
    FN(0x868ab0, void, void *, void *)(view, lobby);
    if (arcade) {
        void *options = FN(0x868a80, void *, unsigned)(0x258);
        FN(0x871e30, void, void *, bool, unsigned)(options, false, 0);
        FN(0x868aa0, void *, void *)(options);
        select_debug(options, 0);
        const float *view_size = (const float *)((const char *)view + 0x5c);
        FN(0x8710e0, void, void *, void *, float, float)(view, options, view_size[0], view_size[1]);
    } else {
        show_map_test(view);
    }
}

static void instruction(uintptr_t offset, void *map, void *thread, const uint8_t *operands) {
    uint16_t *pc = (uint16_t *)(*(char **)((char *)thread + 8) + 2);
    uint16_t saved = *pc;
    FN(offset, void, void *, const uint8_t **, void *)(map, &operands, thread);
    *pc = saved;
}

/* mtAppear receives the side/type squad and a map point index. */
static void spawn(void *map, void *thread, unsigned squad, unsigned point) {
    const uint8_t operands[] = { 1, 0, squad, squad >> 8, 0, 1, 1, 0, point, point >> 8, 0 };
    instruction(0x86dde0, map, thread, operands);
}

static unsigned units_operand(uint8_t *buffer, unsigned side, const Scenario *scenario) {
    bool seen[TYPES];
    for (unsigned i = 0; i < TYPES; ++i)
        seen[i] = false;
    unsigned size = 2;
    buffer[0] = 1; /* Read units by squad. */
    for (unsigned i = 0; i < scenario->count[side]; ++i) {
        unsigned unit = scenario->lineup[side][i];
        if (seen[unit])
            continue;
        seen[unit] = true;
        unsigned id = side * TYPES + unit;
        buffer[size++] = 0;
        buffer[size++] = (uint8_t)id;
        buffer[size++] = (uint8_t)(id >> 8);
    }
    buffer[1] = (uint8_t)((size - 2) / 3);
    return size;
}

void arcade_update(void *map, void *thread) {
    if (!is_range(map) || !thread || !*(void **)((char *)thread + 8))
        return;
    Scenario *scenario = state();
    if (scenario->map != map)
        return;
    unsigned phase = __atomic_load_n(&scenario->phase, __ATOMIC_ACQUIRE);
    if (phase == PLAY_PENDING) {
        /* Scroll all local views to map point zero without a timed wait. */
        const uint8_t scroll[16] = { 0, 1 };
        instruction(0x86df10, map, thread, scroll);
        for (unsigned side = 0; side < 2; ++side)
            for (unsigned i = 0; i < scenario->count[side]; ++i)
                spawn(map, thread, side * TYPES + scenario->lineup[side][i], 1 + side * LIMIT + i);

        for (unsigned side = 0; side < 2; ++side) {
            uint8_t operands[2 + LIMIT * 3 + 9];
            unsigned n = units_operand(operands, side, scenario);
            const unsigned destination = 1 + (1 - side) * LIMIT;
            operands[n++] = 0; operands[n++] = 0; /* Command group */
            operands[n++] = 0; operands[n++] = 0; /* Attack Move */
            operands[n++] = 4; /* Point target independent of the local player's force. */
            operands[n++] = 0; operands[n++] = destination; operands[n++] = 0; operands[n++] = 0;
            instruction(0x57bb94, map, thread, operands);
        }
        __atomic_store_n(&scenario->phase, RUNNING, __ATOMIC_RELEASE);
    } else if (phase == RESET_PENDING) {
        for (unsigned side = 0; side < 2; ++side) {
            uint8_t operands[2 + LIMIT * 3 + 1];
            unsigned n = units_operand(operands, side, scenario);
            operands[n] = 1; /* Remove immediately. */
            instruction(0x57b2cc, map, thread, operands);
        }
        __atomic_store_n(&scenario->phase, SETUP, __ATOMIC_RELEASE);
    }
}
