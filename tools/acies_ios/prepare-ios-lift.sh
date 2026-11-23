#!/bin/bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "Usage: $0 APK NEW_OUTPUT_DIRECTORY" >&2
    exit 2
fi

script_dir=$(cd "$(dirname "$0")" && pwd)
apk="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
output="$2"
revision=4a2004953e396fca04e940c300cad7c9f5fa77f3
archive_sha256=d7c1c0bb43dcb622ab872041b91004a4e7742d4b39c440b461b21b9eefa61f39
jobs=${ACIES_LIFT_JOBS:-$(sysctl -n hw.ncpu)}
asan=${ACIES_IOS_ADDRESS_SANITIZER:-0}

if [[ -e "$output" || ! -f "$apk" ]]; then
    echo "Provide the local APK and a new output directory." >&2
    exit 2
fi
if [[ ! "$jobs" =~ ^[1-9][0-9]*$ || ( "$asan" != 0 && "$asan" != 1 ) ]]; then
    echo "Use a positive ACIES_LIFT_JOBS and set ACIES_IOS_ADDRESS_SANITIZER to 0 or 1." >&2
    exit 2
fi
mkdir -p "$output"
output=$(cd "$output" && pwd)
runtime="$output/androidrecomp-$revision"
mkdir "$output/engine-input" "$output/iphoneos-objects"
archive="${ACIES_ANDROIDRECOMP_ARCHIVE:-$output/androidrecomp.tar.gz}"
if [[ -z "${ACIES_ANDROIDRECOMP_ARCHIVE:-}" ]]; then
    curl --fail --location --silent --show-error --retry 2 \
        "https://codeload.github.com/sp00nznet/androidrecomp/tar.gz/$revision" -o "$archive"
fi
printf '%s  %s\n' "$archive_sha256" "$archive" | shasum -a 256 --check
tar -xzf "$archive" -C "$output"
(cd "$runtime" && git apply "$script_dir/androidrecomp-darwin.patch")

python3 -m venv "$output/venv"
python="$output/venv/bin/python"
"$python" -m pip install --disable-pip-version-check \
    --only-binary=:all: 'capstone==5.0.7' 'pyelftools==0.32'

unzip -q "$apk" 'assets/*' -d "$output"
for library in libcdkapp.so libc++_shared.so; do
    unzip -p "$apk" "lib/arm64-v8a/$library" > "$output/engine-input/$library"
done
"$python" "$runtime/tools/lifter.py" "$output/engine-input/"{libcdkapp.so,libc++_shared.so} \
    --out "$output/full-image" --shards 128

sanitizer=(-DCMAKE_C_FLAGS= -DCMAKE_CXX_FLAGS=)
if [[ "$asan" == 1 ]]; then
    sanitizer=(-DCMAKE_C_FLAGS=-fsanitize=address -DCMAKE_CXX_FLAGS=-fsanitize=address)
fi
cmake -S "$runtime" -B "$output/arc-ios" -DCMAKE_SYSTEM_NAME=iOS \
    -DCMAKE_OSX_SYSROOT=iphoneos -DCMAKE_OSX_ARCHITECTURES=arm64 \
    -DCMAKE_OSX_DEPLOYMENT_TARGET=17.0 -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_DISABLE_FIND_PACKAGE_SDL2=TRUE "${sanitizer[@]}"
cmake --build "$output/arc-ios" --target androidrecomp --parallel "$jobs"

export ACIES_LIFT_OUTPUT="$output" ACIES_LIFT_RUNTIME="$runtime" ACIES_LIFT_ASAN="$asan"
find "$output/full-image" -name '*.c' -print0 | xargs -0 -n 1 -P "$jobs" bash -c '
    set -e
    input="$1"
    filename=${input##*/}
    flags=(-O2)
    if [[ "$ACIES_LIFT_ASAN" == 1 ]]; then
        flags=(-O1 -gline-tables-only -fsanitize=address -fno-omit-frame-pointer)
    fi
    xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -std=c11 -DARC_FRAMES \
        -I"$ACIES_LIFT_RUNTIME/runtime" -I"$ACIES_LIFT_OUTPUT/full-image" "${flags[@]}" \
        -c "$input" -o "$ACIES_LIFT_OUTPUT/iphoneos-objects/${filename%.c}.o"
' _
xcrun ar -rcs "$output/libacies-lifted-iphoneos.a" "$output"/iphoneos-objects/*.o
if [[ "$asan" == 1 ]]; then
    touch "$output/address-sanitizer"
fi
