#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

int acies_aot_game_start(const char* engine, const char* cxx, const char* assets, const char* storage,
                         int width, int height, uint64_t (*resolveGraphics)(const char*),
                         char* output, size_t capacity);
int acies_aot_game_frame(char* output, size_t capacity);
enum AciesTouchPhase {
    AciesTouchBegan,
    AciesTouchMoved,
    AciesTouchEnded,
    AciesTouchCancelled
};
struct AciesTouch {
    int32_t id;
    float x;
    float y;
};
void acies_aot_game_queue_touches(enum AciesTouchPhase phase, const struct AciesTouch* points,
                                 size_t count);
int acies_aot_game_shutdown(char* output, size_t capacity);

#ifdef __cplusplus
}
#endif
