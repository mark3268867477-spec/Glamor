"""
G'lam OS Toolchain Discovery, Multi-File App Builder, and Starter Project Generator.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
from typing import Callable, List, Optional, Tuple

from .elf_check import ElfCheckReport, check_elf_file
from .pkg import CATEGORY_DEFAULT_POLICY, VALID_CATEGORIES, VALID_ID_RE

LogFn = Optional[Callable[[str], None]]


def _log(log_cb: LogFn, msg: str) -> None:
    if log_cb:
        log_cb(msg)


def locate_app_base_dir() -> str:
    env_base = os.environ.get("GLAMOR_PORTABLE_ROOT", "").strip()
    if env_base and os.path.isdir(env_base):
        return os.path.abspath(env_base)
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", ".."))


def locate_sdk_root() -> str:
    env_root = os.environ.get("GLAM_SDK_ROOT", "").strip()
    if env_root and os.path.isdir(env_root):
        return os.path.abspath(env_root)

    base = locate_app_base_dir()
    for rel in ("sdk", "app_sdk_template"):
        cand = os.path.join(base, rel)
        if os.path.isfile(os.path.join(cand, "include", "glam_os_api.h")) or os.path.isfile(
            os.path.join(cand, "include", "swift_os_api.h")
        ):
            return os.path.abspath(cand)

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        cand = os.path.join(meipass, "sdk")
        if os.path.isdir(cand):
            return os.path.abspath(cand)

    return os.path.abspath(os.path.join(base, "sdk" if getattr(sys, "frozen", False) else "app_sdk_template"))


def find_xtensa_gcc(preferred: Optional[str] = None) -> Optional[str]:
    candidates: List[str] = []
    if preferred:
        candidates.append(preferred)
    for env_key in ("GLAM_GCC", "XTENSA_GCC"):
        val = os.environ.get(env_key, "").strip()
        if val:
            candidates.append(val)

    # Prefer bundled portable toolchain next to G'lamor.exe / sdk_root
    base = locate_app_base_dir()
    sdk_root = locate_sdk_root()
    for root_cand in (base, sdk_root):
        candidates.append(os.path.join(root_cand, "toolchain", "bin", "xtensa-esp32s3-elf-gcc.exe"))
        candidates.append(os.path.join(root_cand, "toolchain", "bin", "xtensa-esp32s3-elf-gcc"))

    which_gcc = shutil.which("xtensa-esp32s3-elf-gcc")
    if which_gcc:
        candidates.append(which_gcc)

    glob_patterns = [
        r"C:\Espressif\tools\xtensa-esp-elf\*\xtensa-esp-elf\bin\xtensa-esp32s3-elf-gcc.exe",
        os.path.join(
            os.path.expanduser("~"),
            ".espressif",
            "tools",
            "xtensa-esp-elf",
            "*",
            "xtensa-esp-elf",
            "bin",
            "xtensa-esp32s3-elf-gcc*",
        ),
        r"D:\Espressif\tools\xtensa-esp-elf\*\xtensa-esp-elf\bin\xtensa-esp32s3-elf-gcc.exe",
    ]
    for pat in glob_patterns:
        matches = sorted(glob.glob(pat), reverse=True)
        candidates.extend(matches)

    for cand in candidates:
        if cand and os.path.isfile(cand):
            return os.path.abspath(cand)
    return None


def discover_sources(project_dir: str) -> List[str]:
    proj_abs = os.path.abspath(project_dir)
    sources: List[str] = []

    for fn in sorted(os.listdir(proj_abs)):
        full = os.path.join(proj_abs, fn)
        if os.path.isfile(full) and fn.lower().endswith(".c"):
            sources.append(full)

    src_dir = os.path.join(proj_abs, "src")
    if os.path.isdir(src_dir):
        for root, dirs, files in os.walk(src_dir):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in ("build", "dist"))
            for fn in sorted(files):
                if fn.lower().endswith(".c"):
                    sources.append(os.path.join(root, fn))

    return sources


def detect_entry_linker_script(sources: List[str], sdk_ld_dir: str) -> Tuple[str, str]:
    glam_ld = os.path.join(sdk_ld_dir, "glam_app.ld")
    swift_ld = os.path.join(sdk_ld_dir, "swift_app.ld")

    for src_path in sources:
        try:
            with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read()
            if re.search(r"\bglam_app_entry\b", txt):
                if os.path.isfile(glam_ld):
                    return ("glam_app_entry", glam_ld)
            if re.search(r"\bswift_app_entry\b", txt):
                if os.path.isfile(swift_ld):
                    return ("swift_app_entry", swift_ld)
        except OSError:
            pass

    if os.path.isfile(glam_ld):
        return ("glam_app_entry", glam_ld)
    return ("swift_app_entry", swift_ld)


def build_project(
    project_dir: str,
    gcc_path: Optional[str] = None,
    out_elf: Optional[str] = None,
    log_cb: LogFn = None,
) -> Tuple[str, ElfCheckReport]:
    proj_abs = os.path.abspath(project_dir)
    if not os.path.isdir(proj_abs):
        raise FileNotFoundError(f"项目目录不存在: {proj_abs}")

    gcc = find_xtensa_gcc(gcc_path)
    if not gcc:
        raise FileNotFoundError(
            "未找到 xtensa-esp32s3-elf-gcc 编译器。请确认 G'lamor 同级目录下存在 toolchain/，或在 G'lamor 顶部手动指定 GCC 路径。"
        )

    sdk_root = locate_sdk_root()
    sdk_inc = os.path.join(sdk_root, "include")
    sdk_ld_dir = os.path.join(sdk_root, "ld")
    if not os.path.isfile(os.path.join(sdk_inc, "glam_os_api.h")) and not os.path.isfile(
        os.path.join(sdk_inc, "swift_os_api.h")
    ):
        raise FileNotFoundError(f"未找到 SDK 头文件目录: {sdk_inc}")

    sources = discover_sources(proj_abs)
    if not sources:
        raise FileNotFoundError(f"在 {proj_abs} (及 src/) 中未找到任何 .c 源文件")

    entry_sym, ld_script = detect_entry_linker_script(sources, sdk_ld_dir)
    if not os.path.isfile(ld_script):
        raise FileNotFoundError(f"未找到链接脚本: {ld_script}")

    target_elf = os.path.abspath(out_elf) if out_elf else os.path.join(proj_abs, "app.elf")
    os.makedirs(os.path.dirname(target_elf), exist_ok=True)

    include_dirs = [sdk_inc, proj_abs]
    proj_inc = os.path.join(proj_abs, "include")
    if os.path.isdir(proj_inc):
        include_dirs.append(proj_inc)
    proj_src = os.path.join(proj_abs, "src")
    if os.path.isdir(proj_src):
        include_dirs.append(proj_src)

    cmd = [
        gcc,
        "-mlongcalls",
        "-mtext-section-literals",
        "-fno-common",
        "-ffunction-sections",
        "-fdata-sections",
        "-O2",
        "-Wall",
        "-Wextra",
    ]
    for inc in include_dirs:
        cmd.extend(["-I", inc])
    cmd.extend(sources)
    cmd.extend(
        [
            "-nostdlib",
            f"-Wl,-T,{ld_script}",
            "-Wl,-q",
            "-Wl,--gc-sections",
            "-Wl,--unresolved-symbols=ignore-all",
            "-lgcc",
            "-o",
            target_elf,
        ]
    )

    _log(log_cb, f"[BUILD] GCC: {gcc}")
    _log(log_cb, f"[BUILD] 源文件 ({len(sources)}): {', '.join(os.path.basename(s) for s in sources)}")
    _log(log_cb, f"[BUILD] 入口脚本: {os.path.basename(ld_script)} (ENTRY={entry_sym})")

    sub_env = os.environ.copy()
    gcc_bin_dir = os.path.dirname(os.path.abspath(gcc))
    sub_env["PATH"] = gcc_bin_dir + os.pathsep + sub_env.get("PATH", "")
    run_kwargs = {}
    if os.name == "nt":
        run_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    proc = subprocess.run(
        cmd,
        cwd=proj_abs,
        env=sub_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        **run_kwargs,
    )
    if proc.stdout.strip():
        for line in proc.stdout.strip().splitlines():
            _log(log_cb, f"  {line}")
    if proc.stderr.strip():
        for line in proc.stderr.strip().splitlines():
            _log(log_cb, f"  {line}")

    if proc.returncode != 0:
        raise RuntimeError(f"GCC 编译失败 (exit={proc.returncode})")

    report = check_elf_file(target_elf)
    _log(
        log_cb,
        f"[BUILD] 产出 {os.path.basename(target_elf)} ({report.elf_size} B, PSRAM={report.psram_footprint} B) -> ELF体检: {'通过' if report.ok else '失败'}",
    )
    return target_elf, report


def _create_starter_icon(icon_path: str, app_name: str, accent_hex: str) -> bool:
    try:
        from PIL import Image, ImageDraw, ImageFont

        hx = accent_hex.lstrip("#")
        r = int(hx[0:2], 16)
        g = int(hx[2:4], 16)
        b = int(hx[4:6], 16)

        im = Image.new("RGB", (64, 64), (r, g, b))
        draw = ImageDraw.Draw(im)
        top = (min(255, r + 28), min(255, g + 28), min(255, b + 28))
        bot = (max(0, r - 34), max(0, g - 34), max(0, b - 34))
        for y in range(64):
            t = y / 63.0
            col = (
                int(top[0] * (1 - t) + bot[0] * t),
                int(top[1] * (1 - t) + bot[1] * t),
                int(top[2] * (1 - t) + bot[2] * t),
            )
            draw.line([(0, y), (63, y)], fill=col)

        draw.rounded_rectangle([4, 4, 59, 59], radius=14, outline=(255, 255, 255), width=2)

        ch = (app_name.strip()[:1] or "G").upper()
        font = None
        for font_cand in (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\arialbd.ttf"):
            if os.path.isfile(font_cand):
                try:
                    font = ImageFont.truetype(font_cand, 28)
                    break
                except Exception:
                    pass
        if font is None:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), ch, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (64 - tw) // 2 - bbox[0]
        ty = (64 - th) // 2 - bbox[1]
        draw.text((tx, ty), ch, fill=(255, 255, 255), font=font)
        im.save(icon_path, format="PNG")
        return True
    except Exception:
        return False


def init_project(
    target_dir: str,
    app_id: str,
    app_name: str,
    category: str = "tool",
    bg_policy: Optional[str] = None,
    author: str = "Developer",
    accent: str = "#0EA5E9",
    description: str = "",
) -> str:
    app_id = app_id.strip()
    if not app_id or not VALID_ID_RE.match(app_id) or ".." in app_id or len(app_id.encode("utf-8")) >= 64:
        raise ValueError(f"非法 app_id: {app_id!r}")

    category = category.strip().lower()
    if category not in VALID_CATEGORIES:
        raise ValueError(f"非法 category: {category!r}")
    policy = (bg_policy or CATEGORY_DEFAULT_POLICY[category]).strip().lower()
    if not accent.startswith("#"):
        accent = "#" + accent
    if len(accent) != 7:
        accent = "#0EA5E9"

    proj_abs = os.path.abspath(target_dir)
    os.makedirs(proj_abs, exist_ok=True)

    manifest = {
        "id": app_id,
        "name": app_name.strip() or app_id,
        "version": "1.0.0",
        "api_level": 1,
        "entry": "app.elf",
        "category": category,
        "bg_policy": policy,
        "author": author.strip() or "Developer",
        "accent": accent.upper(),
        "description": description.strip() or f"{app_name.strip() or app_id} - G'lam OS 动态应用",
        "permissions": ["sandbox_data"],
    }

    icon_created = _create_starter_icon(os.path.join(proj_abs, "icon.png"), manifest["name"], accent)
    if icon_created:
        manifest["icon"] = "icon.png"

    with open(os.path.join(proj_abs, "manifest.json"), "w", encoding="utf-8") as mf:
        json.dump(manifest, mf, ensure_ascii=False, indent=2)
        mf.write("\n")

    accent_hex_c = "0x" + accent.lstrip("#").upper() + "U"
    safe_title = manifest["name"].replace('"', '\\"')
    starter_c = f"""/**
 * @file app_main.c
 * @brief {safe_title} ({app_id}) - G'lam OS Dynamic PSRAM App
 */

