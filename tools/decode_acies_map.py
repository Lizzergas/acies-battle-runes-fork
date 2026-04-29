#!/usr/bin/env python3
"""Decode ACIES map .xmf files.

This is a static reader for the native map payload consumed by
Map::Map(AssetIndex4 const&, CSBuffer*, ...).  It reuses the CDK XMF decrypt
layer, the CSRootImage parser, and field order recovered from libcdkapp.so.
The trigger program is intentionally kept as raw nested byte arrays for now;
that bytecode is interpreted by the Map::mt* functions rather than by CDK3's
generic trigger editor.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import struct
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from decode_acies_game_data import (  # noqa: E402
    ASSET_ROOT,
    FIXED_ONE,
    ParseError,
    Reader,
    compact_bytes,
    decode_xmf,
    read_obj_array,
    read_u8_array,
)
from decode_cdk_image import parse_root_image  # noqa: E402


DEFAULT_OUT_DIR = pathlib.Path("decrypts/maps")


def offset_obj(start: int, end: int, values: dict[str, Any]) -> dict[str, Any]:
    return {"_offset": start, "_end": end, "_size": end - start, **values}


def image_meta(data: bytes, offset: int) -> dict[str, Any]:
    meta = parse_root_image(data[offset:])
    encodings = [
        {
            "code": enc["code"],
            "payload_length": enc["payload_length"],
            "payload_offset": offset + 4 + enc["payload_offset"],
        }
        for enc in meta["encodings"]
    ]
    return {
        "offset": offset,
        "length": meta["tail_offset"],
        "empty": meta["empty"],
        "block_length": meta["block_length"],
        "format_prefix": meta.get("format_prefix"),
        "width": meta.get("width"),
        "height": meta.get("height"),
        "encoding_count": meta.get("encoding_count", 0),
        "encodings": encodings,
        "block_remaining": meta.get("block_remaining"),
    }


def read_color(r: Reader, normalized: bool) -> dict[str, Any]:
    start = r.pos
    if normalized:
        raw = list(r.take(4))
        return offset_obj(
            start,
            r.pos,
            {
                "normalized": True,
                "rgba_u8": raw,
                "rgba": [round(v / 255.0, 6) for v in raw],
            },
        )
    return offset_obj(
        start,
        r.pos + 16,
        {"normalized": False, "rgba": [r.read_f32(), r.read_f32(), r.read_f32(), r.read_f32()]},
    )


def read_color3(r: Reader, normalized: bool) -> dict[str, Any]:
    start = r.pos
    if normalized:
        raw = list(r.take(3))
        return offset_obj(
            start,
            r.pos,
            {"normalized": True, "rgb_u8": raw, "rgb": [round(v / 255.0, 6) for v in raw]},
        )
    return offset_obj(
        start,
        r.pos + 12,
        {"normalized": False, "rgb": [r.read_f32(), r.read_f32(), r.read_f32()]},
    )


def read_vector2(r: Reader) -> dict[str, float]:
    return {"x": r.read_f32(), "y": r.read_f32()}


def read_asset_ref2(r: Reader) -> dict[str, Any] | None:
    """Read the BuildReference-style optional two-part asset reference."""
    start = r.pos
    marker = r.read_length()
    if marker == 1:
        return offset_obj(start, r.pos + 2, {"present": True, "marker": marker, "index": r.read_u16()})
    return offset_obj(start, r.pos, {"present": False, "marker": marker})


def read_material(r: Reader) -> dict[str, Any]:
    start = r.pos
    material = {
        "color": read_color(r, normalized=False),
        "float0": r.read_f32(),
        "float1": r.read_f32(),
        "color3": read_color3(r, normalized=False),
    }
    return offset_obj(start, r.pos, material)


def read_unit_base(r: Reader) -> dict[str, Any]:
    start = r.pos
    return offset_obj(
        start,
        r.pos + 8,
        {
            "index": r.read_asset_index2(),
            "level": r.read_i16(),
            "skin": r.read_i16(),
        },
    )


def read_card(r: Reader) -> dict[str, Any]:
    start = r.pos
    item = {"unit_base": read_unit_base(r)}
    return offset_obj(start, r.pos, item)


def read_rune(r: Reader) -> dict[str, Any]:
    start = r.pos
    item = {"index": r.read_asset_index2(), "level": r.read_i16()}
    return offset_obj(start, r.pos, item)


def read_user_thumb(r: Reader, locale_name: bool) -> dict[str, Any]:
    start = r.pos
    user_id = r.read_i64()
    if locale_name:
        name: Any = r.read_locale_string()
    else:
        name = r.read_string()
    item = {
        "id": user_id,
        "name": name,
        "level": r.read_i16(),
        "indices": [r.read_asset_index2(), r.read_asset_index2(), r.read_asset_index2(), r.read_asset_index2()],
        "tag": r.read_string(),
    }
    return offset_obj(start, r.pos, item)


def read_user_record(r: Reader, record_type: str) -> dict[str, Any]:
    start = r.pos
    item = {
        "record_type": record_type,
        "int0": r.read_i32(),
        "int1": r.read_i32(),
        "int2": r.read_i32(),
        "byte0": r.read_u8(),
        "byte1": r.read_u8(),
    }
    return offset_obj(start, r.pos, item)


def read_player(r: Reader, locale_name: bool) -> dict[str, Any]:
    start = r.pos
    item: dict[str, Any] = {
        "thumb": read_user_thumb(r, locale_name=locale_name),
        "short0": r.read_i16(),
    }
    if not locale_name:
        has_clan = r.read_bool()
        item["has_clan"] = has_clan
        if has_clan:
            item["clan"] = read_clan_thumb(r)
        item["record0"] = read_user_record(r, "record0")
        item["record1"] = read_user_record(r, "record1")
    item["force_base_index"] = r.read_asset_index2()
    item["cards"] = read_obj_array(r, 1, read_card)
    item["runes"] = read_obj_array(r, 1, read_rune)
    return offset_obj(start, r.pos, item)


def read_clan_thumb(r: Reader) -> dict[str, Any]:
    start = r.pos
    item = {
        "id": r.read_i64(),
        "name": r.read_string(),
        "indices": [r.read_asset_index2(), r.read_asset_index2(), r.read_asset_index2()],
    }
    return offset_obj(start, r.pos, item)


def parse_map_blocks(r: Reader, selected_block: int = 0) -> dict[str, Any]:
    start = r.pos
    block_count = r.read_length()
    blocks = []
    selected: dict[str, Any] | None = None
    for block_index in range(block_count):
        length_offset = r.pos
        block_length = r.read_i32()
        payload_start = r.pos
        payload_end = payload_start + block_length
        if payload_end > len(r.data):
            raise ParseError(f"map block {block_index} exceeds decoded payload")
        block = {
            "index": block_index,
            "length_offset": length_offset,
            "payload_offset": payload_start,
            "payload_end": payload_end,
            "length": block_length,
        }
        if block_index == selected_block:
            before = r.pos
            block.update(parse_selected_block(r, payload_end))
            selected = block
            block["parsed_size"] = r.pos - before
            if r.pos < payload_end:
                block["trailing"] = compact_bytes(r.take(payload_end - r.pos))
        else:
            r.pos = payload_end
        blocks.append(block)
    return offset_obj(
        start,
        r.pos,
        {"block_count": block_count, "selected_block": selected_block, "blocks": blocks, "selected": selected},
    )


def parse_selected_block(r: Reader, payload_end: int) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": r.read_locale_string(),
        "description": r.read_locale_string(),
        "kind_byte": r.read_u8(),
        "icons": [],
    }
    for _ in range(3):
        present = r.read_bool()
        item["icons"].append({"present": present, "index": r.read_asset_index3() if present else None})

    count = r.read_u8()
    item["force_slots"] = {
        "count": count,
        "items": [
            {"slot": r.read_u8(), "team": r.read_u8(), "control": r.read_u8()} for _ in range(count)
        ],
    }

    count = r.read_u8()
    players = []
    for _ in range(count):
        players.append(
            {
                "byte0": r.read_u8(),
                "byte1": r.read_u8(),
                "byte2": r.read_u8(),
                "byte3": r.read_u8(),
                "player": read_player(r, locale_name=True),
            }
        )
    item["player_slots"] = {"count": count, "items": players}

    if r.pos > payload_end:
        raise ParseError(f"selected block overread by {r.pos - payload_end} bytes")
    return item


def parse_terrain(r: Reader) -> dict[str, Any]:
    start = r.pos
    width = r.read_u8()
    height = r.read_u8()

    root_image = image_meta(r.data, r.pos)
    r.pos += root_image["length"]

    item: dict[str, Any] = {
        "width": width,
        "height": height,
        "root_image": root_image,
        "bytes0": list(r.take(4)),
        "color": read_color(r, normalized=True),
        "light": {
            "float0": r.read_f32(),
            "color3": read_color3(r, normalized=False),
            "vector3": {"x": r.read_f32(), "y": r.read_f32(), "z": r.read_f32()},
        },
    }
    altitude_length = ((width << 3) + 8) * (height + 1)
    altitude_offset = r.pos
    altitude = r.take(altitude_length)
    item["altitude"] = {
        "offset": altitude_offset,
        "length": altitude_length,
        "sample_hex": altitude[:64].hex(),
        "all_zero": all(v == 0 for v in altitude),
    }
    item["surface"] = parse_terrain_surface(r)
    item["waters"] = read_obj_array_with_param(r, parse_water)
    return offset_obj(start, r.pos, item)


def parse_terrain_surface(r: Reader) -> dict[str, Any]:
    start = r.pos
    image_count = r.read_length()
    images = []
    for image_index in range(image_count):
        img = image_meta(r.data, r.pos)
        img["index"] = image_index
        images.append(img)
        r.pos += img["length"]

    item: dict[str, Any] = {
        "images": {"count": image_count, "items": images},
        "short0": r.read_i16(),
        "short1": r.read_i16(),
        "vertex_count_hint": r.read_i32(),
    }

    slice_count = r.read_length()
    slices = []
    for slice_index in range(slice_count):
        slice_start = r.pos
        image_ref = r.read_length()
        material_id = r.read_i16()
        material = read_material(r)
        float0 = r.read_f32()
        float1 = r.read_f32()
        cell_count = r.read_i32()
        cells = [{"x": r.read_u8(), "y": r.read_u8()} for _ in range(cell_count)]
        slices.append(
            offset_obj(
                slice_start,
                r.pos,
                {
                    "index": slice_index,
                    "image_ref": image_ref,
                    "material_id": material_id,
                    "material": material,
                    "float0": float0,
                    "float1": float1,
                    "cell_count": cell_count,
                    "cells": cells,
                },
            )
        )
    item["slices"] = {"count": slice_count, "items": slices}
    return offset_obj(start, r.pos, item)


def read_obj_array_with_param(r: Reader, item_fn) -> dict[str, Any]:
    count = r.read_length()
    return {"count": count, "items": [item_fn(r, i) for i in range(count)]}


def parse_water(r: Reader, index: int) -> dict[str, Any]:
    start = r.pos
    item = {
        "index": index,
        "texture_ref": read_asset_ref2(r),
        "texture_scale": r.read_f32(),
        "perturb_intensity": r.read_f32(),
        "foam_texture_ref": read_asset_ref2(r),
        "foam_scale": r.read_f32(),
        "foam_intensity": r.read_f32(),
        "foam_depth": r.read_f32(),
        "angle": r.read_f32(),
        "forward_speed": r.read_f32(),
        "cross_speed": r.read_f32(),
        "wave_distance": r.read_f32(),
        "wave_altitude": r.read_f32(),
        "depth_max": r.read_f32(),
        "color0": read_color(r, normalized=True),
        "color1": read_color(r, normalized=True),
        "float10": r.read_f32(),
        "float11": r.read_f32(),
        "bool0": r.read_bool(),
    }
    instance_count = r.read_i32()
    item["instances"] = {
        "count": instance_count,
        "items": [{"x": r.read_u8(), "y": r.read_u8(), "z": r.read_f32()} for _ in range(instance_count)],
    }
    return offset_obj(start, r.pos, item)


def parse_tile(r: Reader, index: int, width: int) -> dict[str, Any]:
    start = r.pos
    return offset_obj(
        start,
        r.pos + 1,
        {"index": index, "x": index % width, "y": index // width, "value": r.read_u8()},
    )


def parse_resource_tables(r: Reader) -> dict[str, Any]:
    start = r.pos
    tables = []
    for table_index in range(2):
        outer_count = r.read_length()
        outer = []
        for outer_index in range(outer_count):
            inner_count = r.read_length()
            inner = []
            for _ in range(inner_count):
                inner.append({"x": r.read_fixed(), "y": r.read_fixed(), "amount": r.read_i16()})
            outer.append({"index": outer_index, "count": inner_count, "items": inner})
        tables.append({"index": table_index, "count": outer_count, "items": outer})
    return offset_obj(start, r.pos, {"tables": tables})


def parse_props(r: Reader) -> dict[str, Any]:
    start = r.pos
    tables = []
    for table_index in range(2):
        outer_count = r.read_length()
        outer = []
        for outer_index in range(outer_count):
            inner_count = r.read_length()
            inner = []
            for _ in range(inner_count):
                prop_start = r.pos
                inner.append(
                    offset_obj(
                        prop_start,
                        r.pos + 48,
                        {
                            "index": r.read_asset_index3(),
                            "x": r.read_fixed(),
                            "y": r.read_fixed(),
                            "float0": r.read_f32(),
                            "float1": r.read_f32(),
                            "float2": r.read_f32(),
                            "float3": r.read_f32(),
                            "float4": r.read_f32(),
                            "fixed0": r.read_fixed(),
                        },
                    )
                )
            outer.append({"index": outer_index, "count": inner_count, "items": inner})
        tables.append({"index": table_index, "count": outer_count, "items": outer})
    return offset_obj(start, r.pos, {"tables": tables})


def parse_squad(r: Reader) -> dict[str, Any]:
    start = r.pos
    item: dict[str, Any] = {"index": r.read_asset_index2()}
    has_point = r.read_bool()
    item["has_point"] = has_point
    if has_point:
        item["point"] = {"x": r.read_fixed(), "y": r.read_fixed()}
    item["fixed0"] = r.read_fixed()
    item["byte0"] = r.read_u8()
    item["short0"] = r.read_i16()
    item["short1"] = r.read_i16()
    return offset_obj(start, r.pos, item)


def parse_fpoint(r: Reader) -> dict[str, Any]:
    start = r.pos
    return offset_obj(start, r.pos + 16, {"x": r.read_fixed(), "y": r.read_fixed()})


def parse_area(r: Reader) -> dict[str, Any]:
    start = r.pos
    item = {
        "x": r.read_fixed(),
        "y": r.read_fixed(),
        "radius": r.read_fixed(),
        "points0": read_obj_array(r, 1, parse_fpoint),
        "points1": read_obj_array(r, 1, parse_fpoint),
    }
    return offset_obj(start, r.pos, item)


def parse_camera(r: Reader) -> dict[str, Any]:
    start = r.pos
    item = {
        "floats": [r.read_f32(), r.read_f32(), r.read_f32(), r.read_f32(), r.read_f32(), r.read_f32()],
        "byte0": r.read_u8(),
    }
    return offset_obj(start, r.pos, item)


def parse_map(data: bytes, source: pathlib.Path, layers: list[str], selected_block: int) -> dict[str, Any]:
    r = Reader(data)
    blocks = parse_map_blocks(r, selected_block=selected_block)
    terrain = parse_terrain(r)
    width = terrain["width"]
    height = terrain["height"]

    tile_count = width * height
    tiles = [parse_tile(r, i, width) for i in range(tile_count)]
    item: dict[str, Any] = {
        "kind": "acies-map",
        "source": source.as_posix(),
        "layers": layers,
        "decoded_size": len(data),
        "selected_block": selected_block,
        "blocks": blocks,
        "terrain": terrain,
        "tiles": {
            "count": tile_count,
            "offset": tiles[0]["_offset"] if tiles else r.pos,
            "end": tiles[-1]["_end"] if tiles else r.pos,
            "unique_values": sorted({t["value"] for t in tiles}),
            "items": tiles,
        },
    }

    item["resources"] = parse_resource_tables(r)
    item["props"] = parse_props(r)
    item["squads"] = read_obj_array(r, 2, parse_squad)
    item["unit_settings"] = parse_unit_settings(r)
    item["points"] = read_obj_array(r, 1, parse_fpoint)
    item["areas"] = read_obj_array(r, 1, parse_area)
    item["camera"] = parse_camera(r)
    item["trigger_bytecode"] = read_u8_array(r, 3)
    item["remaining"] = r.remaining
    if r.remaining:
        item["trailing"] = compact_bytes(r.take(r.remaining))
    item["parsed_size"] = r.pos
    return item


def parse_unit_settings(r: Reader) -> dict[str, Any]:
    start = r.pos
    count = r.read_length()
    items = []
    for index in range(count):
        item_start = r.pos
        items.append(
            offset_obj(
                item_start,
                r.pos + 17,
                {"index": index, "x": r.read_fixed(), "y": r.read_fixed(), "byte0": r.read_u8()},
            )
        )
    return offset_obj(start, r.pos, {"count": count, "items": items})


def write_outputs(parsed: dict[str, Any], decoded: bytes, source: pathlib.Path, out_dir: pathlib.Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = source.name.replace(".xmf", "")
    json_path = out_dir / f"{stem}.json"
    decoded_path = out_dir / f"{stem}.decoded"
    json_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    decoded_path.write_bytes(decoded)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=pathlib.Path)
    parser.add_argument("--asset-root", type=pathlib.Path, default=ASSET_ROOT)
    parser.add_argument("--out-dir", type=pathlib.Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--selected-block", type=int, default=0)
    args = parser.parse_args()

    decoded, layers = decode_xmf(args.path, args.asset_root)
    parsed = parse_map(decoded, args.path, layers, args.selected_block)
    write_outputs(parsed, decoded, args.path, args.out_dir)
    print(
        f"{args.path}: decoded={len(decoded)} remaining={parsed['remaining']} "
        f"terrain={parsed['terrain']['width']}x{parsed['terrain']['height']} "
        f"tiles={parsed['tiles']['count']} triggers={parsed['trigger_bytecode']['count']} "
        f"-> {args.out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
