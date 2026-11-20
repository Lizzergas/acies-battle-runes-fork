// A bounded runner for translated Android ELF initialization. The ELF images
// are mapped as data. The guest dispatch table executes compiled Mach-O code.
#include <algorithm>
#include <array>
#include <csetjmp>
#include <chrono>
#include <thread>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <malloc/malloc.h>
#include <pthread.h>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include "elf_image.h"
#include "icu-adapter.h"
#include "game-lifecycle.h"
#include "gles-floats.h"
#include "offline-imports.h"
#if defined(ACIES_GATEWAY_BRIDGE)
#include "gateway-imports.h"
#endif
#if defined(ACIES_CRYPTO_BRIDGE)
#include "crypto-bridge.h"
#include "account-bridge.h"
#endif
#if defined(ACIES_LOCAL_ADMISSION)
#include "local-admission.h"
#endif
#if defined(ACIES_FONT_BRIDGE)
#include "font-bridge.h"
#endif
#if defined(ACIES_MAC_ANGLE)
#include "angle-host.h"
#endif
#include "jni_env.h"
#include "lifted.h"
#include "shim.h"

namespace {

struct TouchEvent {
    AciesTouchPhase phase;
    std::vector<AciesTouch> points;
};

struct State {
    arc::ElfImage cxx;
    arc::ElfImage engine;
    std::vector<uint8_t> gameStack;
    uint64_t gameStackTop = 0;
    bool gameStarted = false;
    std::vector<TouchEvent> touches;
};

uint64_t (*resolveGraphicsImport)(const char*) = nullptr;
extern "C" int acies_take_android_permissions_result();
extern "C" unsigned acies_take_unavailable_android_services();
extern "C" void acies_set_touch_arrays(uint64_t handles[3], const int32_t* ids,
                                       const float* xs, const float* ys, uint32_t count);

std::unique_ptr<State> images;

void freeWithGuestDiagnostic(Arm64Ctx* context) {
    const auto pointer = context->x[0];
    const auto available = pointer ? malloc_size(reinterpret_cast<void*>(pointer)) : 0;
    if (pointer && available == 0) {
        const auto stackStart = reinterpret_cast<uint64_t>(images->gameStack.data());
        const auto stackEnd = stackStart + images->gameStack.size();
        const auto hostTop = reinterpret_cast<uint64_t>(pthread_get_stackaddr_np(pthread_self()));
        const auto hostBottom = hostTop - pthread_get_stacksize_np(pthread_self());
        const bool onGuestStack = stackStart && pointer >= stackStart && pointer < stackEnd;
        const bool onCurrentHostStack = pointer >= hostBottom && pointer < hostTop;
        std::fprintf(stderr,
            "[guest free] ptr=%#llx slot19=%#llx sp=%#llx fp=%#llx lr=%#llx guestStack=%d currentHostStack=%d jni=%d\n",
            (unsigned long long)pointer, (unsigned long long)context->x[19],
            (unsigned long long)context->sp, (unsigned long long)context->x[29],
            (unsigned long long)context->x[30], int(onGuestStack), int(onCurrentHostStack),
            arc_jni_owns(pointer));
        bool arrayDestructor = false;
        for (size_t i = 0; i < arc_frame_count(); ++i) {
            const auto frame = arc_frame_at(i);
            std::fprintf(stderr, "[guest free] frame[%zu]=%#llx\n", i, (unsigned long long)frame);
            if (i < 4 && (frame == 0x550acc || frame == 0x550b04)) arrayDestructor = true;
        }
        const auto object = context->x[19];
        if (arrayDestructor && object) {
            uint64_t backing;
            uint32_t count, capacity;
            std::memcpy(&backing, reinterpret_cast<void*>(object + 0x18), sizeof backing);
            std::memcpy(&count, reinterpret_cast<void*>(object + 0x20), sizeof count);
            std::memcpy(&capacity, reinterpret_cast<void*>(object + 0x24), sizeof capacity);
            std::fprintf(stderr, "[guest free] CSArray this=%#llx backing=%#llx count=%u capacity=%u\n",
                         (unsigned long long)object, (unsigned long long)backing, count, capacity);
        }
        std::fflush(stderr);
    }
    auto original = reinterpret_cast<void (*)(void*)>(arc::ShimResolve("free"));
    original(reinterpret_cast<void*>(pointer));
}


#if defined(ACIES_MAC_ANGLE)
void* traceAssetOpen(void* manager, const char* name, int mode) {
    auto real = reinterpret_cast<void* (*)(void*, const char*, int)>(
        arc::ShimResolveAsset("AAssetManager_open"));
    void* result = real(manager, name, mode);
    std::fprintf(stderr, "[asset-path] %s %s\n", result ? "read" : "miss", name);
    return result;
}

void* traceAssetDir(void* manager, const char* name) {
    auto real = reinterpret_cast<void* (*)(void*, const char*)>(
        arc::ShimResolveAsset("AAssetManager_openDir"));
    void* result = real(manager, name);
    std::fprintf(stderr, "[asset-path] %s %s\n", result ? "directory" : "missing-dir", name);
    return result;
}
#endif

uint64_t base(const arc::ElfImage& image) {
    return reinterpret_cast<uint64_t>(image.base());
}

bool owns(const arc::ElfImage& image, uint64_t address) {
    return address >= base(image) && address - base(image) < image.span();
}

bool stepWithArguments(uint64_t target, uint64_t stack_top, const std::array<uint64_t, 8>& arguments,
                       uint64_t *value, float x = 0, float y = 0) {
    Arm64Ctx context{};
    context.image_base = base(images->engine);
    context.sp = stack_top;
    std::copy(arguments.begin(), arguments.end(), context.x);
    arc_s_w(&context, 0, x);
    arc_s_w(&context, 1, y);
    jmp_buf recovery;
    arc_set_recovery(&recovery);
    if (setjmp(recovery) != 0) {
        arc_set_recovery(nullptr);
        return false;
    }
    arc_dispatch(&context, target);
    arc_set_recovery(nullptr);
    *value = context.x[0];
    return true;
}

bool step(uint64_t target, uint64_t stack_top, uint64_t argument, uint64_t *value,
          uint64_t second = 0, uint64_t third = 0, uint64_t fourth = 0) {
    return stepWithArguments(target, stack_top, {argument, second, third, fourth}, value);
}
}

