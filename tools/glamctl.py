#!/usr/bin/env python3
"""
G'lam OS Developer CLI (glamctl)
Commands:
  init       Create a starter G'lam OS dynamic .elf app project
  build      Compile .c sources in a project directory into app.elf + run ABI check
  check      Run PC-side Xtensa ELF32 ABI whitelist & memory layout preflight check
  pack       Pack project (or manifest + elf) into a .gla (or compat .spk) package
  verify     Verify package CRC32, manifest, and embedded ELF integrity
  build-all  Compile and pack all apps under app_sdk_template/apps into dist/
  install    Safely install .gla/.spk to TF card via --wifi, --port, or --sdcard
  devices    List detected serial ports and removable TF drives
  info       Query G'lam OS device info over Wi-Fi (/api/info)
  apps       List installed apps on device over Wi-Fi (/api/apps)
  uninstall  Uninstall an app on device over Wi-Fi (/api/uninstall)
  screenshot Capture 320x240 device screen BMP over Wi-Fi (/api/screenshot)
  gui        Launch G'lamor Desktop Controller GUI
"""

from __future__ import annotations

import argparse
import json
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from glam_sdk import PKG_EXT, STUDIO_NAME, STUDIO_VERSION  # noqa: E402
from glam_sdk.elf_check import ElfCheckReport, check_elf_file  # noqa: E402
from glam_sdk.pkg import VALID_CATEGORIES, pack_package, verify_package  # noqa: E402
from glam_sdk.serial_port import list_serial_ports  # noqa: E402
from glam_sdk.toolchain import build_project, find_xtensa_gcc, init_project, locate_sdk_root  # noqa: E402
from glam_sdk.transport import (  # noqa: E402
    install_via_sdcard,
    install_via_serial,
    install_via_wifi,
    list_removable_drives,
    wifi_capture_screenshot,
    wifi_get_info,
    wifi_list_apps,
    wifi_uninstall_app,
)


def _print_elf_report(report: ElfCheckReport, path: str) -> None:
    status = "PASS (通过)" if report.ok else "FAIL (未通过)"
    print(f"[ELF CHECK] {path} -> {status}")
    print(
        f"  大小: {report.elf_size} B | PSRAM 占用: {report.psram_footprint} B | "
        f"入口: 0x{report.e_entry:x} ({report.entry_symbol or '未知'}) | RELA节: {report.rela_sections}"
    )
    if report.used_os_symbols:
        print(f"  白名单外部符号 ({len(report.used_os_symbols)}): {', '.join(report.used_os_symbols)}")
    else:
        print("  白名单外部符号: (纯 os->* ABI 调用)")
    if report.warnings:
        for w in report.warnings:
            print(f"  [WARN] {w}")
    if report.errors:
        for err in report.errors:
            print(f"  [ERR]  {err}")


def cmd_init(args: argparse.Namespace) -> int:
    out_dir = init_project(
        target_dir=args.dir,
        app_id=args.id,
        app_name=args.name or args.id,
        category=args.category,
        bg_policy=args.bg_policy,
        author=args.author,
        accent=args.accent,
        description=args.desc,
    )
    print(f"[INIT OK] 已创建 G'lam OS 应用工程: {out_dir}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    elf_path, report = build_project(
        args.project,
        gcc_path=args.gcc,
        out_elf=args.out,
        log_cb=print,
    )
    _print_elf_report(report, elf_path)
    return 0 if report.ok else 1


def cmd_check(args: argparse.Namespace) -> int:
    report = check_elf_file(args.elf)
    _print_elf_report(report, args.elf)
    return 0 if report.ok else 1


