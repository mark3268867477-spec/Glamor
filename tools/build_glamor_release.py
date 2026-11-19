#!/usr/bin/env python3
"""
Offline Zero-Environment Portable Release Builder for G'lamor (Win64).

Builds:
  SWIFT OS/release/Glamor_Portable/
    - G'lamor.exe          (Native Win64 GUI launcher, -mwindows, embedded glamor.ico)
    - glamctl.exe          (Native Win64 CLI launcher, console UTF-8, embedded glamor.ico)
    - runtime/             (Slim Python 3.13 + Tcl/Tk + Pillow)
    - app/                 (glam_studio.py, glamctl.py, glam_sdk/, glamor.ico)
    - sdk/                 (glam_os_api.h, glam_app.ld, sample apps, dist/*.gla)
    - toolchain/           (Slim ESP32-S3 Xtensa C compiler)
    - README_使用说明.txt
  SWIFT OS/release/Glamor_v1.0.0_Win64_Portable.zip
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(TOOLS_DIR, ".."))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from glam_sdk import STUDIO_VERSION  # noqa: E402

RELEASE_DIR = os.path.join(REPO_ROOT, "release")
PORTABLE_DIR = os.path.join(RELEASE_DIR, "Glamor_Portable")
ZIP_PATH = os.path.join(RELEASE_DIR, f"Glamor_v{STUDIO_VERSION}_Win64_Portable.zip")

ESSENTIAL_DLLS_FILES = [
    "_tkinter.pyd",
    "tcl86t.dll",
    "tk86t.dll",
    "zlib1.dll",
    "_ctypes.pyd",
    "libffi-8.dll",
    "_socket.pyd",
    "select.pyd",
    "_queue.pyd",
    "_hashlib.pyd",
    "_ssl.pyd",
    "libssl-3.dll",
    "libcrypto-3.dll",
    "unicodedata.pyd",
    "pyexpat.pyd",
    "_bz2.pyd",
    "_lzma.pyd",
    "_decimal.pyd",
    "_overlapped.pyd",
    "_asyncio.pyd",
    "_elementtree.pyd",
    "_uuid.pyd",
    "_zoneinfo.pyd",
]

EXCLUDED_STDLIB_DIRS = {
    "test",
    "tests",
    "idlelib",
    "ensurepip",
    "turtledemo",
    "venv",
    "pydoc_data",
    "site-packages",
    "__pycache__",
}

LAUNCHER_C_SOURCE = r"""
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>

typedef int (*Py_Main_fn)(int argc, wchar_t **argv);

static void set_both_env(const wchar_t *name, const wchar_t *val) {
    SetEnvironmentVariableW(name, val);
    _wputenv_s(name, val);
}

static void show_error(const wchar_t *msg) {
#if GLAMOR_GUI
    MessageBoxW(NULL, msg, L"G'lamor 启动失败", MB_ICONERROR | MB_OK);
#else
    fwprintf(stderr, L"[G'lamor ERR] %ls\n", msg);
#endif
}

static void join_path(wchar_t *out, size_t cap, const wchar_t *a, const wchar_t *b) {
    _snwprintf(out, cap, L"%ls\\%ls", a, b);
    out[cap - 1] = L'\0';
}

static void prepend_path_env(const wchar_t *p1, const wchar_t *p2) {
    DWORD old_len = GetEnvironmentVariableW(L"PATH", NULL, 0);
    size_t extra = wcslen(p1) + wcslen(p2) + 8;
    size_t total = (size_t)old_len + extra;
    wchar_t *buf = (wchar_t *)calloc(total + 1, sizeof(wchar_t));
    if (!buf) return;
    _snwprintf(buf, total, L"%ls;%ls;", p1, p2);
    if (old_len > 0) {
        size_t cur = wcslen(buf);
        GetEnvironmentVariableW(L"PATH", buf + cur, old_len + 1);
    }
    set_both_env(L"PATH", buf);
    free(buf);
}