#include "glam_os_api.h"

typedef struct {{
    const glam_os_api_t *os;
    char app_id[64];
    glam_obj_t lbl_count;
    glam_obj_t lbl_mem;
    glam_timer_t timer;
    uint32_t clicks;
}} app_state_t;

static app_state_t s_app;

static void update_labels(void)
{{
    const glam_os_api_t *os = s_app.os;
    if (!os) return;

    char buf[96];
    os->fmt_snprintf(buf, sizeof(buf), "已点击计数: %u", (unsigned)s_app.clicks);
    os->ui_set_label_text(s_app.lbl_count, buf);

    os->fmt_snprintf(
        buf,
        sizeof(buf),
        "PSRAM 可用: %u KB  |  SRAM: %u KB",
        (unsigned)(os->get_free_psram() / 1024U),
        (unsigned)(os->get_free_sram() / 1024U)
    );
    os->ui_set_label_text(s_app.lbl_mem, buf);
}}

static void on_add_click(void *user_data)
{{
    (void)user_data;
    s_app.clicks++;
    update_labels();

    if (s_app.os && s_app.os->storage_write_text) {{
        char val[24];
        s_app.os->fmt_snprintf(val, sizeof(val), "%u", (unsigned)s_app.clicks);
        s_app.os->storage_write_text(s_app.app_id, "clicks.txt", val);
    }}
}}

