#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Register the float-taking GLES functions at their relocated target addresses.
// Use the resolver supplied to the loader, after its graphics API is ready.
size_t acies_aot_register_gles_float_imports(uint64_t (*resolve)(const char*));

#ifdef __cplusplus
}
#endif