static int run_glamor(int user_argc, wchar_t **user_argv) {
    wchar_t exe_path[4096];
    DWORD n = GetModuleFileNameW(NULL, exe_path, 4096);
    if (n == 0 || n >= 4096) {
        show_error(L"无法获取可执行文件路径");
        return 1;
    }

    wchar_t exe_dir[4096];
    wcsncpy(exe_dir, exe_path, 4095);
    exe_dir[4095] = L'\0';
    wchar_t *slash = wcsrchr(exe_dir, L'\\');
    if (!slash) slash = wcsrchr(exe_dir, L'/');
    if (slash) *slash = L'\0';

    wchar_t runtime_dir[4096], dlls_dir[4096], app_dir[4096];
    wchar_t tcl_dir[4096], tk_dir[4096], py_dll[4096], script_path[4096];

    join_path(runtime_dir, 4096, exe_dir, L"runtime");
    join_path(dlls_dir, 4096, runtime_dir, L"DLLs");
    join_path(app_dir, 4096, exe_dir, L"app");
    join_path(tcl_dir, 4096, runtime_dir, L"tcl\\tcl8.6");
    join_path(tk_dir, 4096, runtime_dir, L"tcl\\tk8.6");
    join_path(py_dll, 4096, runtime_dir, L"python313.dll");
#if GLAMOR_GUI
    join_path(script_path, 4096, app_dir, L"glam_studio.py");
#else
    join_path(script_path, 4096, app_dir, L"glamctl.py");
#endif

    set_both_env(L"GLAMOR_PORTABLE_ROOT", exe_dir);
    set_both_env(L"PYTHONHOME", runtime_dir);
    set_both_env(L"PYTHONPATH", app_dir);
    set_both_env(L"TCL_LIBRARY", tcl_dir);
    set_both_env(L"TK_LIBRARY", tk_dir);
    set_both_env(L"PYTHONUTF8", L"1");
    set_both_env(L"PYTHONDONTWRITEBYTECODE", L"1");
    set_both_env(L"PYTHONNOUSERSITE", L"1");
    prepend_path_env(runtime_dir, dlls_dir);
    SetDllDirectoryW(runtime_dir);

    HMODULE hPy = LoadLibraryW(py_dll);
    if (!hPy) {
        DWORD err = GetLastError();
        wchar_t msg[1024];
        _snwprintf(msg, 1024, L"无法加载内置 Python 运行库:\n%ls\n错误码: %lu", py_dll, (unsigned long)err);
        show_error(msg);
        return 1;
    }

    Py_Main_fn py_main = (Py_Main_fn)(void *)GetProcAddress(hPy, "Py_Main");
    if (!py_main) {
        show_error(L"python313.dll 中未找到 Py_Main 入口");
        FreeLibrary(hPy);
        return 1;
    }

    int extra_args = (user_argc > 1) ? (user_argc - 1) : 0;
    int new_argc = 4 + extra_args;
    wchar_t **new_argv = (wchar_t **)calloc((size_t)new_argc + 1, sizeof(wchar_t *));
    if (!new_argv) {
        FreeLibrary(hPy);
        return 1;
    }

    new_argv[0] = exe_path;
    new_argv[1] = L"-s";
    new_argv[2] = L"-B";
    new_argv[3] = script_path;
    for (int i = 0; i < extra_args; i++) {
        new_argv[4 + i] = user_argv[1 + i];
    }

    int rc = py_main(new_argc, new_argv);
    free(new_argv);
    FreeLibrary(hPy);
    return rc;
}

#if GLAMOR_GUI
int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, LPWSTR lpCmdLine, int nCmdShow) {
    (void)hInst;
    (void)hPrev;
    (void)lpCmdLine;
    (void)nCmdShow;
    int argc = 0;
    wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    int rc = run_glamor(argc, argv);
    if (argv) LocalFree(argv);
    return rc;
}
#else
int wmain(int argc, wchar_t **argv) {
    SetConsoleOutputCP(CP_UTF8);
    SetConsoleCP(CP_UTF8);
    return run_glamor(argc, argv);
}
#endif
"""

README_TEXT = f"""====================================================================
  G'lamor v{STUDIO_VERSION} — G'lam OS 官方零环境开发控制器 (.gla)