static void on_exit_click(void *user_data)
{{
    (void)user_data;
    if (s_app.os && s_app.os->request_exit) {{
        s_app.os->request_exit();
    }}
}}

static void on_tick(void *user_data)
{{
    (void)user_data;
    update_labels();
}}

static uint32_t parse_uint(const char *s)
{{
    uint32_t v = 0;
    if (!s) return 0;
    while (*s >= '0' && *s <= '9') {{
        v = v * 10U + (uint32_t)(*s - '0');
        s++;
    }}
    return v;
}}

static int app_on_create(const glam_os_api_t *os, glam_obj_t root, const char *app_id, const char *data_dir)
{{
    (void)data_dir;
    uint8_t *raw = (uint8_t *)&s_app;
    for (size_t i = 0; i < sizeof(s_app); i++) {{
        raw[i] = 0;
    }}
    s_app.os = os;
    os->fmt_snprintf(s_app.app_id, sizeof(s_app.app_id), "%s", app_id ? app_id : "{app_id}");

    char saved[24] = {{0}};
    if (os->storage_read_text(s_app.app_id, "clicks.txt", saved, sizeof(saved)) == 0) {{
        s_app.clicks = parse_uint(saved);
    }}

    os->ui_clear_root(root, 0x0B1120U);
    glam_obj_t card = os->ui_create_panel(root, 8, 8, 304, 200, 0x131C31U, 12, {accent_hex_c});

    os->ui_create_label(card, "{safe_title}", 14, 12, 0xF8FAFCU, 16);
    os->ui_create_label(card, "运行于 G'lam OS 扩展内存 (.gla 动态应用)", 14, 38, 0x94A3B8U, 12);

    s_app.lbl_count = os->ui_create_label(card, "已点击计数: 0", 14, 72, 0x38BDF8U, 14);
    s_app.lbl_mem = os->ui_create_label(card, "...", 14, 102, 0xA7F3D0U, 12);

    os->ui_create_button(card, "点我 +1", 14, 146, 132, 38, {accent_hex_c}, on_add_click, NULL);
    os->ui_create_button(card, "退出应用", 158, 146, 132, 38, 0x334155U, on_exit_click, NULL);

    s_app.timer = os->ui_create_timer(on_tick, 1000, NULL);
    update_labels();
    return 0;
}}

static void app_on_destroy(void)
{{
    if (s_app.timer && s_app.os) {{
        s_app.os->ui_delete_timer(s_app.timer);
        s_app.timer = NULL;
    }}
}}

static const glam_app_desc_t s_desc = {{
    .on_create = app_on_create,
    .on_destroy = app_on_destroy,
}};

const glam_app_desc_t *glam_app_entry(void)
{{
    return &s_desc;
}}
"""
    with open(os.path.join(proj_abs, "app_main.c"), "w", encoding="utf-8") as cf:
        cf.write(starter_c)

    return proj_abs
