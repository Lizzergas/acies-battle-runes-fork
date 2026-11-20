#!/bin/bash
set -euo pipefail
work=$(cd "$(dirname "$0")" && pwd)
repo=${1:?Usage: run-community-probe.sh REPOSITORY [PROBE_BINARY]}
probe=${2:-"$work/acies-community-rest-macos"}
storage=$(mktemp -d "$work/session.XXXXXXXX")
http_port=48137
gateway_port=48138
python3 -u "$repo/tools/acies_mock_server.py" --host 127.0.0.1 --port "$http_port" \
    --pvp-port "$gateway_port" --community-db "$storage/accounts.sqlite3" --open-registration \
    --admission-url "https://127.0.0.1:$http_port" > "$storage/server.log" 2>&1 &
mock_pid=$!
trap 'kill "$mock_pid" 2>/dev/null || true; wait "$mock_pid" 2>/dev/null || true' EXIT
for attempt in $(seq 1 60); do
    if nc -z 127.0.0.1 "$http_port" >/dev/null 2>&1; then break; fi
    kill -0 "$mock_pid"
    sleep 0.05
done
kill -0 "$mock_pid"
policy='(version 1)(allow default)(deny network*)(allow network-outbound (remote tcp "localhost:48137") (remote tcp "localhost:48138"))'
ACIES_LOCAL_MOCK_HOST=127.0.0.1 ACIES_LOCAL_MOCK_PORT="$http_port" \
    ACIES_LOCAL_MOCK_GATEWAY_PORT="$gateway_port" \
    sandbox-exec -p "$policy" "$probe" "http://127.0.0.1:$http_port" "$storage/game"
printf 'Fixture logs and isolated account database: %s\n' "$storage"
