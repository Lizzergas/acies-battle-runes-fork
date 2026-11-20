#!/bin/bash
set -euo pipefail
if [[ $# -ne 8 ]]; then
    echo "Usage: build-community-ios.sh LIFT BOOT GRAPHICS CRYPTO APK_DIRECTORY OUTPUT.app ORIGIN BUNDLE_ID" >&2
    exit 2
fi
work=$(cd "$(dirname "$0")" && pwd)
base=$(cd "$1" && pwd)
boot=$(cd "$2" && pwd)
graphics=$(cd "$3" && pwd)
crypto=$(cd "$4" && pwd)
apk=$(cd "$5" && pwd)
app="$6"
origin="$7"
bundle_id="$8"
fixture=${ACIES_COMMUNITY_SYNTHETIC_LOOPBACK:-0}
gateway_port=${ACIES_COMMUNITY_LOCAL_GATEWAY_PORT:-0}
if [[ "$app" != *.app || -e "$app" ]]; then echo "Use a new .app output path." >&2; exit 2; fi
python3 - "$origin" "$fixture" "$gateway_port" <<'PY'
import sys
from urllib.parse import urlsplit
origin, fixture, gateway = sys.argv[1:]
url = urlsplit(origin)
if not url.hostname or url.username or url.password or url.path not in ("", "/") or url.query or url.fragment:
    raise SystemExit("Provide the account server origin without credentials, path, query, or fragment.")
if url.scheme != "https" and not (fixture == "1" and url.scheme == "http" and url.hostname == "127.0.0.1"):
    raise SystemExit("Use HTTPS. A synthetic loopback fixture may explicitly enable HTTP to 127.0.0.1.")
if not 0 <= int(gateway) <= 65535 or 0 < int(gateway) < 1024:
    raise SystemExit("Local gateway port must be zero or an unprivileged port.")
PY

build=$(mktemp -d "$work/ios-build.XXXXXXXX")
arc=$(find "$base" -maxdepth 1 -type d -name 'androidrecomp-*' | head -n 1)
sdk=$(xcrun --sdk iphoneos --show-sdk-path)
flags=(-std=c++17 -O2 -target arm64-apple-ios17.0 -isysroot "$sdk"
       -I"$work" -I"$base" -I"$base/full-image" -I"$arc/runtime"
       -I"$boot" -I"$graphics" -I"$crypto" -Wall -Wextra -Wno-deprecated-declarations)
defines=(-DACIES_LOCAL_ADMISSION -DACIES_FONT_BRIDGE -DACIES_CRYPTO_BRIDGE)
compile() {
    local file="$1"
    local name="$2"
    shift 2
    xcrun --sdk iphoneos clang++ "${flags[@]}" "${defines[@]}" "$@" -c "$file" -o "$build/$name.o"
}
python3 "$work/prepare-community-main.py" "$boot/game-main.mm" "$build/community-game-main.mm"
python3 "$work/patch-gateway-lift.py" "$base/full-image/lifted_028.c" "$build/lifted_028-community.c"
pids=()
for name in bootstrap-probe icu-adapter jni-env-permissions offline-imports; do
    compile "$boot/$name.cpp" "$name" & pids+=("$!")
done
compile "$boot/zlib-adapter.cpp" zlib-adapter -DARC_HAVE_ZLIB & pids+=("$!")
for name in gles-floats drawable-bridge font-bridge; do
    compile "$graphics/$name.cpp" "$name" & pids+=("$!")
done
for name in account-bridge crypto-bridge; do
    compile "$crypto/$name.cpp" "$name" & pids+=("$!")
done
for name in community-auth community-form community-keychain community-native-http; do
    compile "$work/$name.mm" "$name" -fobjc-arc & pids+=("$!")
done
for name in local-community-transport community-gateway-mode; do
    compile "$work/$name.cpp" "$name" & pids+=("$!")
done
compile "$build/community-game-main.mm" community-game-main -fobjc-arc & pids+=("$!")
xcrun --sdk iphoneos clang -std=c11 -O2 -target arm64-apple-ios17.0 -isysroot "$sdk" \
    -I"$work" -I"$base" -I"$base/full-image" -c "$build/lifted_028-community.c" \
    -o "$build/lifted_028-community.o" & pids+=("$!")
for pid in "${pids[@]}"; do wait "$pid"; done

cp "$base/arc-ios/libandroidrecomp.a" "$build/runtime.a"
xcrun ar -d "$build/runtime.a" jni_env.cpp.o shim_zlib.cpp.o
xcrun ranlib "$build/runtime.a"
xcrun --sdk iphoneos clang++ -target arm64-apple-ios17.0 -isysroot "$sdk" \
    "$build"/*.o "$base/libacies-lifted-iphoneos.a" "$build/runtime.a" \
    -framework UIKit -framework QuartzCore -framework OpenGLES -framework Foundation \
    -framework CoreGraphics -framework CoreText -framework CoreFoundation -framework Security \
    -lz -o "$build/AciesCommunityProbe"

mkdir -p "$app"
cp "$build/AciesCommunityProbe" "$app/"
cp "$base/engine-input/"{libcdkapp.so,libc++_shared.so} "$app/"
cp -R "$apk/assets" "$app/game-assets"
python3 - "$app/Info.plist" "$origin" "$bundle_id" "$fixture" "$gateway_port" <<'PY'
import plistlib
import sys
path, origin, identifier, fixture, port = sys.argv[1:]
info = {
    "CFBundleDevelopmentRegion": "en",
    "CFBundleDisplayName": "ACIES Community",
    "CFBundleExecutable": "AciesCommunityProbe",
    "CFBundleIdentifier": identifier,
    "CFBundleInfoDictionaryVersion": "6.0",
    "CFBundlePackageType": "APPL",
    "CFBundleShortVersionString": "0.1",
    "CFBundleVersion": "1",
    "MinimumOSVersion": "17.0",
    "LSRequiresIPhoneOS": True,
    "UIRequiresFullScreen": True,
    "UILaunchScreen": {},
    "UIStatusBarHidden": True,
    "UIViewControllerBasedStatusBarAppearance": False,
    "UISupportedInterfaceOrientations": ["UIInterfaceOrientationLandscapeLeft", "UIInterfaceOrientationLandscapeRight"],
    "AciesCommunityOrigin": origin,
    "AciesCommunitySyntheticLoopback": fixture == "1",
    "AciesCommunityLocalGatewayPort": int(port),
    "NSLocalNetworkUsageDescription": "Connect to your configured local ACIES community server.",
}
if fixture == "1":
    info["NSAppTransportSecurity"] = {"NSAllowsLocalNetworking": True}
with open(path, "wb") as output:
    plistlib.dump(info, output)
PY
plutil -lint "$app/Info.plist"
xcrun vtool -show-build "$app/AciesCommunityProbe"
du -sh "$app"
