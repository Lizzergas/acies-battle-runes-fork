#!/usr/bin/env python3
"""Generate a broad static extraction pack for ACIES libcdkapp.so."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Symbol:
    addr: int
    kind: str
    name: str


def load_symbols(path: Path) -> list[Symbol]:
    out: list[Symbol] = []
    for line in path.read_text(errors="ignore").splitlines():
        m = re.match(r"^([0-9a-f]+)\s+(\w)\s+(.+)$", line)
        if m:
            out.append(Symbol(int(m.group(1), 16), m.group(2), m.group(3)))
    return sorted(out, key=lambda s: s.addr)


def load_rodata(path: Path) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for line in path.read_text(errors="ignore").splitlines():
        parts = line.strip().split(" ", 1)
        if len(parts) == 2:
            try:
                out.append((int(parts[0], 16), parts[1]))
            except ValueError:
                pass
    return out


def next_addr(symbols: list[Symbol], addr: int) -> int:
    for sym in symbols:
        if sym.addr > addr:
            return sym.addr
    return addr + 0x1000


def disassemble(objdump: str, so: Path, sym: Symbol, symbols: list[Symbol], max_len: int = 0x6000) -> str:
    stop = min(next_addr(symbols, sym.addr), sym.addr + max_len)
    return subprocess.check_output(
        [
            objdump,
            "-d",
            "--demangle",
            f"--start-address=0x{sym.addr:x}",
            f"--stop-address=0x{stop:x}",
            str(so),
        ],
        text=True,
        errors="ignore",
    )


def parse_buffer_ops(asm: str) -> list[dict[str, object]]:
    ops: list[dict[str, object]] = []
    recent: list[str] = []
    for line in asm.splitlines():
        recent.append(line)
        recent = recent[-8:]
        m = re.search(r"<CSBuffer::(read|write)([A-Za-z0-9_]+)", line)
        if not m:
            continue
        imm = None
        for prev in reversed(recent[:-1]):
            mi = re.search(r"mov\s+w1,\s*#0x([0-9a-f]+)", prev)
            if mi:
                imm = int(mi.group(1), 16)
                break
            mi = re.search(r"mov\s+w1,\s*#(\d+)", prev)
            if mi:
                imm = int(mi.group(1))
                break
        ops.append({"op": m.group(1), "type": m.group(2), "imm_w1": imm})
    return ops


def classify_symbols(symbols: list[Symbol]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    prefixes = [
        "LobbyGateway::",
        "PVPGateway::",
        "PVPGatewayDelegate::",
        "LobbyGatewayDelegate::",
        "GameResultRecord::",
        "PVPAddress::",
        "Session::",
        "SessionInfo::",
        "Asset::",
        "CSAppSafer::",
        "CSBuffer::",
        "CSJSON",
        "Analysis::",
        "AttainData::",
    ]
    for sym in symbols:
        for prefix in prefixes:
            if sym.name.startswith(prefix):
                groups[prefix.rstrip(":")].append(sym.name)
                break
    return groups


def extract_enum_hints(symbols: list[Symbol]) -> Counter[str]:
    builtin = {
        "bool",
        "char",
        "int",
        "long",
        "unsigned",
        "void",
        "float",
        "double",
        "CSJSONObject",
        "CSBuffer",
        "CSString",
        "CSArray",
        "CSData",
        "AssetIndex2",
        "AssetIndex3",
        "AssetIndex4",
    }
    c: Counter[str] = Counter()
    for sym in symbols:
        if "::request" not in sym.name and "::receive" not in sym.name and "::writeTo" not in sym.name:
            continue
        args = sym.name.rsplit("(", 1)[-1].rsplit(")", 1)[0] if "(" in sym.name else ""
        for token in re.findall(r"\b[A-Z][A-Za-z0-9_:<>]*\b", args):
            base = token.split("::")[-1].split("<", 1)[0]
            if (
                base not in builtin
                and not base.endswith("Gateway")
                and not base.endswith("Delegate")
                and not base.startswith("CS")
                and not base.startswith("User")
            ):
                c[base] += 1
    return c


def md_table(rows: list[list[str]], headers: list[str]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out.extend("| " + " | ".join(r.replace("|", "\\|") for r in row) + " |" for row in rows)
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--objdump", default="/opt/homebrew/opt/binutils/bin/objdump")
    args = ap.parse_args()

    root = args.root
    so = root / "acies-apktool/lib/arm64-v8a/libcdkapp.so"
    outdir = root / "decrypts/libcdkapp/extracted"
    outdir.mkdir(parents=True, exist_ok=True)
    docs = root / "docs"
    docs.mkdir(exist_ok=True)

    symbols = load_symbols(root / "decrypts/libcdkapp/symbols.demangled.txt")
    rodata = load_rodata(root / "decrypts/libcdkapp/rodata-strings-with-offsets.txt")

    # PVP gateway inventory.
    pvp_syms = [s for s in symbols if s.name.startswith("PVPGateway::")]
    pvp_req = [s for s in pvp_syms if "::request" in s.name]
    pvp_recv = [s for s in pvp_syms if "::receive" in s.name]
    pvp_rows: list[list[str]] = []
    pvp_json: list[dict[str, object]] = []
    for sym in sorted(pvp_req + pvp_recv, key=lambda s: s.name):
        try:
            asm = disassemble(args.objdump, so, sym, symbols)
            ops = parse_buffer_ops(asm)
        except Exception:
            ops = []
        op_summary = ", ".join(
            f"{o['op']}{o['type']}" + (f"({o['imm_w1']})" if o["imm_w1"] is not None else "")
            for o in ops[:24]
        )
        pvp_rows.append([f"`{sym.name}`", f"`0x{sym.addr:x}`", op_summary])
        pvp_json.append({"address": f"0x{sym.addr:x}", "symbol": sym.name, "buffer_ops": ops})
    (outdir / "pvp-buffer-ops.json").write_text(json.dumps(pvp_json, indent=2), encoding="utf-8")
    (outdir / "pvp-gateway.md").write_text(
        "# ACIES PVP Gateway Static Inventory\n\n"
        f"PVPGateway symbols: `{len(pvp_syms)}`. Requests: `{len(pvp_req)}`. Receives: `{len(pvp_recv)}`.\n\n"
        "The buffer operation column is a heuristic disassembly pass over `CSBuffer::read*` and `write*` calls. "
        "Immediate values in parentheses are the latest nearby `w1` constant, useful for spotting packet opcodes and literal fields.\n\n"
        + md_table(pvp_rows, ["Symbol", "Address", "CSBuffer ops"])
        + "\n",
        encoding="utf-8",
    )

    # Symbol groups.
    groups = classify_symbols(symbols)
    group_lines: list[str] = ["# ACIES Native Symbol Groups\n"]
    for group, names in sorted(groups.items()):
        group_lines.append(f"## {group} ({len(names)})\n")
        group_lines.extend(f"- `{n}`" for n in sorted(set(names)))
        group_lines.append("")
    (outdir / "symbol-groups.md").write_text("\n".join(group_lines), encoding="utf-8")

    # Asset/file/path refs.
    asset_terms = []
    for off, s in rodata:
        if any(token in s for token in [".xmf", "%03d", "%ld", "images/", "maps/", "meshes/", "replays", "results/", "charges/"]):
            asset_terms.append((off, s))
    (outdir / "asset-file-refs.txt").write_text(
        "\n".join(f"{off:08x} {s}" for off, s in asset_terms) + "\n", encoding="utf-8"
    )

    # Security and anti-cheat refs.
    security_string_patterns = re.compile(
        r"appsafer|cheat|security|root|emulator|debug|signal|crash|encrypt|decrypt|session|secret|token|jwt|\\baes\\b|\\bsha1\\b|\\bsha256\\b|\\bhash\\b",
        re.I,
    )
    security_symbol_patterns = re.compile(
        r"CSAppSafer|Cheat|cheat|Session|Encrypt|Encryption|Decrypt|Decryption|Crypto|Crash|Crashlytics|Token|token|Secret|secret|Signal|signal|Emulator|emulator|Debug|debug|Hash|SHA|AES"
    )
    security_symbol_excludes = (
        "CSRootImage",
        "CSArray<CSRootImage",
        "SurfaceRenderer",
        "SurfaceSlice",
        "VisionRenderer",
        "WaterRenderer",
        "Terrain::drawWater",
        "CSGraphics",
        "CSImage",
        "CSSubImage",
        "CSScratch",
        "CSMeshNode",
        "CSRender",
        "CSCharacters::addRoot",
        "ucol_keyHashCode",
    )
    security_string_excludes = (
        "CSRootImage",
        "CSArrayI11CSRootImage",
        "CSArrayIP11CSRootImage",
        "Expect either an object or array at root",
        "Nothing should follow the root object or array.",
    )
    sec_strings = [
        (off, s)
        for off, s in rodata
        if security_string_patterns.search(s)
        and not any(excluded in s for excluded in security_string_excludes)
    ]
    sec_symbols = [
        s
        for s in symbols
        if security_symbol_patterns.search(s.name)
        and not any(excluded in s.name for excluded in security_symbol_excludes)
    ]
    (outdir / "security-anticheat.md").write_text(
        "# ACIES Security / Anti-Cheat Static References\n\n"
        "## Symbols\n\n"
        + "\n".join(f"- `0x{s.addr:x}` `{s.name}`" for s in sec_symbols)
        + "\n\n## Strings\n\n"
        + "\n".join(f"- `0x{off:x}` `{text}`" for off, text in sec_strings)
        + "\n",
        encoding="utf-8",
    )

    # Replay/match related inventory.
    replay_pat = re.compile(r"replay|Replay|MatchRecord|GameResultRecord|GameRecord|TVReplay|result", re.I)
    replay_symbols = [s for s in symbols if replay_pat.search(s.name)]
    replay_strings = [(off, s) for off, s in rodata if replay_pat.search(s)]
    (outdir / "replay-match.md").write_text(
        "# ACIES Replay / Match / Result Static Inventory\n\n"
        "## Symbols\n\n"
        + "\n".join(f"- `0x{s.addr:x}` `{s.name}`" for s in replay_symbols)
        + "\n\n## Strings\n\n"
        + "\n".join(f"- `0x{off:x}` `{text}`" for off, text in replay_strings)
        + "\n",
        encoding="utf-8",
    )

    # Enum/type hints.
    enum_counts = extract_enum_hints(symbols)
    (outdir / "enum-type-hints.txt").write_text(
        "\n".join(f"{count:4d} {name}" for name, count in enum_counts.most_common()) + "\n",
        encoding="utf-8",
    )

    # High-level summary doc.
    prefix_counts = Counter(sym.name.split("::", 1)[0] for sym in symbols if "::" in sym.name)
    top_prefixes = prefix_counts.most_common(60)
    summary = [
        "# ACIES libcdkapp.so Extraction Pack",
        "",
        "Date: 2026-04-29",
        "",
        "Generated from `acies-apktool/lib/arm64-v8a/libcdkapp.so` and the already-demangled symbol/string files.",
        "",
        "## Generated Artifacts",
        "",
        "- `docs/acies-api-endpoints.md`: HTTP endpoint inventory.",
        "- `docs/acies-json-payloads.md`: JSON data classes, request keys, response keys.",
        "- `decrypts/libcdkapp/extracted/pvp-gateway.md`: PVP binary gateway request/receive map.",
        "- `decrypts/libcdkapp/extracted/pvp-buffer-ops.json`: machine-readable PVP buffer op hints.",
        "- `decrypts/libcdkapp/extracted/symbol-groups.md`: grouped native symbols.",
        "- `decrypts/libcdkapp/extracted/asset-file-refs.txt`: asset/path/template strings.",
        "- `decrypts/libcdkapp/extracted/security-anticheat.md`: security, anti-cheat, token/session refs.",
        "- `decrypts/libcdkapp/extracted/replay-match.md`: replay, match, result refs.",
        "- `decrypts/libcdkapp/extracted/enum-type-hints.txt`: enum/type names inferred from signatures.",
        "",
        "## Counts",
        "",
        f"- Total demangled symbols: `{len(symbols)}`",
        f"- RODATA string entries: `{len(rodata)}`",
        f"- PVPGateway symbols: `{len(pvp_syms)}`",
        f"- PVPGateway request symbols: `{len(pvp_req)}`",
        f"- PVPGateway receive symbols: `{len(pvp_recv)}`",
        f"- Asset/path string refs: `{len(asset_terms)}`",
        f"- Security/anti-cheat symbols: `{len(sec_symbols)}`",
        f"- Security/anti-cheat strings: `{len(sec_strings)}`",
        f"- Replay/match symbols: `{len(replay_symbols)}`",
        "",
        "## Top Native Class/Namespace Prefixes",
        "",
        md_table([[f"`{name}`", str(count)] for name, count in top_prefixes], ["Prefix", "Symbol Count"]),
        "",
        "## Highest-Value Next Targets",
        "",
        "1. PVP packet opcode recovery from `PVPGateway::receivePacket()` and `PVPGateway::request*()`.",
        "2. Deep schema reconstruction for `Account`, `Deck`, `Card`, `Rune`, `Player`, `MatchRecord`, and `GameResultRecord`.",
        "3. Patch/version flow from `LobbyGateway::requestPatch`, `receivePatch`, and asset path templates.",
        "4. Security flow from `CSAppSafer`, `Session`, `cheat-log`, and crash `signal` payloads.",
        "",
    ]
    (docs / "acies-so-extraction.md").write_text("\n".join(summary), encoding="utf-8")

    print(docs / "acies-so-extraction.md")


if __name__ == "__main__":
    main()
