#!/usr/bin/env python3
"""Decode ACIES/CDK mesh .xmf files into JSON metadata and Wavefront OBJ.

This parser follows the native reader in ACIES' libcdkapp.so:

    CSMesh::createWithBuffer(CSBuffer*)
    CSMeshNode::createWithBuffer(CSMeshNode const*, CSBuffer*, unsigned int&)

The open-source CDK3 tree has a newer CSMesh reader, but these APK assets use
the older runtime layout below:

    int32 block_length
    uint7 node_count
    repeat node_count:
        int32 parent_node_index
        uint7 triangle_count
        repeat triangle_count * 3:
            float3 position
            byte4 color
            float2 tex_coord
            float3 normal
        string node_name
        float[16] transform
        bool has_animation
        if has_animation: CSMeshAnimation(...)
        bool flag0
        bool flag1
        bool flag2
        uint8 sort
    int32 footer0
    int32 footer1
    int32 footer2
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import struct
from typing import Any

import xmf_probe


ASSET_ROOT = pathlib.Path("acies-apktool/assets")


class CSBufferReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    @property
    def remaining(self) -> int:
        return len(self.data) - self.pos

    def _take(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise ValueError(f"read overflow at {self.pos} for {n} bytes")
        out = self.data[self.pos : self.pos + n]
        self.pos += n
        return out

    def read_u8(self) -> int:
        return self._take(1)[0]

    def read_i32(self) -> int:
        return struct.unpack("<i", self._take(4))[0]

    def read_f32(self) -> float:
        return struct.unpack("<f", self._take(4))[0]

    def read_length(self) -> int:
        value = 0
        while True:
            current = self.read_u8()
            value = (value << 7) | (current & 0x7F)
            if not current & 0x80:
                return value

    def read_string(self, encoding: str = "utf-8") -> str:
        length = self.read_length()
        if length == 0:
            return ""
        return self._take(length).decode(encoding)

    def read_bool(self) -> bool:
        return self.read_u8() != 0


def decode_xmf(path: pathlib.Path, asset_root: pathlib.Path) -> tuple[bytes, list[str]]:
    raw = path.read_bytes()
    layers: list[str] = []

    if raw.startswith(b"\x1f\x8b"):
        decoded, comp = xmf_probe.maybe_uncompress(raw)
        if comp:
            layers.append(comp)
        return decoded, layers

    rel = xmf_probe.asset_relative(path, asset_root)
    key = xmf_probe.file_key(rel)
    try:
        decrypted = xmf_probe.openssl_aes256_cbc_decrypt(raw, key)
    except Exception:
        return raw, ["plain/unknown"]

    stripped, ok, calc, expected = xmf_probe.strip_xor_check(decrypted)
    if not ok:
        return raw, ["plain/unknown"]

    decoded = stripped
    layers.append(f"aes256-cbc key={key.decode()}")
    layers.append(f"xor32=ok {calc:08x}")
    uncompressed, comp = xmf_probe.maybe_uncompress(decoded)
    if comp:
        decoded = uncompressed
        layers.append(comp)
    return decoded, layers


def finite_values(values: list[float]) -> bool:
    return all(math.isfinite(v) for v in values)


def read_vertex(r: CSBufferReader) -> dict[str, Any]:
    position = [r.read_f32(), r.read_f32(), r.read_f32()]
    color_bytes = [r.read_u8(), r.read_u8(), r.read_u8(), r.read_u8()]
    tex_coord = [r.read_f32(), r.read_f32()]
    normal = [r.read_f32(), r.read_f32(), r.read_f32()]
    if not finite_values(position + tex_coord + normal):
        raise ValueError(f"non-finite vertex value ending at offset {r.pos}")
    return {
        "position": position,
        "color": [round(c / 255.0, 6) for c in color_bytes],
        "color_bytes": color_bytes,
        "tex_coord": tex_coord,
        "normal": normal,
    }


def parse_animation_placeholder(r: CSBufferReader) -> dict[str, Any]:
    start = r.pos
    raise NotImplementedError(
        f"CSMeshAnimation parsing is not implemented yet; animation starts at offset {start}"
    )


def parse_mesh(data: bytes, source: str, layers: list[str]) -> dict[str, Any]:
    r = CSBufferReader(data)
    block_length = r.read_i32()
    if block_length != r.remaining:
        raise ValueError(
            f"block length mismatch: header={block_length} remaining={r.remaining}"
        )

    node_count = r.read_length()
    nodes: list[dict[str, Any]] = []
    all_vertices: list[dict[str, Any]] = []

    for node_index in range(node_count):
        parent_node_index = r.read_i32()
        triangle_count = r.read_length()
        vertices = []
        start_offset = r.pos
        for _ in range(triangle_count * 3):
            vertices.append(read_vertex(r))

        name = r.read_string()
        matrix = [r.read_f32() for _ in range(16)]
        has_animation = r.read_bool()
        animation = None
        if has_animation:
            animation = parse_animation_placeholder(r)
        flags = [r.read_bool(), r.read_bool(), r.read_bool()]
        sort = r.read_u8()

        positions = [v["position"] for v in vertices]
        tex_coords = [v["tex_coord"] for v in vertices]
        normals = [v["normal"] for v in vertices]
        node = {
            "index": node_index,
            "parent_node_index": parent_node_index,
            "triangle_count": triangle_count,
            "vertex_count": len(vertices),
            "vertex_data_offset": start_offset,
            "name": name,
            "matrix": matrix,
            "has_animation": has_animation,
            "animation": animation,
            "flags": {
                "flag0": flags[0],
                "flag1": flags[1],
                "flag2": flags[2],
                "sort": sort,
            },
            "bounds": bounds_for_positions(positions),
            "uv_bounds": bounds_for_positions(tex_coords),
            "normal_bounds": bounds_for_positions(normals),
            "vertices": vertices,
        }
        nodes.append(node)
        all_vertices.extend(vertices)

    footer = [r.read_i32(), r.read_i32(), r.read_i32()]
    if r.remaining:
        raise ValueError(f"mesh has {r.remaining} trailing bytes at offset {r.pos}")

    return {
        "kind": "acies-cdk-mesh",
        "source": source,
        "layers": layers,
        "block_length": block_length,
        "node_count": node_count,
        "footer": footer,
        "total_triangle_count": sum(n["triangle_count"] for n in nodes),
        "total_vertex_count": sum(n["vertex_count"] for n in nodes),
        "bounds": bounds_for_positions([v["position"] for v in all_vertices]),
        "nodes": nodes,
    }


def bounds_for_positions(values: list[list[float]]) -> dict[str, list[float]] | None:
    if not values:
        return None
    width = len(values[0])
    mins = [min(v[i] for v in values) for i in range(width)]
    maxs = [max(v[i] for v in values) for i in range(width)]
    return {"min": mins, "max": maxs}


def metadata_only(mesh: dict[str, Any]) -> dict[str, Any]:
    slim = dict(mesh)
    nodes = []
    for node in mesh["nodes"]:
        node_slim = {k: v for k, v in node.items() if k != "vertices"}
        nodes.append(node_slim)
    slim["nodes"] = nodes
    return slim


def write_obj(mesh: dict[str, Any], path: pathlib.Path) -> None:
    lines = [
        f"# {mesh['source']}",
        "# Generated by tools/decode_cdk_mesh.py",
        f"# nodes={mesh['node_count']} triangles={mesh['total_triangle_count']}",
        "",
    ]
    vertex_base = 1
    for node in mesh["nodes"]:
        safe_name = node["name"] or f"node_{node['index']:03d}"
        lines.append(f"o {safe_name}")
        for vertex in node["vertices"]:
            x, y, z = vertex["position"]
            lines.append(f"v {x:.9g} {y:.9g} {z:.9g}")
        for vertex in node["vertices"]:
            u, v = vertex["tex_coord"]
            lines.append(f"vt {u:.9g} {v:.9g}")
        for vertex in node["vertices"]:
            nx, ny, nz = vertex["normal"]
            lines.append(f"vn {nx:.9g} {ny:.9g} {nz:.9g}")
        for i in range(0, node["vertex_count"], 3):
            a = vertex_base + i
            b = vertex_base + i + 1
            c = vertex_base + i + 2
            lines.append(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}")
        vertex_base += node["vertex_count"]
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=pathlib.Path)
    parser.add_argument("--asset-root", type=pathlib.Path, default=ASSET_ROOT)
    parser.add_argument("--out-dir", type=pathlib.Path, default=pathlib.Path("decrypts/meshes"))
    parser.add_argument(
        "--full-json",
        action="store_true",
        help="also write JSON files that include every vertex",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    meta_dir = args.out_dir / "json"
    full_json_dir = args.out_dir / "json-full"
    obj_dir = args.out_dir / "obj"
    meta_dir.mkdir(parents=True, exist_ok=True)
    if args.full_json:
        full_json_dir.mkdir(parents=True, exist_ok=True)
    obj_dir.mkdir(parents=True, exist_ok=True)

    index = []
    for path in args.paths:
        data, layers = decode_xmf(path, args.asset_root)
        mesh = parse_mesh(data, path.as_posix(), layers)
        stem = path.name.removesuffix(".xmf")
        json_path = meta_dir / f"{stem}.json"
        obj_path = obj_dir / f"{stem}.obj"
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(metadata_only(mesh), f, ensure_ascii=False, indent=2)
            f.write("\n")
        if args.full_json:
            with (full_json_dir / f"{stem}.json").open("w", encoding="utf-8") as f:
                json.dump(mesh, f, ensure_ascii=False, indent=2)
                f.write("\n")
        write_obj(mesh, obj_path)
        index.append(
            {
                "source": path.as_posix(),
                "json": json_path.as_posix(),
                "obj": obj_path.as_posix(),
                "node_count": mesh["node_count"],
                "triangle_count": mesh["total_triangle_count"],
                "vertex_count": mesh["total_vertex_count"],
                "bounds": mesh["bounds"],
                "footer": mesh["footer"],
            }
        )
        print(
            f"{path}: nodes={mesh['node_count']} triangles={mesh['total_triangle_count']} "
            f"vertices={mesh['total_vertex_count']} -> {obj_path}"
        )

    with (args.out_dir / "index.json").open("w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
