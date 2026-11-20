#!/usr/bin/env python3
"""Build the locally hosted Acies Atlas from extracted APK assets."""

from __future__ import annotations

import argparse
from collections import defaultdict
from functools import lru_cache
import json
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory

from PIL import Image

from cdk_xmf_parse import decode_xmf as decode_text_xmf, parse_locale_string_table
from decode_acies_game_data import (
    CORE_ABILITY_ROLES,
    ParseError,
    Reader,
    decode_ability_line,
    decode_xmf,
    localized_name,
    parse_game_database,
)
from decode_acies_map import parse_map
from decode_cdk_image import decode_encoding, parse_root_image, parse_subimage_frames

ROOT = Path(__file__).resolve().parent.parent
UI = Path(__file__).with_name("acies_atlas")
DISPLAY_TAGS = re.compile(r"#(?:color|stroke|font|align|reset)\([^)]*\)|\$(?:emp|color)\([^)]*\)")
AUDIO_MANIFEST = ROOT / "decrypts/audio/manifest.json"
LOBBY_MUSIC_OFFSET = 0x1911F9
VOICE_EVENTS = ("Arrival", "Selection", "Command", "Exit")
VOICE_LANGUAGES = {"en": "English", "ko": "Korean"}
INTERFACE_SOUNDS = {
    (0, 1, 0): ("Button click", "SoundFxClick"),
    (1, 1, 0): ("Tab switch", "SoundFxTabMove"),
    (1, 1, 1): ("Clan created", "SoundFxClanCreate"),
    (1, 1, 2): ("Invitation", "SoundFxInvite"),
    (1, 1, 3): ("Chat notification", "SoundFxChatNotification"),
    (1, 1, 4): ("Warning", "SoundFxWarning"),
    (1, 1, 5): ("Minimap event", "SoundFxMinimapEvent"),
    (1, 1, 6): ("Command cue 1", "SoundFxCommand_0"),
    (1, 1, 7): ("Command cue 2", "SoundFxCommand_1"),
    (1, 1, 8): ("Match start", "SoundFxMatchStart"),
    (1, 1, 9): ("Match cancel", "SoundFxMatchCancel"),
    (1, 1, 10): ("Back button", "SoundFxBack"),
    (1, 1, 11): ("Product popup", "SoundFxProductPopupCommon"),
    (1, 1, 12): ("Skin popup", "SoundFxProductPopupSkin"),
    (1, 1, 13): ("Emoticon popup", "SoundFxProductPopupEmoticon"),
    (1, 1, 14): ("Cash popup", "SoundFxProductPopupCash"),
    (1, 1, 15): ("Gold popup", "SoundFxProductPopupGold"),
}


def label(translations):
    value = DISPLAY_TAGS.sub("", localized_name(translations)).strip()
    return "" if value == "ไม่มีข้อความ" else value


def grouped(section):
    for group, records in enumerate(section["items"]):
        for index, record in enumerate(records["items"]):
            yield f"{group}/{index}", record


def ability_labels(game):
    roles = dict(zip(game["short_table"]["items"], CORE_ABILITY_ROLES))
    return [
        (roles.get(index), label((ability["display"] or {}).get("name")) or f"Ability {index}")
        for index, ability in enumerate(game["abilities"]["items"])
    ]


def abilities(record, names):
    result = []
    for entry in record["ability_unit"]["entries"]["items"]:
        index = entry["key"]
        role, name = names[index]
        program = entry["value"]
        lines = []
        for source_line in program["bytecode_groups"]["items"]:
            instruction = decode_ability_line(source_line)
            instruction["offset"] = source_line["offset"]
            for obj in (instruction.get("source", {}), instruction.get("modifier", {})):
                for fixed in (obj.get("literal"), obj.get("factor"), *obj.get("level_table", [])):
                    if fixed is not None:
                        fixed["offset"] += source_line["offset"]
            lines.append(instruction)
        result.append({
            "id": index, "role": role, "name": name, "lines": lines,
            "bounds": [program[key]["value"] for key in ("min_value", "max_value")],
        })
    return result


def lookup_text(groups, reference):
    group, index = reference
    if group < len(groups) and index < len(groups[group]["strings"]):
        return label(groups[group]["strings"][index])
    return ""


