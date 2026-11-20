#!/usr/bin/env python3
"""Build an unsigned ARM64 APK with ACIES community onboarding and a TLS gateway."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import urlparse

JAVA_ROOT = Path(__file__).resolve().with_name("acies_community")
PACKAGE = "com.creagames.clashoflegions.community"
CLASSPATH = "Lorg/acies/community/CommunityBridge;"
ACTIVITY = "kr.co.brgames.talescraft2.MainActivity"
SOURCE_LIBRARY = "lib/arm64-v8a/libcdkapp.so"
LIBRARY_SHA256 = "38a37aa8e270015b6c766744763b75c638829edf09373498a11fdf5de33e9ddd"
ANDROID = "http://schemas.android.com/apk/res/android"
MIN_SDK = 24
PICKER_CODE = 0x990000
PICKER_DATA = 0x984000


def android(name: str) -> str:
    return f"{{{ANDROID}}}{name}"


def patch_manifest(path: Path) -> None:
    ET.register_namespace("android", ANDROID)
    xml = ET.ElementTree(ET.fromstring(path.read_text().replace("com.creagames.clashoflegions", PACKAGE)))
    root = xml.getroot()
    app = root.find("application")
    game = next(element for element in app.findall("activity") if element.get(android("name")) == ACTIVITY)
    app.set(android("allowBackup"), "false")
    app.set(android("label"), "Acies Community")
    app.set(android("usesCleartextTraffic"), "false")
    game.set(android("label"), "Acies Community")
    for intent in game.findall("intent-filter"):
        if not any(action.get(android("name")) == "android.intent.action.MAIN" for action in intent.findall("action")):
            game.remove(intent)
    xml.write(path, encoding="utf-8", xml_declaration=True)


def replace_exact(text: str, old: str, new: str, count: int = 1) -> str:
    if text.count(old) != count:
        raise ValueError(f"Unexpected APK layout while patching {old.splitlines()[0]}")
    return text.replace(old, new)


def replace_smali_body(text: str, method: str, body: str) -> str:
    text, count = re.subn(rf"(?m)(^\.method {re.escape(method)}\n)[\s\S]*?^\.end method",
                          lambda match: match[1] + body + "\n.end method", text)
    if count != 1:
        raise ValueError(f"Unexpected APK layout while patching {method}")
    return text


def patch_smali(tree: Path) -> None:
    request = tree / "smali/kr/co/brgames/cdk/CSURLRequest.smali"
    text = request.read_text()
    old = "    new-instance v0, Ljava/net/URL;\n\n    invoke-direct {v0, p1}, Ljava/net/URL;-><init>(Ljava/lang/String;)V"
    text = replace_exact(text, old, f"    invoke-static {{p1}}, {CLASSPATH}->rewriteUrl(Ljava/lang/String;)Ljava/net/URL;\n\n    move-result-object v0", 2)
    old = "    :cond_0\n    iget-object v1, p0, Lkr/co/brgames/cdk/CSURLRequest;->_body:[B"
    text = replace_exact(text, old, f"    :cond_0\n    invoke-static {{v0}}, {CLASSPATH}->configure(Ljava/net/HttpURLConnection;)V\n\n" + old.split("\n", 1)[1])
    request.write_text(text)

    activity = tree / "smali/kr/co/brgames/talescraft2/MainActivity.smali"
    activity.write_text(activity.read_text() + f"""
.method protected onCreate(Landroid/os/Bundle;)V
    .locals 0
    invoke-static {{p0}}, {CLASSPATH}->attach(Landroid/app/Activity;)V
    invoke-static {{}}, Lkr/co/brgames/cdk/CSView;->communityBind()V
    invoke-super {{p0, p1}}, Lkr/co/brgames/cdk/CSActivity;->onCreate(Landroid/os/Bundle;)V
    return-void
.end method
""")
    view = tree / "smali/kr/co/brgames/cdk/CSView.smali"
    with view.open("a") as output:
        output.write("""
.method public static communityBind()V
    .locals 1
    const/4 v0, 0x0
    invoke-static {v0, v0}, Lkr/co/brgames/cdk/CSView;->nativeReceiveQuery(Ljava/lang/String;Ljava/lang/String;)V
    return-void