====================================================================

本便携包已内置完整运行环境（Python 3.13 + Tcl/Tk + Pillow + ESP32-S3 Xtensa C 编译器），
第三方开发者**无需安装 Python，也无需安装 ESP-IDF**，解压到任意目录即可直接开发、打包与装机！

一、快速开始（图形界面）
  1. 双击本目录下的 `G'lamor.exe` 打开可视化控制器。
  2. 点击顶部【新建应用】创建工程模板，或点击【打开工程】选择自己写好 .c 源码的目录。
     （内置 `sdk/apps/` 目录已自带音乐、极速赛车、内存检测 3 个官方源码示例）
  3. 用你喜欢的任意编辑器（VS Code / CLion / Sublime 等）编写或修改 .c 文件：
     - 引入 `#include "glam_os_api.h"`
     - 导出入口 `const glam_app_desc_t *glam_app_entry(void)`
     - 界面、内存、音频、存档均通过 `os->xxx(...)` 接口调用
  4. 回到 G'lamor，点击【一键编译 · 体检 · 打包 (.gla)】即可自动完成：
     - 多文件 Xtensa ESP32-S3 交叉编译（自动注入 `-mlongcalls`、`-Wl,-q` 与 `glam_app.ld`）
     - PC 端 17 项 ABI 符号白名单安全预检（提前拦截 `printf`/`malloc` 等非法调用）
     - 40x40 图标自动压缩与 `.gla`（GLAM 包头 + CRC32）打包
  5. 切到【2. 安装到设备】，通过 Wi-Fi 无线 / USB 数据线 / TF 卡三种渠道安全安装（绝不覆盖 Flash OS）。
  6. 切到【3. 设备管理 & 实时投屏】，可查看已安装列表、远程卸载并实时抓取 320x240 真机画面。

二、命令行开发（CI / Makefile 集成）
  在终端直接运行本目录下的 `glamctl.exe`：
    glamctl.exe devices
    glamctl.exe init my_app --id com.dev.demo --name "示例工具"
    glamctl.exe pack my_app --build --out my_app.gla
    glamctl.exe verify my_app.gla
    glamctl.exe install my_app.gla --wifi 192.168.1.50
    glamctl.exe install my_app.gla --port COM7
    glamctl.exe install my_app.gla --sdcard E:\\

三、目录说明
  - G'lamor.exe  : 桌面可视化控制器主程序
  - glamctl.exe  : 命令行工具
  - sdk/         : G'lam OS ABI 头文件 (glam_os_api.h)、链接脚本 (glam_app.ld) 与示例应用
  - toolchain/   : 精简版 ESP32-S3 Xtensa C 交叉编译器（开箱即用）
  - runtime/     : 内置精简 Python 运行环境（请勿删除）
  - app/         : 控制器核心逻辑（请勿删除）