extern "C" int acies_aot_boot_probe(const char* engine_path, const char* cxx_path,
                                    char* output, size_t capacity) {
    if (images) {
        std::snprintf(output, capacity, "The boot probe is single-use per process.");
        return 1;
    }
    if (std::strcmp(arc_image_name(0), "libcdkapp.so") != 0 ||
        std::strcmp(arc_image_name(1), "libc++_shared.so") != 0) {
        std::snprintf(output, capacity, "Unexpected lifted image table.");
        return 1;
    }

    if (!aciesConfigureICU()) {
        std::snprintf(output, capacity, "Darwin ICU could not be initialized.");
        return 1;
    }

    images = std::make_unique<State>();
    std::string error;
    auto resolve = [](const char* name) -> uint64_t {
        if (std::getenv("ACIES_TRACE_GUEST_FREE") && std::strcmp(name, "free") == 0)
            return reinterpret_cast<uint64_t>(&freeWithGuestDiagnostic);
#if defined(ACIES_MAC_ANGLE)
        if (std::getenv("ACIES_TRACE_ASSET_PATHS")) {
            if (std::strcmp(name, "AAssetManager_open") == 0)
                return reinterpret_cast<uint64_t>(&traceAssetOpen);
            if (std::strcmp(name, "AAssetManager_openDir") == 0)
                return reinterpret_cast<uint64_t>(&traceAssetDir);
        }
#endif
#if defined(ACIES_GATEWAY_BRIDGE)
        if (auto address = aciesResolveGatewayImport(name)) return address;
#endif
        if (auto address = aciesResolveOfflineImport(name)) return address;
        if (auto address = aciesResolveICUImport(name)) return address;
        if (resolveGraphicsImport) {
            if (auto address = resolveGraphicsImport(name)) return address;
        }
        if (auto address = arc::ShimOverride(name)) return address;
        if (auto address = images->cxx.Lookup(name)) return address;
        return arc::ShimResolve(name);
    };
    if (!images->cxx.Load(cxx_path, resolve, &error)) {
        std::snprintf(output, capacity, "C++ runtime map failed (%s).", error.c_str());
        return 1;
    }
    arc::ShimRegisterImage(&images->cxx);
    arc_set_image(1, base(images->cxx), images->cxx.span());
    if (!images->engine.Load(engine_path, resolve, &error)) {
        std::snprintf(output, capacity, "ACIES engine map failed (%s).", error.c_str());
        return 1;
    }
    arc::ShimRegisterImage(&images->engine);
    arc_set_image(0, base(images->engine), images->engine.span());

    size_t unresolved = 0;
    for (const auto* image : {&images->cxx, &images->engine}) {
        for (const auto& entry : image->imports()) {
            if (!entry.resolved) {
                ++unresolved;
            } else if (!owns(images->cxx, entry.bound_to) &&
                       !owns(images->engine, entry.bound_to)) {
                arc_register_native(entry.bound_to, entry.name.c_str());
            }
        }
    }
    arc_jni_register();
    if (std::getenv("ACIES_TRACE_GUEST_FREE"))
        arc_register_ctx_native(reinterpret_cast<uint64_t>(&freeWithGuestDiagnostic),
                                "free", &freeWithGuestDiagnostic);
#if defined(ACIES_FONT_BRIDGE)
    acies_aot_install_font_jni();
#endif
#if defined(ACIES_LOCAL_ADMISSION)
    aciesInstallLocalAdmissionJNI();
#endif
#if defined(ACIES_CRYPTO_BRIDGE)
    acies_aot_install_crypto_jni();
    acies_aot_install_device_info_jni();
#endif
    arc::ShimRegisterVarargs();
    if (resolveGraphicsImport) acies_aot_register_gles_float_imports(resolve);
    arc_set_image_base(base(images->engine));

    const auto& constructors = images->engine.init_array();
    if (constructors.size() != 22) {
        std::snprintf(output, capacity, "Expected 22 engine constructors, found %zu.",
                      constructors.size());
        return 1;
    }
    std::vector<uint8_t> guest_stack(1024 * 1024);
    const auto stack_top = (reinterpret_cast<uint64_t>(guest_stack.data()) +
                            guest_stack.size() - 4096) & ~UINT64_C(15);

    uint64_t value = 0;
    for (size_t index = 0; index < constructors.size(); ++index) {
        if (!owns(images->engine, constructors[index]) ||
            !step(constructors[index], stack_top, 0, &value)) {
            std::snprintf(output, capacity, "Constructor %zu stopped (%s).",
                          index, arc_last_trap());
            return 1;
        }
    }
    const uint64_t on_load = images->engine.Lookup("JNI_OnLoad");
    if (!owns(images->engine, on_load) ||
        !step(on_load, stack_top, arc_jni_vm(), &value)) {
        std::snprintf(output, capacity, "JNI_OnLoad stopped (%s).", arc_last_trap());
        return 1;
    }
    std::snprintf(output, capacity,
                  "ACIES AOT INIT %s: %zu/22 constructors, JNI_OnLoad=0x%08llx, %zu unresolved imports",
                  value == UINT64_C(0x10006) ? "PASS" : "FAIL", constructors.size(),
                  static_cast<unsigned long long>(value), unresolved);
    return value == UINT64_C(0x10006) ? 0 : 1;
}

