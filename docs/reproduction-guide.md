# Reproducing ACIES Decompilation and Decoded Artifacts

Date: 2026-04-29

This guide explains how to recreate the large local artifacts that are ignored
by Git:

- `acies-apktool/`
- `acies-jadx/`
- decoded `decrypts/` asset folders
- rebuilt APKs

The repository should only keep the scripts, docs, and small extracted notes.
The original APK, rebuilt APKs, decompiled trees, image dumps, and map dumps are
large generated artifacts and should stay outside Git.

## Prerequisites

Required tools:

```bash
java -version
apktool --version
jadx --version
python3 --version
adb version
```

Optional but useful:

```bash
objdump --version
readelf --version
```

On macOS with Homebrew:

```bash
brew install apktool jadx android-platform-tools binutils
```

For image decoding, create the local Python environment:

```bash
python3 -m venv .venv-xmf
.venv-xmf/bin/python -m pip install --upgrade pip
.venv-xmf/bin/python -m pip install pillow texture2ddecoder
```

The main workspace is:

```bash
cd /Users/p997eyc/projects/boot/acies-disassemble
```

## Inputs

Place the original APK at:

```text
acies.apk
```

The APK is intentionally ignored by Git. GitHub rejects normal Git files larger
than 100 MiB, and this APK is much larger than that.

## Recreate `acies-apktool/`

Use `apktool` when you need editable smali/resources/assets or when rebuilding
the APK.

```bash
rm -rf acies-apktool
apktool d -f acies.apk -o acies-apktool
```

Important outputs:

```text
acies-apktool/AndroidManifest.xml
acies-apktool/assets/
acies-apktool/lib/arm64-v8a/libcdkapp.so
acies-apktool/smali/
acies-apktool/smali_classes2/
acies-apktool/smali_classes3/
```

Patches intended for the rebuilt APK should be made in `acies-apktool/`, not in
the JADX tree.

## Recreate `acies-jadx/`

Use `jadx` for Java source navigation. This tree is not used for rebuilding.

```bash
rm -rf acies-jadx
jadx --no-res -d acies-jadx acies.apk
```

Useful Java locations:

```text
acies-jadx/sources/kr/co/brgames/cdk/
acies-jadx/sources/kr/co/brgames/talescraft2/MainActivity.java
acies-jadx/sources/com/nbp/appsafer/AppSafer.java
```

## Decode and Probe XMF Assets

The generic probe decrypts/decompresses `.xmf` files and writes raw decoded
payloads:

```bash
python3 tools/xmf_probe.py \
  acies-apktool/assets/version.xmf \
  acies-apktool/assets/strings.xmf \
  'acies-apktool/assets/data/game[071].xmf' \
  'acies-apktool/assets/maps/map[000][000][001].xmf' \
  --write-dir decrypts
```

Probe every APK asset:

```bash
find acies-apktool/assets -type f -name '*.xmf' -print0 \
  | xargs -0 python3 tools/xmf_probe.py --write-dir decrypts/probe-all
```

Current XMF facts are documented in:

```text
docs/acies-cdk3-xmf-reverse-engineering.md
```

## Parse Version, Locale, and Strings

```bash
python3 tools/cdk_xmf_parse.py \
  acies-apktool/assets/version.xmf \
  --kind version \
  --output decrypts/version.xmf.json \
  --csv decrypts/version.xmf.csv

python3 tools/cdk_xmf_parse.py \
  acies-apktool/assets/strings.xmf \
  --kind strings \
  --output decrypts/strings.xmf.partial.json \
  --csv decrypts/strings.xmf.partial.csv

python3 tools/cdk_xmf_parse.py \
  acies-apktool/assets/locale.xmf \
  --kind locale \
  --output decrypts/locale.json \
  --csv decrypts/locale.csv
```

`strings.xmf` parsing is intentionally partial; later records use
game-specific structure beyond plain CDK locale strings.

## Decode Game Data

Decode the ACIES `data/game[NNN].xmf` databases:

```bash
python3 tools/decode_acies_game_data.py \
  acies-apktool/assets/data/game*.xmf \
  --out-dir decrypts/game \
  --decoded-dir decrypts/game-decoded
```

Typical outputs:

```text
decrypts/game/index.json
decrypts/game/game[071].xmf.json
decrypts/game/game[071].xmf.units.csv
decrypts/game/game[071].xmf.abilities.csv
decrypts/game/game[071].xmf.runes.csv
decrypts/game/game[071].xmf.sections.csv
decrypts/game/game[071].xmf.summary.json
```

These outputs can be large and are ignored by Git.

## Decode Maps

Decode one map:

```bash
python3 tools/decode_acies_map.py \
  'acies-apktool/assets/maps/map[000][000][001].xmf' \
  --out-dir decrypts/maps
```

Decode all maps:

```bash
mkdir -p decrypts/maps-all
find acies-apktool/assets/maps -type f -name 'map*.xmf' -print0 \
  | while IFS= read -r -d '' path; do
      python3 tools/decode_acies_map.py "$path" --out-dir decrypts/maps-all
    done
```

Map outputs are large and ignored by Git.

## Decode Images

Install image dependencies first:

```bash
python3 -m venv .venv-xmf
.venv-xmf/bin/python -m pip install --upgrade pip
.venv-xmf/bin/python -m pip install pillow texture2ddecoder
```

Decode one or more image banks:

```bash
.venv-xmf/bin/python tools/decode_cdk_image.py \
  'acies-apktool/assets/images/images[003][019].xmf' \
  --out-dir decrypts/images/png \
  --meta-dir decrypts/images/meta
```

Decode all image banks:

```bash
find acies-apktool/assets/images -type f -name 'images*.xmf' -print0 \
  | xargs -0 .venv-xmf/bin/python tools/decode_cdk_image.py \
      --out-dir decrypts/images/png \
      --meta-dir decrypts/images/meta
```

Image outputs are large and ignored by Git.

## Decode Terrain, Meshes, and Animations

Terrain:

```bash
python3 tools/decode_cdk_terrain.py \
  acies-apktool/assets/terrain.xmf \
  --out-dir decrypts/terrain
```

Meshes:

```bash
find acies-apktool/assets/mesh -type f -name '*.xmf' -print0 \
  | xargs -0 python3 tools/decode_cdk_mesh.py --out-dir decrypts/meshes
```

Animations:

```bash
python3 tools/decode_cdk_animation.py \
  acies-apktool/assets/animations.xmf \
  --output decrypts/animations.xmf.json
```

For Git, keep the small summary instead of the full animation dump:

```text
decrypts/animations.xmf.summary.json
```

## Extract Native `libcdkapp.so` Research Pack

The native library is the main source of game behavior and schema information.
After recreating `acies-apktool/`, regenerate endpoint/schema/PVP notes with:

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

If Homebrew `binutils` is not installed, try the system tool names:

```bash
python3 tools/extract_acies_json_inventory.py --root . --out docs
python3 tools/extract_acies_so_pack.py --root .
```

Generated references:

```text
docs/acies-api-endpoints.md
docs/acies-json-payloads.md
docs/acies-so-extraction.md
decrypts/libcdkapp/extracted/pvp-gateway.md
decrypts/libcdkapp/extracted/pvp-buffer-ops.json
decrypts/libcdkapp/extracted/replay-match.md
decrypts/libcdkapp/extracted/security-anticheat.md
decrypts/libcdkapp/extracted/symbol-groups.md
```

## Run the Local Backend Mock

Start the mock backend:

```bash
python3 tools/acies_mock_server.py \
  --port 8080 \
  --status 200 \
  --guest-success \
  --tutorial-stages
```

The patched APK redirects ACIES HTTP requests to:

```text
http://10.0.2.2:8080
```

Android emulator `10.0.2.2` maps to the host machine.

Useful docs:

```text
docs/acies-local-mock-backend.md
docs/acies-login-flow.md
docs/acies-api-endpoints.md
docs/acies-json-payloads.md
```

## Rebuild the APK From `acies-apktool/`

Build:

```bash
apktool b acies-apktool -o acies-rebuilt-unsigned.apk
```

If Android build tools are available, align and sign:

```bash
zipalign -p -f 4 acies-rebuilt-unsigned.apk acies-rebuilt-aligned.apk

apksigner sign \
  --ks debug.keystore \
  --out acies-rebuilt-signed.apk \
  acies-rebuilt-aligned.apk
```

If using a standard Android debug keystore, generate it if needed:

```bash
keytool -genkeypair \
  -v \
  -keystore debug.keystore \
  -storepass android \
  -alias androiddebugkey \
  -keypass android \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000 \
  -dname "CN=Android Debug,O=Android,C=US"
```

Install and launch:

```bash
adb install -r acies-rebuilt-signed.apk
adb shell am force-stop com.creagames.clashoflegions
adb shell am start -n com.creagames.clashoflegions/kr.co.brgames.talescraft2.MainActivity
```

The rebuilt APK files are ignored by Git.

## Useful Logcat Commands

Focused local-backend run:

```bash
adb logcat -c
adb shell am force-stop com.creagames.clashoflegions
adb shell am start -n com.creagames.clashoflegions/kr.co.brgames.talescraft2.MainActivity
adb logcat -v threadtime \
  | grep -iE 'CSURLRequest|CSURLConnectionBridge|CSCrypto|CSSignal|LobbyGateway|PVPGateway|CSGooglePlay|CSFirebase|fatal|signal|crash'
```

Capture a full run:

```bash
adb logcat -c
adb shell am force-stop com.creagames.clashoflegions
adb shell am start -n com.creagames.clashoflegions/kr.co.brgames.talescraft2.MainActivity
adb logcat -v threadtime | tee acies-full-run.log
```

Logs are ignored by Git.

## What Should Be Committed

Commit:

```text
.gitignore
AGENTS.md
docs/
tools/
decrypts/libcdkapp/
small decrypts/*.csv and decrypts/*.json summaries
cdk3/README.md if useful
```

Do not commit:

```text
*.apk
*.idsig
acies-apktool/
acies-jadx/
captures/
logs
.venv-xmf/
decrypts/images/
decrypts/maps-all/
decrypts/maps/
decrypts/game/
decrypts/meshes/
decrypts/terrain/
```

