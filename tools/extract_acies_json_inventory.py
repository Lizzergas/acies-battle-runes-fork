#!/usr/bin/env python3
"""Extract ACIES JSON/model hints from libcdkapp native symbols.

This is a static-analysis helper. It does not execute the APK or contact any
remote service. It uses the exported/native symbol table and a lightweight
disassembly pass to associate string constants with CSJSONWriter and
CSJSONObject access calls.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Symbol:
    addr: int
    name: str


def load_rodata(path: Path) -> dict[int, str]:
    entries: dict[int, str] = {}
    for line in path.read_text(errors="ignore").splitlines():
        parts = line.strip().split(" ", 1)
        if len(parts) != 2:
            continue
        try:
            entries[int(parts[0], 16)] = parts[1]
        except ValueError:
            pass
    return entries


def load_symbols(path: Path) -> list[Symbol]:
    out: list[Symbol] = []
    for line in path.read_text(errors="ignore").splitlines():
        m = re.match(r"^([0-9a-f]+)\s+\w\s+(.+)$", line)
        if not m:
            continue
        out.append(Symbol(int(m.group(1), 16), m.group(2)))
    return sorted(out, key=lambda s: s.addr)


def load_segments(readelf: str, so: Path) -> tuple[bytes, list[tuple[int, int, int]]]:
    data = so.read_bytes()
    out = subprocess.check_output([readelf, "-W", "-l", str(so)], text=True, errors="ignore")
    loads: list[tuple[int, int, int]] = []
    for line in out.splitlines():
        parts = line.split()
        if parts and parts[0] == "LOAD":
            loads.append((int(parts[1], 16), int(parts[2], 16), int(parts[4], 16)))
    return data, loads


def read_cstr(data: bytes, loads: list[tuple[int, int, int]], va: int) -> str | None:
    for off, vaddr, filesz in loads:
        if vaddr <= va < vaddr + filesz:
            file_off = off + (va - vaddr)
            raw = data[file_off : file_off + 256].split(b"\0", 1)[0]
            if not raw:
                return None
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("utf-8", "replace")
    return None


def select_symbols(symbols: list[Symbol]) -> tuple[list[Symbol], list[Symbol], list[Symbol]]:
    models: dict[str, Symbol] = {}
    receives_by_name: dict[str, Symbol] = {}
    requests_by_name: dict[str, Symbol] = {}
    model_re = re.compile(
        r"^([A-Za-z_][\w]*)::("
        r"[A-Za-z_][\w]*|createWithJSON|userWithJSON|playerWithJSON|"
        r"profileWithJSON|addressWithJSON|load|updateWithJSON"
        r")\(CSJSONObject const\*"
    )
    for sym in symbols:
        if "CSJSONObject const*" in sym.name:
            m = model_re.match(sym.name)
            if m:
                cls = m.group(1)
                if cls.startswith("CSJSON"):
                    continue
                if cls not in models:
                    models[cls] = sym
        if sym.name.startswith("LobbyGateway::receive") and "(CSJSONObject const*" in sym.name:
            receives_by_name.setdefault(sym.name, sym)
        if sym.name.startswith("LobbyGateway::request") and "(" in sym.name:
            requests_by_name.setdefault(sym.name, sym)
    return (
        sorted(models.values(), key=lambda s: s.name),
        sorted(receives_by_name.values(), key=lambda s: s.name),
        sorted(requests_by_name.values(), key=lambda s: s.name),
    )


def next_addr(symbols: list[Symbol], addr: int) -> int:
    for sym in symbols:
        if sym.addr > addr:
            return sym.addr
    return addr + 0x800


def disassemble(objdump: str, so: Path, start: int, stop: int) -> str:
    return subprocess.check_output(
        [
            objdump,
            "-d",
            "--demangle",
            f"--start-address=0x{start:x}",
            f"--stop-address=0x{stop:x}",
            str(so),
        ],
        text=True,
        errors="ignore",
    )


def analyze_function(
    text: str, rodata: dict[int, str], data: bytes, loads: list[tuple[int, int, int]]
) -> dict[str, list[str]]:
    pages: dict[str, int] = {}
    regs: dict[str, int] = {}
    writer_keys: list[str] = []
    reader_keys: list[str] = []
    contains_keys: list[str] = []
    endpoints: list[str] = []

    for line in text.splitlines():
        m = re.search(r"\s(adrp)\s+(x\d+),\s*([0-9a-f]+)\s+", line)
        if m:
            pages[m.group(2)] = int(m.group(3), 16)
            continue

        m = re.search(r"\sadd\s+(x\d+),\s*(x\d+),\s*#0x([0-9a-f]+)", line)
        if m and m.group(2) in pages:
            regs[m.group(1)] = pages[m.group(2)] + int(m.group(3), 16)
            continue

        if "CSJSONWriter::write" in line:
            addr = regs.get("x1", -1)
            if addr < 0:
                continue
            s = rodata.get(addr) or read_cstr(data, loads, addr) or f"@0x{addr:x}"
            if s not in writer_keys:
                writer_keys.append(s)
            continue

        if "CSJSONObject::containsKey" in line:
            addr = regs.get("x1", -1)
            if addr < 0:
                continue
            s = rodata.get(addr) or read_cstr(data, loads, addr) or f"@0x{addr:x}"
            if s not in contains_keys:
                contains_keys.append(s)
            continue

        if "CSJSONObject::" in line and "ForKey" in line:
            addr = regs.get("x1", -1)
            if addr < 0:
                continue
            s = rodata.get(addr) or read_cstr(data, loads, addr) or f"@0x{addr:x}"
            if s not in reader_keys:
                reader_keys.append(s)
            continue

        if "LobbyGateway::sendPacket" in line:
            addr = regs.get("x3", -1)
            if addr < 0:
                continue
            s = rodata.get(addr) or read_cstr(data, loads, addr) or f"@0x{addr:x}"
            if s not in endpoints:
                endpoints.append(s)
            continue

    return {
        "writes": writer_keys,
        "reads": reader_keys,
        "contains": contains_keys,
        "endpoints": endpoints,
    }


def endpoint_paths(path: Path) -> set[str]:
    return set(p.strip() for p in path.read_text(errors="ignore").splitlines() if p.strip())


def md_list(items: list[str]) -> str:
    return "\n".join(f"- `{x}`" for x in items) if items else "- none found"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--objdump", default="/opt/homebrew/opt/binutils/bin/objdump")
    ap.add_argument("--readelf", default="/opt/homebrew/opt/binutils/bin/readelf")
    ap.add_argument("--out", type=Path, default=Path("docs/acies-json-payloads.md"))
    args = ap.parse_args()

    root = args.root
    so = root / "acies-apktool/lib/arm64-v8a/libcdkapp.so"
    data, loads = load_segments(args.readelf, so)
    rodata = load_rodata(root / "decrypts/libcdkapp/rodata-strings-with-offsets.txt")
    symbols = load_symbols(root / "decrypts/libcdkapp/symbols.demangled.txt")
    endpoints = endpoint_paths(root / "decrypts/libcdkapp/api-endpoints.txt")
    models, receives, requests = select_symbols(symbols)

    selected = models + receives + requests
    analysis: dict[str, dict[str, list[str]]] = {}
    by_addr = {s.addr: s for s in symbols}
    del by_addr
    for sym in selected:
        stop = next_addr(symbols, sym.addr)
        if stop - sym.addr > 0x5000:
            stop = sym.addr + 0x5000
        try:
            asm = disassemble(args.objdump, so, sym.addr, stop)
        except subprocess.CalledProcessError:
            continue
        analysis[sym.name] = analyze_function(asm, rodata, data, loads)

    lines: list[str] = []
    lines.append("# ACIES JSON Payload And Data-Class Inventory")
    lines.append("")
    lines.append("Date: 2026-04-29")
    lines.append("")
    lines.append("Static analysis sources:")
    lines.append("")
    lines.append("- `acies-apktool/lib/arm64-v8a/libcdkapp.so`")
    lines.append("- `decrypts/libcdkapp/symbols.demangled.txt`")
    lines.append("- `decrypts/libcdkapp/rodata-strings-with-offsets.txt`")
    lines.append("- `captures/acies_mock/*.body`")
    lines.append("")
    lines.append(
        "This document lists native classes and payload hints recoverable from "
        "symbols and string references. It is not a full server contract: field "
        "types and nested response objects still need deeper function-level "
        "decompilation or live archival responses."
    )
    lines.append("")
    lines.append("## JSON-Backed Data Classes")
    lines.append("")
    lines.append(f"Found `{len({m.name.split('::', 1)[0] for m in models})}` classes/factories that consume `CSJSONObject`:")
    lines.append("")
    for cls in sorted({m.name.split("::", 1)[0] for m in models}):
        class_syms = [m.name for m in models if m.name.startswith(cls + "::")]
        key_union: list[str] = []
        for name in class_syms:
            for key in analysis.get(name, {}).get("reads", []) + analysis.get(name, {}).get("contains", []):
                if key not in key_union:
                    key_union.append(key)
        lines.append(f"### `{cls}`")
        lines.append("")
        lines.append("Constructors/factories:")
        lines.extend(f"- `{s}`" for s in class_syms)
        lines.append("")
        lines.append("JSON keys referenced directly:")
        lines.append(md_list(key_union))
        lines.append("")

    lines.append("## Lobby Request Payload Hints")
    lines.append("")
    lines.append(
        "For request functions, `endpoint` comes from the `sendPacket` string, "
        "and `body keys` are direct `CSJSONWriter::write*` key strings."
    )
    lines.append("")
    lines.append("| Request function | Endpoint | Body keys |")
    lines.append("| --- | --- | --- |")
    for sym in sorted(requests, key=lambda s: s.name):
        a = analysis.get(sym.name, {})
        ep = ", ".join(f"`{e}`" for e in a.get("endpoints", []) if e in endpoints) or ""
        keys = ", ".join(f"`{k}`" for k in a.get("writes", [])) or ""
        lines.append(f"| `{sym.name}` | {ep} | {keys} |")
    lines.append("")

    lines.append("## Lobby Response Payload Hints")
    lines.append("")
    lines.append(
        "For receive functions, keys are direct `CSJSONObject::*ForKey` or "
        "`containsKey` string references in that handler. Many handlers delegate "
        "nested parsing to data classes listed above."
    )
    lines.append("")
    lines.append("| Receive function | Keys read/checked directly |")
    lines.append("| --- | --- |")
    for sym in sorted(receives, key=lambda s: s.name):
        a = analysis.get(sym.name, {})
        keys: list[str] = []
        for key in a.get("reads", []) + a.get("contains", []):
            if key not in keys:
                keys.append(key)
        lines.append(f"| `{sym.name}` | {', '.join(f'`{k}`' for k in keys)} |")
    lines.append("")

    lines.append("## Observed Startup Payloads")
    lines.append("")
    lines.append("Captured request bodies against the local mock backend:")
    lines.append("")
    lines.append("`POST /api/client/admission`")
    lines.append("")
    lines.append("```json")
    lines.append('{"secret":"<uuid>","version":"2.5.1.338","language":"en","region":"US","market":1}')
    lines.append("```")
    lines.append("")
    lines.append("Some admission requests also include a `signal` crash-report string.")
    lines.append("")
    lines.append("`POST /api/client/login`")
    lines.append("")
    lines.append("```json")
    lines.append('{"secret":"<uuid>","version":"2.5.1.338","assetVersion":0,"language":"en","region":"US","market":1}')
    lines.append("```")
    lines.append("")

    out = root / args.out
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