extern "C" int acies_aot_asset_probe(const char* engine_path, const char* cxx_path,
                                     const char* asset_root, const char* storage,
                                     char* output, size_t capacity) {
    const std::string archive_path = std::string(asset_root) + "/version.xmf";
    std::ifstream archive(archive_path, std::ios::binary);
    const std::vector<char> expected((std::istreambuf_iterator<char>(archive)),
                                    std::istreambuf_iterator<char>());
    if (expected.empty()) {
        std::snprintf(output, capacity, "Could not read reference version.xmf.");
        return 1;
    }

    arc::ShimSetAssetRoot(asset_root);
    if (acies_aot_boot_probe(engine_path, cxx_path, output, capacity) != 0) return 1;
    uint64_t value = 0;
    std::vector<uint8_t> stack(1024 * 1024);
    const auto stack_top = (reinterpret_cast<uint64_t>(stack.data()) +
                            stack.size() - 4096) & ~UINT64_C(15);
    const uint64_t init = images->engine.Lookup("_ZN6CSFile10initializeEPvPKc");
    if (!owns(images->engine, init) ||
        !step(init, stack_top, arc_jni_object(), &value,
              reinterpret_cast<uint64_t>(storage))) {
        std::snprintf(output, capacity, "CSFile::initialize failed (%s).", arc_last_trap());
        return 1;
    }

    const auto raw = images->engine.Lookup("_ZN6CSFile26createRawWithContentOfFileEPKcjRjb");
    if (!owns(images->engine, raw)) return 1;
    const char* name = "assets/version.xmf";
    for (const auto offset : {0u, 17u}) {
        uint32_t length = offset == 0 ? 0 : 127;
        const size_t expected_length = offset == 0 ? expected.size() : length;
        if (!step(raw, stack_top, reinterpret_cast<uint64_t>(name), &value, offset,
                  reinterpret_cast<uint64_t>(&length), 0) || !value) {
            std::snprintf(output, capacity, "CSFile asset read failed at %u (%s).",
                          offset, arc_last_trap());
            return 1;
        }
        void* bytes = reinterpret_cast<void*>(value);
        const bool same = length == expected_length && offset + length <= expected.size() &&
                          std::memcmp(bytes, expected.data() + offset, length) == 0;
        auto release = reinterpret_cast<void (*)(void*)>(arc::ShimResolve("free"));
        release(bytes);
        if (!same) {
            std::snprintf(output, capacity, "CSFile bytes differ at offset %u.", offset);
            return 1;
        }
    }
    const char* boot_report = output;
    std::string boot(boot_report);
    std::snprintf(output, capacity, "%s\nACIES AOT ASSET PASS: %zu exact bytes and a seek/read matched.",
                  boot.c_str(), expected.size());
    return 0;
}

