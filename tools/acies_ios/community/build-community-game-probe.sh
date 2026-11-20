#!/bin/bash
set -euo pipefail
work=$(cd "$(dirname "$0")" && pwd)
base=${1:?Usage: build-community-game-probe.sh LIFT BOOT GRAPHICS CRYPTO}
boot=${2:?Usage: build-community-game-probe.sh LIFT BOOT GRAPHICS CRYPTO}
graphics=${3:?Usage: build-community-game-probe.sh LIFT BOOT GRAPHICS CRYPTO}
crypto=${4:?Usage: build-community-game-probe.sh LIFT BOOT GRAPHICS CRYPTO}
arc=$(find "$base" -maxdepth 1 -type d -name 'androidrecomp-*' | head -n 1)
mac="$base/arc-macos-boot"
objects=$(dirname "$(find "$mac/CMakeFiles/arc_boot.dir" -name 'dispatch.c.o' | head -n 1)")
cd "$work"
includes=(-I. -I"$base" -I"$base/full-image" -I"$arc/runtime" -I"$boot" -I"$graphics" -I"$crypto")
for source in community-auth community-probe community-native-http; do
    xcrun clang++ -fobjc-arc -std=c++17 -O2 -DACIES_WITH_GAME -Wall -Wextra -Werror \
        -c "$source.mm" -o "$source-macos.o"
done
xcrun clang++ -std=c++17 -O2 -DACIES_MAC_ANGLE -DARC_HAVE_ZLIB -DACIES_LOCAL_ADMISSION \
    -DACIES_FONT_BRIDGE -DACIES_CRYPTO_BRIDGE -Wno-deprecated-declarations "${includes[@]}" \
    "$boot"/{bootstrap-probe,angle-host,icu-adapter,jni-env-permissions,offline-imports,zlib-adapter}.cpp \
    "$graphics"/{gles-floats,font-bridge}.cpp "$crypto"/{account-bridge,crypto-bridge}.cpp \
    local-community-transport.cpp community-{auth,probe,native-http}-macos.o \
    "$mac/libandroidrecomp.a" "$objects"/*.o \
    -framework Foundation -framework CoreText -framework CoreGraphics -framework CoreFoundation -lz \
    -o acies-community-game-macos
