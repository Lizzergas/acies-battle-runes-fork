#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void acies_aot_use_community_gateway(bool enabled);
uint64_t acies_aot_community_gateway_secret(uint64_t image_base, uint64_t legacy_locale);

#ifdef __cplusplus
}
#endif