def cmd_pack(args: argparse.Namespace) -> int:
    target = os.path.abspath(args.target)
    if os.path.isdir(target):
        manifest_path = os.path.join(target, "manifest.json")
        if not os.path.isfile(manifest_path):
            raise FileNotFoundError(f"目录中缺少 manifest.json: {target}")
        if args.build:
            elf_path, report = build_project(target, gcc_path=args.gcc, log_cb=print)
            if not report.ok and not args.no_check:
                _print_elf_report(report, elf_path)
                return 1
        else:
            elf_path = os.path.abspath(args.elf) if args.elf else os.path.join(target, "app.elf")
    else:
        manifest_path = target
        if not args.elf:
            raise ValueError("当第一个参数为 manifest.json 时必须指定 --elf <app.elf>")
        elf_path = os.path.abspath(args.elf)

    with open(manifest_path, "r", encoding="utf-8") as mf:
        mdata = json.load(mf)
    app_id = str(mdata.get("id", "app")).strip() or "app"

    if args.out:
        out_path = os.path.abspath(args.out)
    else:
        ext = ".spk" if args.compat_swpk else PKG_EXT
        parent_dir = os.path.dirname(manifest_path)
        out_path = os.path.join(parent_dir, f"{app_id}{ext}")

    info = pack_package(
        manifest_path,
        elf_path,
        out_path,
        icon_path=args.icon,
        compat_swpk=args.compat_swpk,
        run_elf_check=not args.no_check,
    )
    print(
        f"[PACK OK] {info['path']} ({info['total_size']} B) | "
        f"magic={info['magic']} id={info['id']} ver={info['version']} "
        f"elf={info['elf_size']} B crc32=0x{info['crc32']:08X}"
    )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    info = verify_package(args.pkg, run_elf_check=not args.no_check)
    print(
        f"[VERIFY OK] {args.pkg}: magic={info['magic']} id={info['id']} name={info['name']} "
        f"ver={info['version']} elf={info['elf_size']} B total={info['total_size']} B "
        f"crc32=0x{info['crc32']:08X} icon={'有(40x40 JPG)' if info['has_icon'] else '无'}"
    )
    if info.get("elf_report"):
        _print_elf_report(info["elf_report"], f"{args.pkg}:app.elf")
    return 0


def cmd_build_all(args: argparse.Namespace) -> int:
    sdk_root = locate_sdk_root()
    apps_dir = os.path.abspath(args.apps_dir) if args.apps_dir else os.path.join(sdk_root, "apps")
    dist_dir = os.path.abspath(args.dist) if args.dist else os.path.join(sdk_root, "dist")
    os.makedirs(dist_dir, exist_ok=True)

    gcc = find_xtensa_gcc(args.gcc)
    if not gcc:
        raise FileNotFoundError("未找到 xtensa-esp32s3-elf-gcc 编译器")

    app_dirs = []
    for entry in sorted(os.listdir(apps_dir)):
        full = os.path.join(apps_dir, entry)
        if os.path.isdir(full) and os.path.isfile(os.path.join(full, "manifest.json")):
            app_dirs.append(full)

    if not app_dirs:
        print(f"[WARN] 未在 {apps_dir} 找到包含 manifest.json 的应用目录")
        return 0

    ext = ".spk" if args.compat_swpk else PKG_EXT
    built = 0
    for app_dir in app_dirs:
        with open(os.path.join(app_dir, "manifest.json"), "r", encoding="utf-8") as f:
            mobj = json.load(f)
        app_id = str(mobj.get("id", os.path.basename(app_dir))).strip()
        elf_path, report = build_project(app_dir, gcc_path=gcc, log_cb=print)
        if not report.ok:
            _print_elf_report(report, elf_path)
            return 1
        out_pkg = os.path.join(dist_dir, f"{app_id}{ext}")
        info = pack_package(
            os.path.join(app_dir, "manifest.json"),
            elf_path,
            out_pkg,
            compat_swpk=args.compat_swpk,
            run_elf_check=True,
        )
        print(
            f"[PACK OK] {os.path.basename(out_pkg)} ({info['total_size']} B) | "
            f"crc32=0x{info['crc32']:08X}"
        )
        built += 1

    print(f"[DONE] 成功编译并打包 {built} 个 G'lam OS 应用至 {dist_dir}")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    if args.wifi:
        install_via_wifi(args.wifi, args.pkg, log_cb=print)
    elif args.port:
        def _prog(cur: int, total: int) -> None:
            pct = int(cur * 100 / total) if total else 100
            print(f"  [SERIAL] 已发送 {cur}/{total} B ({pct}%)", end="\r")

        install_via_serial(
            args.port,
            args.pkg,
            baud=args.baud,
            force_legacy_proto=args.legacy_proto,
            progress_cb=_prog,
            log_cb=print,
        )
        print()
    elif args.sdcard:
        install_via_sdcard(args.sdcard, args.pkg, log_cb=print)
    return 0


