#!/usr/bin/env python3
"""Decode ACIES terrain.xmf texture-bank payloads.

ACIES' assets/terrain.xmf is gzip-compressed.  The decompressed payload is not
a full Terrain::Terrain(CSBuffer*) geometry object; it is two arrays of CDK
CSRootImage blocks:

    uint7 lightmap_image_count
    repeat lightmap_image_count: CSRootImage block
    uint7 terrain_texture_count
    repeat terrain_texture_count: CSRootImage block

The CSRootImage block format and ETC2/raw decoding are shared with
tools/decode_cdk_image.py.
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
from typing import Any

import xmf_probe
from decode_cdk_image import decode_encoding, metadata_for_json, parse_root_image, write_png


ASSET_ROOT = pathlib.Path("acies-apktool/assets")
DEFAULT_GROUP_NAMES = ["lightmaps", "terrain_textures"]


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    @property
    def remaining(self) -> int:
        return len(self.data) - self.pos

    def read_u8(self) -> int:
        if self.pos >= len(self.data):
            raise ValueError("read overflow while reading byte")
        value = self.data[self.pos]
        self.pos += 1
        return value

    def read_length(self) -> int:
        value = 0
        while True:
            current = self.read_u8()
            value = (value << 7) | (current & 0x7F)
            if not current & 0x80:
                return value


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
        calc_text = f"{calc:08x}" if calc is not None else "none"
        expected_text = f"{expected:08x}" if expected is not None else "none"
        return raw, [f"decrypt-check-failed calc={calc_text} expected={expected_text}"]

    decoded = stripped
    layers = [f"aes256-cbc key={key.decode()}", f"xor32=ok {calc:08x}"]
    uncompressed, comp = xmf_probe.maybe_uncompress(decoded)
    if comp:
        decoded = uncompressed
        layers.append(comp)
    return decoded, layers


def parse_terrain_bank(data: bytes, source: pathlib.Path, layers: list[str]) -> dict[str, Any]:
    reader = Reader(data)
    groups = []
    group_index = 0
    while reader.remaining:
        group_offset = reader.pos
        image_count = reader.read_length()
        images = []
        for image_index in range(image_count):
            image_offset = reader.pos
            meta = parse_root_image(data[reader.pos :])
            consumed = meta["tail_offset"]
            reader.pos += consumed
            encodings = [
                {
                    "code": enc["code"],
                    "payload_length": enc["payload_length"],
                    "payload_offset": image_offset + 4 + enc["payload_offset"],
                }
                for enc in meta["encodings"]
            ]
            images.append(
                {
                    "index": image_index,
                    "offset": image_offset,
                    "length": consumed,
                    "empty": meta["empty"],
                    "width": meta.get("width"),
                    "height": meta.get("height"),
                    "format_prefix": meta.get("format_prefix"),
                    "encoding_count": meta.get("encoding_count"),
                    "encodings": encodings,
                }
            )
        groups.append(
            {
                "index": group_index,
                "name": DEFAULT_GROUP_NAMES[group_index]
                if group_index < len(DEFAULT_GROUP_NAMES)
                else f"group_{group_index}",
                "offset": group_offset,
                "image_count": image_count,
                "images": images,
            }
        )
        group_index += 1

    return {
        "kind": "acies-terrain-texture-bank",
        "source": source.as_posix(),
        "layers": layers,
        "decoded_size": len(data),
        "group_count": len(groups),
        "image_count": sum(g["image_count"] for g in groups),
        "groups": groups,
    }


def export_terrain_bank(
    data: bytes,
    parsed: dict[str, Any],
    source: pathlib.Path,
    layers: list[str],
    out_dir: pathlib.Path,
) -> None:
    png_dir = out_dir / "png"
    meta_dir = out_dir / "meta"
    png_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    for group in parsed["groups"]:
        group_png_dir = png_dir / group["name"]
        group_meta_dir = meta_dir / group["name"]
        group_png_dir.mkdir(parents=True, exist_ok=True)
        group_meta_dir.mkdir(parents=True, exist_ok=True)
        for image in group["images"]:
            meta = parse_root_image(data[image["offset"] :])
            stem = f"terrain-{group['index']:02d}-{image['index']:03d}"
            meta_path = group_meta_dir / f"{stem}.json"
            meta_path.write_text(
                json.dumps(metadata_for_json(meta, source, layers), ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
            if meta["empty"] or not meta["encodings"]:
                continue
            rgba, description = decode_encoding(meta, meta["encodings"][0])
            png_path = group_png_dir / f"{stem}.png"
            write_png(rgba, meta["width"], meta["height"], png_path)
            image["png"] = png_path.as_posix()
            image["encoding_description"] = description
            image["meta"] = meta_path.as_posix()


def write_html_index(parsed: dict[str, Any], out_dir: pathlib.Path) -> None:
    lines = [
        "<!doctype html>",
        "<meta charset=\"utf-8\">",
        "<title>ACIES terrain.xmf</title>",
        "<style>",
        "body{font-family:system-ui,-apple-system,sans-serif;margin:24px;background:#111;color:#eee}",
        "h1,h2{font-weight:600}",
        ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:14px}",
        ".item{background:#1b1b1b;border:1px solid #333;border-radius:6px;padding:8px}",
        "img{width:100%;image-rendering:auto;background:#000}",
        ".meta{font-size:12px;color:#bbb;line-height:1.35;margin-top:6px;word-break:break-word}",
        "a{color:#9bd}",
        "</style>",
        "<h1>ACIES terrain.xmf</h1>",
        f"<p>{parsed['group_count']} groups, {parsed['image_count']} images, decoded size {parsed['decoded_size']} bytes.</p>",
    ]
    for group in parsed["groups"]:
        lines.append(f"<h2>{html.escape(group['name'])}</h2>")
        lines.append("<div class=\"grid\">")
        for image in group["images"]:
            png = image.get("png")
            meta = image.get("meta")
            enc = image["encodings"][0] if image["encodings"] else {}
            lines.append("<div class=\"item\">")
            if png:
                rel_png = pathlib.Path(png).relative_to(out_dir).as_posix()
                lines.append(f"<a href=\"{html.escape(rel_png)}\"><img src=\"{html.escape(rel_png)}\"></a>")
            lines.append("<div class=\"meta\">")
            lines.append(f"{group['index']:02d}/{image['index']:03d}<br>")
            lines.append(f"{image.get('width')}x{image.get('height')} code={enc.get('code')}<br>")
            if image.get("encoding_description"):
                lines.append(f"{html.escape(image['encoding_description'])}<br>")
            if meta:
                rel_meta = pathlib.Path(meta).relative_to(out_dir).as_posix()
                lines.append(f"<a href=\"{html.escape(rel_meta)}\">metadata</a>")
            lines.append("</div></div>")
        lines.append("</div>")
    (out_dir / "index.html").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=pathlib.Path)
    parser.add_argument("--asset-root", type=pathlib.Path, default=ASSET_ROOT)
    parser.add_argument("--out-dir", type=pathlib.Path, default=pathlib.Path("decrypts/terrain"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    data, layers = decode_xmf(args.path, args.asset_root)
    parsed = parse_terrain_bank(data, args.path, layers)
    export_terrain_bank(data, parsed, args.path, layers, args.out_dir)
    index_path = args.out_dir / "index.json"
    index_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_html_index(parsed, args.out_dir)
    decoded_path = args.out_dir / f"{args.path.name}.decoded"
    decoded_path.write_bytes(data)
    print(
        f"{args.path}: groups={parsed['group_count']} images={parsed['image_count']} "
        f"decoded={parsed['decoded_size']} -> {args.out_dir}"
    )
    for group in parsed["groups"]:
        print(f"  {group['name']}: {group['image_count']} images")


if __name__ == "__main__":
    main()