def map_catalog(asset_root, strings):
    for path in sorted((asset_root / "maps").glob("map*.xmf")):
        raw, layers = decode_xmf(path, asset_root)
        data = parse_map(raw, path, layers, 0)
        if data["remaining"]:
            raise ParseError(f"{path.name} has {data['remaining']} unparsed bytes")
        meta = data["blocks"]["selected"]
        objectives = []
        for trigger in data["triggers"]:
            operands = trigger["operands"]
            if trigger["name"] != "mission" or not operands or operands["action"] != "upsert":
                continue
            ref = operands.get("text_ref")
            objective = label(operands.get("text")) if ref is None else lookup_text(strings, ref)
            objectives.append({
                "id": operands["mission_id"], "group": trigger["group"], "line": trigger["line"],
                "offset": trigger["offset"], "text": objective, "ref": ref,
            })
        yield {
            "id": path.stem, "name": label(meta["name"]) or path.stem,
            "description": label(meta["description"]),
            "width": data["terrain"]["width"], "height": data["terrain"]["height"],
            "icon_ref": next((entry["index"] for entry in meta["icons"] if entry["present"]), None),
            "objectives": objectives,
            "trigger_count": len(data["triggers"]),
            "audio_refs": [
                {"action": t["operands"]["action"], "sounds": t["operands"]["sounds"]}
                for t in data["triggers"]
                if t["name"] == "sound" and t["operands"] and "sounds" in t["operands"]
            ],
            "rules": [
                {"name": t["name"], "group": t["group"], "line": t["line"], "operands": t["operands"]}
                for t in data["triggers"]
                if t["operands"] and t["name"] in ("resource", "supply", "max_supply", "wait", "timer")
            ],
        }


@lru_cache(maxsize=4)
def atlas(asset_root, group, index):
    path = asset_root / "images" / f"images[{group:03d}][{index:03d}].xmf"
    raw, _ = decode_xmf(path, asset_root)
    meta = parse_root_image(raw)
    frames = parse_subimage_frames(raw, meta.get("tail_offset", 4))
    for encoding in meta["encodings"]:
        if encoding["code"] in (6, 7, 15):
            rgba, _ = decode_encoding(meta, encoding)
            return Image.frombytes("RGBA", (meta["width"], meta["height"]), rgba), frames
    raise ValueError("no supported texture encoding")


def export_icons(data, asset_root, output):
    entries = [
        (tuple(record["icon_ref"]), record)
        for kind in ("units", "runes", "maps")
        for record in data[kind] if record["icon_ref"] is not None
    ]
    entries.sort(key=lambda entry: entry[0])
    icon_dir = output / "icons"
    icon_dir.mkdir(exist_ok=True)
    written = {}
    for ref, record in entries:
        if ref not in written:
            group, atlas_id, index = ref
            destination = icon_dir / f"{group}-{atlas_id}-{index}.png"
            try:
                image, frames = atlas(asset_root, group, atlas_id)
                frame = frames[index]
                x0, y0, x1, y1 = frame
                if not (0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height):
                    raise ValueError(f"invalid frame {frame} for {image.size}")
                image.crop(frame).save(destination)
                written[ref] = f"icons/{destination.name}"
            except (OSError, ValueError, ParseError, IndexError) as error:
                print(f"Icon {ref}: {error}")
                written[ref] = None
        record["icon"] = written[ref]


def sound_filename(index):
    return "sound" + "".join(f"[{part:03d}]" for part in index) + ".ogg"