extern "C" int acies_aot_icu_probe(const char* engine_path, const char* cxx_path,
                                  char* output, size_t capacity) {
    if (acies_aot_boot_probe(engine_path, cxx_path, output, capacity) != 0) return 1;
    uint64_t value = 0;
    std::vector<uint8_t> stack(1024 * 1024);
    const auto stack_top = (reinterpret_cast<uint64_t>(stack.data()) +
                            stack.size() - 4096) & ~UINT64_C(15);
    const auto copy = images->engine.Lookup("u_strncpy");
    const char16_t original[] = u"ACIES 안녕";
    char16_t copied[sizeof(original) / sizeof(original[0])]{};
    if (!owns(images->engine, copy) ||
        !step(copy, stack_top, reinterpret_cast<uint64_t>(copied), &value,
              reinterpret_cast<uint64_t>(original), std::size(original))) {
        std::snprintf(output, capacity, "Guest u_strncpy stopped (%s).", arc_last_trap());
        return 1;
    }
    if (value != reinterpret_cast<uint64_t>(copied) ||
        std::memcmp(original, copied, sizeof(original)) != 0) {
        std::snprintf(output, capacity, "Guest u_strncpy returned unexpected UTF-16.");
        return 1;
    }
    const std::string boot(output);
    std::snprintf(output, capacity, "%s\nACIES AOT ICU PASS: original u_strncpy preserved Korean UTF-16.",
                  boot.c_str());
    return 0;
}