def cmd_devices(_args: argparse.Namespace) -> int:
    gcc = find_xtensa_gcc()
    print(f"GCC 编译器: {gcc or '未检测到'}")
    ports = list_serial_ports()
    print(f"可用串口 ({len(ports)}):")
    for p in ports:
        print(f"  - {p['device']}: {p['description']}")
    drives = list_removable_drives()
    print(f"可移动 TF 盘符 ({len(drives)}): {', '.join(drives) if drives else '无'}")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    info = wifi_get_info(args.wifi)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def cmd_apps(args: argparse.Namespace) -> int:
    apps = wifi_list_apps(args.wifi)
    print(json.dumps(apps, ensure_ascii=False, indent=2))
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    res = wifi_uninstall_app(args.wifi, args.app_id)
    print(json.dumps(res, ensure_ascii=False))
    return 0


def cmd_screenshot(args: argparse.Namespace) -> int:
    bmp = wifi_capture_screenshot(args.wifi)
    out = os.path.abspath(args.out)
    with open(out, "wb") as f:
        f.write(bmp)
    print(f"[SCREENSHOT OK] 已保存截图 {out} ({len(bmp)} B)")
    return 0


def cmd_gui(_args: argparse.Namespace) -> int:
    import glam_studio

    return glam_studio.main()


