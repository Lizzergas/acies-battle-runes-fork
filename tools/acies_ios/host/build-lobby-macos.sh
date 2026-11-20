#!/bin/bash
set -euo pipefail
d="$(cd "$(dirname "$0")" && pwd)"
track="$1"
g="$2"
c="$3"
n="$4"
r=("$track"/androidrecomp-*/runtime)
lifted_objects=("$track"/arc-macos-boot/CMakeFiles/arc_boot.dir/tmp/*/full-image/*.o)
clang++ -std=c++17 -g -O2 -Wall -Wextra -Wno-deprecated-declarations \
    -DACIES_MAC_ANGLE -DARC_HAVE_ZLIB -DACIES_FONT_BRIDGE -DACIES_LOCAL_ADMISSION \
    -DACIES_CRYPTO_BRIDGE -DACIES_GATEWAY_BRIDGE -I"${r[0]}" -I"$track/full-image" -I"$g" -I"$c" -I"$n" \
    "$d/"{bootstrap-probe.cpp,icu-adapter.cpp,angle-host.cpp,jni-env-permissions.cpp,offline-imports.cpp,zlib-adapter.cpp,local-admission.cpp,main.cpp} \
    "$g/"{gles-floats.cpp,font-bridge.cpp} "$c/"{crypto-bridge.cpp,account-bridge.cpp} "$n/gateway-imports.cpp" \
    "$track/arc-macos-boot/libandroidrecomp.a" "${lifted_objects[@]}" \
    -lz -framework CoreFoundation -framework CoreGraphics -framework CoreText -o "$d/${ACIES_MAC_EXECUTABLE:-bootstrap-macos-lobby}"
