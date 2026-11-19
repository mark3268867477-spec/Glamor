#!/usr/bin/env python3
"""
Backward-compatible CLI shim for pack_spk.py -> glam_sdk.pkg (.gla / .spk).
"""

import argparse
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from glam_sdk.pkg import (  # noqa: E402,F401
    HEADER_FMT,
    HEADER_SIZE,
    generate_c_header,
    pack_package,
    verify_package,
)


def pack_spk(manifest_path: str, elf_path: str, out_path: str, compat_swpk: bool = False) -> bytes:
    pack_package(manifest_path, elf_path, out_path, compat_swpk=compat_swpk)
    with open(out_path, "rb") as f:
        return f.read()


def verify_spk(spk_path: str) -> dict:
    return verify_package(spk_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="G'lam OS .gla/.spk package builder & verifier")
    parser.add_argument("--manifest", help="Path to manifest.json")
    parser.add_argument("--elf", help="Path to compiled app.elf")
    parser.add_argument("--out", help="Output .gla/.spk path")
    parser.add_argument("--verify", help="Verify an existing .gla/.spk file")
    parser.add_argument("--c-header", help="Generate C seed header from package files")
    parser.add_argument("--compat-swpk", action="store_true", help="Write legacy SWPK header instead of GLAM")
    parser.add_argument("spks", nargs="*", help="Input package files for --c-header")
    args = parser.parse_args()

    try:
        if args.verify:
            info = verify_package(args.verify)
            print(
                f"[OK] {args.verify}: magic={info['magic']} id={info['id']} name={info['name']} "
                f"ver={info['version']} elf={info['elf_size']}B total={info['total_size']}B "
                f"crc32=0x{info['crc32']:08X}"
            )
            return 0

        if args.c_header:
            if not args.spks:
                raise ValueError("--c-header requires at least one package file")
            generate_c_header(args.spks, args.c_header)
            print(f"[OK] Generated C seed header: {args.c_header} ({len(args.spks)} apps)")
            return 0

        if args.manifest and args.elf and args.out:
            compat = args.compat_swpk or args.out.lower().endswith(".spk")
            info = pack_package(args.manifest, args.elf, args.out, compat_swpk=compat)
            print(
                f"[OK] Packed {args.out} ({info['total_size']} bytes) | magic={info['magic']} "
                f"id={info['id']} elf={info['elf_size']}B crc32=0x{info['crc32']:08X}"
            )
            return 0

        parser.print_help()
        return 1
    except Exception as exc:
        print(f"[ERR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
