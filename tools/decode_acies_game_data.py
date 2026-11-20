#!/usr/bin/env python3
"""Decode ACIES data/game[NNN].xmf database files.

The outer XMF decrypt layer is shared with tools/xmf_probe.py.  The inner
schema is ACIES-specific and was recovered from Asset::loadGame(int) plus the
small record constructors exported by libcdkapp.so.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import struct
import sys
from typing import Any, Callable

import xmf_probe


ASSET_ROOT = pathlib.Path("acies-apktool/assets")
DEFAULT_OUT_DIR = pathlib.Path("decrypts/game")
FIXED_ONE = 1 << 16


class ParseError(RuntimeError):
    pass


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    @property
    def remaining(self) -> int:
        return len(self.data) - self.pos

    def take(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise ParseError(f"read overflow at offset {self.pos} for {n} bytes")
        out = self.data[self.pos : self.pos + n]
        self.pos += n
        return out

    def read_u8(self) -> int:
        return self.take(1)[0]

    def read_bool(self) -> bool:
        return self.read_u8() != 0

    def read_i16(self) -> int:
        return struct.unpack("<h", self.take(2))[0]

    def read_u16(self) -> int:
        return struct.unpack("<H", self.take(2))[0]

    def read_i32(self) -> int:
        return struct.unpack("<i", self.take(4))[0]

    def read_u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def read_i64(self) -> int:
        return struct.unpack("<q", self.take(8))[0]

    def read_f32(self) -> float:
        return struct.unpack("<f", self.take(4))[0]

    def read_length(self) -> int:
        value = 0
        while True:
            current = self.read_u8()
            value = (value << 7) | (current & 0x7F)
            if not current & 0x80:
                return value

    def read_string(self) -> str:
        length = self.read_length()
        if length == 0:
            return ""
        return self.take(length).decode("utf-8")

    def read_locale_string(self) -> dict[str, str]:
        count = self.read_length()
        values: dict[str, str] = {}
        for _ in range(count):
            locale = self.read_string()
            values[locale] = self.read_string()
        return values

    def read_fixed(self) -> dict[str, Any]:
        raw = self.read_i64()
        return {"raw": raw, "value": raw / FIXED_ONE}

    def read_located_fixed(self) -> dict[str, Any]:
        offset = self.pos
        return {"offset": offset, **self.read_fixed()}

    def read_asset_index2(self) -> list[int]:
        return [self.read_u16(), self.read_u16()]

    def read_asset_index3(self) -> list[int]:
        return [self.read_u16(), self.read_u16(), self.read_u16()]


def decode_xmf(path: pathlib.Path, asset_root: pathlib.Path) -> tuple[bytes, list[str]]:
    raw = path.read_bytes()
    if raw.startswith(b"\x1f\x8b"):
        decoded, comp = xmf_probe.maybe_uncompress(raw)
        return decoded, [comp or "gzip"]

    rel = xmf_probe.asset_relative(path, asset_root)
    key = xmf_probe.file_key(rel)
    decrypted = xmf_probe.openssl_aes256_cbc_decrypt(raw, key)
    stripped, ok, calc, expected = xmf_probe.strip_xor_check(decrypted)
    if not ok:
        raise ParseError(f"XMF decrypt checksum failed: calc={calc:08x} expected={expected:08x}")

    decoded = stripped
    layers = [f"aes256-cbc key={key.decode()}", f"xor32=ok {calc:08x}"]
    uncompressed, comp = xmf_probe.maybe_uncompress(decoded)
    if comp:
        decoded = uncompressed
        layers.append(comp)
    return decoded, layers


def annotate(r: Reader, kind: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    start = r.pos
    obj = fn()
    obj["_type"] = kind
    obj["_offset"] = start
    obj["_end"] = r.pos
    obj["_size"] = r.pos - start
    return obj


def color_from_raw(raw: int) -> dict[str, Any]:
    value = raw & 0xFFFFFFFF
    return {
        "raw": value,
        "hex": f"#{value:08x}",
        "bytes_le": [
            value & 0xFF,
            (value >> 8) & 0xFF,
            (value >> 16) & 0xFF,
            (value >> 24) & 0xFF,
        ],
        "argb": [
            (value >> 24) & 0xFF,
            (value >> 16) & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF,
        ],
    }


def compact_bytes(data: bytes) -> dict[str, Any]:
    out: dict[str, Any] = {"count": len(data), "hex": data.hex()}
    if len(data) <= 64:
        out["values"] = list(data)
    return out


def read_u8_array(r: Reader, dim: int) -> Any:
    count = r.read_length()
    if dim == 1:
        offset = r.pos
        return {"offset": offset, **compact_bytes(r.take(count))}
    items = []
    for i in range(count):
        try:
            items.append(read_u8_array(r, dim - 1))
        except Exception as e:
            raise ParseError(f"u8_array_dim{dim}[{i}] at offset {r.pos}: {e}") from e
    return {"count": count, "items": items}


def read_obj_array(r: Reader, dim: int, item: Callable[[Reader], Any]) -> dict[str, Any]:
    count = r.read_length()
    if dim == 1:
        items = []
        for i in range(count):
            start = r.pos
            try:
                items.append(item(r))
            except Exception as e:
                name = getattr(item, "__name__", "item")
                raise ParseError(f"{name}[{i}] started at {start}, failed at {r.pos}: {e}") from e
        return {"count": count, "items": items}
    items = []
    for i in range(count):
        start = r.pos
        try:
            items.append(read_obj_array(r, dim - 1, item))
        except Exception as e:
            raise ParseError(f"array_dim{dim}[{i}] started at {start}, failed at {r.pos}: {e}") from e
    return {"count": count, "items": items}


def parse_unit_base(r: Reader) -> dict[str, Any]:
    return annotate(
        r,
        "UnitBase",
        lambda: {
            "index": r.read_asset_index2(),
            "level": r.read_i16(),
            "skin": r.read_i16(),
        },
    )


def parse_card(r: Reader) -> dict[str, Any]:
    return annotate(r, "Card", lambda: {"unit_base": parse_unit_base(r)})


def parse_rune_instance(r: Reader) -> dict[str, Any]:
    return annotate(
        r,
        "Rune",
        lambda: {
            "index": r.read_asset_index2(),
            "level": r.read_i16(),
        },
    )


def parse_virtual_force(r: Reader) -> dict[str, Any]:
    def body() -> dict[str, Any]:
        card_count = r.read_length()
        cards = [parse_card(r) for _ in range(card_count)]
        rune_count = r.read_length()
        runes = [parse_rune_instance(r) for _ in range(rune_count)]
        levels_count = r.read_length()
        levels = []
        for _ in range(levels_count):
            levels.append({"index": r.read_asset_index2(), "level": r.read_i16()})
        return {
            "kind": r.read_u8(),
            "fixed0": r.read_fixed(),
            "fixed1": r.read_fixed(),
            "cards": {"count": card_count, "items": cards},
            "runes": {"count": rune_count, "items": runes},
            "unit_levels": {"count": levels_count, "items": levels},
        }

    # The constructor reads kind/fixed/fixed before the arrays.  Keep the arrays
    # in output after those fields by doing the reads in the exact native order.
    start = r.pos
    kind = r.read_u8()
    fixed0 = r.read_fixed()
    fixed1 = r.read_fixed()
    cards = read_obj_array(r, 1, parse_card)
    runes = read_obj_array(r, 1, parse_rune_instance)
    count = r.read_length()
    unit_levels = [{"index": r.read_asset_index2(), "level": r.read_i16()} for _ in range(count)]
    return {
        "_type": "VirtualForce",
        "_offset": start,
        "_end": r.pos,
        "_size": r.pos - start,
        "kind": kind,
        "fixed0": fixed0,
        "fixed1": fixed1,
        "cards": cards,
        "runes": runes,
        "unit_levels": {"count": count, "items": unit_levels},
    }


def parse_virtual_unit(r: Reader) -> dict[str, Any]:
    def body() -> dict[str, Any]:
        levels_count = r.read_length()
        levels = []
        for _ in range(levels_count):
            levels.append({"index": r.read_asset_index2(), "value_fixed_raw": r.read_i32() << 16})
        return {
            "unit_base": parse_unit_base(r),
            "fixed0": r.read_fixed(),
            "fixed1": r.read_fixed(),
            "byte0": r.read_u8(),
            "byte1": r.read_u8(),
            "flags": [r.read_bool() for _ in range(6)],
            "byte2": r.read_u8(),
            "levels": {"count": levels_count, "items": levels},
        }

    start = r.pos
    unit_base = parse_unit_base(r)
    fixed0 = r.read_fixed()
    fixed1 = r.read_fixed()
    byte0 = r.read_u8()
    byte1 = r.read_u8()
    flags = [r.read_bool() for _ in range(6)]
    byte2 = r.read_u8()
    count = r.read_length()
    levels = [{"index": r.read_asset_index2(), "value_fixed_raw": r.read_i32() << 16} for _ in range(count)]
    return {
        "_type": "VirtualUnit",
        "_offset": start,
        "_end": r.pos,
        "_size": r.pos - start,
        "unit_base": unit_base,
        "fixed0": fixed0,
        "fixed1": fixed1,
        "byte0": byte0,
        "byte1": byte1,
        "flags": flags,
        "byte2": byte2,
        "levels": {"count": count, "items": levels},
    }


def parse_ability_data(r: Reader) -> dict[str, Any]:
    def body() -> dict[str, Any]:
        display = None
        if r.read_bool():
            display = {
                "icon": r.read_asset_index3(),
                "name": r.read_locale_string(),
                "byte0": r.read_u8(),
                "byte1": r.read_u8(),
            }
        return {"display": display, "bytecode_groups": read_u8_array(r, 2)}

    return annotate(r, "AbilityData", body)


def parse_ability_target_data(r: Reader) -> dict[str, Any]:
    def body() -> dict[str, Any]:
        name = r.read_locale_string()
        virtual_force = parse_virtual_force(r) if r.read_bool() else None
        return {
            "name": name,
            "virtual_force": virtual_force,
            "virtual_unit": parse_virtual_unit(r),
        }

    return annotate(r, "AbilityTargetData", body)


def parse_command_data(r: Reader) -> dict[str, Any]:
    return annotate(
        r,
        "CommandData",
        lambda: {
            "icon": r.read_asset_index3(),
            "name": r.read_locale_string(),
            "description": r.read_locale_string(),
        },
    )


def parse_damage_type_data(r: Reader) -> dict[str, Any]:
    return annotate(r, "DamageTypeData", lambda: {"icon": r.read_asset_index3(), "name": r.read_locale_string()})


def parse_resource_level_data(r: Reader) -> dict[str, Any]:
    return annotate(
        r,
        "ResourceLevelData",
        lambda: {
            "level": r.read_i16(),
            "icon": r.read_asset_index3(),
        },
    )


def parse_resource_data(r: Reader) -> dict[str, Any]:
    def body() -> dict[str, Any]:
        return {
            "icon": r.read_asset_index3(),
            "name": r.read_locale_string(),
            "fixed0": r.read_fixed(),
            "float0": r.read_f32(),
            "float1": r.read_f32(),
            "float2": r.read_f32(),
            "byte0": r.read_u8(),
            "color": color_from_raw(r.read_u32()),
            "levels": read_obj_array(r, 1, parse_resource_level_data),
        }

    return annotate(r, "ResourceData", body)


def parse_ability_description_data(r: Reader) -> dict[str, Any]:
    return annotate(
        r,
        "AbilityDescriptionData",
        lambda: {
            "name": r.read_locale_string(),
            "description": r.read_locale_string(),
            "bytecode_groups": read_u8_array(r, 2),
        },
    )


def parse_ability_unit_entry(r: Reader) -> dict[str, Any]:
    def body() -> dict[str, Any]:
        bytecode_groups = read_u8_array(r, 2)
        target_refs = read_obj_array(r, 1, lambda rr: rr.read_i16())
        return {
            "bytecode_groups": bytecode_groups,
            "target_refs": target_refs,
            "min_value": r.read_located_fixed(),
            "max_value": r.read_located_fixed(),
        }

    return annotate(r, "AbilityUnitData.Entry", body)


def parse_ability_unit_data(r: Reader) -> dict[str, Any]:
    def body() -> dict[str, Any]:
        entry_count = r.read_length()
        entries = []
        for _ in range(entry_count):
            entries.append({"key": r.read_i16(), "value": parse_ability_unit_entry(r)})
        return {
            "entries": {"count": entry_count, "items": entries},
            "descriptions": read_obj_array(r, 1, parse_ability_description_data),
        }

    return annotate(r, "AbilityUnitData", body)


def parse_buff_data(r: Reader) -> dict[str, Any]:
    return annotate(
        r,
        "BuffData",
        lambda: {
            "duration": r.read_located_fixed(),
            "ability_unit": parse_ability_unit_data(r),
            "bytecode_groups": read_u8_array(r, 2),
        },
    )


def parse_rune_data(r: Reader) -> dict[str, Any]:
    def body() -> dict[str, Any]:
        return {
            "icon0": r.read_asset_index3(),
            "icon1": r.read_asset_index3(),
            "name": r.read_locale_string(),
            "description": r.read_locale_string(),
            "short0": r.read_i16(),
            "short1": r.read_i16(),
            "short2": r.read_i16(),
            "byte0": r.read_u8(),
            "byte1": r.read_u8(),
            "byte2": r.read_u8(),
            "raw_bytes": read_u8_array(r, 1),
            "ability_unit": parse_ability_unit_data(r),
        }

    return annotate(r, "RuneData", body)


def parse_command_unit_data(r: Reader) -> dict[str, Any]:
    return annotate(
        r,
        "CommandUnitData",
        lambda: {
            "bytecode_groups0": read_u8_array(r, 2),
            "bytecode_groups1": read_u8_array(r, 2),
        },
    )


def parse_voice_data(r: Reader) -> dict[str, Any]:
    def body() -> dict[str, Any]:
        return {
            "assets0": read_obj_array(r, 1, lambda rr: rr.read_asset_index3()),
            "assets1": read_obj_array(r, 1, lambda rr: rr.read_asset_index3()),
            "assets2": read_obj_array(r, 1, lambda rr: rr.read_asset_index3()),
            "assets3": read_obj_array(r, 1, lambda rr: rr.read_asset_index3()),
        }

    return annotate(r, "VoiceData", body)


def parse_skin_slot(r: Reader) -> dict[str, Any]:
    return {
        "slot": r.read_u8(),
        "index": r.read_asset_index3(),
        "variant": r.read_i16() if r.read_bool() else -1,
        "enabled": r.read_bool(),
    }


def parse_skin_data(r: Reader) -> dict[str, Any]:
    def body() -> dict[str, Any]:
        optional_indices = []
        for _ in range(5):
            optional_indices.append(r.read_asset_index3() if r.read_bool() else None)

        name = r.read_locale_string()
        byte0 = r.read_u8()
        description = r.read_locale_string()
        ability_unit = parse_ability_unit_data(r)

        slot_count = r.read_length()
        slots = [parse_skin_slot(r) for _ in range(slot_count)]

        replace_count = r.read_length()
        replacements = [
            {"from": r.read_asset_index3(), "to": r.read_asset_index3()} for _ in range(replace_count)
        ]

        voice_group_count = r.read_length()
        voice_groups = []
        for _ in range(voice_group_count):
            voice = parse_voice_data(r)
            string_count = r.read_length()
            keys = [r.read_string() for _ in range(string_count)]
            voice_groups.append({"voice": voice, "keys": keys})

        return {
            "indices": optional_indices,
            "name": name,
            "byte0": byte0,
            "description": description,
            "ability_unit": ability_unit,
            "slots": {"count": slot_count, "items": slots},
            "replacements": {"count": replace_count, "items": replacements},
            "voice_groups": {"count": voice_group_count, "items": voice_groups},
            "extra_indices": read_obj_array(r, 1, lambda rr: rr.read_asset_index3()),
            "int0": r.read_i32(),
        }

    return annotate(r, "SkinData", body)


UNIT_BALANCE_COLUMNS = (
    "population_cost",
    "extra_units_per_batch",
    "gold_cost",
    "gas_cost",
    "base_production_seconds",
    "attack_type_id",
    "armor_type_id",
)


def parse_unit_data(r: Reader) -> dict[str, Any]:
    def body() -> dict[str, Any]:
        name = r.read_locale_string()
        description = r.read_locale_string()
        balance_start = r.pos
        byte0 = r.read_u8()
        byte1 = r.read_u8()
        byte2 = r.read_u8()
        flag0 = r.read_bool()
        byte3 = r.read_u8()
        byte4 = r.read_u8()
        byte5 = r.read_u8()
        flag1 = r.read_bool()
        byte6 = r.read_u8()
        byte7 = r.read_u8()
        byte8 = r.read_u8()
        short0 = r.read_i16()
        short1 = r.read_i16()
        short2 = r.read_i16()
        byte9 = r.read_u8()
        byte10 = r.read_u8()
        fixed0 = r.read_fixed()
        float0 = r.read_f32()
        float1 = r.read_f32()
        float2 = r.read_f32()
        float3 = r.read_f32()
        optional_icon = r.read_asset_index3() if r.read_bool() else None
        return {
            "name": name,
            "description": description,
            "byte0": byte0,
            "byte1": byte1,
            "byte2": byte2,
            "flag0": flag0,
            "byte3": byte3,
            "byte4": byte4,
            "byte5": byte5,
            "flag1": flag1,
            "byte6": byte6,
            "byte7": byte7,
            "byte8": byte8,
            "short0": short0,
            "short1": short1,
            "short2": short2,
            "balance_fields": {
                "population_cost": {"value": byte7, "offset": balance_start + 9, "type": "u8"},
                "extra_units_per_batch": {"value": byte8, "offset": balance_start + 10, "type": "u8"},
                "gold_cost": {"value": short0 & 0xFFFF, "offset": balance_start + 11, "type": "u16le"},
                "gas_cost": {"value": short1 & 0xFFFF, "offset": balance_start + 13, "type": "u16le"},
                "base_production_seconds": {"value": short2 & 0xFFFF, "offset": balance_start + 15, "type": "u16le"},
                "attack_type_id": {"value": (byte4 ^ 128) - 128, "offset": balance_start + 5, "type": "i8"},
                "armor_type_id": {"value": (byte5 ^ 128) - 128, "offset": balance_start + 6, "type": "i8"},
            },
            "byte9": byte9,
            "byte10": byte10,
            "fixed0": fixed0,
            "float0": float0,
            "float1": float1,
            "float2": float2,
            "float3": float3,
            "optional_icon": optional_icon,
            "ability_unit": parse_ability_unit_data(r),
            "indices": read_obj_array(r, 1, lambda rr: rr.read_asset_index2()),
            "bytecode_groups": read_u8_array(r, 2),
            "bytecode_groups3": read_u8_array(r, 3),
            "commands": parse_asset2_dict(r, parse_command_unit_data),
            "skins": read_obj_array(r, 1, parse_skin_data),
        }

    return annotate(r, "UnitData", body)


def parse_ping_data(r: Reader) -> dict[str, Any]:
    return annotate(
        r,
        "PingData",
        lambda: {
            "icon0": r.read_asset_index3(),
            "icon1": r.read_asset_index3(),
            "color": color_from_raw(r.read_u32()),
            "name": r.read_locale_string(),
        },
    )


def parse_announce_data(r: Reader) -> dict[str, Any]:
    def body() -> dict[str, Any]:
        name = r.read_locale_string()
        description = r.read_locale_string()
        group_count = r.read_length()
        groups = []
        for _ in range(group_count):
            key = r.read_asset_index2()
            string_count = r.read_length()
            items = []
            for _ in range(string_count):
                items.append({"text": r.read_string()})
            groups.append({"key": key, "items": {"count": string_count, "items": items}})
        return {
            "name": name,
            "description": description,
            "groups": {"count": group_count, "items": groups},
            "int0": r.read_i32(),
        }

    return annotate(r, "AnnounceData", body)


def parse_asset2_dict(r: Reader, value_parser: Callable[[Reader], Any]) -> dict[str, Any]:
    count = r.read_length()
    items = [{"key": r.read_asset_index2(), "value": value_parser(r)} for _ in range(count)]
    return {"count": count, "items": items}


def parse_enabled_asset2_ints(r: Reader) -> dict[str, Any]:
    count = r.read_length()
    items = []
    enabled_values = []
    for _ in range(count):
        key = r.read_asset_index2()
        value = r.read_i32()
        item = {"key": key, "value": value, "enabled": bool(value & 1)}
        items.append(item)
        if value & 1:
            enabled_values.append(value)
    return {"count": count, "items": items, "enabled_values": enabled_values}


def section(r: Reader, name: str, fn: Callable[[], Any], sections: list[dict[str, Any]]) -> Any:
    start = r.pos
    value = fn()
    sections.append({"name": name, "offset": start, "end": r.pos, "size": r.pos - start})
    return value


def parse_game_database(data: bytes) -> dict[str, Any]:
    r = Reader(data)
    sections: list[dict[str, Any]] = []

    header = section(
        r,
        "header",
        lambda: {
            "short0": r.read_i16(),
            "short1": r.read_i16(),
            "float0": r.read_f32(),
            "float1": r.read_f32(),
        },
        sections,
    )
    abilities = section(r, "abilities", lambda: read_obj_array(r, 1, parse_ability_data), sections)
    ability_targets = section(
        r, "ability_targets", lambda: read_obj_array(r, 1, parse_ability_target_data), sections
    )
    short_count = None
    shorts = section(
        r,
        "short_table",
        lambda: {"count": (short_count := r.read_length()), "items": [r.read_i16() for _ in range(short_count)]},
        sections,
    )
    commands = section(r, "commands", lambda: read_obj_array(r, 2, parse_command_data), sections)
    damage_types_a = section(r, "damage_types_a", lambda: read_obj_array(r, 1, parse_damage_type_data), sections)
    damage_types_b = section(r, "damage_types_b", lambda: read_obj_array(r, 1, parse_damage_type_data), sections)

    def read_damage_matrix() -> dict[str, Any]:
        rows = []
        for _ in range(damage_types_a["count"]):
            rows.append([r.read_located_fixed() for _ in range(damage_types_b["count"])])
        return {"rows": damage_types_a["count"], "columns": damage_types_b["count"], "items": rows}

    damage_matrix = section(r, "damage_matrix", read_damage_matrix, sections)
    units = section(r, "units", lambda: read_obj_array(r, 2, parse_unit_data), sections)
    resource0 = section(r, "resource0", lambda: parse_resource_data(r), sections)
    resource1 = section(r, "resource1", lambda: parse_resource_data(r), sections)
    buffs = section(r, "buffs", lambda: read_obj_array(r, 2, parse_buff_data), sections)
    runes = section(r, "runes", lambda: read_obj_array(r, 2, parse_rune_data), sections)
    bytecode_table = section(r, "bytecode_table", lambda: read_u8_array(r, 3), sections)
    pings = section(r, "pings", lambda: read_obj_array(r, 1, parse_ping_data), sections)
    announces = section(r, "announces", lambda: read_obj_array(r, 1, parse_announce_data), sections)
    enabled0 = section(r, "enabled_table0", lambda: parse_enabled_asset2_ints(r), sections)
    enabled1 = section(r, "enabled_table1", lambda: parse_enabled_asset2_ints(r), sections)

    return {
        "kind": "acies-game-database",
        "decoded_size": len(data),
        "remaining": r.remaining,
        "sections": sections,
        "header": header,
        "abilities": abilities,
        "ability_targets": ability_targets,
        "short_table": shorts,
        "commands": commands,
        "damage_types_a": damage_types_a,
        "damage_types_b": damage_types_b,
        "damage_matrix": damage_matrix,
        "units": units,
        "resource0": resource0,
        "resource1": resource1,
        "buffs": buffs,
        "runes": runes,
        "bytecode_table": bytecode_table,
        "pings": pings,
        "announces": announces,
        "enabled_table0": enabled0,
        "enabled_table1": enabled1,
    }


def write_csv(path: pathlib.Path, header: list[str], rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def localized_name(value: dict[str, str] | None) -> str:
    if not value:
        return ""
    return value.get("en") or value.get("ko") or next(iter(value.values()), "")


ABILITY_OPERATIONS = ("set", "add", "subtract", "multiply", "divide", "min", "max")
ABILITY_REGISTERS = ("result", "register_1", "register_2", "register_3")
ABILITY_LEVEL_MODES = ("compound_multiplier", "linear_multiplier", "linear_addition")
ABILITY_COMPARISONS = ("equal", "greater", "greater_or_equal", "less", "less_or_equal")
CORE_ABILITY_ROLES = ("base_health", "additional_health", "vision", "attack_damage",
                      "minimum_attack_range", "maximum_attack_range", "attack_speed", "movement_speed")


def decode_ability_line(line: dict[str, Any]) -> dict[str, Any]:
    """Decode the arithmetic instruction in AbilityData::value, if present."""
    data = bytes.fromhex(line["hex"])
    if not data:
        return {"operation": "empty"}
    if (data[0] == 1 and len(data) == 14 and data[10] == 0
            and data[1] < len(ABILITY_REGISTERS) and data[11] < len(ABILITY_COMPARISONS)):
        r = Reader(data)
        r.take(2)
        literal = r.read_located_fixed()
        return {"operation": "compare_register", "destination": ABILITY_REGISTERS[data[1]],
                "source": {"literal": literal}, "comparison": ABILITY_COMPARISONS[data[11]],
                "else_line": struct.unpack_from("<H", data, 12)[0]}
    if data[0] == 2 and len(data) >= 6:
        r = Reader(data)
        r.read_u8()
        subject = "target" if r.read_bool() else "unit"
        source_type = r.read_u8()
        if source_type < len(ABILITY_REGISTERS) and r.remaining == 3:
            source = {"register": ABILITY_REGISTERS[source_type]}
        elif source_type == 4 and r.remaining == 11:
            source = {"literal": r.read_located_fixed()}
        else:
            return {"operation": "opaque", "opcode": 2}
        return {"operation": "compare_unit_state", "subject": subject, "source": source,
                "predicate_id": r.read_u8(), "else_line": r.read_u16()}
    if data[0] == 6 and len(data) == 7:
        group, index, else_line = struct.unpack_from("<HHH", data, 1)
        return {"operation": "branch_on_rune", "rune": [group, index], "else_line": else_line}
    if data[0] == 7 and len(data) >= 27:
        # UnitBase::matchLength counts optional values and variable-size lists.
        filter_bytes = data[1:-2]
        base = filter_bytes[2] * 5
        if base + 15 < len(filter_bytes):
            tail = base + (25 if filter_bytes[base + 15] else 16)
            if tail + 7 < len(filter_bytes) and tail + 8 + filter_bytes[tail + 7] * 13 == len(filter_bytes):
                return {"operation": "branch_on_target_match", "filter_hex": filter_bytes.hex(),
                        "else_line": struct.unpack_from("<H", data, len(data) - 2)[0]}
    if data[0] == 8 and len(data) == 5:
        return {"operation": "compare_unit_property", "subject": "target" if data[1] else "unit",
                "expected": struct.unpack_from("b", data, 2)[0], "else_line": struct.unpack_from("<H", data, 3)[0]}
    if data[0] == 9 and len(data) == 16:
        r = Reader(data)
        r.read_u8()
        subject = "target" if r.read_bool() else "unit"
        index = r.read_asset_index2()
        return {"operation": "check_unit_asset_condition", "subject": subject, "asset_index": index,
                "source": {"literal": r.read_located_fixed()}, "else_line": r.read_u16()}
    if data[0] == 10 and len(data) == 3:
        return {"operation": "check_target_force", "else_line": struct.unpack_from("<H", data, 1)[0]}
    if data[0] == 12 and len(data) == 2 and data[1] < len(ABILITY_REGISTERS):
        return {"operation": "apply_damage_matrix", "destination": ABILITY_REGISTERS[data[1]]}
    if data[0] == 13 and len(data) == 3:
        return {"operation": "jump", "line": struct.unpack_from("<H", data, 1)[0]}
    if data[0] != 0:
        return {"operation": "opaque", "opcode": data[0]}

    r = Reader(data)
    try:
        r.read_u8()
        destination = ABILITY_REGISTERS[r.read_u8()]
        source_type = r.read_u8()
        if source_type <= 3:
            source = {"register": ABILITY_REGISTERS[source_type]}
        elif source_type == 4:
            source = {"literal": r.read_located_fixed()}
        elif source_type == 5:
            source = {"level_table": [r.read_located_fixed() for _ in range(r.read_length())]}
        else:
            source = {"ability_of": {6: "unit", 7: "target", 8: "parent"}[source_type], "id": r.read_i16()}

        modifier_type = r.read_u8()
        modifier: dict[str, Any] = {}
        if modifier_type == 1:
            modifier = {"factor": r.read_located_fixed(), "mode": ABILITY_LEVEL_MODES[r.read_u8()]}
        elif modifier_type in (2, 3, 4):
            modifier = {"ability_of": {2: "unit", 3: "target", 4: "parent"}[modifier_type], "id": r.read_i16()}
        elif modifier_type == 5:
            modifier = {"modifier_type": 5, "source": "unit_metric"}
        elif modifier_type in (6, 7):
            modifier = {"asset_index": r.read_asset_index2(), "modifier_type": modifier_type}
        elif modifier_type != 0:
            return {"operation": "opaque", "opcode": 0}

        operation = ABILITY_OPERATIONS[r.read_u8()]
        if not r.remaining:
            return {"operation": operation, "destination": destination, "source": source, "modifier": modifier}
    except (ParseError, IndexError, KeyError):
        pass
    return {"operation": "opaque", "opcode": 0}


def emit_ability_programs(parsed: dict[str, Any], stem: str, out_dir: pathlib.Path) -> None:
    abilities = parsed["abilities"]["items"]
    names = [localized_name(a["display"]["name"]) if a["display"] else "" for a in abilities]
    roles = dict(zip(parsed["short_table"]["items"], CORE_ABILITY_ROLES))
    rows = []

    def append_program(kind: str, group: int | str, index: int, name: str,
                       ability_id: int, entry: dict[str, Any]) -> None:
        ability_name = names[ability_id] if 0 <= ability_id < len(names) else ""
        for line_index, line in enumerate(entry["bytecode_groups"]["items"]):
            instruction = decode_ability_line(line)
            for field in (instruction.get("source", {}), instruction.get("modifier", {})):
                for fixed in [field.get("literal"), field.get("factor"), *field.get("level_table", [])]:
                    if fixed is not None:
                        fixed["offset"] += line["offset"]
            source = instruction.get("source", {})
            literal = source.get("literal", {})
            rows.append([
                kind, group, index, name, ability_id, ability_name, roles.get(ability_id, ""),
                line_index, line["offset"],
                instruction["operation"], instruction.get("destination", ""),
                literal.get("value", ""), literal.get("offset", ""),
                json.dumps(instruction, ensure_ascii=False),
                json.dumps(entry.get("target_refs", {}).get("items", [])),
                entry.get("min_value", {}).get("value", ""), entry.get("min_value", {}).get("offset", ""),
                entry.get("max_value", {}).get("value", ""), entry.get("max_value", {}).get("offset", ""),
                line["hex"],
            ])

    for ability_id, ability in enumerate(abilities):
        append_program("global", "", ability_id, names[ability_id], ability_id, ability)

    for kind in ("units", "runes", "buffs"):
        for group_index, group in enumerate(parsed[kind]["items"]):
            for index, record in enumerate(group["items"]):
                for entry in record["ability_unit"]["entries"]["items"]:
                    append_program(kind, group_index, index, localized_name(record.get("name")),
                                   entry["key"], entry["value"])

    write_csv(out_dir / f"{stem}.ability-programs.csv", [
        "kind", "group", "index", "name", "ability_id", "ability_name", "core_role", "line", "line_offset",
        "operation", "destination", "literal", "literal_offset", "instruction", "target_refs",
        "lower_bound", "lower_bound_offset", "upper_bound", "upper_bound_offset", "hex",
    ], rows)


def emit_csvs(parsed: dict[str, Any], stem: str, out_dir: pathlib.Path) -> None:
    write_csv(
        out_dir / f"{stem}.sections.csv",
        ["name", "offset", "end", "size"],
        [[s["name"], s["offset"], s["end"], s["size"]] for s in parsed["sections"]],
    )
    write_csv(
        out_dir / f"{stem}.abilities.csv",
        ["index", "offset", "size", "name", "has_display"],
        [
            [
                i,
                item["_offset"],
                item["_size"],
                localized_name(item["display"]["name"]) if item["display"] else "",
                item["display"] is not None,
            ]
            for i, item in enumerate(parsed["abilities"]["items"])
        ],
    )

    unit_rows = []
    for group_i, group in enumerate(parsed["units"]["items"]):
        for unit_i, unit in enumerate(group["items"]):
            row = [group_i, unit_i, unit["_offset"], unit["_size"], localized_name(unit["name"])]
            for field in UNIT_BALANCE_COLUMNS:
                info = unit["balance_fields"][field]
                row.extend((info["value"], info["offset"]))
            unit_rows.append(row)
    unit_header = ["group", "index", "offset", "size", "name"]
    for field in UNIT_BALANCE_COLUMNS:
        unit_header.extend((field, f"{field}_offset"))
    write_csv(out_dir / f"{stem}.units.csv", unit_header, unit_rows)

    rune_rows = []
    for group_i, group in enumerate(parsed["runes"]["items"]):
        for rune_i, rune in enumerate(group["items"]):
            match = rune["raw_bytes"]
            rune_rows.append([group_i, rune_i, rune["_offset"], rune["_size"], localized_name(rune["name"]),
                              localized_name(rune["description"]), match["offset"], match["hex"]])
    write_csv(out_dir / f"{stem}.runes.csv", ["group", "index", "offset", "size", "name", "description",
                                             "target_filter_offset", "target_filter_hex"], rune_rows)
    emit_ability_programs(parsed, stem, out_dir)

    attack_types = parsed["damage_types_a"]["items"]
    armor_types = parsed["damage_types_b"]["items"]
    write_csv(out_dir / f"{stem}.damage-matrix.csv", ["attack", "armor", "multiplier", "raw", "offset"], [
        [localized_name(attack_types[i]["name"]), localized_name(armor_types[j]["name"]),
         cell["value"], cell["raw"], cell["offset"]]
        for i, row in enumerate(parsed["damage_matrix"]["items"])
        for j, cell in enumerate(row)
    ])
    write_csv(out_dir / f"{stem}.buffs.csv", ["group", "index", "duration", "duration_offset"], [
        [group_index, index, buff["duration"]["value"], buff["duration"]["offset"]]
        for group_index, group in enumerate(parsed["buffs"]["items"])
        for index, buff in enumerate(group["items"])
    ])


def summary(parsed: dict[str, Any], path: pathlib.Path, layers: list[str]) -> dict[str, Any]:
    return {
        "source": path.as_posix(),
        "kind": parsed["kind"],
        "decoded_size": parsed["decoded_size"],
        "remaining": parsed["remaining"],
        "layers": layers,
        "header": parsed["header"],
        "section_sizes": parsed["sections"],
        "counts": {
            "abilities": parsed["abilities"]["count"],
            "ability_targets": parsed["ability_targets"]["count"],
            "commands_outer": parsed["commands"]["count"],
            "damage_types_a": parsed["damage_types_a"]["count"],
            "damage_types_b": parsed["damage_types_b"]["count"],
            "units_outer": parsed["units"]["count"],
            "buffs_outer": parsed["buffs"]["count"],
            "runes_outer": parsed["runes"]["count"],
            "pings": parsed["pings"]["count"],
            "announces": parsed["announces"]["count"],
            "enabled_table0": parsed["enabled_table0"]["count"],
            "enabled_table1": parsed["enabled_table1"]["count"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Decode ACIES data/game[NNN].xmf databases.")
    parser.add_argument("paths", nargs="+", type=pathlib.Path)
    parser.add_argument("--asset-root", type=pathlib.Path, default=ASSET_ROOT)
    parser.add_argument("--out-dir", type=pathlib.Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--decoded-dir", type=pathlib.Path, default=None)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    decoded_dir = args.decoded_dir or args.out_dir / "decoded"
    decoded_dir.mkdir(parents=True, exist_ok=True)

    index = []
    for path in args.paths:
        data, layers = decode_xmf(path, args.asset_root)
        parsed = parse_game_database(data)
        stem = path.name

        decoded_path = decoded_dir / f"{stem}.decoded"
        decoded_path.write_bytes(data)

        json_path = args.out_dir / f"{stem}.json"
        json_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        summary_obj = summary(parsed, path, layers)
        summary_path = args.out_dir / f"{stem}.summary.json"
        summary_path.write_text(json.dumps(summary_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        emit_csvs(parsed, stem, args.out_dir)

        index.append(
            {
                "source": path.as_posix(),
                "json": json_path.as_posix(),
                "summary": summary_path.as_posix(),
                "decoded": decoded_path.as_posix(),
                "remaining": parsed["remaining"],
                "decoded_size": len(data),
            }
        )
        print(f"{path}: decoded={len(data)} remaining={parsed['remaining']} json={json_path}")

    (args.out_dir / "index.json").write_text(
        json.dumps({"kind": "acies-game-database-index", "items": index}, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
