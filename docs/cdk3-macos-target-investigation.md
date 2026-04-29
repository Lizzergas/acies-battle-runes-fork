# CDK3 macOS Target Investigation

Date: 2026-04-29

This note investigates what it would take to add a native macOS target for the
CDK3 client engine in this workspace, and how that relates to ACIES.

Related context:

- `docs/acies-cdk3-xmf-reverse-engineering.md`
- `cdk3/README.md`
- `cdk3/client/src/CDKProject.windows/CDK.vcxproj`
- `cdk3/client/src/CDK/Sources/Platform`

## Short Answer

CDK3 can plausibly get a native macOS engine target, but the cloned repository
does not contain one. The best starting point is the existing Windows desktop
host, not the Android APK shell.

The Windows target already uses a desktop stack:

- GLFW for window creation and input
- OpenGL 3.3 core profile
- GLEW for OpenGL function loading
- OpenAL for audio
- FreeType for font rasterization
- FreeImage for bitmap decode/save
- libcurl/OpenSSL for HTTP and crypto
- pthread-compatible threading

That maps to macOS much better than the Android or iOS implementation. The
macOS target should be a new `CDK_MACOS` platform layer plus a CMake target that
builds the common engine sources and a small desktop host executable.

## Important Limitation For ACIES

A CDK3 macOS target is not the same thing as a native ACIES macOS port.

The APK's actual game logic lives mainly inside Android native libraries such as
`libcdkapp.so`. That binary is built for Android/Bionic/JNI and cannot simply be
linked into a macOS process. A native ACIES build would need one of these:

- original ACIES game C++ source code, rebuilt against the macOS CDK3 target
- a reimplementation of the game layer on top of CDK3 and the extracted assets
- an Android runtime/emulator path

So the practical macOS target can run CDK3 engine code, asset viewers, test
scenes, or a new/recreated game layer. It cannot directly run the shipped ACIES
APK game binary.

## What Exists In CDK3

The client tree has 336 C++/Objective-C++ implementation files under
`cdk3/client/src/CDK/Sources`.

There are 266 non-platform implementation files that are mostly reusable for
macOS. Existing platform implementations are:

```text
cdk3/client/src/CDK/Sources/Platform/android
cdk3/client/src/CDK/Sources/Platform/ios
cdk3/client/src/CDK/Sources/Platform/windows
```

There is no:

- `Platform/macos`
- Xcode project
- macOS CMake target
- Metal renderer
- Vulkan renderer

The renderer abstraction has enum slots for Vulkan and Metal, but only the
OpenGL context is implemented:

```text
cdk3/client/src/CDK/Sources/Graphics/Context/CSGraphicsContext.h
cdk3/client/src/CDK/Sources/Graphics/Context/OpenGL/CSOpenGLApi.cpp
```

`CSOpenGLApi.cpp` already emits desktop GLSL for Windows:

```cpp
#ifdef CDK_WINDOWS
static const char* ShaderVersion = "#version 330\n";
#else
static const char* ShaderVersion = "#version 330 es\n";
#endif
```

For macOS, the first target should use the same desktop GLSL path:
`#version 330`, not the GLES path.

## Best Technical Path

### Phase 1: Build System

Create a new CMake-based desktop build target instead of trying to translate the
Visual Studio project manually every time.

Suggested structure:

```text
cdk3/client/src/CMakeLists.txt
cdk3/client/src/CDK/Sources/Platform/macos/
```

Compile with:

```text
-std=c++17
-DCDK_IMPL
-DCDK_MACOS
```

The CMake target should include:

- all common `CDK/Sources/**/*.cpp`
- `Platform/CSFileRawImpl.cpp`
- `Platform/CSLog+common.cpp`
- `Platform/CSMemory.cpp`
- `Platform/icu_compat.cpp`
- `Platform/macos/*.cpp`
- copied/adapted desktop files from `Platform/windows`

Exclude:

- `Platform/android/**`
- `Platform/ios/**`
- `Platform/windows/**`
- mobile extension implementations unless explicitly stubbed or ported

### Phase 2: Desktop Host

Start by adapting:

```text
cdk3/client/src/CDK/Sources/Platform/windows/main.cpp
```

into:

```text
cdk3/client/src/CDK/Sources/Platform/macos/main.cpp
```

Keep the same flow:

1. Initialize GLFW.
2. Create an OpenGL 3.3 core window.
3. Initialize GLEW.
4. Initialize `CSStringContentTable`, `CSFile`, `CSThread`, `CSSignal`,
   `CSGraphics`, `CSAudio`, font/text/network helpers.
5. Call `CSApplication::initialize(...)`.
6. Call `onStart()`.
7. Poll GLFW events and drive `CSApplication::timeout()`.
8. Call `onDestroy()` and finalize everything.

This is the fastest way to get a native window and render loop.

### Phase 3: macOS Platform Glue

Create `Platform/macos` files matching the public platform headers:

```text
CSApplication+macos.cpp
CSAudio.cpp
CSAudioOgg.cpp
CSAudioWave.cpp
CSCrypto.cpp
CSDevice.cpp
CSDeviceConfig.cpp
CSEncoder.cpp
CSFile.cpp
CSFontImpl.cpp
CSLocalNotification.cpp
CSLog.cpp
CSRaster.cpp
CSSignal.cpp
CSTextFieldBridge.cpp
CSTextFieldImpl.cpp
CSURLConnectionBridge.cpp
CSURLConnectionImpl.cpp
CSURLRequestBridge.cpp
CSURLRequestImpl.cpp
CSVideoViewBridge.cpp
CSWebViewBridge.cpp
main.cpp
```

Most of these can begin as copies of the Windows implementation, then be edited
for POSIX/macOS APIs.

High-value edits:

- Replace Windows-only headers: `windows.h`, `direct.h`, `io.h`, `WinSock2.h`.
- Replace `_mkdir`, `access`, `stricmp`, `MessageBox`, `__argv`, `__argc`.
- Use POSIX paths and APIs: `unistd.h`, `sys/stat.h`, `mkdir(path, 0755)`.
- Use BSD sockets path from `CSSocket.cpp` rather than Winsock.
- Use `sysctl`/`host_statistics64` or simple placeholders for memory stats.
- Use `CFUUIDCreate` or a persisted UUID file for device UUID.
- Use `NSWorkspace` or a command bridge for `openURL`, or stub it initially.

### Phase 4: OpenGL Details

macOS supports OpenGL up to 4.1 core, although it is deprecated by Apple. For a
first CDK3 target, that is still the shortest practical route because CDK3 only
has an OpenGL backend.

Use the Windows context settings as the baseline:

```cpp
glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 3);
glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);
glfwWindowHint(GLFW_OPENGL_FORWARD_COMPAT, GL_TRUE);
```

Add `CDK_MACOS` to the OpenGL include branches:

```cpp
#elif defined(CDK_WINDOWS) || defined(CDK_MACOS)
# include <GL/glew.h>
```

Also make the shader version desktop GLSL:

```cpp
#if defined(CDK_WINDOWS) || defined(CDK_MACOS)
static const char* ShaderVersion = "#version 330\n";
#else
static const char* ShaderVersion = "#version 330 es\n";
#endif
```

The existing shader resources already use modern GLSL features such as
`layout(location=...)`, `in`, `out`, and uniform blocks, so desktop OpenGL 3.3 is
a reasonable first target.

### Phase 5: Dependencies

Current local status:

```text
cmake: installed
clang/clang++: installed
brew: installed
pkg-config/pkgconf: not installed
glfw: not installed
glew: not installed
freeimage: not installed
openal-soft: not installed
libogg: not installed
libvorbis: not installed
freetype: installed
icu4c: installed
openssl@3: installed
```

Install likely missing dependencies with:

```bash
brew install pkgconf glfw glew freeimage openal-soft libogg libvorbis freetype icu4c openssl@3 curl
```

`openal-soft` is keg-only in Homebrew, so CMake will likely need explicit include
and library paths for it.

### Phase 6: Minimal Smoke App

The engine expects application-level functions declared in:

```text
cdk3/client/src/CDK/Sources/Interface/CSApplication.h
```

The desktop host calls:

```cpp
onStart();
onDestroy();
```

Before trying to run ACIES assets, create a tiny test application that defines
those functions and draws a simple CDK scene or even just clears the render
target. This proves:

- the build links
- the window opens
- the render thread attaches
- OpenGL function loading works
- the CDK initialization/finalization sequence is valid on macOS

Only after that should asset loading, XMF rendering, audio, and networking be
added back.

## Biggest Risks

1. `CDK_WINDOWS` is used as both "Windows OS" and "desktop OpenGL build".
   Introducing `CDK_MACOS` will expose places that really mean "desktop" versus
   places that really mean "Win32".
2. The Visual Studio project is the only complete desktop source list. A CMake
   target must reproduce that list or glob carefully while excluding wrong
   platform directories.
3. Some Windows desktop support files depend on bundled `.lib` and header trees
   under `Platform/windows/include`. On macOS these should come from Homebrew.
4. Apple deprecates OpenGL. That is acceptable for a local reverse-engineering
   and asset-viewer target, but not a future-proof shipping route.
5. A full ACIES game port remains blocked by missing game source.

## Recommendation

For this workspace, the useful next milestone is not "native ACIES" yet. It is:

1. Add `CDK_MACOS` preprocessor support.
2. Add a CMake target that builds the CDK3 common engine plus a macOS desktop
   host.
3. Port enough platform glue to open a GLFW window and clear/render a frame.
4. Add an asset-viewer/test-scene layer that loads decoded XMF/image/mesh data.

That gives a real macOS executable and makes the extracted ACIES assets easier
to inspect, without pretending the Android `libcdkapp.so` can be reused
natively.