def cmd_pc_agent(args: argparse.Namespace) -> int:
    import time as _time
    from glam_sdk.pc_agent import ExternalMcpManager, GlamorPcBridge, PcToolExecutor

    def _log(msg: str, _tag: str = "") -> None:
        print(msg, flush=True)

    ext_mcp = ExternalMcpManager(log_cb=_log)
    if args.mcp_config and os.path.isfile(args.mcp_config):
        with open(args.mcp_config, "r", encoding="utf-8") as f:
            ext_mcp.reload_from_json(f.read())

    executor = PcToolExecutor(ext_mcp=ext_mcp, log_cb=_log)
    bridge = GlamorPcBridge(executor=executor, on_log=_log)
    bridge.start(mode=args.mode, port=args.port or "", baud=args.baud, wifi_ip=args.wifi or "")
    try:
        while True:
            _time.sleep(1.0)
    except KeyboardInterrupt:
        bridge.stop()
        ext_mcp.stop_all()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="glamctl",
        description=f"{STUDIO_NAME} v{STUDIO_VERSION} — G'lam OS 第三方应用构建、ELF 体检、.gla 打包与装机工具",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="创建新 G'lam OS 应用工程模板")
    p_init.add_argument("dir", help="目标项目目录")
    p_init.add_argument("--id", required=True, help="应用 ID，例如 com.dev.myapp")
    p_init.add_argument("--name", default="", help="桌面显示名称")
    p_init.add_argument("--category", default="tool", choices=VALID_CATEGORIES)
    p_init.add_argument("--bg-policy", default=None, help="kill_all / partial_service / keep_all")
    p_init.add_argument("--author", default="Developer")
    p_init.add_argument("--accent", default="#0EA5E9")
    p_init.add_argument("--desc", default="")
    p_init.set_defaults(func=cmd_init)

    p_build = sub.add_parser("build", help="编译项目中的所有 .c 文件为 app.elf 并执行 ABI 预检")
    p_build.add_argument("project", help="应用工程目录")
    p_build.add_argument("--out", help="输出 app.elf 路径")
    p_build.add_argument("--gcc", help="指定 xtensa-esp32s3-elf-gcc 路径")
    p_build.set_defaults(func=cmd_build)

    p_check = sub.add_parser("check", help="对 app.elf 执行 PC 端 ABI 符号白名单与重定位预检")
    p_check.add_argument("elf", help="待检测 app.elf 路径")
    p_check.set_defaults(func=cmd_check)

    p_pack = sub.add_parser("pack", help="将应用工程或 manifest+elf 打包为 .gla 安装包")
    p_pack.add_argument("target", help="应用工程目录 或 manifest.json 路径")
    p_pack.add_argument("--elf", help="指定 app.elf 路径")
    p_pack.add_argument("--icon", help="指定图标路径 (PNG/JPG/BMP)")
    p_pack.add_argument("--out", help="输出 .gla 路径")
    p_pack.add_argument("--build", action="store_true", help="打包前先编译源码")
    p_pack.add_argument("--gcc", help="配合 --build 使用，指定 GCC 路径")
    p_pack.add_argument("--compat-swpk", action="store_true", help="生成兼容旧系统固件的 SWPK 包头")
    p_pack.add_argument("--no-check", action="store_true", help="跳过 ELF ABI 预检")
    p_pack.set_defaults(func=cmd_pack)

    p_verify = sub.add_parser("verify", help="校验 .gla/.spk 安装包完整性与内部 ELF")
    p_verify.add_argument("pkg", help=".gla 或 .spk 安装包路径")
    p_verify.add_argument("--no-check", action="store_true", help="跳过内部 ELF ABI 预检")
    p_verify.set_defaults(func=cmd_verify)

    p_all = sub.add_parser("build-all", help="批量编译打包目录下所有应用为 .gla")
    p_all.add_argument("apps_dir", nargs="?", default="", help="应用集合目录（默认 app_sdk_template/apps）")
    p_all.add_argument("--dist", default="", help="输出目录（默认 app_sdk_template/dist）")
    p_all.add_argument("--gcc", help="指定 xtensa-esp32s3-elf-gcc 路径")
    p_all.add_argument("--compat-swpk", action="store_true", help="使用 SWPK 包头")
    p_all.set_defaults(func=cmd_build_all)

    p_inst = sub.add_parser("install", help="安全安装 .gla/.spk 至设备 TF 卡（绝不刷 Flash）")
    p_inst.add_argument("pkg", help=".gla 或 .spk 安装包路径")
    mode = p_inst.add_mutually_exclusive_group(required=True)
    mode.add_argument("--wifi", help="设备局域网 IP")
    mode.add_argument("--port", help="USB 串口号，例如 COM7")
    mode.add_argument("--sdcard", help="TF 卡盘符/路径，例如 E:\\")
    p_inst.add_argument("--baud", type=int, default=115200, help="串口波特率 (默认 115200)")
    p_inst.add_argument("--legacy-proto", action="store_true", help="强制使用旧版 spk_* 串口协议")
    p_inst.set_defaults(func=cmd_install)

    p_dev = sub.add_parser("devices", help="查看本机检测到的串口、TF 卡盘符与编译器")
    p_dev.set_defaults(func=cmd_devices)

    p_info = sub.add_parser("info", help="通过 Wi-Fi 查询设备运行信息")
    p_info.add_argument("--wifi", required=True, help="设备局域网 IP")
    p_info.set_defaults(func=cmd_info)

    p_apps = sub.add_parser("apps", help="通过 Wi-Fi 列出设备已安装应用")
    p_apps.add_argument("--wifi", required=True, help="设备局域网 IP")
    p_apps.set_defaults(func=cmd_apps)

    p_uninst = sub.add_parser("uninstall", help="通过 Wi-Fi 卸载设备上的应用")
    p_uninst.add_argument("--wifi", required=True, help="设备局域网 IP")
    p_uninst.add_argument("app_id", help="要卸载的 app_id")
    p_uninst.set_defaults(func=cmd_uninstall)

    p_shot = sub.add_parser("screenshot", help="通过 Wi-Fi 抓取设备当前屏幕截图 (BMP)")
    p_shot.add_argument("--wifi", required=True, help="设备局域网 IP")
    p_shot.add_argument("--out", default="glam_screen.bmp", help="输出 BMP 路径")
    p_shot.set_defaults(func=cmd_screenshot)

    p_gui = sub.add_parser("gui", help="启动 G'lamor 桌面可视化控制器")
    p_gui.set_defaults(func=cmd_gui)

    p_pca = sub.add_parser("pc-agent", help="启动小智 Windows PC 控制桥接守护进程 (USB 串口 + Wi-Fi 双通道)")
    p_pca.add_argument("--mode", default="auto", choices=["auto", "serial", "wifi"], help="桥接通道模式")
    p_pca.add_argument("--port", default="", help="USB 串口号，例如 COM7 (默认自动探测)")
    p_pca.add_argument("--baud", type=int, default=115200, help="串口波特率 (默认 115200)")
    p_pca.add_argument("--wifi", default="", help="设备局域网 IP")
    p_pca.add_argument("--mcp-config", default="", help="外部 mcpServers JSON 配置文件路径")
    p_pca.set_defaults(func=cmd_pc_agent)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"[ERR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