extern "C" int acies_aot_game_start(const char* engine_path, const char* cxx_path,
                                     const char* asset_root, const char* storage,
                                     int width, int height, uint64_t (*graphics)(const char*),
                                     char* output, size_t capacity) {
    if (images || !graphics || width <= 0 || height <= 0) {
        std::snprintf(output, capacity, "ACIES game startup prerequisites are missing.");
        return 1;
    }
    // The isolated compatibility probe provides no attestation response.
    setenv("ARC_NIMBLE_CALLBACK", "off", 1);
    resolveGraphicsImport = graphics;
    arc::ShimSetAssetRoot(asset_root);
    if (acies_aot_boot_probe(engine_path, cxx_path, output, capacity) != 0) return 1;
    images->gameStack.resize(1024 * 1024);
    images->gameStackTop = (reinterpret_cast<uint64_t>(images->gameStack.data()) +
                             images->gameStack.size() - 4096) & ~UINT64_C(15);
    auto* stackArgs = reinterpret_cast<uint64_t*>(images->gameStackTop);
    stackArgs[0] = arc_jni_object();
    stackArgs[1] = arc_jni_string(storage);
    const auto start = images->engine.Lookup("Java_kr_co_brgames_cdk_CSView_nativeStart");
    const uint64_t w = width;
    const uint64_t h = height;
    uint64_t value = 0;
    if (!owns(images->engine, start) ||
        !stepWithArguments(start, images->gameStackTop,
                           {arc_jni_env(), arc_jni_object(), w, h, w, h, 0, 0}, &value)) {
        std::snprintf(output, capacity, "ACIES AOT nativeStart stopped (%s).", arc_last_trap());
        return 1;
    }
    images->gameStarted = true;
    const std::string boot(output);
    std::snprintf(output, capacity, "%s\nACIES AOT NATIVE START PASS", boot.c_str());
    return 0;
}

extern "C" void acies_aot_game_queue_touches(AciesTouchPhase phase, const AciesTouch* points,
                                            size_t count) {
    if (!images || !images->gameStarted || !points || count == 0 || count > 32) return;
    images->touches.push_back({phase, {points, points + count}});
}

namespace {
bool dispatchQueuedTouches() {
    auto events = std::move(images->touches);
    images->touches.clear();
    for (const auto& event : events) {
        const char* method = nullptr;
        switch (event.phase) {
            case AciesTouchBegan: method = "Java_kr_co_brgames_cdk_CSView_nativeTouchesBegan"; break;
            case AciesTouchMoved: method = "Java_kr_co_brgames_cdk_CSView_nativeTouchesMoved"; break;
            case AciesTouchEnded: method = "Java_kr_co_brgames_cdk_CSView_nativeTouchesEnded"; break;
            case AciesTouchCancelled: method = "Java_kr_co_brgames_cdk_CSView_nativeTouchesCancelled"; break;
        }
        const auto target = method ? images->engine.Lookup(method) : 0;
        if (!owns(images->engine, target)) return false;
        uint64_t value = 0;
        if (event.phase == AciesTouchBegan || event.phase == AciesTouchEnded) {
            for (const auto& point : event.points) {
                if (!stepWithArguments(target, images->gameStackTop,
                                       {arc_jni_env(), arc_jni_object(), uint64_t(point.id)},
                                       &value, point.x, point.y)) return false;
            }
            continue;
        }
        std::array<int32_t, 32> ids{};
        std::array<float, 32> xs{}, ys{};
        for (size_t i = 0; i < event.points.size(); ++i) {
            ids[i] = event.points[i].id;
            xs[i] = event.points[i].x;
            ys[i] = event.points[i].y;
        }
        uint64_t handles[3];
        acies_set_touch_arrays(handles, ids.data(), xs.data(), ys.data(), event.points.size());
        const bool handled = stepWithArguments(target, images->gameStackTop,
                           {arc_jni_env(), arc_jni_object(), handles[0], handles[1], handles[2]},
                           &value);
        acies_set_touch_arrays(handles, nullptr, nullptr, nullptr, 0);
        if (!handled) return false;
    }
    return true;
}
}

