#!/usr/bin/env python3
from pathlib import Path
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("original", type=Path)
parser.add_argument("derived", type=Path)
args = parser.parse_args()
source = args.original.read_text()
start = "void fn0_500ee0(Arm64Ctx* c)"
before = '''  /* 501078: ldr x1, [x8, #8] */
  ARC_X_W(c, 1, arc_ld64((ARC_X_R(c, 8) + INT64_C(8))));
  /* 50107c: bl #0x868d80 */'''
replacement = '''  /* 501078: ldr x1, [x8, #8] */
  ARC_X_W(c, 1, acies_aot_community_gateway_secret(
    arc_image_bases[0], arc_ld64((ARC_X_R(c, 8) + INT64_C(8)))));
  /* 50107c: bl #0x868d80 */'''
if args.original.resolve() == args.derived.resolve():
    parser.error("Supply a separate output path.")
if source.count(before) != 1 or source.count(start) != 1:
    parser.error("Expected the ACIES 2.5.1 lifted gateway login routine.")
source = source.replace('#include "lifted.h"', '#include "lifted.h"\n#include "community-gateway-mode.h"', 1)
args.derived.write_text(source.replace(before, replacement, 1))
