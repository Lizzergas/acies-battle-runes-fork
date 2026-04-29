#!/usr/bin/env python3
"""Structured parsers for CDK3-built ACIES .xmf payloads.

This is intentionally small: it reuses the container decrypt/decompress layer
from xmf_probe.py, then applies schemas confirmed in the CDK3 source tree.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import struct
import sys
from collections import Counter
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

    def read_i16(self) -> int:
        return struct.unpack("<h", self._take(2))[0]

    def read_u16(self) -> int:
        return struct.unpack("<H", self._take(2))[0]

    def read_i32(self) -> int:
        return struct.unpack("<i", self._take(4))[0]

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

    def read_locale_string(self) -> dict[str, str]:
        count = self.read_length()
        values: dict[str, str] = {}
        for _ in range(count):
            locale = self.read_string()
            values[locale] = self.read_string()
        return values


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
        if calc is None:
            return raw, ["plain/unknown"]
        return raw, [f"decrypt-check-failed calc={calc:08x} expected={expected:08x}"]

    decoded = stripped
    layers.append(f"aes256-cbc key={key.decode()}")
    layers.append(f"xor32=ok {calc:08x}")
    uncompressed, comp = xmf_probe.maybe_uncompress(decoded)
    if comp:
        decoded = uncompressed
        layers.append(comp)
    return decoded, layers


def parse_version_local(data: bytes) -> dict[str, Any]:
    r = CSBufferReader(data)
    bundle_version = r.read_u16()
    revision = r.read_u16()
    count = r.read_length()
    entries = []
    for _ in range(count):
        entries.append(
            {
                "path": r.read_string(),
                "version": r.read_i16(),
            }
        )
    return {
        "kind": "version-local",
        "bundle_version": bundle_version,
        "revision": revision,
        "count": count,
        "remaining": r.remaining,
        "extensions": dict(Counter(pathlib.PurePosixPath(e["path"]).suffix or "<none>" for e in entries)),
        "entries": entries,
    }


def parse_locale_string_table(data: bytes) -> dict[str, Any]:
    r = CSBufferReader(data)
    # Asset::loadStrings() reads this as CSArray<CSLocaleString, 2>.
    outer_count = r.read_length()
    groups = []
    parse_error = None
    for group_index in range(outer_count):
        group_offset = r.pos
        item_count = r.read_length()
        strings = []
        for item_index in range(item_count):
            try:
                strings.append(r.read_locale_string())
            except Exception as e:
                parse_error = {
                    "group_index": group_index,
                    "item_index": item_index,
                    "offset": r.pos,
                    "message": str(e),
                }
                break
        groups.append(
            {
                "index": group_index,
                "offset": group_offset,
                "count": item_count,
                "parsed_count": len(strings),
                "strings": strings,
            }
        )
        if parse_error:
            break
    locales = sorted({locale for group in groups for item in group["strings"] for locale in item})
    parsed_count = sum(group["parsed_count"] for group in groups)
    count = sum(group["count"] for group in groups)
    parsed: dict[str, Any] = {
        "kind": "locale-string-table",
        "outer_count": outer_count,
        "parsed_outer_count": len(groups),
        "count": count,
        "parsed_count": parsed_count,
        "remaining": r.remaining,
        "locales": locales,
        "groups": groups,
    }
    if parse_error:
        parsed["parse_error"] = parse_error
    return parsed


def parse_locale_metadata(data: bytes) -> dict[str, Any]:
    r = CSBufferReader(data)
    count = r.read_length()
    locales = []
    for i in range(count):
        unknown_i32 = r.read_i32()
        payload_length = r.read_i32()
        payload_offset = r.pos
        payload = r._take(payload_length)
        pr = CSBufferReader(payload)
        alias_count = pr.read_length()
        aliases = [pr.read_string() for _ in range(alias_count)]
        display_name = pr.read_string()
        digit_group_separator = pr.read_u8()
        if pr.remaining:
            raise ValueError(
                f"locale record {i} has {pr.remaining} trailing bytes in payload"
            )
        locales.append(
            {
                "index": i,
                "unknown_i32": unknown_i32,
                "payload_length": payload_length,
                "payload_offset": payload_offset,
                "aliases": aliases,
                "primary_locale": aliases[0] if aliases else "",
                "display_name": display_name,
                "digit_group_separator": (
                    chr(digit_group_separator) if digit_group_separator else ""
                ),
                "digit_group_separator_byte": digit_group_separator,
            }
        )
    return {
        "kind": "locale-metadata",
        "count": count,
        "remaining": r.remaining,
        "locales": locales,
    }


def guess_kind(path: pathlib.Path) -> str:
    name = path.name
    if name == "version.xmf" or name.startswith("version.xmf."):
        return "version"
    if name == "strings.xmf" or name.startswith("strings.xmf."):
        return "strings"
    if name == "locale.xmf" or name.startswith("locale.xmf."):
        return "locale"
    return "strings" if "strings.xmf" in path.as_posix() else "version"


def to_csv_rows(parsed: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    if parsed["kind"] == "version-local":
        return ["path", "version"], [[e["path"], e["version"]] for e in parsed["entries"]]
    if parsed["kind"] == "locale-string-table":
        locales = parsed["locales"]
        header = ["group", "index", "global_index", *locales]
        rows = []
        global_index = 0
        for group in parsed["groups"]:
            for i, item in enumerate(group["strings"]):
                rows.append([group["index"], i, global_index, *[item.get(locale, "") for locale in locales]])
                global_index += 1
        return header, rows
    if parsed["kind"] == "locale-metadata":
        return (
            [
                "index",
                "unknown_i32",
                "primary_locale",
                "aliases",
                "display_name",
                "digit_group_separator",
                "digit_group_separator_byte",
            ],
            [
                [
                    e["index"],
                    e["unknown_i32"],
                    e["primary_locale"],
                    "|".join(e["aliases"]),
                    e["display_name"],
                    e["digit_group_separator"],
                    e["digit_group_separator_byte"],
                ]
                for e in parsed["locales"]
            ],
        )
    raise ValueError(f"no CSV exporter for {parsed['kind']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse selected CDK3 .xmf payloads.")
    parser.add_argument("path", type=pathlib.Path)
    parser.add_argument("--asset-root", type=pathlib.Path, default=ASSET_ROOT)
    parser.add_argument("--kind", choices=["auto", "version", "strings", "locale"], default="auto")
    parser.add_argument("--decoded", action="store_true", help="Input is already decrypted/decompressed.")
    parser.add_argument("--output", type=pathlib.Path, help="Write parsed JSON.")
    parser.add_argument("--csv", type=pathlib.Path, help="Write a CSV view for parsed records.")
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args()

    if not args.path.exists():
        print(f"missing path: {args.path}", file=sys.stderr)
        return 2

    if args.decoded:
        data = args.path.read_bytes()
        layers = ["decoded-input"]
    else:
        data, layers = decode_xmf(args.path, args.asset_root)

    kind = guess_kind(args.path) if args.kind == "auto" else args.kind
    if kind == "version":
        parsed = parse_version_local(data)
    elif kind == "locale":
        parsed = parse_locale_metadata(data)
    else:
        parsed = parse_locale_string_table(data)
    parsed["source"] = str(args.path)
    parsed["layers"] = layers
    parsed["decoded_size"] = len(data)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(parsed, ensure_ascii=False, indent=args.indent) + "\n", encoding="utf-8")
    else:
        print(json.dumps(parsed, ensure_ascii=False, indent=args.indent))

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        header, rows = to_csv_rows(parsed)
        with args.csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)

    parsed_count = parsed.get("parsed_count", parsed["count"])
    summary = (
        f"{parsed['kind']}: parsed={parsed_count}/{parsed['count']} "
        f"remaining={parsed['remaining']} decoded={len(data)}"
    )
    if args.output or args.csv:
        print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
