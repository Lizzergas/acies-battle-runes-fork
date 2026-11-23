#!/bin/bash
set -euo pipefail

if [[ $# -ne 5 ]]; then
    echo "Usage: $0 <aot-build-dir> <graphics-sources-dir> <extracted-apk-dir> <output.app> <bundle-id>" >&2
    exit 2
fi

source_dir="$(cd "$(dirname "$0")" && pwd)"
aot_dir="$(cd "$1" && pwd)"
graphics_dir="$(cd "$2" && pwd)"
apk_dir="$(cd "$3" && pwd)"
app="$4"
bundle_id="$5"

if [[ "$app" != *.app || -e "$app" ]]; then
    echo "Provide a new .app path." >&2
    exit 2
fi

runtime_dirs=("$aot_dir"/androidrecomp-*/runtime)
runtime_dir="${runtime_dirs[0]}"
sdk="$(xcrun --sdk iphoneos --show-sdk-path)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/acies-game-ios.XXXXXXXX")"
trap 'rm -rf -- "$build_dir"' EXIT

sanitizer=()
sanitizer_runtime=
if [[ -f "$aot_dir/address-sanitizer" ]]; then
    sanitizer=(-fsanitize=address -gline-tables-only -fno-omit-frame-pointer)
    sanitizer_runtime="$(xcrun --sdk iphoneos clang --print-file-name=libclang_rt.asan_ios_dynamic.dylib)"
    test -f "$sanitizer_runtime"
fi

features=(-DACIES_FONT_BRIDGE)
extra_objects=()
if [[ "${ACIES_ENABLE_LOCAL_MOCK:-0}" == 1 ]]; then
    features+=(-DACIES_LOCAL_ADMISSION)
    extra_objects+=("$build_dir/local-admission.o")
    test -n "${ACIES_LOCAL_MOCK_HOST:-}"
    test -n "${ACIES_LOCAL_MOCK_PORT:-}"
fi
if [[ -n "${ACIES_CRYPTO_BRIDGE_DIR:-}" ]]; then
    features+=(-DACIES_CRYPTO_BRIDGE -I"$ACIES_CRYPTO_BRIDGE_DIR")
    extra_objects+=("$build_dir/crypto.o" "$build_dir/device-info.o")
fi

if [[ -n "${ACIES_GATEWAY_BRIDGE_DIR:-}" ]]; then
    features+=(-DACIES_GATEWAY_BRIDGE -I"$ACIES_GATEWAY_BRIDGE_DIR")
    extra_objects+=("$build_dir/gateway.o")
fi

compiler=(xcrun --sdk iphoneos clang++ -std=c++17 -O2 -target arm64-apple-ios17.0 -isysroot "$sdk"
          -I"$source_dir" -I"$runtime_dir" -I"$aot_dir/full-image" -I"$graphics_dir" -Wall -Wextra
          "${sanitizer[@]+"${sanitizer[@]}"}")
compile() {
    local source="$1"
    local output="$2"
    shift 2
    "${compiler[@]}" "$@" -c "$source" -o "$build_dir/$output.o"
}

pids=()
compile "$source_dir/bootstrap-probe.cpp" bootstrap "${features[@]}" & pids+=("$!")
compile "$source_dir/icu-adapter.cpp" icu & pids+=("$!")
compile "$source_dir/jni-env-permissions.cpp" jni & pids+=("$!")
compile "$source_dir/offline-imports.cpp" offline & pids+=("$!")
compile "$source_dir/zlib-adapter.cpp" zlib -DARC_HAVE_ZLIB & pids+=("$!")
compile "${ACIES_GAME_MAIN_SOURCE:-$source_dir/game-main.mm}" main -fobjc-arc -Wno-deprecated-declarations "${features[@]}" & pids+=("$!")
compile "$graphics_dir/gles-floats.cpp" gles & pids+=("$!")
compile "$graphics_dir/drawable-bridge.cpp" drawable -Wno-deprecated-declarations & pids+=("$!")
compile "$graphics_dir/font-bridge.cpp" font & pids+=("$!")
if [[ "${ACIES_ENABLE_LOCAL_MOCK:-0}" == 1 ]]; then
    compile "$source_dir/local-admission.cpp" local-admission & pids+=("$!")
fi
if [[ -n "${ACIES_CRYPTO_BRIDGE_DIR:-}" ]]; then
    compile "$ACIES_CRYPTO_BRIDGE_DIR/crypto-bridge.cpp" crypto -Wno-deprecated-declarations &
    pids+=("$!")
    compile "$ACIES_CRYPTO_BRIDGE_DIR/account-bridge.cpp" device-info & pids+=("$!")
fi
if [[ -n "${ACIES_GATEWAY_BRIDGE_DIR:-}" ]]; then
    compile "$ACIES_GATEWAY_BRIDGE_DIR/gateway-imports.cpp" gateway & pids+=("$!")
fi
for pid in "${pids[@]}"; do wait "$pid"; done

runtime_archive="$build_dir/libandroidrecomp.a"
cp "$aot_dir/arc-ios/libandroidrecomp.a" "$runtime_archive"
xcrun ar -d "$runtime_archive" jni_env.cpp.o shim_zlib.cpp.o
xcrun ranlib "$runtime_archive"
"${compiler[@]}" "$build_dir/"{bootstrap,icu,jni,offline,zlib,main,gles,drawable,font}.o \
    "${extra_objects[@]+"${extra_objects[@]}"}" "$aot_dir/libacies-lifted-iphoneos.a" "$runtime_archive" \
    -Wl,-rpath,@executable_path/Frameworks \
    -framework UIKit -framework QuartzCore -framework OpenGLES \
    -framework Foundation -framework CoreGraphics -framework CoreText -framework CoreFoundation -lz -o "$build_dir/AciesGameProbe"
xcrun vtool -show-build "$build_dir/AciesGameProbe"

asset_paths=(
    animations.xmf locale.xmf strings.xmf version.xmf
    graphics/fill.fsh graphics/fill.vsh graphics/graphics.fsh graphics/graphics.vsh
    'images/images[000][001].xmf' 'images/images[000][026].xmf'
    'images/images[000][027].xmf' 'images/images[000][028].xmf' 'images/images[000][029].xmf'
    'sounds/sound[000][000][000].ogg'
)
for asset_path in "${asset_paths[@]}"; do
    test -f "$apk_dir/assets/$asset_path"
done
if [[ "${ACIES_ENABLE_LOCAL_MOCK:-0}" == 1 ]]; then
    asset_paths+=(graphics/blur.fsh graphics/blur.vsh 'images/images[000][000].xmf')
fi
test -d "$apk_dir/assets/fonts/bold"
test -d "$apk_dir/assets/fonts/normal"

mkdir -p "$app/game-assets"/{graphics,images,sounds,fonts}
cp "$build_dir/AciesGameProbe" "$app/AciesGameProbe"
if [[ -n "$sanitizer_runtime" ]]; then
    mkdir "$app/Frameworks"
    cp "$sanitizer_runtime" "$app/Frameworks/"
fi
cp "$aot_dir/engine-input/"{libcdkapp.so,libc++_shared.so} "$app/"
if [[ "${ACIES_STAGE_FULL_ASSETS:-0}" == 1 ]]; then
    cp -Rc "$apk_dir/assets/." "$app/game-assets/"
else
    for asset_path in "${asset_paths[@]}"; do
        cp "$apk_dir/assets/$asset_path" "$app/game-assets/$asset_path"
    done
    cp -R "$apk_dir/assets/fonts/"{bold,normal} "$app/game-assets/fonts/"
fi

python3 - "$app/Info.plist" "$bundle_id" <<'PY'
import os
import plistlib
import sys

info_path, bundle_id = sys.argv[1:]
info = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleDisplayName": "ACIES Compatibility",
        "CFBundleExecutable": "AciesGameProbe",
        "CFBundleIdentifier": bundle_id,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": "AciesGameProbe",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": os.environ.get("ACIES_BUILD_NUMBER", "3"),
        "LSRequiresIPhoneOS": True,
        "MinimumOSVersion": "17.0",
        "UIDeviceFamily": [1, 2],
        "UILaunchScreen": {},
        "UIRequiresFullScreen": True,
        "UIStatusBarHidden": True,
        "UISupportedInterfaceOrientations": [
            "UIInterfaceOrientationLandscapeLeft",
            "UIInterfaceOrientationLandscapeRight",
        ],
        "UIViewControllerBasedStatusBarAppearance": False,
}
if os.environ.get("ACIES_GAME_MAIN_SOURCE"):
    info["CFBundleURLTypes"] = [{
        "CFBundleURLName": "ACIES standalone test controls",
        "CFBundleURLSchemes": ["acies-standalone-test"],
    }]
if os.environ.get("ACIES_ENABLE_LOCAL_MOCK") == "1":
    info.update({
        "AciesLocalMockHost": os.environ["ACIES_LOCAL_MOCK_HOST"],
        "AciesLocalMockHTTPPort": os.environ["ACIES_LOCAL_MOCK_PORT"],
        "AciesLocalMockGatewayPort": os.environ.get("ACIES_LOCAL_MOCK_GATEWAY_PORT", ""),
        "NSLocalNetworkUsageDescription": "Connect to the configured local ACIES preservation server.",
    })
with open(info_path, "wb") as output:
    plistlib.dump(info, output)
PY

plutil -lint "$app/Info.plist"
du -sh "$app"
