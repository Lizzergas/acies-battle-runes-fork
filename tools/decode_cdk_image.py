#!/usr/bin/env python3
"""Decode ACIES/CDK root-image .xmf textures to PNG.

The APK image assets use an older CSRootImage block format visible in
libcdkapp.so:

    uint32 block_length
    int16  format_prefix
    int16  width
    int16  height
    uint8  encoding_count
    repeat encoding_count:
        uint8  encoding_code
        uint32 payload_length
        bytes  payload

For the ACIES samples inspected so far:

- encoding_code 6 is ETC2 RGB8
- encoding_code 7 is ETC2 RGBA8
- encoding_code 15 is raw RGBA8888

For ETC2 payloads, the payload starts with a mip-level count byte followed by
ETC2 blocks. Raw RGBA8888 payloads are width * height * 4 bytes with no mip
prefix.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import struct
import sys
from typing import Any

import xmf_probe


ASSET_ROOT = pathlib.Path("acies-apktool/assets")


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
        return raw, [f"decrypt-check-failed calc={calc:08x} expected={expected:08x}"]

    decoded = stripped
    layers = [f"aes256-cbc key={key.decode()}", f"xor32=ok {calc:08x}"]
    uncompressed, comp = xmf_probe.maybe_uncompress(decoded)
    if comp:
        decoded = uncompressed
        layers.append(comp)
    return decoded, layers


def parse_root_image(data: bytes) -> dict[str, Any]:
    if len(data) < 4:
        raise ValueError("file is too small for a CSRootImage block")

    block_length = struct.unpack_from("<I", data, 0)[0]
    if block_length == 0:
        return {
            "empty": True,
            "block_length": 0,
            "tail_length": len(data) - 4,
            "encodings": [],
        }
    if block_length > len(data) - 4:
        raise ValueError(f"block length {block_length} exceeds payload size {len(data)}")
    if block_length < 7:
        raise ValueError(f"block length {block_length} is too small")

    block = data[4 : 4 + block_length]
    format_prefix, width, height, encoding_count = struct.unpack_from("<hhhB", block, 0)
    pos = 7
    encodings = []
    for _ in range(encoding_count):
        if pos + 5 > len(block):
            raise ValueError("encoding header overflows root-image block")
        code = block[pos]
        payload_length = struct.unpack_from("<I", block, pos + 1)[0]
        payload_start = pos + 5
        payload_end = payload_start + payload_length
        if payload_end > len(block):
            raise ValueError("encoding payload overflows root-image block")
        encodings.append(
            {
                "code": code,
                "payload_length": payload_length,
                "payload_offset": payload_start,
                "payload": block[payload_start:payload_end],
            }
        )
        pos = payload_end

    return {
        "empty": False,
        "block_length": block_length,
        "format_prefix": format_prefix,
        "width": width,
        "height": height,
        "encoding_count": encoding_count,
        "encodings": encodings,
        "tail_offset": 4 + block_length,
        "tail_length": len(data) - (4 + block_length),
        "block_remaining": len(block) - pos,
    }


def decode_encoding(meta: dict[str, Any], encoding: dict[str, Any]) -> tuple[bytes, str]:
    try:
        import texture2ddecoder
    except ImportError as e:
        raise RuntimeError(
            "texture2ddecoder is required. Use .venv-xmf/bin/python or install texture2ddecoder."
        ) from e

    width = meta["width"]
    height = meta["height"]
    code = encoding["code"]
    payload = encoding["payload"]

    if code == 6:
        if not payload:
            raise ValueError("ETC2 RGB8 payload is empty")
        level_count = payload[0]
        level_size = math.ceil(width / 4) * math.ceil(height / 4) * 8
        if len(payload) < 1 + level_size:
            raise ValueError(
                f"ETC2 RGB8 level 0 needs {level_size} bytes, got {len(payload) - 1}"
            )
        rgba = texture2ddecoder.decode_etc2(payload[1 : 1 + level_size], width, height)
        return rgba, f"ETC2_RGB8 mip_levels={level_count}"

    if code == 7:
        if not payload:
            raise ValueError("ETC2 RGBA8 payload is empty")
        level_count = payload[0]
        level_size = math.ceil(width / 4) * math.ceil(height / 4) * 16
        if len(payload) < 1 + level_size:
            raise ValueError(
                f"ETC2 RGBA8 level 0 needs {level_size} bytes, got {len(payload) - 1}"
            )
        rgba = texture2ddecoder.decode_etc2a8(payload[1 : 1 + level_size], width, height)
        return rgba, f"ETC2_RGBA8 mip_levels={level_count}"

    if code == 15:
        expected = width * height * 4
        if len(payload) != expected:
            raise ValueError(f"RGBA8888 payload needs {expected} bytes, got {len(payload)}")
        return payload, "RGBA8888"

    raise NotImplementedError(f"unsupported image encoding code {code}")


def write_png(rgba: bytes, width: int, height: int, output: pathlib.Path) -> None:
    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError("Pillow is required. Use .venv-xmf/bin/python or install pillow.") from e

    output.parent.mkdir(parents=True, exist_ok=True)
    Image.frombytes("RGBA", (width, height), rgba).save(output)


def metadata_for_json(meta: dict[str, Any], source: pathlib.Path, layers: list[str]) -> dict[str, Any]:
    result = {k: v for k, v in meta.items() if k != "encodings"}
    result["source"] = str(source)
    result["layers"] = layers
    result["encodings"] = [
        {
            "code": enc["code"],
            "payload_length": enc["payload_length"],
            "payload_offset": enc["payload_offset"],
        }
        for enc in meta["encodings"]
    ]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Decode ACIES/CDK root-image .xmf textures.")
    parser.add_argument("paths", nargs="+", type=pathlib.Path)
    parser.add_argument("--asset-root", type=pathlib.Path, default=ASSET_ROOT)
    parser.add_argument("--decoded", action="store_true", help="Input files are already decoded payloads.")
    parser.add_argument("--out-dir", type=pathlib.Path, default=pathlib.Path("decrypts/images/png"))
    parser.add_argument("--meta-dir", type=pathlib.Path, default=pathlib.Path("decrypts/images/meta"))
    args = parser.parse_args()

    for path in args.paths:
        data, layers = (path.read_bytes(), ["decoded-input"]) if args.decoded else decode_xmf(path, args.asset_root)
        meta = parse_root_image(data)
        out_stem = path.name.replace(".xmf.decoded", "").replace(".xmf", "")
        meta_path = args.meta_dir / f"{out_stem}.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(
            json.dumps(metadata_for_json(meta, path, layers), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        if meta["empty"]:
            print(f"{path}: empty image block, wrote {meta_path}")
            continue
        if not meta["encodings"]:
            print(f"{path}: no encodings, wrote {meta_path}")
            continue

        rgba, description = decode_encoding(meta, meta["encodings"][0])
        out_path = args.out_dir / f"{out_stem}.png"
        write_png(rgba, meta["width"], meta["height"], out_path)
        print(
            f"{path}: {meta['width']}x{meta['height']} {description} "
            f"tail={meta['tail_length']} -> {out_path}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
