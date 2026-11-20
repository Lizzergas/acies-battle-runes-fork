#!/usr/bin/env python3
"""Build an unsigned, ARM64 Acies client with a local Arcade range."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zipfile

from decode_acies_game_data import FIXED_ONE, Reader, decode_xmf, localized_name, parse_game_database
from decode_acies_map import parse_map
from xmf_probe import file_key, strip_xor_check


LIBRARY = "lib/arm64-v8a/libcdkapp.so"
FINGERPRINT = "38a37aa8e270015b6c766744763b75c638829edf09373498a11fdf5de33e9ddd"
TERRAIN = "maps/map[000][001][001].xmf"
MAP = "maps/map[006][000][001].xmf"
CODE = 0x990000
DRAW = CODE + 0x200
TOUCH = CODE + 0x400
FRAME = CODE + 0x500
TEXT = FRAME + 0x10
CENTER = FRAME + 0x20
INDEX = FRAME + 0x30
NOP = 0xD503201F
EXTENSION = CODE + 0x1000
CONTROL_CONSTRUCTOR = CODE + 0x6100
CONTROL_DRAW = CODE + 0x6400
CONTROL_RECT = CODE + 0x6800
CONTROL_CENTER = CONTROL_RECT + 16
DEBUG_DRAW = CODE + 0x6900
DEBUG_LABEL = CODE + 0x6B00
SCENARIO_STATE_END = 0x984000
TEAM_LIMIT = 24
ROSTER_GROUPS = (0, 1, 3, 4)


def roster_entries(data):
    return [(group, index, localized_name(unit["name"]).strip())
            for group in ROSTER_GROUPS
            for index, unit in enumerate(data["units"]["items"][group]["items"])]


def signed(value, bits):
    return (value ^ (1 << (bits - 1))) - (1 << (bits - 1))


def immediate(value, bits):
    if not -(1 << (bits - 1)) <= value < (1 << (bits - 1)):
        raise ValueError(f"Branch or address displacement {value} does not fit {bits} bits")
    return value & ((1 << bits) - 1)


def branch(pc, target, link=False):
    return (0x94000000 if link else 0x14000000) | immediate((target - pc) // 4, 26)


def adr(pc, target, register):
    diff = immediate(target - pc, 21)
    return 0x10000000 | ((diff & 3) << 29) | ((diff >> 2) << 5) | register


def relocate(word, before, after, start, end, destination):
    def target_address(target):
        return destination + target - start if start <= target < end else target

    if word & 0x7C000000 == 0x14000000:  # B and BL
        target = target_address(before + 4 * signed(word & 0x3FFFFFF, 26))
        return branch(after, target, bool(word >> 31))
    if word & 0xFF000010 == 0x54000000 or word & 0x7E000000 == 0x34000000:  # B.cond and CBZ/CBNZ
        target = target_address(before + 4 * signed((word >> 5) & 0x7FFFF, 19))
        return (word & ~(0x7FFFF << 5)) | (immediate((target - after) // 4, 19) << 5)
    if word & 0x9F000000 == 0x90000000:  # ADRP
        pages = signed(((word >> 5) & 0x7FFFF) * 4 + ((word >> 29) & 3), 21)
        target = (before & ~0xFFF) + pages * 4096
        diff = immediate((target >> 12) - (after >> 12), 21)
        return (word & 0x9F00001F) | ((diff & 3) << 29) | ((diff >> 2) << 5)
    if word & 0x9F000000 == 0x10000000 or word & 0x7E000000 == 0x36000000:
        raise ValueError(f"Unexpected PC-relative instruction at {before:#x}")
    return word


def clone(original, start, end, destination, replacements):
    for before in range(start, end, 4):
        pc = destination + before - start
        word = struct.unpack_from("<I", original, before)[0]
        yield replacements[before](pc) if before in replacements else relocate(word, before, pc, start, end, destination)


def assemble_touch(directory):
    # Follows MapTestLayer::onTouchesEndedMap's offline path and CSView transition.
    # Native branches and addresses are resolved here so the object has no relocations.
    source = """
        stp x29, x30, [sp, #-48]!
        mov x29, sp
        stp x19, x20, [sp, #16]
        str x21, [sp, #32]
        mov x19, x0
        ldr x8, [x19]
        ldr x8, [x8, #0x38]
        blr x8
        cbz x0, done
        mov x20, x0
        ADDR 1
        mov w0, #30
        adrp x8, 0
        ldr x8, [x8, #0xb58]
        ldr x2, [x8]
        cbz x2, done
        mov x3, x2
        mov w4, #1
        CALL 0x872650
        cbz x0, done
        mov x21, x0
        mov x0, x20
        mov w1, wzr
        CALL 0x871ab0
        mov x0, x20
        mov x1, x21
        CALL 0x868ab0
    done:
        ldr x21, [sp, #32]
        ldp x19, x20, [sp, #16]
        ldp x29, x30, [sp], #48
        ret
    """
    lines = [".text"]
    pc = TOUCH
    for line in filter(None, map(str.strip, source.splitlines())):
        if line.startswith("CALL "):
            line = f".inst {branch(pc, int(line.split()[1], 16), True):#x}"
        elif line.startswith("ADDR "):
            line = f".inst {adr(pc, INDEX, int(line.split()[1])):#x}"
        elif line == "adrp x8, 0":
            line = f".inst {relocate(0xB0000A28, 0x797724, pc, 0, 0, 0):#x}"
        lines.append(line)
        if not line.endswith(":"):
            pc += 4
    asm = directory / "arcade-touch.S"
    obj = directory / "arcade-touch.o"
    asm.write_text("\n".join(lines) + "\n")
    subprocess.run(["clang", "--target=aarch64-linux-android", "-c", asm, "-o", obj], check=True)
    data = obj.read_bytes()
    start = struct.unpack_from("<Q", data, 40)[0]
    size, count = struct.unpack_from("<HH", data, 58)
    for index in range(count):
        header = start + index * size
        section_type, flags = struct.unpack_from("<IQ", data, header + 4)
        if section_type == 1 and flags & 4:
            offset, length = struct.unpack_from("<QQ", data, header + 24)
            return data[offset:offset + length]
    raise ValueError("No executable section in launcher object")


def compile_scenario(directory, roster, ndk):
    if len(roster) != 56:
        raise ValueError("Unexpected Arcade roster; update the native roster size")
    source = Path(__file__).with_name("acies_arcade")
    names = [name or f"Unit {group}/{index}" for group, index, name in roster]
    declarations = {"roster": names}
    for side in (1, 2):
        declarations[f"team{side}_labels"] = [f"Add to team {side} ({i})" for i in range(TEAM_LIMIT + 1)]
    (directory / "roster.h").write_text("\n".join(
        f"static const char {key}[][{max(len(name.encode()) for name in contents) + 1}] = {{ "
        + ", ".join(json.dumps(name, ensure_ascii=False) for name in contents) + " };"
        for key, contents in declarations.items()
    ) + "\n")

    clang = ndk / "bin" / "clang"
    link = ndk / "bin" / "ld.lld"
    objcopy = ndk / "bin" / "llvm-objcopy"
    nm = ndk / "bin" / "llvm-nm"
    program = directory / "scenario.o"
    hooks = directory / "hooks.o"
    out = directory / "scenario.elf"
    flat = directory / "scenario.bin"
    flags = ["--target=aarch64-linux-android23", "-ffreestanding", "-fno-stack-protector",
             "-fno-unwind-tables", "-fno-asynchronous-unwind-tables", "-fno-jump-tables",
             "-fno-pic", "-fno-pie", "-Os"]
    subprocess.run([clang, *flags, "-I", directory, "-c", source / "scenario.c", "-o", program], check=True)
    subprocess.run([clang, *flags, "-c", source / "hooks.S", "-o", hooks], check=True)
    layout = directory / "layout.ld"
    layout.write_text(f"""SECTIONS {{
        . = {EXTENSION:#x};
        arcade_image_start = .;
        .arcade : {{ *(.text*) *(.rodata*) *(.data.rel.ro*) *(.data*) *(.got*) }}
        /DISCARD/ : {{ *(.comment*) *(.note*) *(.eh_frame*) }}
    }}
    draw_delegate_slot = 0x8ddd40;
    button_constructor = {CONTROL_CONSTRUCTOR:#x};
    button_draw = {CONTROL_DRAW:#x};
    option_after_contact = 0x732e00;
    original_map_test_return = 0x626344;
    lobby_after_rewards = 0x626738;
    original_update = 0x581dcc;
    """)
    subprocess.run([link, "--no-undefined", "-T", layout, "-e", "arcade_start",
                    "-o", out, program, hooks], check=True)
    subprocess.run([objcopy, "--only-section=.arcade", "-O", "binary", out, flat], check=True)
    listing = subprocess.check_output([nm, "--defined-only", out], text=True)
    addresses = {name: int(address, 16) for address, _, name in (line.split() for line in listing.splitlines())}
    payload = flat.read_bytes()
    if len(payload) > CONTROL_CONSTRUCTOR - EXTENSION:
        raise ValueError("Native scenario code overlaps the button routines")
    # This code is injected after ELF linking. Callback addresses must be computed
    # at runtime relative to the client image, including those held in structs.
    callbacks = ("select_debug", "draw_arcade_entry", "draw_map_test_entry",
                 "open_map_test", "draw_scenario_control", "arcade_click")
    if any(struct.pack("<Q", address) in payload
           for address in (DEBUG_DRAW, TOUCH, *(addresses[name] for name in callbacks))):
        raise ValueError("Native scenario payload contains an absolute callback address")
    return payload, addresses


def install_scenario(code, raw, image, directory, roster, ndk):
    payload, symbols = compile_scenario(directory, roster, ndk)
    code[EXTENSION - CODE:EXTENSION - CODE + len(payload)] = payload

    # Reuse the verified lobby button construction with supplied frame and delegates.
    # The assembly wrapper places the frame pointer in x25 and the owner in x19.
    constructor = list(clone(raw, 0x732C88, 0x732E00, CONTROL_CONSTRUCTOR, {
        0x732CAC: lambda _: 0xAA1903E8,  # mov x8, x25
        0x732CB0: lambda _: 0x3DC00100,  # ldr q0, [x8]
        0x732CE4: lambda _: 0xF9400B29,  # ldr x9, [x25, #16] (draw)
        0x732D7C: lambda _: 0xF9400F29,  # ldr x9, [x25, #24] (touch)
    }))
    # The cloned constructor calls virtual addLayer. Preserve its own return address.
    # Callers reserve 48 bytes for the clone's temporary storage.
    # Return via the wrapper's saved LR slot, carrying the created button in x21.
    constructor.extend((0xF94017FE, 0xD65F03C0))  # ldr x30, [sp,#40]; ret
    struct.pack_into(f"<{len(constructor)}I", code, CONTROL_CONSTRUCTOR - CODE, *constructor)

    none = lambda _: NOP
    replacements = {pc: none for pc in range(0x733340, 0x733378, 4)}
    replacements.update({pc: none for pc in range(0x7333B0, 0x7333D4, 4)})
    replacements.update({
        0x73330C: lambda pc: adr(pc, CONTROL_RECT, 8),
        0x733310: lambda _: 0x3DC00100,
        0x7333D4: lambda _: 0xAA1803E1,  # mov x1, x24 (caption)
        0x7333DC: lambda pc: branch(pc, 0x86AE20, True),
        0x7333E0: lambda pc: adr(pc, CONTROL_CENTER, 8),
        0x7333E4: lambda _: 0xFD400100,
        0x7333F4: lambda _: 0x52A86308,  # mov w8, #0x43180000 (152 px)
    })
    draw = list(clone(raw, 0x7332D4, 0x73343C, CONTROL_DRAW, replacements))
    struct.pack_into(f"<{len(draw)}I", code, CONTROL_DRAW - CODE, *draw)
    struct.pack_into("<6f", code, CONTROL_RECT - CODE, 0.0, 0.0, 180.0, 37.0, 90.0, 18.5)

    # Use the existing tab renderer with the dedicated Debug id and caption.
    tab_draw = list(clone(raw, 0x7330A4, 0x733258, DEBUG_DRAW, {
        0x7330C4: none,
        **{pc: none for pc in range(0x7330D0, 0x7330F4, 4)},
        0x7330F4: lambda _: 0x52800117,  # mov w23, #8
        **{pc: none for pc in range(0x7331B8, 0x7331DC, 4)},
        0x7331DC: lambda pc: adr(pc, DEBUG_LABEL, 1),
        0x7331E4: lambda pc: branch(pc, 0x86AE20, True),
    }))
    struct.pack_into(f"<{len(tab_draw)}I", code, DEBUG_DRAW - CODE, *tab_draw)
    code[DEBUG_LABEL - CODE:DEBUG_LABEL - CODE + 6] = b"Debug\0"
    struct.pack_into("<I", image, 0x732DFC, branch(0x732DFC, symbols["debug_settings_hook"]))
    struct.pack_into("<I", image, 0x626340, branch(0x626340, symbols["debug_return_hook"]))
    struct.pack_into("<I", image, 0x6145D0, branch(0x6145D0, symbols["arcade_start"]))
    struct.pack_into("<I", image, 0x581DC8, branch(0x581DC8, symbols["arcade_update_hook"]))


def patch_library(raw, directory, roster=None, ndk=None):
    if hashlib.sha256(raw).hexdigest() != FINGERPRINT:
        raise ValueError("Unsupported ARM64 client binary")
    image = bytearray(raw)
    code = bytearray(0x7000 if roster is not None else 0x540)
    start, end = 0x732C88, 0x732E00
    none = lambda _: NOP
    # The battle Options constructor branches straight to end and skips Contact.
    # Intercept only the lobby's Contact add call, then add the Arcade sibling.
    button = [0xD63F0100]  # blr x8, the original Contact add call
    button.extend(clone(raw, start, end, CODE + 4, {
        0x732CAC: lambda pc: adr(pc, FRAME, 8),
        0x732CB0: lambda _: 0x3DC00100,  # ldr q0, [x8]
        0x732CE4: lambda pc: adr(pc, DRAW, 9),
        0x732D7C: lambda pc: adr(pc, TOUCH, 9),
    }))
    button.append(branch(CODE + len(button) * 4, end))
    struct.pack_into(f"<{len(button)}I", code, 0, *button)
    draw = list(clone(raw, 0x7332D4, 0x73343C, DRAW, {
        0x733374: none,  # Omit the Contact envelope.
        **{pc: none for pc in range(0x7333B0, 0x7333D4, 4)},
        0x7333D4: lambda pc: adr(pc, TEXT, 1),
        0x7333DC: lambda pc: branch(pc, 0x86AE20, True),  # StringParam(const char*)
        0x7333E0: lambda pc: adr(pc, CENTER, 8),
        0x7333E4: lambda _: 0xFD400100,  # ldr d0, [x8]
    }))
    struct.pack_into(f"<{len(draw)}I", code, DRAW - CODE, *draw)
    touch = assemble_touch(directory)
    code[TOUCH - CODE:TOUCH - CODE + len(touch)] = touch
    struct.pack_into("<4f8s8x2f8x4H", code, FRAME - CODE,
                     10.0, 474.0, 280.0, 60.0, b"Arcade", 140.0, 30.0, 6, 0, 1, 0)
    struct.pack_into("<I", image, end - 4, branch(end - 4, CODE))

    if roster is not None:
        install_scenario(code, raw, image, directory, roster, ndk)

    # The original PT_NOTE is redundant for loading. Use that program-header slot
    # for an appended read-only executable segment, leaving existing mappings intact.
    phoff = struct.unpack_from("<Q", image, 32)[0]
    phsize, phcount = struct.unpack_from("<HH", image, 54)
    note, = [p for p in range(phoff, phoff + phsize * phcount, phsize)
             if struct.unpack_from("<I", image, p)[0] == 4]
    if roster is not None:
        last_writable_load, = [p for p in range(phoff, phoff + phsize * phcount, phsize)
                               if struct.unpack_from("<IIQQ", image, p)[:2] == (1, 6)
                               and struct.unpack_from("<Q", image, p + 16)[0] == 0x8EE968]
        struct.pack_into("<Q", image, last_writable_load + 40, SCENARIO_STATE_END - 0x8EE968)
    offset = (len(image) + 0x3FFF) & ~0x3FFF
    image.extend(bytes(offset - len(image)))
    image.extend(code)
    struct.pack_into("<II6Q", image, note, 1, 5, offset, CODE, CODE, len(code), len(code), 0x4000)
    return image


def length(value):
    parts = [value & 127]
    while value >= 128:
        value >>= 7
        parts.append((value & 127) | 128)
    return bytes(reversed(parts))


def text(value):
    data = value.encode()
    return length(len(data)) + data


def array(values):
    return length(len(values)) + b"".join(values)


def point(x, y):
    return struct.pack("<qq", round(x * FIXED_ONE), round(y * FIXED_ONE))


def create_map(asset_root, roster=None):
    source = asset_root / TERRAIN
    raw, layers = decode_xmf(source, asset_root)
    template = parse_map(raw, source, layers, 0)
    if template["remaining"] or template["blocks"]["block_count"] != 1:
        raise ValueError("Unexpected terrain template structure")
    game, _ = decode_xmf(asset_root / "data/game[083].xmf", asset_root)
    data = parse_game_database(game)
    # Controllable troops, utility units and buildings. Spell effects are different
    # object types and need deck setup rather than placement on the map.
    sandbox = roster is not None
    units = [(group, index) for group, index, _ in (roster if sandbox else roster_entries(data))]
    tiles = template["tiles"]["items"]
    width = template["terrain"]["width"]

    def spots(x_start, x_stop):
        return [(x + 0.5, y + 0.5) for y in range(37, 76, 4) for x in range(x_start, x_stop, 4)
                if all(tiles[(y + dy) * width + x + dx]["value"] == 4
                       for dx in (-1, 0, 1) for dy in (-1, 0, 1))]

    def squad(indices, locations, slot):
        return array([struct.pack("<HHB", *unit, 1) + point(*location)
                      + struct.pack("<qBHH", 0, slot, 1, 0)
                      for unit, location in zip(indices, locations, strict=True)])

    home = spots(39, 79)
    enemy = spots(91, 133)
    if len(home) < len(units) or len(enemy) < 12:
        raise ValueError("Too few clear placement cells for the range")
    targets = [(3, 1), (3, 2), (3, 7), (3, 17)] * 3
    spawn = array([squad(units, home[:len(units)], 0), squad(targets, enemy[:12], 1)])
    triggers = [
        bytes.fromhex("0c 02 01 00 00 00 00 00 00"),  # force 0, point 0, no random offset
        b"\x07\x00\x00" + struct.pack("<h", 500),
        b"\x06\x00\x00\x00" + struct.pack("<h", 10000),
        b"\x06\x00\x01\x00" + struct.pack("<h", 10000),
        bytes.fromhex("0d01000000000000"),
        bytes.fromhex("0d01000100000000"),
        bytes.fromhex("1c000100"),
    ]
    points = [point(53, 46)]
    expected_groups = [len(units), 12]
    if sandbox:
        if min(len(home), len(enemy)) < TEAM_LIMIT:
            raise ValueError("Too few scenario deployment positions")
        spawn = array([squad([unit], [locations[0]], side)
                       for side, locations in enumerate((home, enemy)) for unit in units])
        points[0] = point(103, 54.5)
        # These pads and the corridor between them lie on one flat plateau.
        for start, front in ((93, 101.5), (104, 104.5)):
            locations = [(x + 0.5, y + 0.5)
                         for x in range(start, start + 10, 2) for y in range(49, 60, 2)]
            if any(tiles[int(y) * width + int(x)]["value"] != 4 for x, y in locations):
                raise ValueError("Scenario clearing contains a blocked deployment cell")
            ordered = sorted(locations, key=lambda xy: (xy[0] - front) ** 2 + (xy[1] - 54.5) ** 2)
            points.extend(point(*xy) for xy in ordered[:TEAM_LIMIT])
        reveal = bytes.fromhex("1b0000000019000001")  # Reveal 25 tiles around point 0.
        triggers = triggers[:4] + [reveal, triggers[-1], bytes.fromhex("39 06 00 01")]
        expected_groups = [1] * (2 * len(units))
    # Retain the game's terrain and prop art, with a new roster, spawn layout,
    # resources, rule script, and camera starting point.
    block = template["blocks"]["selected"]
    r = Reader(raw)
    r.pos = block["payload_offset"]
    r.read_locale_string()
    r.read_locale_string()
    names = array([text("en") + text("Unit Test Range")])
    descriptions = array([text("en") + text("Test Acies units against targets on a private practice map.")])
    header = names + descriptions + raw[r.pos:block["payload_end"]]
    camera = template["camera"]
    # The native constructor requires a starting placement for each active force.
    placements = array([points[0] + b"\x00", point(103, 46) + b"\x02"])
    patched = (b"\x01" + struct.pack("<I", len(header)) + header
               + raw[block["payload_end"]:template["props"]["_end"]]
               + spawn + placements + array(points) + b"\x00"
               + raw[camera["_offset"]:camera["_end"]] + array([array([length(len(t)) + t for t in triggers])]))
    verified = parse_map(patched, Path(MAP), [], 0)
    if (verified["remaining"] or [g["count"] for g in verified["squads"]["items"]] != expected_groups
            or verified["unit_settings"]["count"] != verified["blocks"]["selected"]["force_slots"]["count"]):
        raise ValueError("Generated map did not round-trip")
    compressed = gzip.compress(patched, mtime=0)
    _, _, checksum, _ = strip_xor_check(compressed + bytes(4))
    key = file_key(MAP)
    encrypted = subprocess.run(
        ["openssl", "enc", "-aes-256-cbc", "-K", key.hex(), "-iv", key[:16].hex()],
        input=compressed + struct.pack("<I", checksum), capture_output=True, check=True,
    ).stdout
    print(f"Generated {MAP} with {len(units)} deployable types and {len(expected_groups)} squads.")
    return encrypted


def build(source, output, asset_root, ndk=None):
    roster = None
    if ndk is not None:
        game, _ = decode_xmf(asset_root / "data/game[083].xmf", asset_root)
        roster = roster_entries(parse_game_database(game))
    asset = f"assets/{MAP}"
    with tempfile.TemporaryDirectory(prefix="acies-arcade-") as temporary:
        with zipfile.ZipFile(source) as original:
            library = patch_library(original.read(LIBRARY), Path(temporary), roster, ndk)
            scenario = create_map(asset_root, roster)
            with zipfile.ZipFile(output, "x") as modified:
                for entry in original.infolist():
                    if entry.filename.startswith("META-INF/") and entry.filename.endswith((".SF", ".RSA", ".DSA", ".EC", ".MF")):
                        continue
                    if entry.filename == LIBRARY:
                        modified.writestr(entry, library)
                    else:
                        with original.open(entry) as src, modified.open(entry, "w") as dst:
                            shutil.copyfileobj(src, dst, 1024 * 1024)
                modified.writestr(asset, scenario)
    print(f"Wrote unsigned APK to {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--asset-root", type=Path, default=Path("acies-apktool/assets"))
    parser.add_argument("--scenario-toolchain", type=Path, help="NDK LLVM prebuilt directory for the in-game scenario controls")
    args = parser.parse_args()
    build(args.source, args.output, args.asset_root, args.scenario_toolchain)


if __name__ == "__main__":
    main()
