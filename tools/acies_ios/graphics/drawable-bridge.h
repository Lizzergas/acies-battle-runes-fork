#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void acies_aot_set_drawable_framebuffer(unsigned framebuffer);
uint64_t acies_aot_resolve_drawable_import(const char* name);

#ifdef __cplusplus
}
#endif