.end method
""")

    # Use the same local AppSafer adapter as the existing signed lab APK.
    app_safer = tree / "smali/kr/co/brgames/cdk/extension/CSAppSafer.smali"
    text = app_safer.read_text()
    for method in ("initialize()", "setUserId(Ljava/lang/String;)"):
        text = replace_smali_body(text, f"public static {method}V", "    .locals 0\n    return-void")
    app_safer.write_text(text)

    extensions = app_safer.parent
    play = extensions / "CSGooglePlay.smali"
    # Legacy account settings still reference this entry point. Deliver the same
    # cancellation on the game thread as a user dismissing the old sign-in.
    play.write_text(replace_smali_body(play.read_text(), "public static login()V", """    .locals 3
    invoke-static {}, Lkr/co/brgames/cdk/CSActivity;->sharedActivity()Lkr/co/brgames/cdk/CSActivity;
    move-result-object v0
    invoke-virtual {v0}, Lkr/co/brgames/cdk/CSActivity;->view()Lkr/co/brgames/cdk/CSView;
    move-result-object v0
    const/4 v1, 0x1
    new-instance v2, Lkr/co/brgames/cdk/extension/CSGooglePlayImpl$$ExternalSyntheticLambda6;
    invoke-direct {v2, v1}, Lkr/co/brgames/cdk/extension/CSGooglePlayImpl$$ExternalSyntheticLambda6;-><init>(I)V
    invoke-virtual {v0, v2}, Lkr/co/brgames/cdk/CSView;->queueEvent(Ljava/lang/Runnable;)V
    return-void"""))

    firebase = extensions / "CSFirebase.smali"
    text = firebase.read_text()
    # The original Firebase initialization can show a blocking Play Services
    # install/update dialog. Keep initialization and omit that recovery UI.
    method = text.split(".method static synthetic lambda$initialize$2()V\n", 1)[1].split(".end method", 1)[0]
    prompt = method[method.index("    .line 23"):method.index("    .line 33")]
    firebase.write_text(replace_exact(text, prompt + "    .line 33\n    :cond_0\n", "    .line 33\n"))


def compile_picker(directory: Path, toolchain: Path) -> tuple[bytes, dict[str, int]]:
    clang, link, objcopy, nm = (toolchain / "bin" / name for name in ("clang", "ld.lld", "llvm-objcopy", "llvm-nm"))
    flags = ["--target=aarch64-linux-android24", "-ffreestanding", "-fno-stack-protector",
             "-fno-unwind-tables", "-fno-asynchronous-unwind-tables", "-fno-jump-tables", "-fno-pic", "-fno-pie", "-Os"]
    c, assembly, image, flat = (directory / name for name in ("picker.o", "hooks.o", "picker.elf", "picker.bin"))
    subprocess.run([str(clang), *flags, "-c", str(JAVA_ROOT / "account_picker.c"), "-o", str(c)], check=True)
    subprocess.run([str(clang), *flags, "-c", str(JAVA_ROOT / "account_hooks.S"), "-o", str(assembly)], check=True)
    layout = directory / "picker.ld"
    layout.write_text(f"""SECTIONS {{
    . = {PICKER_CODE:#x};
    .community : {{ *(.text*) *(.rodata*) }}
    /DISCARD/ : {{ *(.comment*) *(.note*) *(.eh_frame*) }}
}}
picker = {PICKER_DATA:#x};
account_java = {PICKER_DATA + 0x200:#x};
original_receive_query = 0x810134;
object_new = 0x868a80;
object_autorelease = 0x868aa0;
object_retain = 0x868e30;
object_release = 0x868c50;
layer_set_frame = 0x870410;
layer_add = 0x7ff110;
layer_remove = 0x7fcc4c;
field_init = 0x871b00;
field_font = 0x806a24;
field_color = 0x8069f0;
field_placeholder = 0x806a74;
field_max = 0x806b54;
field_secure = 0x806ab4;
field_focus = 0x806914;
field_clear = 0x8069e8;
field_text = 0x8069d8;
cstring = 0x868ce0;
cstring_format = 0x868960;
file_storage_path = 0x868c10;
file_make_directory = 0x813084;
current_account = 0x8ef368;
system_font = 0x7e89d4;
graphics_push = 0x7d6adc;
graphics_pop = 0x7d6bc4;
graphics_color = 0x7d6e0c;
graphics_round_rect = 0x7ce570;
graphics_string_init = 0x7d44c4;
graphics_string_destroy = 0x7d455c;
graphics_string = 0x7d3ad8;
account_completed = 0x8718f0;
game_jni_env = 0x8133e4;
memcpy = 0x869a60;
memset = 0x868d20;
""")
    subprocess.run([str(link), "--no-undefined", "-T", str(layout), "-e", "community_bind_entry",
                    "-o", str(image), str(c), str(assembly)], check=True)
    subprocess.run([str(objcopy), "--only-section=.community", "-O", "binary", str(image), str(flat)], check=True)
    listing = subprocess.check_output([str(nm), "--defined-only", str(image)], text=True)
    addresses = {name: int(address, 16) for address, _, name in (line.split() for line in listing.splitlines())}
    return flat.read_bytes(), addresses


def replace_branch(library: bytearray, instruction: int, target: int, *, link: bool = False) -> None:
    distance = target - instruction
    if distance % 4 or not -(1 << 27) <= distance < (1 << 27):
        raise ValueError("Native hook is outside the branch range")
    struct.pack_into("<I", library, instruction, (0x94000000 if link else 0x14000000) | ((distance // 4) & 0x3FFFFFF))


def patch_native(path: Path, directory: Path, toolchain: Path) -> None:
    library = bytearray(path.read_bytes())
    if hashlib.sha256(library).hexdigest() != LIBRARY_SHA256:
        raise ValueError("Expected the original ARM64 ACIES 2.5.1 library")

    # Show the original title's account picker even if an older native session
    # exists. First launch goes through doLogin, while a returning installation
    # can enter directly from doPatchComplete after loading its revision.
    replace_branch(library, 0x7B8E94, 0x7B8EBC)
    replace_branch(library, 0x7B8838, 0x7B891C)
    # Skip the title's billing connection and use the same ready state as
    # onLobbyIAPSync. Patch both the method and its virtual dispatch thunk.
    for state, connect in ((0x7B9BF0, 0x7B9C0C), (0x7B9C3C, 0x7B9C58)):
        struct.pack_into("<I", library, state, 0x52800109)  # mov w9, #8
        struct.pack_into("<I", library, connect, 0xD503201F)  # nop
    # Once authenticated, the title tap can finish directly through the game.
    # The community account takes the place of the old Play Games link prompt.
    replace_branch(library, 0x7B7680, 0x7B7688)

    # PVPGateway::requestLogin writes a CSString after the serialized player.
    # Use that locale field for the native SessionInfo.secret from HTTPS login.
    # This lets the gateway authenticate the game frame itself. The loopback
    # TLS forwarder accepts and transfers bytes without adding any credential.
    offset = 0x501068
    gateway = 0x8EEA48  # LobbyGateway::__gateway, the library's own data symbol.
    pages = ((gateway >> 12) - (offset >> 12)) & 0x1FFFFF
    adrp = 0x90000008 | ((pages & 3) << 29) | ((pages >> 2) << 5)
    load_gateway = 0xF9400108 | ((gateway & 0xFFF) // 8) << 10
    struct.pack_into("<5I", library, offset, adrp, load_gateway, 0xF9402108, 0xF9401101, 0xF9402260)

    code, symbols = compile_picker(directory, toolchain)
    for address, hook in {
        0x810130: "community_bind_entry", 0x7B30B4: "draw_account_picker",
        0x7B2ED0: "draw_sign_in", 0x7B2F54: "draw_register", 0x7B2FD8: "draw_continue",
        0x7B2F50: "tap_sign_in", 0x7B2FD4: "tap_register", 0x7B3058: "tap_continue",
    }.items():
        replace_branch(library, address, symbols[hook])
    replace_branch(library, 0x7B2978, symbols["init_account_picker_frame"], link=True)
    # GameRecord uses flat filenames for pending results and reconnect data.
    # Route all of its reads and writes through the signed-in player's directory.
    for address in (0x4F468C, 0x4F46CC, 0x4F4810, 0x4F48AC, 0x4F48EC, 0x4F48FC,
                    0x4F4980, 0x4F49D8, 0x4F49F8, 0x4F4A68, 0x4F4C48):
        replace_branch(library, address, symbols["player_record_path"], link=True)

    # The original note is redundant for loading. Extend the existing writable
    # BSS for transient picker state and place the code in a separate RX mapping.
    phoff = struct.unpack_from("<Q", library, 32)[0]
    phsize, phcount = struct.unpack_from("<HH", library, 54)
    headers = range(phoff, phoff + phsize * phcount, phsize)
    note, = [p for p in headers if struct.unpack_from("<I", library, p)[0] == 4]
    writable, = [p for p in headers if struct.unpack_from("<IIQQ", library, p)[0:2] == (1, 6)
                 and struct.unpack_from("<Q", library, p + 16)[0] == 0x8EE968]
    struct.pack_into("<Q", library, writable + 40, PICKER_DATA + 0x1000 - 0x8EE968)
    offset = (len(library) + 0x3FFF) & ~0x3FFF
    library.extend(bytes(offset - len(library)))
    library.extend(code)
    struct.pack_into("<II6Q", library, note, 1, 5, offset, PICKER_CODE, PICKER_CODE, len(code), len(code), 0x4000)
    path.write_bytes(library)


def build(source: Path, target: Path, sdk: Path, platform: str, build_tools: str, origin: str,
          gateway_port: int, ca: Path | None, toolchain: Path) -> None:
    if target.exists():
        raise FileExistsError(f"Output already exists: {target}")
    android_jar = sdk / "platforms" / platform / "android.jar"
    d8 = sdk / "build-tools" / build_tools / "d8"
    with tempfile.TemporaryDirectory(prefix="acies-community-", dir=target.parent) as tmp:
        root = Path(tmp)
        tree = root / "acies-apktool"
        subprocess.run(["apktool", "d", str(source), "-o", str(tree)], check=True)
        patch_manifest(tree / "AndroidManifest.xml")
        yml = tree / "apktool.yml"
        config, count = re.subn(r"(?m)^(\s*minSdkVersion:\s*)\d+$", rf"\g<1>{MIN_SDK}", yml.read_text())
        if count != 1:
            raise ValueError("Decoded APK has no minimum Android version")
        yml.write_text(config)
        patch_smali(tree)
        patch_native(tree / SOURCE_LIBRARY, root, toolchain)
        for folder in (tree / "lib").iterdir():
            if folder.name != "arm64-v8a":
                shutil.rmtree(folder)

        build_config = root / "BuildConfig.java"
        build_config.write_text(f"""package org.acies.community;
final class BuildConfig {{
    static final String ORIGIN = {json.dumps(origin)};
    static final int GATEWAY_PORT = {gateway_port};
    static final boolean LOCAL_CA = {str(ca is not None).lower()};
}}
""")
        classes = root / "classes"
        classes.mkdir()
        subprocess.run(["javac", "--release", "8", "-classpath", str(android_jar), "-d", str(classes),
                        str(build_config), *map(str, sorted(JAVA_ROOT.glob("*.java")))], check=True)
        jar = root / "community.jar"
        with zipfile.ZipFile(jar, "w") as archive:
            for item in classes.rglob("*.class"):
                archive.write(item, item.relative_to(classes))
        subprocess.run([str(d8), "--release", "--min-api", str(MIN_SDK), "--lib", str(android_jar),
                        "--output", str(root), str(jar)], check=True)
        rebuilt = root / "rebuilt.apk"
        subprocess.run(["apktool", "b", str(tree), "-o", str(rebuilt)], check=True)
        # APK alignment and signing happen after the new dex and certificate are added.
        with zipfile.ZipFile(rebuilt, "a", compression=zipfile.ZIP_DEFLATED) as apk:
            existing_dex = [int(number or 1) for item in apk.namelist()
                            if (match := re.fullmatch(r"classes(\d*)\.dex", item)) for number in match.groups()]
            apk.write(root / "classes.dex", f"classes{max(existing_dex) + 1}.dex")
            if ca is not None:
                apk.write(ca, "assets/community-ca.pem")
        rebuilt.replace(target)
    print(f"Unsigned community APK: {target}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--gateway-port", type=int, default=9443)
    parser.add_argument("--ca-cert", type=Path, help="Trust only this development CA for the configured local server.")
    parser.add_argument("--sdk", type=Path, default=os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT"))
    parser.add_argument("--platform", default="android-35")
    parser.add_argument("--build-tools", default="36.0.0")
    parser.add_argument("--ndk-toolchain", type=Path, help="NDK LLVM prebuilt directory. Defaults to an installed SDK NDK.")
    args = parser.parse_args()
    parsed = urlparse(args.origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        parser.error("--origin must be an HTTPS origin without a path or credentials")
    if not 1 <= args.gateway_port <= 65535:
        parser.error("--gateway-port must be between 1 and 65535")
    if args.sdk is None:
        parser.error("Set ANDROID_HOME or pass --sdk")
    toolchains = sorted(args.sdk.glob("ndk/*/toolchains/llvm/prebuilt/*/bin/clang"))
    if args.ndk_toolchain is None and toolchains:
        args.ndk_toolchain = toolchains[-1].parent.parent
    if args.ndk_toolchain is None:
        parser.error("Install the Android NDK or pass --ndk-toolchain")
    build(args.source.resolve(), args.output.resolve(), args.sdk.resolve(), args.platform, args.build_tools,
          args.origin.rstrip("/"), args.gateway_port, args.ca_cert, args.ndk_toolchain.resolve())


if __name__ == "__main__":
    main()