#if defined(ACIES_LOCAL_ADMISSION)
namespace {
bool deliverLocalAdmissionReplies() {
    std::vector<LocalAdmissionReply> ready;
    ready.reserve(16);
    LocalAdmissionReply reply;
    while (ready.size() < 16 && aciesTakeLocalAdmissionReply(reply)) {
        ready.push_back(std::move(reply));
    }
    // Callbacks may synchronously queue retries. These belong to the next
    // display tick, just as on Android's event queue.
    for (const LocalAdmissionReply& reply : ready) {
        if (!aciesLocalReplyStillActive(reply.target)) continue;
        uint64_t value = 0;
        auto invoke = [&](const char* name, uint64_t argument = 0) {
            const auto function = images->engine.Lookup(name);
            return owns(images->engine, function) &&
                   step(function, images->gameStackTop, arc_jni_env(), &value,
                        arc_jni_object(), reply.target, argument);
        };
        if (!reply.status) {
            if (!invoke("Java_kr_co_brgames_cdk_CSURLConnectionBridge_nativeError")) return false;
            continue;
        }
        if (!invoke("Java_kr_co_brgames_cdk_CSURLConnectionBridge_nativeReceiveResponse",
                    reply.status)) return false;
        if (!aciesLocalReplyStillActive(reply.target)) continue;
        const uint64_t body = aciesSetLocalAdmissionByteArray(&reply.body);
        const bool accepted = invoke("Java_kr_co_brgames_cdk_CSURLConnectionBridge_nativeReceiveData",
                                     body);
        aciesSetLocalAdmissionByteArray(nullptr);
        if (!accepted) return false;
        if (!aciesLocalReplyStillActive(reply.target)) continue;
        if (!invoke("Java_kr_co_brgames_cdk_CSURLConnectionBridge_nativeFinishLoading")) return false;
        std::fprintf(stderr, "[local HTTP] delivered HTTP %d, %zu bytes to original callbacks\n",
                     reply.status, reply.body.size());
    }
    return true;
}
}
#endif

extern "C" int acies_aot_game_frame(char* output, size_t capacity) {
    if (!images || !images->gameStarted) return 1;
    uint64_t value = 0;
    const unsigned services = acies_take_unavailable_android_services();
    const struct {unsigned flag; const char* method; unsigned code;} unavailable[] = {
        {1u, "Java_kr_co_brgames_cdk_extension_CSGooglePlay_nativeLoginResult", 2u},
        {2u, "Java_kr_co_brgames_cdk_extension_CSGoogleIAP_nativeError", 3u},
    };
    for (const auto& service : unavailable) {
        if (!(services & service.flag)) continue;
        const auto callback = images->engine.Lookup(service.method);
        if (!owns(images->engine, callback) ||
            !step(callback, images->gameStackTop, arc_jni_env(), &value, arc_jni_object(),
                  service.code)) {
            std::snprintf(output, capacity, "ACIES AOT Android service callback stopped (%s).",
                          arc_last_trap());
            return 1;
        }
    }
#if defined(ACIES_LOCAL_ADMISSION)
    if (!deliverLocalAdmissionReplies()) {
        std::snprintf(output, capacity, "Original local admission callback stopped (%s).",
                      arc_last_trap());
        return 1;
    }
#endif
    const int permissions = acies_take_android_permissions_result();
    if (permissions >= 0) {
        const auto checkDone = images->engine.Lookup(
            "Java_kr_co_brgames_cdk_extension_CSAndroidPermissions_nativeCheckDone");
        if (!owns(images->engine, checkDone) ||
            !step(checkDone, images->gameStackTop, arc_jni_env(), &value, arc_jni_object(),
                  static_cast<uint64_t>(permissions))) {
            std::snprintf(output, capacity, "ACIES AOT Android permission callback stopped (%s).",
                          arc_last_trap());
            return 1;
        }
        std::fprintf(stderr, "ACIES AOT Android package permission callback completed (%d).\n",
                     permissions);
    }
    if (!dispatchQueuedTouches()) {
        std::snprintf(output, capacity, "ACIES AOT original touch callback stopped (%s).",
                      arc_last_trap());
        return 1;
    }
    const auto tick = images->engine.Lookup("Java_kr_co_brgames_cdk_CSView_nativeTimeout");
    if (!owns(images->engine, tick) ||
        !step(tick, images->gameStackTop, arc_jni_env(), &value, arc_jni_object())) {
        std::snprintf(output, capacity, "ACIES AOT nativeTimeout stopped (%s).", arc_last_trap());
        return 1;
    }
    return 0;
}

