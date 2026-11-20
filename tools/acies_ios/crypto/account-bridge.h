#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void acies_aot_install_device_info_jni(void);
void acies_aot_install_account_jni(void);
bool acies_aot_take_account_event(const char** native_callback, int32_t* argument);

#ifdef __cplusplus
}
#endif
