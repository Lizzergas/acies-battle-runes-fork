#!/usr/bin/env python3
"""Inspect or export a modified menu.xmf for the supported Acies Android build."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import struct
import subprocess

from xmf_probe import file_key, openssl_aes256_cbc_decrypt, strip_xor_check

ASSET_PATH = "data/menu.xmf"
ORIGINAL_SHA256 = "e18365269e5cc3bca0b7e5bc3036f0287c939d2601ad7389879d0058d21f1972"
CLAN_CREATE_GOLD_OFFSET = 0x16E600
CLAN_CREATE_GOLD_ORIGINAL = 30_000
CLAN_JOIN_SCORE_LIMIT_OFFSET = 0x16E608
CLAN_JOIN_SCORE_STEP_OFFSET = 0x16E60C
CLAN_MEMBER_LIMIT_OFFSET = 0x16E616


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset", type=Path, help="Original extracted assets/data/menu.xmf")
    parser.add_argument("--clan-create-gold", type=int, help="New clan creation price in gold")
    parser.add_argument("--output", type=Path, help="Path for a new patched asset")
    args = parser.parse_args()
    if (args.clan_create_gold is None) != (args.output is None):
        parser.error("--clan-create-gold and --output must be used together")
    if args.clan_create_gold is not None and not 0 <= args.clan_create_gold <= 999_999:
        parser.error("the clan creation price must be between 0 and 999999")

    source = args.asset.read_bytes()
    if hashlib.sha256(source).hexdigest() != ORIGINAL_SHA256:
        parser.exit(1, "Unsupported menu.xmf fingerprint. Use the original supported asset.\n")

    key = file_key(ASSET_PATH)
    decoded, valid, _, _ = strip_xor_check(openssl_aes256_cbc_decrypt(source, key))
    current_fee = struct.unpack_from("<i", decoded, CLAN_CREATE_GOLD_OFFSET)[0]
    if not valid or current_fee != CLAN_CREATE_GOLD_ORIGINAL:
        parser.exit(1, "The decoded menu checksum or original clan price did not match.\n")
    print(f"Clan creation price at decoded offset 0x{CLAN_CREATE_GOLD_OFFSET:x}: {current_fee} gold")
    join_limit, join_step = struct.unpack_from("<II", decoded, CLAN_JOIN_SCORE_LIMIT_OFFSET)
    print(f"Clan join-score limit at decoded offset 0x{CLAN_JOIN_SCORE_LIMIT_OFFSET:x}: {join_limit}")
    print(f"Clan join-score step at decoded offset 0x{CLAN_JOIN_SCORE_STEP_OFFSET:x}: {join_step}")
    member_limit = struct.unpack_from("<H", decoded, CLAN_MEMBER_LIMIT_OFFSET)[0]
    print(f"Clan member limit shown in the client at decoded offset 0x{CLAN_MEMBER_LIMIT_OFFSET:x}: {member_limit}")
    if args.output is None:
        return

    patched = bytearray(decoded)
    struct.pack_into("<i", patched, CLAN_CREATE_GOLD_OFFSET, args.clan_create_gold)
    _, _, checksum, _ = strip_xor_check(patched + bytes(4))
    patched.extend(struct.pack("<I", checksum))
    encrypted = subprocess.run(
        ["openssl", "enc", "-aes-256-cbc", "-K", key.hex(), "-iv", key[:16].hex()],
        input=patched, capture_output=True, check=True,
    ).stdout
    with args.output.open("xb") as output:
        output.write(encrypted)
    print(f"Exported {args.output} with a clan creation price of {args.clan_create_gold} gold")


if __name__ == "__main__":
    main()
