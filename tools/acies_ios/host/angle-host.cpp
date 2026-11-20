#include "angle-host.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>

#include "arm64_context.h"

namespace {
using EGLHandle = void*;
using EGLint = int32_t;
using EGLBoolean = uint32_t;

constexpr EGLint kNone = 0x3038;
constexpr EGLint kPlatformAngle = 0x3202;
constexpr EGLint kPlatformAngleType = 0x3203;
constexpr EGLint kPlatformAngleMetal = 0x3489;

void* glesLibrary = nullptr;
void* eglLibrary = nullptr;
using GetEGLProc = void* (*)(const char*);
GetEGLProc getEGLProc = nullptr;

template <class T>
T resolveEGL(const char* name) {
    return reinterpret_cast<T>(::dlsym(eglLibrary, name));
}

uint64_t guestGetProc(const char* name) {
    if (auto address = aciesResolveAngleImport(name)) {
        arc_register_native(address, name);
        return address;
    }
    return 0;
}

bool angleError(const char* stage) {
    const auto error = resolveEGL<EGLint (*)()>("eglGetError");
    std::fprintf(stderr, "ANGLE setup failed at %s (0x%x)\n", stage, error ? error() : 0);
    return false;
}
}

bool aciesConfigureAngle() {
    const char* angleDirectory = std::getenv("ACIES_ANGLE_DIR");
    if (!angleDirectory) return false;

    char eglPath[4096];
    char glesPath[4096];
    std::snprintf(eglPath, sizeof(eglPath), "%s/libEGL.dylib", angleDirectory);
    std::snprintf(glesPath, sizeof(glesPath), "%s/libGLESv2.dylib", angleDirectory);
    eglLibrary = ::dlopen(eglPath, RTLD_LAZY | RTLD_LOCAL);
    if (!eglLibrary) {
        std::fprintf(stderr, "ANGLE EGL unavailable (%s)\n", ::dlerror());
        return false;
    }
    glesLibrary = ::dlopen(glesPath, RTLD_LAZY | RTLD_LOCAL);
    if (!glesLibrary) {
        std::fprintf(stderr, "ANGLE GLES unavailable (%s)\n", ::dlerror());
        return false;
    }

    getEGLProc = resolveEGL<GetEGLProc>("eglGetProcAddress");
    const auto getDisplay = reinterpret_cast<EGLHandle (*)(EGLint, void*, const EGLint*)>(
        getEGLProc("eglGetPlatformDisplayEXT"));
    const auto initialize = resolveEGL<EGLBoolean (*)(EGLHandle, EGLint*, EGLint*)>("eglInitialize");
    const auto bindApi = resolveEGL<EGLBoolean (*)(EGLint)>("eglBindAPI");
    const auto chooseConfig = resolveEGL<EGLBoolean (*)(EGLHandle, const EGLint*, EGLHandle*,
                                                        EGLint, EGLint*)>("eglChooseConfig");
    const auto createSurface = resolveEGL<EGLHandle (*)(EGLHandle, EGLHandle, const EGLint*)>(
        "eglCreatePbufferSurface");
    const auto createContext = resolveEGL<EGLHandle (*)(EGLHandle, EGLHandle, EGLHandle, const EGLint*)>(
        "eglCreateContext");
    const auto makeCurrent = resolveEGL<EGLBoolean (*)(EGLHandle, EGLHandle, EGLHandle, EGLHandle)>(
        "eglMakeCurrent");

    const EGLint displayAttributes[] = {kPlatformAngleType, kPlatformAngleMetal, kNone};
    auto display = getDisplay(kPlatformAngle, nullptr, displayAttributes);
    EGLint major = 0;
    EGLint minor = 0;
    if (!display || !initialize(display, &major, &minor)) return angleError("eglInitialize");

    constexpr EGLint kOpenGlesApi = 0x30A0;
    if (!bindApi(kOpenGlesApi)) return angleError("eglBindAPI");

    const EGLint configAttributes[] = {
        0x3033, 1, // EGL_SURFACE_TYPE, EGL_PBUFFER_BIT
        0x3040, 0x40, // EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT
        0x3024, 8, 0x3023, 8, 0x3022, 8, 0x3021, 8, // R, G, B, A
        0x3025, 24, 0x3026, 8, // depth and stencil size
        kNone
    };
    EGLHandle config = nullptr;
    EGLint configCount = 0;
    if (!chooseConfig(display, configAttributes, &config, 1, &configCount) || !configCount) {
        return angleError("eglChooseConfig");
    }

    const EGLint surfaceAttributes[] = {0x3057, 1280, 0x3056, 720, kNone}; // width, height
    auto surface = createSurface(display, config, surfaceAttributes);
    if (!surface) return angleError("eglCreatePbufferSurface");
    const EGLint contextAttributes[] = {0x3098, 3, kNone}; // EGL_CONTEXT_CLIENT_VERSION
    auto context = createContext(display, config, nullptr, contextAttributes);
    if (!context) return angleError("eglCreateContext");
    if (!makeCurrent(display, surface, surface, context)) return angleError("eglMakeCurrent");

    auto glGetString = reinterpret_cast<const char* (*)(unsigned)>(::dlsym(glesLibrary, "glGetString"));
    std::fprintf(stderr, "ANGLE EGL %d.%d (%s)\n", major, minor, glGetString(0x1F02));
    return true;
}

uint64_t aciesResolveAngleImport(const char* name) {
    if (!glesLibrary || !name) return 0;
    if (std::strcmp(name, "eglGetProcAddress") == 0) return reinterpret_cast<uint64_t>(&guestGetProc);
    if (std::strncmp(name, "gl", 2) != 0) return 0;
    if (auto* found = ::dlsym(glesLibrary, name)) return reinterpret_cast<uint64_t>(found);
    return reinterpret_cast<uint64_t>(getEGLProc(name));
}
