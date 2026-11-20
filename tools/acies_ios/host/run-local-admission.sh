#!/bin/bash
set -euo pipefail
source_dir="$(cd "$(dirname "$0")" && pwd)"
aot_dir="$1"
project="$(cd "$2" && pwd)"
port=48091
gateway_port=48092
storage="${ACIES_PROBE_STORAGE:-$source_dir/local-admission-storage}"
captures="${ACIES_PROBE_CAPTURE_DIR:-$source_dir/local-admission-captures}"
mkdir -p "$storage"
guest_args=()
if [[ "${ACIES_ENABLE_TEST_PEER:-0}" == 1 ]]; then
    guest_args=(--guest-device 127.0.0.1 MAC --guest-device 192.168.0.153 Echo)
fi
python3 -u "$project/tools/acies_mock_server.py" --host 127.0.0.1 --port "$port" \
    --admission-url "http://127.0.0.1:$port" --captures "$captures" \
    --status 200 --guest-success --lobby-listener --pvp-port "$gateway_port"     "${guest_args[@]+"${guest_args[@]}"}" > "$source_dir/local-admission-server.log" 2>&1 &
mock_pid=$!
trap 'kill "$mock_pid" 2>/dev/null || true; wait "$mock_pid" 2>/dev/null || true' EXIT
for attempt in $(seq 1 60); do
    if nc -z 127.0.0.1 "$port" >/dev/null 2>&1; then break; fi
    kill -0 "$mock_pid"
    sleep 0.05
done
kill -0 "$mock_pid"

sandbox_profile='(version 1)(allow default)(deny network*)(allow network-outbound (remote tcp "localhost:48091") (remote tcp "localhost:48092"))'
ACIES_LOCAL_MOCK_HOST=127.0.0.1 ACIES_LOCAL_MOCK_PORT="$port" ACIES_LOCAL_MOCK_GATEWAY_PORT="$gateway_port" ACIES_PROBE_FRAMES="${ACIES_PROBE_FRAMES:-420}" ACIES_TRACE_ASSET_PATHS=1 \
    ARC_TRACE_FN=7b84a4,8159f8,815a04,815a94,7b910c,7b9124,7b8e74 ARC_TRACE_JNI=1 \
    ACIES_ANGLE_DIR="$HOME/Library/Android/sdk/emulator/lib64/gles_angle" \
    sandbox-exec -p "$sandbox_profile" "$source_dir/${ACIES_PROBE_BINARY:-bootstrap-macos-admission}" start \
        "$aot_dir/engine-input/libcdkapp.so" "$aot_dir/engine-input/libc++_shared.so" \
        "$project/acies-apktool/assets" "$storage" > "$source_dir/title-admission.log" 2>&1
