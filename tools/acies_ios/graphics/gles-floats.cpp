#include "gles-floats.h"

#include "arm64_context.h"

namespace {

template <typename Signature>
struct Target {
    uint64_t address = 0;

    Signature function() const {
        return reinterpret_cast<Signature>(static_cast<uintptr_t>(address));
    }
};

Target<void (*)(float, float, float, float)> clear_color;
Target<void (*)(float)> clear_depth;
Target<void (*)(float)> line_width;
Target<void (*)(int32_t, float)> uniform_one;
Target<void (*)(int32_t, float, float)> uniform_two;
Target<void (*)(int32_t, float, float, float)> uniform_three;

void clearColor(Arm64Ctx* guest) {
    clear_color.function()(ARC_S_R(guest, 0), ARC_S_R(guest, 1),
                           ARC_S_R(guest, 2), ARC_S_R(guest, 3));
}

void clearDepth(Arm64Ctx* guest) {
    clear_depth.function()(ARC_S_R(guest, 0));
}

void lineWidth(Arm64Ctx* guest) {
    line_width.function()(ARC_S_R(guest, 0));
}

void uniformOne(Arm64Ctx* guest) {
    uniform_one.function()(static_cast<int32_t>(ARC_W_R(guest, 0)), ARC_S_R(guest, 0));
}

void uniformTwo(Arm64Ctx* guest) {
    uniform_two.function()(static_cast<int32_t>(ARC_W_R(guest, 0)),
                           ARC_S_R(guest, 0), ARC_S_R(guest, 1));
}

void uniformThree(Arm64Ctx* guest) {
    uniform_three.function()(static_cast<int32_t>(ARC_W_R(guest, 0)),
                             ARC_S_R(guest, 0), ARC_S_R(guest, 1), ARC_S_R(guest, 2));
}

struct Entry {
    const char* name;
    uint64_t* address;
    ArcCtxFn invoke;
};

const Entry imports[] = {
    {"glClearColor", &clear_color.address, clearColor},
    {"glClearDepthf", &clear_depth.address, clearDepth},
    {"glLineWidth", &line_width.address, lineWidth},
    {"glUniform1f", &uniform_one.address, uniformOne},
    {"glUniform2f", &uniform_two.address, uniformTwo},
    {"glUniform3f", &uniform_three.address, uniformThree},
};

} // namespace

extern "C" size_t acies_aot_register_gles_float_imports(uint64_t (*resolve)(const char*)) {
    size_t registered = 0;
    for (const auto& entry : imports) {
        const uint64_t address = resolve(entry.name);
        if (address) {
            *entry.address = address;
            arc_register_ctx_native(address, entry.name, entry.invoke);
            ++registered;
        }
    }
    return registered;
}
