#!/usr/bin/env python3
"""Export the original ACIES animation inventory and lightweight web previews."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from math import dist, isfinite
from pathlib import Path
import shutil
import struct

from PIL import Image

import decode_cdk_animation as cdk
from decode_cdk_mesh import decode_xmf as decode_mesh_xmf, parse_mesh
from decode_acies_map import Reader as MapReader, decode_xmf as decode_map_xmf, parse_map, read_trigger_forces

ROOT = Path(__file__).resolve().parent.parent
REFERENCES = {
    "0/15/14": ("Tutorial 1 · Attack Move marker", "map[003][001][001] · group 2, line 53"),
    "0/15/15": ("Tutorial 1 · Move marker", "map[003][001][001] · group 2, line 30"),
    "0/15/22": ("Tutorial 1 · Troops focus cue", "map[003][001][001] · group 2, line 22"),
    "0/15/29": ("Tutorial 1 · Briefing art", "map[003][001][001] · group 2, line 3"),
    "0/15/35": ("Tutorial 1 · Briefing backdrop", "map[003][001][001] · group 2, line 0"),
    "0/15/0": ("Tutorial hand pointer", "map[003][006][001] · group 4, line 14"),
}
PORTRAITS = {"3/16/1": "Veteran", "3/16/4": "Instructor and Swordsman", "3/16/6": "Veteran (runes)",
             "3/16/10": "Sharpshooter", "3/16/11": "Senior Mage", "3/16/12": "Spell Instructor", "3/16/13": "Aide"}
TUTORIALS = ["Tutorial Opening", "Tutorial 1", "Tutorial 2", "Tutorial 3", "Rune Tutorial",
             "Drag Setup & Multi-Targeting", "Squad Setup & Release"]

CAPTURES = (
    ("briefing", "Briefing cards", "Unit portrait, Move, and Attack Move at the start of Tutorial 1."),
    ("dialogue", "Instructor dialogue", "Portrait, named speaker, dialogue box, and battlefield dimming."),
    ("focus", "Troops focus", "The cyan cue points to the active HUD control."),
    ("selection", "Selection confirmed", "Green indicators confirm the Troops input."),
    ("move", "Move destination", "The destination appears on the battlefield after selecting the squad."),
    ("attack", "Attack Move destination", "The next target introduces the double-tap order."),
    ("opening", "Tutorial Opening", "Scripted battle and world effects on a physical Pixel."),
)


def number(value, default=0):
    return round(value, 5) if isfinite(value) and abs(value) <= 100_000 else default


def channel(movement):
    if movement is None:
        return None
    if movement["type_id"] == 1:
        return [[0, number(movement["value"]), number(movement["value_var"])]]
    if movement["type_id"] == 2:
        return [[0, number(movement["start"]), number(movement["start_var"])],
                [1, number(movement["end"]), number(movement["end_var"])]]
    return [[number(p["time"]), number(p["value"]), number(p["value_var"])] for p in movement["points"]]


def image_key(ref, *, root=False):
    if (len(ref) == 3 or root and len(ref) == 2) and all(part != 65535 for part in ref):
        return "-".join(map(str, ref))
    return None


def sprite_frame(frame, limitations, *, extended=False):
    reader = cdk.Reader(bytes.fromhex(frame["hex"]))
    drawings = []
    color, blend = [255] * 4, 0
    while reader.remaining:
        opcode = reader.read_u8()
        payload = reader.take(reader.read_length())
        if opcode == 0 and len(payload) == 4:
            color = list(payload)
        elif opcode == 5 and len(payload) == 1:
            blend = payload[0]
        elif opcode == 20:
            color, blend = [255] * 4, 0
            if extended:
                drawings.append(["reset"])
        elif extended and opcode in (12, 13, 14) and len(payload) == 12:
            drawings.append([("translate", "scale", "rotate")[opcode - 12],
                             *[number(v) for v in struct.unpack("<3f", payload)]])
        elif extended and opcode in (15, 16):
            drawings.append(["scale", -1, -1 if opcode == 16 else 1, 1])
        elif extended and opcode == 17 and len(payload) == 1:
            drawings.append(["billboard", {0: 1, 1: 2, 2: 3}.get(payload[0], 0)])
        elif extended and opcode in (18, 19):
            drawings.append(["push" if opcode == 18 else "pop"])
        elif opcode == 21:
            # CSGraphics::sprImage at 0x7d023c chooses a point, rect, or cropped rect.
            src = cdk.Reader(payload)
            key = image_key([src.read_u16() for _ in range(src.read_u8())], root=extended)
            mode = src.read_u8()
            if key is None or mode not in (0, 1, 2):
                limitations.add("Special image references")
                continue
            x, y, z = [number(src.read_f32()) for _ in range(3)]
            if mode == 0:
                dimensions = [0, 0]
                align = src.read_u8()
            else:
                dimensions = [number(src.read_f32()), number(src.read_f32())]
                align = 0
            crop = [src.read_i16() for _ in range(4)] if mode == 2 else None
            drawings.append(["image", key, x, y, *dimensions, align, color, blend, crop, *([z] if extended else [])])
        elif opcode == 23 and len(payload) >= 21:
            x, y, z, width, height = [number(v) for v in struct.unpack_from("<5f", payload)]
            drawings.append(["rect", x, y, width, height, color, bool(payload[20]), *([z] if extended else [])])
        elif extended and opcode in (22, 24) and len(payload) >= (24 if opcode == 22 else 29):
            count = 6 if opcode == 22 else 7
            values = [number(v) for v in struct.unpack_from(f"<{count}f", payload)]
            if opcode == 22:
                drawings.append(["line", *values, color])
            else:
                drawings.append(["arc", *values, color, bool(payload[28])])
        else:
            limitations.add(f"Sprite command {opcode}")
    return drawings


def transforms(node):
    path = node["path"]
    # Native positionDuration reads local XYZ at offsets 0x40, 0x48 and 0x50.
    # The two earlier channels are target-relative motion, rather than local axes.
    offsets = [channel(path[key]) for key in ("z", "rotation_x", "rotation_y")]
    seconds = number(path["duration"])
    if path["using_speed"] and seconds > 0:
        first = [track[0][1] if track else 0 for track in offsets]
        last = [track[-1][1] if track else 0 for track in offsets]
        seconds = dist(first, last) / seconds
    return {"path": {**dict(zip("xyz", offsets)), "seconds": number(seconds), "loop": path["loop"]},
            **{name: {**{axis: channel(node[name][axis]) for axis in "xyz"},
                      "seconds": number(node[name]["duration"]), "loop": node[name]["loop"]}
               for name in ("scale", "rotation")}}


def make_preview(root, *, direction=None):
    duration, limitations, textures = 0.0, set(), set()
    layers = []
    records = Counter(node["substance"]["kind"] for node in cdk.walk_animations(root) if node["substance"])

    def walk(node, start, parent_transforms):
        nonlocal duration
        facing = node["key_mask"] & 0x3ffc
        if direction is not None and facing and not facing & direction:
            return start
        start += max(0, number(node["latency"]))
        node_time = max(0, number(node["duration"]))
        if node["stencil"] or node["target"] or node["invert"]:
            limitations.add("Native mask or target behavior")
        local_transforms = transforms(node)
        positioned = [*parent_transforms, [start, local_transforms]]
        substance = node["substance"]
        if substance:
            kind = substance["kind"]
            if kind == "sprite":
                frames = [sprite_frame(row, limitations, extended=True) for row in substance["bytecode"]["items"]]
                for frame in frames:
                    textures.update(item[1] for item in frame if item[0] == "image")
                if any(item[0] in ("image", "rect", "line", "arc") for frame in frames for item in frame):
                    seconds = max(0, number(substance["duration"])) * len(frames)
                    node_time = max(node_time, seconds * max(1, substance["loop"]["count"]) or 1)
                    layers.append({"kind": kind, "start": start, "end": start + node_time,
                                   "transforms": positioned, "seconds": seconds,
                                   "loop": substance["loop"], "frames": frames})
            elif kind == "particle":
                choices = [key for row in substance["sources"]["items"] if (key := image_key(row["items"], root=True))]
                if choices:
                    textures.update(choices)
                    life = max(0.04, number(substance["life"]))
                    delay = max(0, number(substance["emission_delay"]))
                    emission_time = max(node_time, local_transforms["path"]["seconds"], 0.35)
                    node_time = max(node_time, delay + emission_time + life)
                    shape = substance["shape"] or {}
                    ranges = shape.get("range", shape.get("bottom_range", 0))
                    radius = max(abs(number(v)) for v in ranges) if isinstance(ranges, list) else abs(number(ranges))
                    layers.append({"kind": kind, "start": start, "end": start + node_time,
                                   "transforms": positioned, "images": choices, "life": life,
                                   "variance": abs(number(substance["life_var"])), "delay": delay,
                                   "emission": emission_time, "rate": number(substance["emission_rate"]),
                                   "max": substance["emission_max"], "prewarm": number(substance["prewarm_time"]),
                                   "shape": shape.get("kind", "point"), "radius": radius,
                                   "range": [number(value) for value in ranges] if isinstance(ranges, list) else [number(ranges)] * 3,
                                   "shell": substance["shape_shell"], "billboard": substance["view_mode"],
                                   "stretch": number(substance.get("stretch_rate", 0)),
                                   "color": [channel(c) for c in substance["color"]],
                                   "velocity": [channel(c) for c in substance["position"]],
                                   "radial": channel(substance["radial"]),
                                   "size": channel(substance["scale"][0]), "spin": channel(substance["rotation"][2]),
                                   "blend": substance["blend_mode"]})
                else:
                    limitations.add("Particle image sources")
            elif kind == "model":
                mesh = image_key(substance["indices"]["items"], root=True)
                materials = [image_key(m["indices"]["items"], root=True) for m in substance["materials"]["items"]]
                textures.update(key for key in materials if key)
                if mesh:
                    node_time = max(node_time, number(node["rotation"]["duration"]), 1)
                    layers.append({"kind": kind, "start": start, "end": start + node_time,
                                   "transforms": positioned, "mesh": mesh, "materials": materials})
                    limitations.add("Mesh material lighting approximated")
            else:
                choices = [key for row in substance["sources"]["items"] if (key := image_key(row["items"], root=True))]
                if choices:
                    textures.update(choices)
                    node_time = max(node_time, number(substance["color_duration"]), 1.5)
                    layers.append({"kind": kind, "start": start, "end": start + node_time,
                                   "transforms": positioned, "images": choices,
                                   "color": [channel(c) for c in substance["color"]],
                                   "blend": substance["blend_mode"]})
                limitations.add("Trail or chain shown along a sample path")
        end = start + node_time
        derivation = node["derivation"]
        if derivation:
            children = derivation["children"]["items"]
            if derivation["kind"] in ("emission", "random"):
                limitations.add("Native animation spawning")
            previous_end = start
            for child in children:
                child_start = previous_end if derivation["kind"] == "linked" else start
                previous_end = walk(child, child_start, positioned)
                end = max(end, previous_end)
        duration = max(duration, end)
        return end

    walk(root, 0, [])
    return {"seconds": round(max(1, duration), 3), "layers": layers}, textures, records, limitations


def write_json(path, payload):
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
                         encoding="utf-8")
    temporary.replace(path)


def export_texture(key, asset_root, destination, load_atlas):
    group, index, *frames_ref = map(int, key.split("-"))
    image, frames = load_atlas(asset_root, group, index)
    x0, y0, x1, y1 = frames[frames_ref[0]] if frames_ref else (0, 0, image.width, image.height)
    if not (0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height):
        raise ValueError(f"Invalid crop for {key}")
    crop = image.crop((x0, y0, x1, y1))
    crop.save(destination / f"{key}.webp", format="WEBP", lossless=True, method=2)


def export_captures(source, destination):
    if source is None:
        return []
    visual = []
    folder = destination / "captures"
    folder.mkdir(exist_ok=True)
    for key, title, description in CAPTURES:
        for extension in ("webp", "png"):
            name = f"{key}.{extension}"
            if (source / name).is_file():
                shutil.copyfile(source / name, folder / name)
                visual.append({"title": title, "description": description, "image": f"vfx/captures/{name}"})
                break
    film = source / "tutorial-controls.mp4"
    if film.is_file():
        shutil.copyfile(film, folder / film.name)
        poster = next((capture["image"] for capture in visual if capture["title"] == "Troops focus"), None)
        visual.append({"title": "Tutorial 1 on a lab phone", "description": "Original client footage.",
                       "video": f"vfx/captures/{film.name}", "poster": poster})
    return visual


def tutorial_uses(asset_root):
    uses, portraits = {}, {}
    for index, title in enumerate(TUTORIALS):
        path = asset_root / "maps" / f"map[003][{index:03d}][001].xmf"
        if not path.is_file():
            continue
        raw, layers = decode_map_xmf(path, asset_root)
        for trigger in parse_map(raw, path, layers, 0)["triggers"]:
            opcode = trigger["opcode"]
            if opcode not in (30, 35, 54):
                continue
            raw_line = bytes.fromhex(trigger["hex"])
            reader = MapReader(raw_line[1:])
            if opcode == 30:
                # Map::mtEffect ends with AssetIndex3 and three single-byte flags.
                reader = MapReader(raw_line[-9:-3])
            elif opcode == 54:
                # Map::mtAnimation calls GameAnimation only in mode 1 (create).
                read_trigger_forces(reader)
                reader.take(2)
                if reader.read_u8() != 1:
                    continue
            ref = "/".join(map(str, reader.read_asset_index3()))
            # GameLayer::onDrawSpeech resolves the speech operand through Asset::image.
            table = portraits if opcode == 35 else uses
            table.setdefault(ref, []).append({"tutorial": index, "title": title,
                                              "group": trigger["group"], "line": trigger["line"],
                                              "kind": trigger["name"]})
    return uses, portraits


def annotate_tutorials(inventory, uses):
    featured = {ref: order for order, ref in enumerate(REFERENCES)}
    for row in inventory:
        row["name"], row["evidence"] = REFERENCES.get(row["id"], (f"{row['kind'].title()} {row['id']}", ""))
        row["tutorials"] = uses.get(row["id"], [])
    inventory.sort(key=lambda row: (featured.get(row["id"], len(featured)), not row["tutorials"],
                                    not row["preview"], row["offset"]))


def export_portraits(uses, asset_root, sprites, load_atlas):
    portraits = []
    for ref, usage in sorted(uses.items(), key=lambda pair: tuple(map(int, pair[0].split("/")))):
        key = ref.replace("/", "-")
        export_texture(key, asset_root, sprites, load_atlas)
        portraits.append({"title": PORTRAITS.get(ref, f"Portrait {ref}"), "id": ref,
                          "image": f"vfx/sprites/{key}.webp",
                          "tutorials": list(dict.fromkeys(row["title"] for row in usage))})
    return portraits


def export_sprites(keys, asset_root, sprites, load_atlas):
    available = set()
    # Walk one texture atlas at a time so each encoded sheet only needs one decode.
    for key in sorted(keys, key=lambda value: tuple(map(int, value.split("-")))):
        try:
            export_texture(key, asset_root, sprites, load_atlas)
        except (OSError, ValueError, RuntimeError, IndexError, NotImplementedError):
            continue
        available.add(key)
    return available


def export_meshes(keys, asset_root, directory):
    directory.mkdir(exist_ok=True)
    available = set()
    for key in sorted(keys):
        group, index = map(int, key.split("-"))
        source = asset_root / "meshes" / f"mesh[{group:03d}][{index:03d}].xmf"
        if not source.is_file():
            continue
        raw, layers = decode_mesh_xmf(source, asset_root)
        model = parse_mesh(raw, str(source), layers)
        nodes = [{"parent": node["parent_node_index"], "matrix": node["matrix"], "material": node["flags"]["sort"],
                  "vertices": [[*v["position"], *v["tex_coord"]] for v in node["vertices"]]}
                 for node in model["nodes"]]
        write_json(directory / f"{key}.json", {"nodes": nodes})
        available.add(key)
    return available


def export_battlefield(asset_root, captures, destination):
    path = asset_root / "maps" / "map[003][001][001].xmf"
    if not path.is_file():
        return None
    raw, layers = decode_map_xmf(path, asset_root)
    fov, near, far, tilt, distance, zoom = parse_map(raw, path, layers, 0)["camera"]["floats"]
    camera = {"fov": fov, "near": near, "far": far, "tilt": tilt, "distance": distance, "zoom": zoom}
    if captures is not None:
        source = next((captures / name for name in ("focus.png", "focus.webp") if (captures / name).is_file()), None)
        if source:
            with Image.open(source) as shot:
                # Tutorial 1 on the lab phone, cropped past the HUD and prompt.
                width, height = shot.size
                crop = tuple(round(value * scale) for value, scale in zip((395, 105, 1475, 712),
                                                                         (width / 1600, height / 720) * 2))
                shot.crop(crop).convert("RGB").resize((960, 540), Image.Resampling.LANCZOS).save(
                    destination / "battlefield.webp", "WEBP", quality=87)
            camera["image"] = "vfx/battlefield.webp"
    return camera


def export_vfx(asset_root, output, load_atlas, captures=None):
    source = asset_root / "animations.xmf"
    raw, _ = cdk.decode_xmf(source, asset_root)
    reader = cdk.Reader(raw)
    groups, errors = cdk.read_obj_array_partial(reader, 3, cdk.read_animation)
    destination = output / "vfx"
    sprites, effects = destination / "sprites", destination / "effects"
    sprites.mkdir(parents=True, exist_ok=True)
    effects.mkdir(exist_ok=True)
    all_textures, all_meshes, programs = set(), set(), []
    for first, group in enumerate(groups["items"]):
        for second, category in enumerate(group["items"]):
            for third, node in enumerate(category["items"]):
                asset_id = f"{first}/{second}/{third}"
                preview, textures, kinds, limitations = make_preview(node, direction=4 if first == 1 else None)
                programs.append((asset_id, node["_offset"], preview, textures, kinds, limitations))
                all_textures.update(textures)
                all_meshes.update(layer["mesh"] for layer in preview["layers"] if layer["kind"] == "model")
    del groups

    available = export_sprites(all_textures, asset_root, sprites, load_atlas)
    meshes = export_meshes(all_meshes, asset_root, destination / "meshes")
    inventory = []
    for asset_id, offset, preview, textures, kinds, limitations in programs:
        resolved = sorted(textures & available)
        if len(resolved) != len(textures):
            limitations.add("Unavailable image frames")
        has_drawing = any(item[0] in ("rect", "line", "arc") for layer in preview["layers"] if layer["kind"] == "sprite"
                          for frame in layer["frames"] for item in frame)
        mesh_refs = sorted({layer["mesh"] for layer in preview["layers"] if layer["kind"] == "model"} & meshes)
        playable = bool(resolved or has_drawing or mesh_refs)
        file_id = asset_id.replace("/", "-")
        if playable:
            preview["images"] = resolved
            preview["meshes"] = mesh_refs
            write_json(effects / f"{file_id}.json", preview)
        kind = max(kinds, key=kinds.get, default="timing")
        inventory.append({"id": asset_id, "kind": kind, "layers": dict(kinds), "offset": offset,
                          "limits": sorted(limitations), "preview": f"vfx/effects/{file_id}.json" if playable else None,
                          "icon": f"vfx/sprites/{resolved[0]}.webp" if resolved else None,
                          "duration": preview["seconds"] if playable else None})
    uses, portraits = tutorial_uses(asset_root)
    annotate_tutorials(inventory, uses)
    for row in inventory:
        row["world"] = (row["id"].split("/")[0] not in ("0", "3") or row["kind"] in ("model", "chain", "trail")
                        or any(use["kind"] == "effect" for use in row["tutorials"]))
    visual = export_captures(captures, destination)
    write_json(destination / "catalog.json", {
        "records": inventory, "captures": visual, "remaining": reader.remaining, "errors": errors,
        "tutorials": TUTORIALS, "portraits": export_portraits(portraits, asset_root, sprites, load_atlas),
        "battlefield": export_battlefield(asset_root, captures, destination),
    })
    print(f"VFX: {len(inventory)} animation entries, {sum(bool(row['preview']) for row in inventory)} previews, "
          f"{len(available)} animation texture crops, {reader.remaining} undecoded bytes", flush=True)


def main():
    from build_acies_atlas import atlas

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=ROOT / "acies-apktool/assets")
    parser.add_argument("--output", type=Path, default=ROOT / "work/acies-atlas")
    parser.add_argument("--captures", type=Path, help="Optional original-client reference images and clip")
    args = parser.parse_args()
    export_vfx(args.assets.resolve(), args.output.resolve(), atlas, args.captures)


if __name__ == "__main__":
    main()