def audio_usage(game, maps, asset_root, unit_names):
    usage = {
        sound_filename(index): {"name": name, "symbol": symbol, "usage_kind": "Interface"}
        for index, (name, symbol) in INTERFACE_SOUNDS.items()
    }

    menu = asset_root / "data" / "menu.xmf"
    if menu.is_file():
        raw, _ = decode_xmf(menu, asset_root)
        if len(raw) == 0x191218:
            playlist = Reader(raw[LOBBY_MUSIC_OFFSET:])
            count = playlist.read_length()
            if playlist.remaining == count * 6:
                for number in range(1, count + 1):
                    index = playlist.read_asset_index3()
                    usage[sound_filename(index)] = {
                        "name": f"Lobby music {number}", "usage_kind": "Lobby",
                        "symbol": "LobbyLayer::playBgm",
                    }

    map_uses = defaultdict(list)
    for mission in maps:
        for reference in mission["audio_refs"]:
            for index in reference["sounds"]:
                map_uses[reference["action"], tuple(index)].append(mission["name"])
    for (action, index), names in map_uses.items():
        is_music = action == "play_music"
        kind = "Battle music" if is_music else "Map effect"
        usage[sound_filename(index)] = {
            "name": f"{kind} {index[2] + 1}" if is_music else f"{names[0]} · Sound effect",
            "usage_kind": kind, "symbol": "Map::mtSound", "uses": list(dict.fromkeys(names)),
        }

    voices = defaultdict(dict)
    for unit_id, unit in grouped(game["units"]):
        unit_name = unit_names[unit_id]
        for skin in unit["skins"]["items"]:
            skin_name = label(skin["name"])
            owner = f"{unit_name} ({skin_name})" if skin_name and skin_name.casefold() != unit_name.casefold() else unit_name
            for group in skin["voice_groups"]["items"]:
                languages = ", ".join(VOICE_LANGUAGES.get(key, key) for key in group["keys"])
                for slot, event in enumerate(VOICE_EVENTS):
                    for variant, index in enumerate(group["voice"][f"assets{slot}"]["items"], 1):
                        name = f"{owner} · {event} {variant}"
                        reference = f"{name} · {languages}" if languages else name
                        voices[sound_filename(index)][reference] = name
    for filename, references in voices.items():
        usage[filename] = {
            "name": next(iter(references.values())), "usage_kind": "Unit voice",
            "symbol": "SkinData::voice → Map::voice", "uses": list(references),
        }

    announcers = {}
    for pack, announce in enumerate(game["announces"]["items"], 1):
        for group in announce["groups"]["items"]:
            languages = [VOICE_LANGUAGES.get(item["text"], item["text"]) for item in group["items"]["items"]]
            announcers[tuple(group["key"])] = pack, languages
    return usage, announcers


def audio_catalog(manifest_path, usage, announcers):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    catalog = {"music": [], "sounds": []}
    unidentified_music = 0
    for record in manifest["audio"]:
        filename = record["file"]
        tags = {key.casefold(): value for key, value in record["tags"].items()}
        kind = "music" if record["category"] == "music" else "sounds"
        title = tags.get("title")
        native = re.fullmatch(r"(.+) \((SoundBgm\w+)\)", record["label"])
        identity = usage.get(filename, {})
        asset_id = re.fullmatch(r"sound\[(\d+)\]\[(\d+)\]\[(\d+)\]\.ogg", filename)
        if not identity and asset_id:
            first, second, line = map(int, asset_id.groups())
            if (first, second) in announcers:
                pack, languages = announcers[first, second]
                identity = {
                    "name": f"Announcer {pack} · Line {line + 1}", "usage_kind": "Announcer",
                    "symbol": "AnnounceData::voice", "uses": languages,
                }
        if native:
            name, symbol = native.groups()
        else:
            name, symbol = title or identity.get("name") or record["label"], identity.get("symbol")
        usage_kind = identity.get("usage_kind", "Title and reward" if native else "Embedded title" if title else "Unidentified")
        if usage_kind == "Unidentified":
            if kind == "music":
                unidentified_music += 1
                name = f"Unidentified track {unidentified_music}"
            elif asset_id:
                name = "Sound effect " + "-".join(asset_id.groups())
        catalog[kind].append({
            "id": filename,
            "name": name,
            "source": record["source"],
            "duration": record["duration_seconds"],
            "title": title,
            "symbol": symbol,
            "usage_kind": usage_kind,
            "uses": identity.get("uses", []),
            "artist": tags.get("artist"),
            "engineer": tags.get("engineer") or tags.get("ieng"),
            "album": tags.get("album"),
            "copyright": tags.get("copyright"),
            "license": tags.get("license") or tags.get("licence"),
        })
    return catalog


def link_extracted_audio(output, manifest_path, audio):
    source = manifest_path.parent / "all"
    expected = {record["id"] for kind in ("music", "sounds") for record in audio[kind]}
    files = list(source.iterdir())
    if not expected or {file.name for file in files} != expected or any(
        not file.is_file() or file.is_symlink() for file in files
    ):
        raise ValueError(f"{source} must contain exactly the audio files listed in {manifest_path}")

    link = output / "apk-audio"
    if link.is_symlink() and link.resolve() == source:
        return
    if link.exists() and not link.is_symlink():
        raise FileExistsError(link)
    with TemporaryDirectory(dir=output) as temp:
        pending = Path(temp) / link.name
        pending.symlink_to(source, target_is_directory=True)
        pending.replace(link)