"""


def find_source_xtensa_root() -> str:
    patterns = [
        r"C:\Espressif\tools\xtensa-esp-elf\*\xtensa-esp-elf",
        os.path.join(os.path.expanduser("~"), ".espressif", "tools", "xtensa-esp-elf", "*", "xtensa-esp-elf"),
        r"D:\Espressif\tools\xtensa-esp-elf\*\xtensa-esp-elf",
    ]
    for pat in patterns:
        for cand in sorted(glob.glob(pat), reverse=True):
            if os.path.isfile(os.path.join(cand, "bin", "xtensa-esp32s3-elf-gcc.exe")):
                return cand
    raise FileNotFoundError("未找到本机 Espressif xtensa-esp-elf 工具链目录")


def dir_size_bytes(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for fn in files:
            total += os.path.getsize(os.path.join(root, fn))
    return total


def copy_file_if_exists(src: str, dst: str) -> bool:
    if os.path.isfile(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        return True
    return False


def copy_slim_python_runtime(dst_runtime: str) -> None:
    py_root = os.path.abspath(sys.base_prefix)
    print(f"[1/6] 打包精简 Python 3.13 运行时 <- {py_root}")
    os.makedirs(dst_runtime, exist_ok=True)

    for fn in ("python313.dll", "python3.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
        if not copy_file_if_exists(os.path.join(py_root, fn), os.path.join(dst_runtime, fn)):
            if fn == "python313.dll":
                raise FileNotFoundError(f"缺少核心运行库: {os.path.join(py_root, fn)}")

    src_dlls = os.path.join(py_root, "DLLs")
    dst_dlls = os.path.join(dst_runtime, "DLLs")
    os.makedirs(dst_dlls, exist_ok=True)
    for fn in ESSENTIAL_DLLS_FILES:
        copy_file_if_exists(os.path.join(src_dlls, fn), os.path.join(dst_dlls, fn))

    src_tcl = os.path.join(py_root, "tcl")
    dst_tcl = os.path.join(dst_runtime, "tcl")
    for sub in ("tcl8.6", "tk8.6", "tcl8"):
        s = os.path.join(src_tcl, sub)
        if os.path.isdir(s):
            shutil.copytree(
                s,
                os.path.join(dst_tcl, sub),
                ignore=shutil.ignore_patterns("demos", "images", "msgs", "tzdata"),
            )

    src_lib = os.path.join(py_root, "Lib")
    dst_lib = os.path.join(dst_runtime, "Lib")
    os.makedirs(dst_lib, exist_ok=True)
    for entry in os.listdir(src_lib):
        if entry in EXCLUDED_STDLIB_DIRS or entry.endswith(".pyc"):
            continue
        s = os.path.join(src_lib, entry)
        d = os.path.join(dst_lib, entry)
        if os.path.isdir(s):
            shutil.copytree(
                s,
                d,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "test", "tests"),
            )
        else:
            shutil.copy2(s, d)

    src_pil = os.path.join(src_lib, "site-packages", "PIL")
    if os.path.isdir(src_pil):
        dst_pil = os.path.join(dst_lib, "site-packages", "PIL")
        shutil.copytree(src_pil, dst_pil, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        print("  [WARN] 未检测到 PIL (Pillow)，图标压缩和投屏预览功能将受限")

    print(f"      runtime/ 体积: {dir_size_bytes(dst_runtime) / (1024 * 1024):.1f} MB")


def copy_slim_xtensa_toolchain(dst_tc: str) -> None:
    src_tc = find_source_xtensa_root()
    print(f"[2/6] 打包精简 ESP32-S3 Xtensa C 编译器 <- {src_tc}")

    gcc_ver_base = os.path.join(src_tc, "lib", "gcc", "xtensa-esp-elf")
    versions = sorted(d for d in os.listdir(gcc_ver_base) if os.path.isdir(os.path.join(gcc_ver_base, d)))
    if not versions:
        raise FileNotFoundError(f"未找到 GCC 版本目录: {gcc_ver_base}")
    gcc_ver = versions[-1]

    src_bin = os.path.join(src_tc, "bin")
    dst_bin = os.path.join(dst_tc, "bin")
    os.makedirs(dst_bin, exist_ok=True)
    for fn in ("xtensa-esp32s3-elf-gcc.exe", "xtensa-esp-elf-gcc.exe"):
        if not copy_file_if_exists(os.path.join(src_bin, fn), os.path.join(dst_bin, fn)):
            raise FileNotFoundError(f"缺少编译器文件: {fn}")
    for dll in glob.glob(os.path.join(src_bin, "*.dll")):
        shutil.copy2(dll, os.path.join(dst_bin, os.path.basename(dll)))

    src_libexec = os.path.join(src_tc, "libexec", "gcc", "xtensa-esp-elf", gcc_ver)
    dst_libexec = os.path.join(dst_tc, "libexec", "gcc", "xtensa-esp-elf", gcc_ver)
    os.makedirs(dst_libexec, exist_ok=True)
    for fn in ("cc1.exe", "collect2.exe", "liblto_plugin.dll", "lto-wrapper.exe"):
        copy_file_if_exists(os.path.join(src_libexec, fn), os.path.join(dst_libexec, fn))
    for dll in glob.glob(os.path.join(src_libexec, "*.dll")):
        shutil.copy2(dll, os.path.join(dst_libexec, os.path.basename(dll)))

    copy_file_if_exists(
        os.path.join(src_tc, "lib", "xtensa_esp32s3.so"),
        os.path.join(dst_tc, "lib", "xtensa_esp32s3.so"),
    )
    copy_file_if_exists(
        os.path.join(src_tc, "lib", "bfd-plugins", "liblto_plugin.dll"),
        os.path.join(dst_tc, "lib", "bfd-plugins", "liblto_plugin.dll"),
    )
    src_gcc_lib = os.path.join(gcc_ver_base, gcc_ver)
    dst_gcc_lib = os.path.join(dst_tc, "lib", "gcc", "xtensa-esp-elf", gcc_ver)
    for sub in ("include", "include-fixed"):
        s = os.path.join(src_gcc_lib, sub)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(dst_gcc_lib, sub))
    copy_file_if_exists(
        os.path.join(src_gcc_lib, "esp32s3", "libgcc.a"),
        os.path.join(dst_gcc_lib, "esp32s3", "libgcc.a"),
    )

    src_target_bin = os.path.join(src_tc, "xtensa-esp-elf", "bin")
    dst_target_bin = os.path.join(dst_tc, "xtensa-esp-elf", "bin")
    os.makedirs(dst_target_bin, exist_ok=True)
    for fn in ("as.exe", "ld.exe"):
        if not copy_file_if_exists(os.path.join(src_target_bin, fn), os.path.join(dst_target_bin, fn)):
            raise FileNotFoundError(f"缺少汇编/链接器: {fn}")
    for dll in glob.glob(os.path.join(src_target_bin, "*.dll")):
        shutil.copy2(dll, os.path.join(dst_target_bin, os.path.basename(dll)))

    src_target_inc = os.path.join(src_tc, "xtensa-esp-elf", "include")
    dst_target_inc = os.path.join(dst_tc, "xtensa-esp-elf", "include")
    os.makedirs(dst_target_inc, exist_ok=True)
    for entry in os.listdir(src_target_inc):
        if entry.lower() == "c++":
            continue
        s = os.path.join(src_target_inc, entry)
        d = os.path.join(dst_target_inc, entry)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)

    print(f"      toolchain/ 体积: {dir_size_bytes(dst_tc) / (1024 * 1024):.1f} MB")


def copy_app_and_sdk(dst_root: str) -> None:
    print("[3/6] 拷贝 G'lamor 应用代码与 SDK 模板...")
    dst_app = os.path.join(dst_root, "app")
    os.makedirs(dst_app, exist_ok=True)
    for fn in ("glam_studio.py", "glamctl.py", "glamor.ico"):
        src = os.path.join(TOOLS_DIR, fn)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(dst_app, fn))
    shutil.copytree(
        os.path.join(TOOLS_DIR, "glam_sdk"),
        os.path.join(dst_app, "glam_sdk"),
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    src_sdk = os.path.join(REPO_ROOT, "app_sdk_template")
    dst_sdk = os.path.join(dst_root, "sdk")
    for sub in ("include", "ld", "apps", "dist"):
        s = os.path.join(src_sdk, sub)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(dst_sdk, sub), ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def compile_native_launchers(dst_root: str) -> None:
    print("[4/6] 使用 MinGW64 编译原生 Win64 G'lamor.exe 与 glamctl.exe...")
    gcc = shutil.which("gcc")
    windres = shutil.which("windres")
    if not gcc or not windres:
        raise FileNotFoundError("未在 PATH 中找到 MinGW64 gcc / windres")

    ico_src = os.path.join(TOOLS_DIR, "glamor.ico")
    if not os.path.isfile(ico_src):
        raise FileNotFoundError(f"缺少图标文件: {ico_src}")

    with tempfile.TemporaryDirectory(prefix="glamor_exe_build_") as tmp:
        shutil.copy2(ico_src, os.path.join(tmp, "glamor.ico"))

        rc_content = """#include <winver.h>
