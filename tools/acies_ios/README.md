# Standalone ACIES iOS compatibility host

This source builds a UIKit host for use with a local copy of the ACIES
Android package and its ahead-of-time translated ARM64 engine. See the
[port notes](../../docs/acies-android-wrapper-ios-port-research.md) for the
validated milestones and match checks.

The build scripts expect a prepared AOT directory containing:

- The patched `androidrecomp-*` checkout.
- `engine-input/libcdkapp.so` and `engine-input/libc++_shared.so` from the
  APK's `lib/arm64-v8a/` directory.
- `full-image/` with the generated dispatch and lifted sources.
- `libacies-lifted-iphoneos.a` and `arc-ios/libandroidrecomp.a`, built for
  iPhoneOS arm64. The Mac probes use the separate `arc-macos-boot/` build.

Prepare that directory from the APK with one command. It downloads
[androidrecomp at 4a200495](https://github.com/sp00nznet/androidrecomp/tree/4a2004953e396fca04e940c300cad7c9f5fa77f3),
checks the archive's SHA-256, applies the [Darwin patch](androidrecomp-darwin.patch),
installs pinned `capstone` and `pyelftools` into a private venv, lifts both ELF
inputs into 128 shards, and builds the iPhoneOS runtime and lifted archive:

```bash
tools/acies_ios/prepare-ios-lift.sh acies.apk "$LIFT"
```

`$LIFT` must not exist yet. It also serves as `APK_DIR`, because the script
unpacks the APK's `assets/` there. Set `ACIES_ANDROIDRECOMP_ARCHIVE` to reuse a
downloaded archive, `ACIES_LIFT_JOBS` to limit parallel compiles, or
`ACIES_IOS_ADDRESS_SANITIZER=1` for an AddressSanitizer build. The host build
script detects the sanitizer marker and bundles its runtime.

The Darwin patch also fixes the runtime's pthread registry for Bionic's static
mutex initializers. `CSLock(true)` stores `PTHREAD_RECURSIVE_MUTEX_INITIALIZER`
(`0x4000`) without calling `pthread_mutex_init`. The original registry treated
that value as an existing id, so the engine's task locks never excluded
anything. Worker threads then double-released `CSArray` and animation objects,
which caused the match-start invalid free and the post-Fireball heap
corruption. The JNI and zlib host adapters are adapted from androidrecomp under
the [MIT license](LICENSE.androidrecomp).

## Private LAN build

Set `LIFT` and `APK_DIR` to the prepared AOT directory and extracted APK.
Set `LAN_HOST` to the Mac interface that both test phones can reach. From
the repository root:

```bash
ios="$PWD/tools/acies_ios"
ACIES_ENABLE_LOCAL_MOCK=1 ACIES_STAGE_FULL_ASSETS=1 \
ACIES_LOCAL_MOCK_HOST="$LAN_HOST" ACIES_LOCAL_MOCK_PORT=18081 \
ACIES_LOCAL_MOCK_GATEWAY_PORT=19091 \
ACIES_CRYPTO_BRIDGE_DIR="$ios/crypto" ACIES_GATEWAY_BRIDGE_DIR="$ios/gateway" \
"$ios/host/build-stage-ios.sh" "$LIFT" "$ios/graphics" "$APK_DIR" \
    /tmp/AciesStandaloneLAN.app local.acies.compatibility
```

Development-sign the app with a matching bundle identifier and a provisioning
profile for the test iPhone. The ordinary host accepts UIKit touch input. For
a local device automation build, set `ACIES_GAME_MAIN_SOURCE` to
`"$ios/lab/game-main.mm"` before building. The lab host enables controls only
when launched with an explicit per-run test token. Keep it out of distributed
builds.

Run the mock server on the same Mac interface, with the iPhone address first
and the Android address second:

```bash
python3 -u tools/acies_mock_server.py \
    --host "$LAN_HOST" --port 18081 --admission-url "http://$LAN_HOST:18081" \
    --pvp-port 19091 --lobby-listener --guest-success \
    --guest-device "$IPHONE_IP" iPhone --guest-device "$ANDROID_IP" Android \
    --captures captures/ios-port-research/one-v-one/pair-server
```

Use an Android test APK configured for that same origin. The server stores
guest progress and results in the capture directory. An active match lives
in the server process, so keep it running until both clients report results.

## Community account build

```bash
"$ios/community/build-community-ios.sh" "$LIFT" "$ios/host" "$ios/graphics" \
    "$ios/crypto" "$APK_DIR" /tmp/AciesCommunity.app "$COMMUNITY_ORIGIN" \
    local.acies.community.prototype
```

The account origin uses HTTPS and system trust. For a LAN lab server, set
`ACIES_COMMUNITY_TEST_CA` to a private test CA's PEM file, as with the Android
`--ca-cert` option. The build bundles it as `community-test-ca.der`. Account and
game HTTPS requests then accept only chains anchored at that CA, and host or IP
name checks still apply. Leave it unset for distributed builds. Run the server
with `--admission-url` set to the same origin, behind a TLS proxy that presents
a certificate for the LAN IP.

On iPhoneW, the signed build passed Sign up, Sign in, and Continue (saved
session) against a LAN server on 2026-11-21. Each flow handed the session to the
translated client. A verified TLS gateway transport remains open.