def build(asset_root, output, version, manifest_path=AUDIO_MANIFEST, include_audio=False,
          include_vfx=False, vfx_captures=None, include_unit_art=False):
    path = asset_root / "data" / f"game[{version:03d}].xmf"
    raw, _ = decode_xmf(path, asset_root)
    game = parse_game_database(raw)
    if game["remaining"]:
        raise ParseError(f"{path.name} has {game['remaining']} unparsed bytes")
    names = ability_labels(game)
    strings_raw, _ = decode_text_xmf(asset_root / "strings.xmf", asset_root)
    strings = parse_locale_string_table(strings_raw)["groups"]
    units = []
    unit_data = list(grouped(game["units"]))
    for index, unit in unit_data:
        skins = unit["skins"]["items"]
        units.append({
            "id": index, "name": label(unit["name"]) or f"Unnamed unit {index}",
            "description": label(unit["description"]),
            "icon_ref": (skins[0]["indices"][0] if skins else None) or unit["optional_icon"],
            "stats": unit["balance_fields"], "abilities": abilities(unit, names),
        })
    runes = [
        {
            "id": index, "name": label(rune["name"]) or f"Unnamed rune {index}",
            "description": label(rune["description"]),
            "icon_ref": rune["icon0"], "abilities": abilities(rune, names),
        }
        for index, rune in grouped(game["runes"])
    ]
    data = {
        "version": version, "units": units, "runes": runes, "maps": list(map_catalog(asset_root, strings)),
        "attack_types": [label(r["name"]) for r in game["damage_types_a"]["items"]],
        "armor_types": [label(r["name"]) for r in game["damage_types_b"]["items"]],
        "damage_matrix": game["damage_matrix"]["items"],
    }
    if manifest_path.is_file():
        unit_names = {unit["id"]: unit["name"] for unit in units}
        usage, announcers = audio_usage(game, data["maps"], asset_root, unit_names)
        data.update(audio_catalog(manifest_path, usage, announcers))
        print(f"audio: {len(data['music'])} music and cue entries, {len(data['sounds'])} other sounds")
    elif manifest_path != AUDIO_MANIFEST or include_audio:
        raise FileNotFoundError(manifest_path)
    else:
        print(f"Audio catalog unavailable: {manifest_path}. Run tools/extract_acies_audio.py to generate it.")
    output.mkdir(parents=True, exist_ok=True)
    export_icons(data, asset_root, output)
    if include_audio:
        link_extracted_audio(output, manifest_path, data)
        data["audio_playback"] = True
    elif (output / "apk-audio").is_symlink():
        (output / "apk-audio").unlink()
    if include_vfx or vfx_captures is not None:
        from build_acies_vfx import export_vfx

        export_vfx(asset_root, output, atlas, vfx_captures)
    if include_unit_art:
        from build_acies_unit_art import export_unit_art

        export_unit_art(units, unit_data, asset_root, output, atlas, label)
    for path in UI.iterdir():
        if path.is_file():
            shutil.copyfile(path, output / path.name)
    (output / "atlas.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for kind in ("units", "runes", "maps"):
        records = data[kind]
        print(f"{kind}: {len(records)} records, {sum(bool(item.get('icon')) for item in records)} with art")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=ROOT / "acies-apktool/assets")
    parser.add_argument("--output", type=Path, default=ROOT / "work/acies-atlas")
    parser.add_argument("--version", type=int, default=83)
    parser.add_argument("--audio-manifest", type=Path, default=AUDIO_MANIFEST,
                        help="Path to the manifest generated by extract_acies_audio.py")
    parser.add_argument("--include-audio", action="store_true",
                        help="Enable playback by linking the extracted audio into the local build")
    parser.add_argument("--include-vfx", action="store_true", help="Export the animation library and previews")
    parser.add_argument("--vfx-captures", type=Path, help="Export VFX with authentic tutorial captures from this folder")
    parser.add_argument("--include-unit-art", action="store_true", help="Export inspectable unit motion sprites")
    args = parser.parse_args()
    build(args.assets.resolve(), args.output.resolve(), args.version, args.audio_manifest.resolve(),
          include_audio=args.include_audio, include_vfx=args.include_vfx, vfx_captures=args.vfx_captures,
          include_unit_art=args.include_unit_art)


if __name__ == "__main__":
    main()