IDI_ICON1 ICON "glamor.ico"

VS_VERSION_INFO VERSIONINFO
 FILEVERSION 1,0,0,0
 PRODUCTVERSION 1,0,0,0
 FILEFLAGSMASK 0x3fL
 FILEFLAGS 0x0L
 FILEOS VOS_NT_WINDOWS32
 FILETYPE VFT_APP
 FILESUBTYPE VFT2_UNKNOWN
BEGIN
    BLOCK "StringFileInfo"
    BEGIN
        BLOCK "080404b0"
        BEGIN
            VALUE "CompanyName", "G'lam OS Team"
            VALUE "FileDescription", "G'lamor - G'lam OS Developer Controller"
            VALUE "FileVersion", "1.0.0.0"
            VALUE "ProductName", "G'lamor"
            VALUE "ProductVersion", "1.0.0.0"
        END
    END
    BLOCK "VarFileInfo"
    BEGIN
        VALUE "Translation", 0x0804, 1200
    END
END
"""
        rc_path = os.path.join(tmp, "glamor.rc")
        res_obj = os.path.join(tmp, "glamor_res.o")
        c_path = os.path.join(tmp, "launcher.c")

        with open(rc_path, "w", encoding="utf-8") as f:
            f.write(rc_content)
        with open(c_path, "w", encoding="utf-8") as f:
            f.write(LAUNCHER_C_SOURCE)

        subprocess.run([windres, "-O", "coff", rc_path, res_obj], cwd=tmp, check=True)

        gui_exe = os.path.join(dst_root, "G'lamor.exe")
        subprocess.run(
            [
                gcc,
                "-O2",
                "-Wall",
                "-Wextra",
                "-DGLAMOR_GUI=1",
                "-municode",
                "-mwindows",
                "-static",
                "-s",
                c_path,
                res_obj,
                "-o",
                gui_exe,
                "-lshell32",
                "-luser32",
            ],
            cwd=tmp,
            check=True,
        )

        cli_exe = os.path.join(dst_root, "glamctl.exe")
        subprocess.run(
            [
                gcc,
                "-O2",
                "-Wall",
                "-Wextra",
                "-DGLAMOR_GUI=0",
                "-municode",
                "-static",
                "-s",
                c_path,
                res_obj,
                "-o",
                cli_exe,
            ],
            cwd=tmp,
            check=True,
        )

    print(
        f"      G'lamor.exe ({os.path.getsize(gui_exe) // 1024} KB), "
        f"glamctl.exe ({os.path.getsize(cli_exe) // 1024} KB)"
    )


def write_readme_and_zip(dst_root: str, zip_out: str) -> None:
    print("[5/6] 生成 README_使用说明.txt...")
    with open(os.path.join(dst_root, "README_使用说明.txt"), "w", encoding="utf-8") as f:
        f.write(README_TEXT)

    print(f"[6/6] 打包便携分发压缩包 -> {zip_out}")
    os.makedirs(os.path.dirname(zip_out), exist_ok=True)
    if os.path.exists(zip_out):
        os.remove(zip_out)

    base_name = os.path.basename(dst_root)
    with zipfile.ZipFile(zip_out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, _dirs, files in os.walk(dst_root):
            for fn in sorted(files):
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, dst_root)
                zf.write(full, os.path.join(base_name, rel))

    folder_mb = dir_size_bytes(dst_root) / (1024 * 1024)
    zip_mb = os.path.getsize(zip_out) / (1024 * 1024)
    print(f"[DONE] 便携目录体积: {folder_mb:.1f} MB | 压缩包体积: {zip_mb:.1f} MB")


def main() -> int:
    if os.path.exists(PORTABLE_DIR):
        shutil.rmtree(PORTABLE_DIR)
    os.makedirs(PORTABLE_DIR, exist_ok=True)

    copy_slim_python_runtime(os.path.join(PORTABLE_DIR, "runtime"))
    copy_slim_xtensa_toolchain(os.path.join(PORTABLE_DIR, "toolchain"))
    copy_app_and_sdk(PORTABLE_DIR)
    compile_native_launchers(PORTABLE_DIR)
    write_readme_and_zip(PORTABLE_DIR, ZIP_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