extern "C" int acies_aot_game_shutdown(char* output, size_t capacity) {
    if (!images || !images->gameStarted) return 1;
    images->gameStarted = false;
    uint64_t value = 0;
    const auto destroy = images->engine.Lookup("Java_kr_co_brgames_cdk_CSView_nativeDestroy");
    if (!owns(images->engine, destroy) ||
        !step(destroy, images->gameStackTop, arc_jni_env(), &value, arc_jni_object())) {
        std::snprintf(output, capacity, "ACIES AOT nativeDestroy stopped (%s).", arc_last_trap());
        return 1;
    }
    std::snprintf(output, capacity, "ACIES AOT NATIVE DESTROY PASS");
    return 0;
}

#if defined(ACIES_MAC_ANGLE)
extern "C" int acies_aot_native_start_probe(const char* engine_path, const char* cxx_path,
                                           const char* asset_root, const char* storage,
                                           char* output, size_t capacity) {
    if (!aciesConfigureAngle()) {
        std::snprintf(output, capacity, "Could not open Mac ANGLE context.");
        return 1;
    }
    if (acies_aot_game_start(engine_path, cxx_path, asset_root, storage, 1280, 720,
                             aciesResolveAngleImport, output, capacity)) return 1;
    std::fprintf(stderr, "%s\n", output);
    auto readPixels = reinterpret_cast<void (*)(int, int, int, int, unsigned, unsigned, void*)>(
        aciesResolveAngleImport("glReadPixels"));
    auto getError = reinterpret_cast<unsigned (*)()>(aciesResolveAngleImport("glGetError"));
    std::vector<uint8_t> rgba(1280 * 720 * 4);
    const std::string framePath = std::string(storage) + "/frame.ppm";
    const auto* count = std::getenv("ACIES_PROBE_FRAMES");
    const unsigned frameCount = count ? std::max(1, std::atoi(count)) : 120;
    const auto* commands = std::getenv("ACIES_PROBE_TAP_FILE");
    std::streamoff commandsOffset = 0;
    int32_t commandId = 2000;
    for (unsigned tick = 0; tick < frameCount; ++tick) {
        if (commands && tick % 5 == 0) {
            std::ifstream touchCommands(commands);
            touchCommands.seekg(commandsOffset);
            std::string line;
            while (std::getline(touchCommands, line) && !touchCommands.eof()) {
                commandsOffset += static_cast<std::streamoff>(line.size() + 1);
                std::istringstream command(line);
                AciesTouch tap{++commandId, 0, 0};
                if (command >> tap.x >> tap.y) {
                    acies_aot_game_queue_touches(AciesTouchBegan, &tap, 1);
                    acies_aot_game_queue_touches(AciesTouchEnded, &tap, 1);
                    std::fprintf(stderr, "Mac test tap %.1f %.1f on tick %u\n", tap.x, tap.y, tick);
                }
            }
        }
        if (std::getenv("ACIES_PROBE_GUEST_FLOW")) {
            const struct {unsigned tick; float x, y;} taps[] = {
                {260, 369, 275}, {270, 369, 376}, {280, 640, 535},
                {390, 640, 478}, {470, 792, 557}, {530, 487, 491}, {595, 640, 595}
            };
            for (const auto& tap : taps) {
                if (tick == tap.tick || tick == tap.tick + 1) {
                    const AciesTouch point{static_cast<int32_t>(tap.tick), tap.x, tap.y};
                    acies_aot_game_queue_touches(tick == tap.tick ? AciesTouchBegan : AciesTouchEnded,
                                                 &point, 1);
                }
            }
        }
        if (std::getenv("ACIES_PROBE_LOBBY_TAP")) {
            const struct {unsigned tick; float x, y;} taps[] = {
                {825, 640, 663}, {875, 640, 663}, {925, 640, 663}
            };
            for (const auto& tap : taps) {
                if (tick == tap.tick || tick == tap.tick + 1) {
                    const AciesTouch point{static_cast<int32_t>(tap.tick), tap.x, tap.y};
                    acies_aot_game_queue_touches(tick == tap.tick ? AciesTouchBegan : AciesTouchEnded,
                                                 &point, 1);
                }
            }
        }
        if (std::getenv("ACIES_PROBE_AUTOMATCH")) {
            const struct {unsigned tick; float x, y;} taps[] = {
                {1050, 640, 382}, {1080, 640, 382}, {1110, 640, 382},
                {1140, 640, 382}, {1170, 640, 382}, {1200, 640, 382},
                {1230, 640, 382}, {1260, 640, 382},
                {1320, 896, 405}, {1440, 640, 616}, {1530, 640, 533}
            };
            for (const auto& tap : taps) {
                if (tick == tap.tick || tick == tap.tick + 1) {
                    const AciesTouch point{static_cast<int32_t>(tap.tick), tap.x, tap.y};
                    acies_aot_game_queue_touches(tick == tap.tick ? AciesTouchBegan : AciesTouchEnded,
                                                 &point, 1);
                }
            }
        }
        if (std::getenv("ACIES_PROBE_TAP") && tick >= 260 && tick <= 263) {
            const AciesTouchPhase phases[] = {AciesTouchBegan, AciesTouchMoved,
                                               AciesTouchEnded, AciesTouchCancelled};
            const AciesTouch point{1, 640.0f + (tick == 261 ? 4.0f : 0.0f), 590.0f};
            acies_aot_game_queue_touches(phases[tick - 260], &point, 1);
        }
        if (acies_aot_game_frame(output, capacity)) {
            std::fprintf(stderr, "tick %u stopped: %s\n", tick, output);
            return 1;
        }
        if (tick == 0 || tick % 30 == 29) {
            readPixels(0, 0, 1280, 720, 0x1908, 0x1401, rgba.data());
            size_t nonBlack = 0;
            for (size_t pixel = 0; pixel < rgba.size(); pixel += 4) {
                if (rgba[pixel] || rgba[pixel + 1] || rgba[pixel + 2]) ++nonBlack;
            }
            const unsigned error = getError();
            std::fprintf(stderr, "tick %u, %zu non-black pixels, GL error 0x%x\n",
                         tick + 1, nonBlack, error);
            if (nonBlack && !error) {
                std::ofstream out(framePath, std::ios::binary);
                out << "P6\n1280 720\n255\n";
                for (auto row = 719; row >= 0; --row) {
                    for (auto col = 0; col < 1280; ++col) {
                        const auto pixel = (row * 1280 + col) * 4;
                        out.write(reinterpret_cast<const char*>(&rgba[pixel]), 3);
                    }
                }
            }
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(17));
    }
    return acies_aot_game_shutdown(output, capacity);
}
#endif
