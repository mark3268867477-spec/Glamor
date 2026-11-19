#!/usr/bin/env python3
"""
Backward-compatible CLI shim for swift_install.py -> glam_sdk.transport.
"""

import argparse
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from glam_sdk.transport import install_via_sdcard, install_via_serial, install_via_wifi  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="G'lam OS Dual-Channel App Installer")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--sdcard", help="Channel 1: Mount path of TF card (e.g. E:\\)")
    mode.add_argument("--wifi", help="Channel 2A: ESP32 IP address for Wi-Fi HTTP upload")
    mode.add_argument("--port", help="Channel 2B: Serial port (e.g. COM7)")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate (default 115200)")
    parser.add_argument("spk", help="Path to .gla or .spk package")
    args = parser.parse_args()

    try:
        if args.sdcard:
            install_via_sdcard(args.sdcard, args.spk, log_cb=print)
        elif args.wifi:
            install_via_wifi(args.wifi, args.spk, log_cb=print)
        elif args.port:
            def _prog(cur: int, total: int) -> None:
                pct = int(cur * 100 / total) if total else 100
                print(f"  [SERIAL] Sent {cur}/{total} bytes ({pct}%)", end="\r")

            install_via_serial(args.port, args.spk, baud=args.baud, progress_cb=_prog, log_cb=print)
            print()
        return 0
    except Exception as exc:
        print(f"[INSTALL FAILED] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
