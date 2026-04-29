#!/usr/bin/env python3
import argparse
import gzip
import hashlib
import pathlib
import struct
import subprocess
import sys
import tempfile
import zlib


ASSET_ROOT = pathlib.Path("acies-apktool/assets")


def asset_relative(path: pathlib.Path, asset_root: pathlib.Path) -> str:
    try:
        return path.resolve().relative_to(asset_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def file_key(relpath: str) -> bytes:
    return hashlib.sha1(("brtc" + relpath).encode("utf-8")).hexdigest()[:32].encode("ascii")


def openssl_aes256_cbc_decrypt(data: bytes, key: bytes) -> bytes:
    # CSCrypto.java uses AES/CBC/PKCS5Padding with the ASCII key bytes as the
    # AES-256 key and the first 16 key bytes as the IV.
    cmd = [
        "openssl",
        "enc",
        "-d",
        "-aes-256-cbc",
        "-K",
        key.hex(),
        "-iv",
        key[:16].hex(),
    ]
    proc = subprocess.run(cmd, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip())
    return proc.stdout


def strip_xor_check(data: bytes) -> tuple[bytes, bool, int | None, int | None]:
    if len(data) < 4:
        return data, False, None, None
    word_count = (len(data) - 4) // 4
    check_count = min(word_count, 256)
    calc = 0
    for i in range(check_count):
        calc ^= struct.unpack_from("<I", data, i * 4)[0]
    expected = struct.unpack_from("<I", data, len(data) - 4)[0]
    return data[:-4], calc == expected, calc, expected


def maybe_uncompress(data: bytes) -> tuple[bytes, str | None]:
    if data.startswith(b"\x1f\x8b"):
        return gzip.decompress(data), "gzip"
    try:
        return zlib.decompress(data), "zlib"
    except zlib.error:
        return data, None


def read_len(buf: bytes, pos: int) -> tuple[int, int]:
    value = 0
    while True:
        b = buf[pos]
        pos += 1
        value = (value << 7) | (b & 0x7F)
        if not b & 0x80:
            return value, pos


def preview_strings(buf: bytes, limit: int) -> list[str]:
    out: list[str] = []
    pos = 0
    while pos < len(buf) and len(out) < limit:
        try:
            n, pos2 = read_len(buf, pos)
        except Exception:
            break
        if n == 0 or n > 4096 or pos2 + n > len(buf):
            pos += 1
            continue
        chunk = buf[pos2 : pos2 + n]
        try:
            text = chunk.decode("utf-8")
        except UnicodeDecodeError:
            pos += 1
            continue
        if text and all((c.isprintable() or c.isspace()) for c in text):
            out.append(text.replace("\n", "\\n"))
            pos = pos2 + n
        else:
            pos += 1
    return out


def analyze(path: pathlib.Path, asset_root: pathlib.Path, write_dir: pathlib.Path | None, strings: int) -> int:
    raw = path.read_bytes()
    rel = asset_relative(path, asset_root)
    decoded = raw
    layers: list[str] = []

    if raw.startswith(b"\x1f\x8b"):
        decoded = gzip.decompress(raw)
        layers.append("gzip")
    else:
        key = file_key(rel)
        try:
            decrypted = openssl_aes256_cbc_decrypt(raw, key)
            stripped, ok, calc, expected = strip_xor_check(decrypted)
            if ok:
                decoded = stripped
                layers.append(f"aes256-cbc key={key.decode()}")
                layers.append(f"xor32=ok {calc:08x}")
                uncompressed, comp = maybe_uncompress(decoded)
                if comp:
                    decoded = uncompressed
                    layers.append(comp)
            else:
                layers.append(
                    "plain/unknown"
                    if calc is None
                    else f"decrypt-check-failed calc={calc:08x} expected={expected:08x}"
                )
        except Exception:
            layers.append("plain/unknown")

    print(f"{path}")
    print(f"  rel: {rel}")
    print(f"  raw: {len(raw)} bytes")
    print(f"  layers: {', '.join(layers)}")
    print(f"  decoded: {len(decoded)} bytes")
    print(f"  head: {decoded[:32].hex()}")

    if strings:
        items = preview_strings(decoded, strings)
        if items:
            print("  strings:")
            for item in items:
                print(f"    {item[:160]}")

    if write_dir:
        write_dir.mkdir(parents=True, exist_ok=True)
        out = write_dir / (path.name + ".decoded")
        out.write_bytes(decoded)
        print(f"  wrote: {out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe/decrypt ACIES .xmf assets.")
    parser.add_argument("paths", nargs="+", type=pathlib.Path)
    parser.add_argument("--asset-root", type=pathlib.Path, default=ASSET_ROOT)
    parser.add_argument("--write-dir", type=pathlib.Path)
    parser.add_argument("--strings", type=int, default=8)
    args = parser.parse_args()

    missing = [str(p) for p in args.paths if not p.exists()]
    if missing:
        print("missing paths: " + ", ".join(missing), file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory():
        for i, path in enumerate(args.paths):
            if i:
                print()
            analyze(path, args.asset_root, args.write_dir, args.strings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
