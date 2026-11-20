#!/usr/bin/env python3
"""Decode ACIES old-CDK animations.xmf into structural JSON.

The APK's libcdkapp.so does not use the newer open-source CDK3
CSAnimationFragment layout.  Asset::loadAnimations() reads
CSArray<CSAnimation, 3, true>, and CSAnimation::CSAnimation(CSBuffer*) in this
binary is a flatter older record built from CSMovement, CSAnimationLoop,
CSAnimationSubstance, and CSAnimationDerivation.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import struct
from collections import Counter
from typing import Any, Callable

import xmf_probe


ASSET_ROOT = pathlib.Path("acies-apktool/assets")


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
        return self.take(length).decode("utf-8", errors="replace")


def decode_xmf(path: pathlib.Path, asset_root: pathlib.Path) -> tuple[bytes, list[str]]:
    raw = path.read_bytes()
    if raw.startswith(b"\x1f\x8b"):
        decoded, comp = xmf_probe.maybe_uncompress(raw)
        return decoded, [comp or "gzip"]

    rel = xmf_probe.asset_relative(path, asset_root)
    key = xmf_probe.file_key(rel)
    try:
        decrypted = xmf_probe.openssl_aes256_cbc_decrypt(raw, key)
        stripped, ok, calc, expected = xmf_probe.strip_xor_check(decrypted)
    except Exception:
        return raw, ["plain/unknown"]
    if not ok:
        return raw, [f"plain/unknown decrypt-check-failed calc={calc:08x} expected={expected:08x}"]

    decoded = stripped
    layers = [f"aes256-cbc key={key.decode()}", f"xor32=ok {calc:08x}"]
    uncompressed, comp = xmf_probe.maybe_uncompress(decoded)
    if comp:
        decoded = uncompressed
        layers.append(comp)
    return decoded, layers


def annotated(r: Reader, kind: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    start = r.pos
    item = fn()
    item["_type"] = kind
    item["_offset"] = start
    item["_end"] = r.pos
    item["_size"] = r.pos - start
    return item


def read_obj_array(r: Reader, dim: int, fn: Callable[[Reader], Any]) -> dict[str, Any]:
    count = r.read_length()
    items = []
    for i in range(count):
        start = r.pos
        try:
            items.append(read_obj_array(r, dim - 1, fn) if dim > 1 else fn(r))
        except Exception as e:
            raise ParseError(f"array dim={dim} item={i} started at {start}, failed at {r.pos}: {e}") from e
    return {"count": count, "items": items}


def read_obj_array_partial(
    r: Reader, dim: int, fn: Callable[[Reader], Any], path: str = ""
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    count = r.read_length()
    items = []
    errors: list[dict[str, Any]] = []
    for i in range(count):
        start = r.pos
        item_path = f"{path}/{i}" if path else str(i)
        try:
            if dim > 1:
                child, child_errors = read_obj_array_partial(r, dim - 1, fn, item_path)
                items.append(child)
                errors.extend(child_errors)
                if child_errors:
                    break
            else:
                items.append(fn(r))
        except Exception as e:
            errors.append(
                {
                    "path": item_path,
                    "dim": dim,
                    "start": start,
                    "offset": r.pos,
                    "message": str(e),
                    "next_hex": r.data[r.pos : r.pos + 64].hex(),
                }
            )
            break
    return {"count": count, "parsed_count": len(items), "items": items}, errors


def read_u8_array(r: Reader, dim: int) -> Any:
    count = r.read_length()
    if dim == 1:
        data = r.take(count)
        return {"count": count, "hex": data.hex(), "values": list(data) if count <= 64 else None}
    return {"count": count, "items": [read_u8_array(r, dim - 1) for _ in range(count)]}


def read_u16_array(r: Reader, dim: int) -> Any:
    count = r.read_length()
    if dim == 1:
        return {"count": count, "items": [r.read_u16() for _ in range(count)]}
    return {"count": count, "items": [read_u16_array(r, dim - 1) for _ in range(count)]}


def read_loop(r: Reader) -> dict[str, Any]:
    return {
        "count": r.read_u16(),
        "round_trip": r.read_bool(),
        "finish": r.read_bool(),
    }


def read_movement(r: Reader) -> dict[str, Any] | None:
    start = r.pos
    ty = r.read_u8()
    if ty == 0:
        return None
    if ty == 1:
        return {
            "_type": "CSMovementConstant",
            "_offset": start,
            "type_id": ty,
            "value": r.read_f32(),
            "value_var": r.read_f32(),
            "_end": r.pos,
        }
    if ty == 2:
        return {
            "_type": "CSMovementLinear",
            "_offset": start,
            "type_id": ty,
            "start": r.read_f32(),
            "start_var": r.read_f32(),
            "end": r.read_f32(),
            "end_var": r.read_f32(),
            "_end": r.pos,
        }
    if ty == 3:
        count = r.read_length()
        points = []
        for _ in range(count):
            points.append(
                {
                    "time": r.read_f32(),
                    "value": r.read_f32(),
                    "value_var": r.read_f32(),
                    "left_angle": r.read_f32(),
                    "right_angle": r.read_f32(),
                }
            )
        return {
            "_type": "CSMovementCurve",
            "_offset": start,
            "type_id": ty,
            "count": count,
            "points": points,
            "_end": r.pos,
        }
    raise ParseError(f"unknown CSMovement type {ty} at offset {start}")


def read_material(r: Reader) -> dict[str, Any]:
    start = r.pos
    return {
        "_type": "CSMaterial",
        "_offset": start,
        "color": [r.read_f32(), r.read_f32(), r.read_f32(), r.read_f32()],
        "duration": r.read_f32(),
        "rotation": r.read_f32(),
        "emission": [r.read_f32(), r.read_f32(), r.read_f32()],
        "_end": r.pos,
    }


def read_particle_shape(r: Reader) -> dict[str, Any] | None:
    start = r.pos
    ty = r.read_u8()
    names = {0: "sphere", 1: "hemisphere", 2: "cone", 3: "circle", 4: "box", 5: "rect"}
    if ty not in names:
        return None
    item: dict[str, Any] = {"_type": "CSParticleShape", "_offset": start, "type_id": ty, "kind": names[ty]}
    if ty in (0, 1):
        item["range"] = r.read_f32()
    elif ty == 2:
        item["top_range"] = r.read_f32()
        item["bottom_range"] = r.read_f32()
        item["height"] = r.read_f32()
    elif ty in (3, 5):
        item["range"] = [r.read_f32(), r.read_f32()]
    elif ty == 4:
        item["range"] = [r.read_f32(), r.read_f32(), r.read_f32()]
    item["_end"] = r.pos
    return item


def read_sprite(r: Reader) -> dict[str, Any]:
    return annotated(
        r,
        "CSSprite",
        lambda: {
            "duration": r.read_f32(),
            "loop": read_loop(r),
            "bytecode": read_u8_array(r, 2),
        },
    )


def read_particle(r: Reader) -> dict[str, Any]:
    def body() -> dict[str, Any]:
        item: dict[str, Any] = {
            "shape": read_particle_shape(r),
            "shape_shell": r.read_bool(),
            "life": r.read_f32(),
            "life_var": r.read_f32(),
            "emission_rate": r.read_f32(),
            "emission_max": r.read_i32(),
            "prewarm_time": r.read_f32(),
            "emission_delay": r.read_f32(),
            "flags0": [r.read_bool(), r.read_bool(), r.read_bool(), r.read_bool()],
            "view": r.read_u8(),
            "sources": read_u16_array(r, 2),
            "blend_mode": r.read_u8(),
            "material": read_material(r),
            "color": [read_movement(r), read_movement(r), read_movement(r), read_movement(r)],
            "color_each": r.read_bool(),
            "radial": read_movement(r),
            "position": [read_movement(r), read_movement(r), read_movement(r)],
            "billboard": [read_movement(r), read_movement(r), read_movement(r)],
            "rotation": [read_movement(r), read_movement(r), read_movement(r)],
            "scale_each": r.read_bool(),
            "scale": [read_movement(r), read_movement(r), read_movement(r)],
            "local_space": r.read_bool(),
            "view_mode": r.read_u8(),
        }
        if item["view_mode"] == 4:
            item["stretch_rate"] = r.read_f32()
        item["clear"] = r.read_bool()
        return item

    return annotated(r, "CSParticle", body)


def read_trail_like(r: Reader, kind: str) -> dict[str, Any]:
    def body() -> dict[str, Any]:
        trail = kind == "CSTrail"
        result = {
            "blend_mode": r.read_u8(),
            "sources": read_u16_array(r, 2),
            "material": read_material(r),
            "flags": [r.read_bool() for _ in range(3 if trail else 2)],
            "distance": r.read_f32(),
        }
        if trail:
            result.update(emission_life=r.read_f32(), emission_smoothness=r.read_f32())
        result.update({
            "repeat_scale": r.read_f32(),
            "color_duration": r.read_f32(),
            "color_loop": read_loop(r),
            "color": [read_movement(r), read_movement(r), read_movement(r), read_movement(r)],
            "color_each": r.read_bool(),
            "rotation": r.read_f32(),
            "rotation_loop": read_loop(r),
        })
        return result

    return annotated(r, kind, body)


def read_mesh_material(r: Reader) -> dict[str, Any]:
    start = r.pos
    return {
        "_type": "CSMeshMaterial",
        "_offset": start,
        "material": read_material(r),
        "flag": r.read_bool(),
        "indices": read_u16_array(r, 1),
        "_end": r.pos,
    }


def read_model(r: Reader) -> dict[str, Any]:
    def body() -> dict[str, Any]:
        indices = read_u16_array(r, 1)
        materials = read_obj_array(r, 1, read_mesh_material)
        return {"indices": indices, "materials": materials}

    return annotated(r, "CSModel", body)


def read_substance(r: Reader) -> dict[str, Any] | None:
    start = r.pos
    ty = r.read_u8()
    if ty == 0:
        return None
    names = {1: "sprite", 2: "particle", 3: "trail", 4: "chain", 5: "model"}
    try:
        if ty == 1:
            data = read_sprite(r)
        elif ty == 2:
            data = read_particle(r)
        elif ty == 3:
            data = read_trail_like(r, "CSTrail")
        elif ty == 4:
            data = read_trail_like(r, "CSChain")
        elif ty == 5:
            data = read_model(r)
        else:
            raise ParseError(f"unknown substance type {ty} at offset {start}")
    except Exception as e:
        raise ParseError(f"substance type {ty} ({names.get(ty, '?')}) at offset {start}: {e}") from e
    data["type_id"] = ty
    data["kind"] = names.get(ty, f"unknown-{ty}")
    data["_substance_offset"] = start
    return data


def read_derivation(r: Reader) -> dict[str, Any] | None:
    start = r.pos
    ty = r.read_u8()
    if ty == 0:
        return None
    names = {1: "multi", 2: "linked", 3: "emission", 4: "random"}
    count = r.read_length()
    children = [read_animation(r) for _ in range(count)]
    item: dict[str, Any] = {
        "_type": "CSAnimationDerivation",
        "_offset": start,
        "type_id": ty,
        "kind": names.get(ty, f"unknown-{ty}"),
        "children": {"count": count, "items": children},
    }
    if ty == 2:
        item["loop_count"] = r.read_i32()
    elif ty == 3:
        item["delay"] = r.read_f32()
        item["capacity"] = r.read_i32()
        item["prewarm"] = r.read_bool()
    elif ty == 4:
        item["loop"] = r.read_bool()
    elif ty != 1:
        raise ParseError(f"unknown derivation type {ty} at offset {start}")
    item["_end"] = r.pos
    return item


def read_animation(r: Reader) -> dict[str, Any]:
    def body() -> dict[str, Any]:
        out: dict[str, Any] = {
            "key_mask": r.read_i32(),
            "random_weight": r.read_u8(),
            "flags0": [r.read_bool(), r.read_bool(), r.read_bool(), r.read_bool()],
            "path": {},
            "rotation": {},
            "scale": {},
        }
        out["path"]["x"] = read_movement(r)
        out["path"]["y"] = read_movement(r)
        if out["path"]["y"] is not None:
            out["path"]["radial"] = r.read_f32()
            out["path"]["tangential_angle"] = r.read_f32()
        out["path"]["z"] = read_movement(r)
        out["path"]["rotation_x"] = read_movement(r)
        out["path"]["rotation_y"] = read_movement(r)
        out["path"]["duration"] = r.read_f32()
        out["path"]["using_speed"] = r.read_bool()
        out["path"]["loop"] = read_loop(r)
        out["path"]["billboard"] = r.read_bool()

        out["rotation"]["x"] = read_movement(r)
        out["rotation"]["y"] = read_movement(r)
        out["rotation"]["z"] = read_movement(r)
        out["rotation"]["duration"] = r.read_f32()
        out["rotation"]["loop"] = read_loop(r)
        out["rotation"]["each"] = r.read_bool()

        out["scale"]["x"] = read_movement(r)
        out["scale"]["y"] = read_movement(r)
        out["scale"]["z"] = read_movement(r)
        out["scale"]["duration"] = r.read_f32()
        out["scale"]["loop"] = read_loop(r)
        out["scale"]["each"] = r.read_bool()

        out["pivot"] = r.read_bool()
        out["stencil"] = r.read_bool()
        has_target = r.read_bool()
        out["target"] = None
        if has_target:
            out["target"] = {"kind": r.read_u8(), "duration": r.read_f32()}
        out["closing"] = r.read_bool()
        has_invert = r.read_bool()
        out["invert"] = None
        if has_invert:
            out["invert"] = {"movement": read_movement(r), "duration": r.read_f32(), "loop": read_loop(r)}
        out["duration"] = r.read_f32()
        out["latency"] = r.read_f32()
        out["locale_visible"] = r.read_bool()
        out["visible"] = r.read_bool()
        has_indices = r.read_bool()
        out["indices"] = None
        if has_indices:
            out["indices"] = read_u16_array(r, 1)
            out["indices_timing"] = {
                "duration": r.read_f32(),
                "latency": r.read_f32(),
                "random": r.read_f32(),
                "flag": r.read_bool(),
            }
        out["using_locale"] = r.read_bool()
        locale_count = r.read_length()
        out["locales"] = {"count": locale_count, "items": [r.read_string() for _ in range(locale_count)]}
        out["substance"] = read_substance(r)
        out["derivation"] = read_derivation(r)
        return out

    return annotated(r, "CSAnimation", body)


def walk_animations(node: Any):
    if isinstance(node, dict):
        if node.get("_type") == "CSAnimation":
            yield node
        for value in node.values():
            yield from walk_animations(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_animations(value)


def parse_animations(data: bytes, source: str, layers: list[str]) -> dict[str, Any]:
    r = Reader(data)
    animations, errors = read_obj_array_partial(r, 3, read_animation)
    flat = list(walk_animations(animations))
    substances = Counter((a.get("substance") or {}).get("kind", "none") for a in flat)
    derivations = Counter((a.get("derivation") or {}).get("kind", "none") for a in flat)
    return {
        "kind": "acies-old-cdk-animations",
        "source": source,
        "layers": layers,
        "remaining": r.remaining,
        "parse_errors": errors,
        "animation_count_recursive": len(flat),
        "substance_counts": dict(substances),
        "derivation_counts": dict(derivations),
        "animations": animations,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=pathlib.Path)
    ap.add_argument("--asset-root", type=pathlib.Path, default=ASSET_ROOT)
    ap.add_argument("--output", type=pathlib.Path, required=True)
    ap.add_argument("--summary", action="store_true", help="Write counts and parse status without the animation tree")
    args = ap.parse_args()

    data, layers = decode_xmf(args.input, args.asset_root)
    parsed = parse_animations(data, str(args.input), layers)
    if args.summary:
        tree = parsed.pop("animations")
        groups = [{"index": index, "count": group["count"], "parsed_count": len(group["items"]),
                   "animations": sum(len(category["items"]) for category in group["items"])}
                  for index, group in enumerate(tree["items"])]
        parsed.update(top_level_counts=[tree["count"]], first_level_parsed=len(groups), groups=groups,
                      animation_count_top_level=sum(group["animations"] for group in groups))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"animations: recursive={parsed['animation_count_recursive']} "
        f"remaining={parsed['remaining']} substances={parsed['substance_counts']}"
    )


if __name__ == "__main__":
    main()
