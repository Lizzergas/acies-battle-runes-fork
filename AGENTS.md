# AGENTS.md

This repository documents and tools a local preservation/reverse-engineering
workflow for the Android game ACIES / Clash of Legions package:

```text
com.creagames.clashoflegions
kr.co.brgames.talescraft2.MainActivity
```

The original production backend is unavailable. The project goal is to keep the
client running locally by documenting its protocols, decoding its assets, and
serving compatible local mock responses.

## Current Workspace Assumptions

Work from:

```bash
cd /Users/p997eyc/projects/boot/acies-disassemble
```

Important generated directories may exist locally but are ignored by Git:

```text
acies-apktool/
acies-jadx/
decrypts/images/
decrypts/maps-all/
decrypts/game/
captures/
.venv-xmf/
```

If those folders are missing, recreate them from `acies.apk` using:

```text
docs/reproduction-guide.md
```

Do not assume `acies-apktool/` or `acies-jadx/` are committed.

## Safety and Scope

- Keep large generated artifacts out of Git.
- Do not commit APKs, rebuilt APKs, idsig files, logs, captures, or decoded
  image/map dumps.
- Prefer small reproducible scripts and documentation.
- Patches that affect rebuilds belong in `acies-apktool/`; JADX output is for
  reading/navigation only.
- The local backend is for preservation/testing against a dead service. Avoid
  adding behavior that targets live third-party systems.

## Key Documentation

Start here:

```text
docs/reproduction-guide.md
docs/acies-local-mock-backend.md
docs/acies-login-flow.md
docs/acies-api-endpoints.md
docs/acies-json-payloads.md
docs/acies-cdk3-xmf-reverse-engineering.md
docs/acies-so-extraction.md
```

Native/PVP research:

```text
decrypts/libcdkapp/extracted/pvp-gateway.md
decrypts/libcdkapp/extracted/pvp-buffer-ops.json
decrypts/libcdkapp/extracted/replay-match.md
decrypts/libcdkapp/extracted/security-anticheat.md
decrypts/libcdkapp/extracted/symbol-groups.md
decrypts/libcdkapp/api-endpoints.txt
decrypts/libcdkapp/domains.txt
decrypts/libcdkapp/symbols.demangled.txt
decrypts/libcdkapp/strings.txt
```

## Key Scripts

Backend:

```text
tools/acies_mock_server.py
```

XMF/decode tooling:

```text
tools/xmf_probe.py
tools/cdk_xmf_parse.py
tools/decode_acies_game_data.py
tools/decode_acies_map.py
tools/decode_cdk_animation.py
tools/decode_cdk_image.py
tools/decode_cdk_mesh.py
tools/decode_cdk_terrain.py
```

Native extraction:

```text
tools/extract_acies_json_inventory.py
tools/extract_acies_so_pack.py
```

## High-Value Commands

Check repo size before pushing:

```bash
du -sh .
git ls-files --others --exclude-standard -z | xargs -0 du -ch | tail -1
git status --short --ignored
```

Recreate decompiled trees:

```bash
apktool d -f acies.apk -o acies-apktool
jadx --no-res -d acies-jadx acies.apk
```

Run the local mock backend:

```bash
python3 tools/acies_mock_server.py \
  --port 8080 \
  --status 200 \
  --guest-success \
  --tutorial-stages
```

Launch the app on an emulator:

```bash
adb shell am force-stop com.creagames.clashoflegions
adb shell am start -n com.creagames.clashoflegions/kr.co.brgames.talescraft2.MainActivity
```

Focused logcat:

```bash
adb logcat -v threadtime \
  | grep -iE 'CSURLRequest|CSURLConnectionBridge|CSCrypto|CSSignal|LobbyGateway|PVPGateway|CSGooglePlay|CSFirebase|fatal|signal|crash'
```

Parse core assets:

```bash
python3 tools/cdk_xmf_parse.py acies-apktool/assets/version.xmf \
  --kind version \
  --output decrypts/version.xmf.json \
  --csv decrypts/version.xmf.csv

python3 tools/cdk_xmf_parse.py acies-apktool/assets/strings.xmf \
  --kind strings \
  --output decrypts/strings.xmf.partial.json \
  --csv decrypts/strings.xmf.partial.csv
```

Decode gameplay data:

```bash
python3 tools/decode_acies_game_data.py \
  acies-apktool/assets/data/game*.xmf \
  --out-dir decrypts/game \
  --decoded-dir decrypts/game-decoded
```

Decode one map:

```bash
python3 tools/decode_acies_map.py \
  'acies-apktool/assets/maps/map[000][000][001].xmf' \
  --out-dir decrypts/maps
```

Regenerate native extraction notes:

```bash
python3 tools/extract_acies_json_inventory.py \
  --root . \
  --objdump /opt/homebrew/opt/binutils/bin/objdump \
  --readelf /opt/homebrew/opt/binutils/bin/readelf \
  --out docs

python3 tools/extract_acies_so_pack.py \
  --root . \
  --objdump /opt/homebrew/opt/binutils/bin/objdump
```

## Local Backend State

The HTTP mock has working synthetic guest login and tutorial-stage support.
Current useful command:

```bash
python3 tools/acies_mock_server.py --port 8080 --status 200 --guest-success --tutorial-stages
```

Known implemented route families include:

```text
/api/client/admission
/api/client/login
/api/client-secure/push-token
/api/client-secure/game/result
/api/client-secure/game/prev-result
/api/client-secure/tutorial/step
/api/client-secure/pvp-server
/api/client-secure/profile/stat
/api/client-secure/match-record/list
```

When a new crash occurs after an HTTP response, map the native stack to the
corresponding JSON schema in:

```text
docs/acies-json-payloads.md
decrypts/libcdkapp/extracted/*.md
```

Then update `tools/acies_mock_server.py` and document the new endpoint behavior
in `docs/acies-local-mock-backend.md`.

## PVP Gateway Notes

`/api/client-secure/pvp-server` only returns a host/port JSON object. The actual
PVP protocol is a separate TCP binary protocol implemented by `PVPGateway`.

Important references:

```text
decrypts/libcdkapp/extracted/pvp-gateway.md
decrypts/libcdkapp/extracted/pvp-buffer-ops.json
```

Known frame shape:

```text
54 43
uint32_le sequence
uint32_le payload_length
payload bytes, first byte = opcode
```

Before attempting a full PVP rewrite, build a Python packet tracer that accepts
the socket, validates sequence numbers, logs opcodes, and stubs login/ping.

## Git Hygiene

The root `.gitignore` is intentionally aggressive. If a generated artifact is
needed for research, prefer either:

1. a small summary file under `docs/` or `decrypts/libcdkapp/`, or
2. a documented reproduction command in `docs/reproduction-guide.md`.

Before committing:

```bash
git status --short --ignored
git ls-files -z | xargs -0 du -ch | tail -1
find . -type f -size +50M -not -path './.git/*' -print
```

