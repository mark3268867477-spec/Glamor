#!/usr/bin/env python3
"""
G'lamor - G'lam OS Zero-Env Controller, ELF Preflight Checker, .gla Packager & Device Manager
for G'lam OS (ESP32-S3 Dynamic PSRAM ELF Platform).
"""

from __future__ import annotations

import ctypes
import io
import json
import os
import queue
import shutil
import sys
import threading
import time

_portable_root = os.environ.get("GLAMOR_PORTABLE_ROOT", "").strip()
if _portable_root and os.path.isdir(os.path.join(_portable_root, "runtime", "tcl", "tcl8.6")):
    os.environ["TCL_LIBRARY"] = os.path.join(_portable_root, "runtime", "tcl", "tcl8.6")
    os.environ["TK_LIBRARY"] = os.path.join(_portable_root, "runtime", "tcl", "tk8.6")

import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List, Optional
import webbrowser

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from glam_sdk import PKG_EXT, STUDIO_NAME, STUDIO_VERSION  # noqa: E402
from glam_sdk.elf_check import ElfCheckReport, check_elf_file  # noqa: E402
from glam_sdk.pkg import (  # noqa: E402
    CATEGORY_DEFAULT_POLICY,
    VALID_BG_POLICIES,
    VALID_CATEGORIES,
    pack_package,
    validate_manifest_dict,
    verify_package,
)
from glam_sdk.serial_port import list_serial_ports  # noqa: E402
from glam_sdk.toolchain import (  # noqa: E402
    build_project,
    discover_sources,
    find_xtensa_gcc,
    init_project,
    locate_app_base_dir,
    locate_sdk_root,
)
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

try:
    from PIL import Image, ImageDraw, ImageOps, ImageTk  # type: ignore

    HAS_PIL = True
except Exception:
    HAS_PIL = False

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".glamor.json")
LEGACY_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".glam_studio.json")

BG_MAIN = "#0B1120"
BG_CARD = "#131C31"
BG_RECESS = "#0D1526"
BG_INPUT = "#1A253D"
BORDER_SUBTLE = "#26344E"
TEXT_PRI = "#F8FAFC"
TEXT_SEC = "#94A3B8"
TEXT_MUTED = "#64748B"
ACCENT = "#38BDF8"
ACCENT_BTN = "#0284C7"
ACCENT_HOVER = "#0EA5E9"
OK_FG = "#4ADE80"
OK_BG = "#06361D"
WARN_FG = "#FBBF24"
WARN_BG = "#422006"
ERR_FG = "#F87171"
ERR_BG = "#450A0A"

POLICY_HINTS = {
    "kill_all": "退出即销毁：离开时立刻释放全部 PSRAM（适合游戏与一次性工具）",
    "partial_service": "保留后台服务：释放前台 UI，仅保留音频/计时服务（适合音乐/时钟）",
    "keep_all": "整应用挂起：保留 PSRAM 现场并冻结定时器，0% CPU 瞬时切回",
}


def _enable_windows_dpi_awareness() -> None:
    if os.name == "nt":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


class NewProjectDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, default_parent_dir: str, on_created: Callable[[str], None]):
        super().__init__(parent)
        self.title("新建 G'lam 应用项目")
        self.configure(bg=BG_MAIN)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.on_created = on_created

        self.var_parent = tk.StringVar(value=default_parent_dir)
        self.var_id = tk.StringVar(value="com.dev.hello")
        self.var_name = tk.StringVar(value="我的应用")
        self.var_cat = tk.StringVar(value="tool")
        self.var_accent = tk.StringVar(value="#0EA5E9")
        self.var_author = tk.StringVar(value="Developer")
        self.var_desc = tk.StringVar(value="基于 G'lam OS SDK 开发的动态应用")

        pad = ttk.Frame(self, style="Main.TFrame", padding=16)
        pad.pack(fill="both", expand=True)

        ttk.Label(pad, text="新建 G'lam OS 动态应用 (.gla)", style="Title.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12)
        )

        rows = [
            ("存放父目录:", self.var_parent, True),
            ("应用 ID:", self.var_id, False),
            ("显示名称:", self.var_name, False),
            ("作者:", self.var_author, False),
            ("应用简介:", self.var_desc, False),
        ]
        for idx, (lbl, var, has_browse) in enumerate(rows, start=1):
            ttk.Label(pad, text=lbl, style="Field.TLabel").grid(row=idx, column=0, sticky="w", pady=5, padx=(0, 8))
            ent = ttk.Entry(pad, textvariable=var, width=38)
            ent.grid(row=idx, column=1, sticky="ew", pady=5)
            if has_browse:
                ttk.Button(pad, text="浏览...", command=self._browse_dir, style="Secondary.TButton").grid(
                    row=idx, column=2, padx=(6, 0), pady=5
                )

        ttk.Label(pad, text="应用分类:", style="Field.TLabel").grid(row=6, column=0, sticky="w", pady=5)
        cb_cat = ttk.Combobox(pad, textvariable=self.var_cat, values=list(VALID_CATEGORIES), state="readonly", width=18)
        cb_cat.grid(row=6, column=1, sticky="w", pady=5)

        ttk.Label(pad, text="主题颜色:", style="Field.TLabel").grid(row=7, column=0, sticky="w", pady=5)
        acc_fr = ttk.Frame(pad, style="Main.TFrame")
        acc_fr.grid(row=7, column=1, sticky="w", pady=5)
        ttk.Entry(acc_fr, textvariable=self.var_accent, width=12).pack(side="left")
        self.swatch = tk.Label(acc_fr, width=3, bg=self.var_accent.get(), relief="flat")
        self.swatch.pack(side="left", padx=8)
        ttk.Button(acc_fr, text="选色", command=self._pick_color, style="Secondary.TButton").pack(side="left")

        btns = ttk.Frame(pad, style="Main.TFrame")
        btns.grid(row=8, column=0, columnspan=3, sticky="e", pady=(14, 0))
        ttk.Button(btns, text="取消", command=self.destroy, style="Secondary.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="创建工程", command=self._submit, style="Accent.TButton").pack(side="left")

        self.update_idletasks()
        px = parent.winfo_rootx() + max(40, (parent.winfo_width() - self.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(40, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{px}+{py}")

    def _browse_dir(self) -> None:
        d = filedialog.askdirectory(initialdir=self.var_parent.get() or os.getcwd(), title="选择父目录")
        if d:
            self.var_parent.set(d)

    def _pick_color(self) -> None:
        res = colorchooser.askcolor(color=self.var_accent.get(), title="选择主题色", parent=self)
        if res and res[1]:
            hx = res[1].upper()
            self.var_accent.set(hx)
            self.swatch.configure(bg=hx)

    def _submit(self) -> None:
        app_id = self.var_id.get().strip()
        parent_dir = self.var_parent.get().strip()
        if not parent_dir or not app_id:
            messagebox.showwarning("参数不完整", "请填写存放目录和应用 ID", parent=self)
            return
        target = os.path.join(parent_dir, app_id)
        if os.path.exists(target) and os.listdir(target):
            if not messagebox.askyesno("目录非空", f"目录 {target} 已存在且非空，是否覆盖模板文件？", parent=self):
                return
        try:
            out = init_project(
                target_dir=target,
                app_id=app_id,
                app_name=self.var_name.get().strip() or app_id,
                category=self.var_cat.get().strip(),
                author=self.var_author.get().strip() or "Developer",
                accent=self.var_accent.get().strip() or "#0EA5E9",
                description=self.var_desc.get().strip(),
            )
            self.destroy()
            self.on_created(out)
        except Exception as exc:
            messagebox.showerror("创建失败", str(exc), parent=self)


class GlamStudioApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{STUDIO_NAME} v{STUDIO_VERSION}  —  G'lam OS 官方开发控制器 · 编译 · ELF 体检 · .gla 打包")
        self.root.geometry("1120x780")
        self.root.minsize(960, 660)
        self.root.configure(bg=BG_MAIN)
        self._apply_window_icon()

        self.cfg = self._load_config()
        self.sdk_root = locate_sdk_root()

        self._img_icon40 = None
        self._img_icon72 = None
        self._img_screen = None
        self._last_bmp_bytes: Optional[bytes] = None
        self._auto_shot_job: Optional[str] = None
        self._busy = False
        self._log_queue: queue.Queue = queue.Queue()

        # Shared state variables
        is_portable = bool(os.environ.get("GLAMOR_PORTABLE_ROOT", "").strip()) or getattr(sys, "frozen", False)
        detected_gcc = find_xtensa_gcc() or ""
        saved_gcc = self.cfg.get("gcc_path", "").strip()
        if is_portable and detected_gcc:
            initial_gcc = detected_gcc
        elif saved_gcc and os.path.isfile(saved_gcc):
            initial_gcc = saved_gcc
        else:
            initial_gcc = detected_gcc
        self.var_gcc = tk.StringVar(value=initial_gcc)
        self.var_mode = tk.StringVar(value="project")
        self.var_project_dir = tk.StringVar(value="")
        self.var_standalone_elf = tk.StringVar(value="")
        self.var_out_pkg = tk.StringVar(value="")
        self.var_compat_swpk = tk.BooleanVar(value=False)

        # Manifest editor variables
        self.var_id = tk.StringVar()
        self.var_name = tk.StringVar()
        self.var_version = tk.StringVar(value="1.0.0")
        self.var_category = tk.StringVar(value="tool")
        self.var_bg_policy = tk.StringVar(value="keep_all")
        self.var_accent = tk.StringVar(value="#0EA5E9")
        self.var_author = tk.StringVar(value="Developer")
        self.var_desc = tk.StringVar()
        self.var_icon_src = tk.StringVar()
        self.var_perm_sandbox = tk.BooleanVar(value=True)
        self.var_perm_audio = tk.BooleanVar(value=False)
        self.var_perm_media = tk.BooleanVar(value=False)

        # Install tab variables
        self.var_inst_pkg = tk.StringVar(value=self.cfg.get("last_pkg", ""))
        self.var_wifi_ip = tk.StringVar(value=self.cfg.get("wifi_ip", "192.168.1.50"))
        self.var_serial_port = tk.StringVar(value=self.cfg.get("serial_port", ""))
        self.var_serial_baud = tk.StringVar(value="115200")
        self.var_serial_legacy = tk.BooleanVar(value=False)
        self.var_sd_drive = tk.StringVar(value=self.cfg.get("sd_drive", ""))
        self.var_inst_status = tk.StringVar(value="就绪：请选择 .gla 安装包并选择安装通道")

        # Device tab variables
        self.var_dev_os = tk.StringVar(value="未连接")
        self.var_dev_mem = tk.StringVar(value="PSRAM: --  |  SRAM: --")
        self.var_dev_sd = tk.StringVar(value="TF 卡: --")
        self.var_auto_shot = tk.BooleanVar(value=False)

        self._setup_styles()
        self._build_layout()
        self._refresh_gcc_badge()
        self._refresh_ports_and_drives()

        default_proj = self.cfg.get("last_project", "")
        if not default_proj or not os.path.isdir(default_proj):
            cand = os.path.join(self.sdk_root, "apps", "com.glam.racer")
            if os.path.isdir(cand):
                default_proj = cand
        if default_proj and os.path.isdir(default_proj):
            self.load_project(default_proj)

        if self.var_inst_pkg.get() and os.path.isfile(self.var_inst_pkg.get()):
            self._inspect_pkg_path(self.var_inst_pkg.get())

        self.root.after(100, self._drain_log_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_window_icon(self) -> None:
        cands = []
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            cands.append(os.path.join(meipass, "glamor.ico"))
        base = locate_app_base_dir()
        cands.extend([
            os.path.join(base, "glamor.ico"),
            os.path.join(base, "app", "glamor.ico"),
            os.path.join(TOOLS_DIR, "glamor.ico"),
            os.path.join(TOOLS_DIR, "glam_studio.ico"),
        ])
        for ico in cands:
            if os.path.isfile(ico):
                try:
                    self.root.iconbitmap(ico)
                    return
                except Exception:
                    pass

    def _load_config(self) -> Dict[str, Any]:
        for path in (CONFIG_PATH, LEGACY_CONFIG_PATH):
            try:
                if os.path.isfile(path):
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
        return {}

    def _save_config(self) -> None:
        data = {
            "gcc_path": self.var_gcc.get().strip(),
            "last_project": self.var_project_dir.get().strip(),
            "last_pkg": self.var_inst_pkg.get().strip(),
            "wifi_ip": self.var_wifi_ip.get().strip(),
            "serial_port": self.var_serial_port.get().strip(),
            "sd_drive": self.var_sd_drive.get().strip(),
        }
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _on_close(self) -> None:
        if self._auto_shot_job:
            try:
                self.root.after_cancel(self._auto_shot_job)
            except Exception:
                pass
        self._save_config()
        self.root.destroy()

    def _setup_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        ui_font = ("Microsoft YaHei UI", 10)
        ui_bold = ("Microsoft YaHei UI", 10, "bold")
        title_font = ("Microsoft YaHei UI", 12, "bold")
        small_font = ("Microsoft YaHei UI", 9)

        self.root.option_add("*TCombobox*Listbox.background", BG_INPUT)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT_PRI)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_BTN)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")

        style.configure("Main.TFrame", background=BG_MAIN)
        style.configure("Card.TFrame", background=BG_CARD)
        style.configure("Recess.TFrame", background=BG_RECESS)

        style.configure("TLabel", background=BG_CARD, foreground=TEXT_PRI, font=ui_font)
        style.configure("Main.TLabel", background=BG_MAIN, foreground=TEXT_PRI, font=ui_font)
        style.configure("Title.TLabel", background=BG_MAIN, foreground=TEXT_PRI, font=title_font)
        style.configure("CardTitle.TLabel", background=BG_CARD, foreground=ACCENT, font=ui_bold)
        style.configure("Field.TLabel", background=BG_CARD, foreground=TEXT_SEC, font=small_font)
        style.configure("Muted.TLabel", background=BG_MAIN, foreground=TEXT_SEC, font=small_font)
        style.configure("CardMuted.TLabel", background=BG_CARD, foreground=TEXT_SEC, font=small_font)

        style.configure(
            "TEntry",
            fieldbackground=BG_INPUT,
            foreground=TEXT_PRI,
            insertcolor=TEXT_PRI,
            bordercolor=BORDER_SUBTLE,
            lightcolor=BORDER_SUBTLE,
            darkcolor=BORDER_SUBTLE,
            padding=5,
        )
        style.configure(
            "TCombobox",
            fieldbackground=BG_INPUT,
            background=BG_INPUT,
            foreground=TEXT_PRI,
            arrowcolor=ACCENT,
            bordercolor=BORDER_SUBTLE,
            padding=4,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", BG_INPUT)],
            foreground=[("readonly", TEXT_PRI)],
            selectbackground=[("readonly", BG_INPUT)],
            selectforeground=[("readonly", TEXT_PRI)],
        )

        style.configure("TCheckbutton", background=BG_CARD, foreground=TEXT_PRI, font=small_font)
        style.map("TCheckbutton", background=[("active", BG_CARD)])
        style.configure("TRadiobutton", background=BG_CARD, foreground=TEXT_PRI, font=small_font)
        style.map("TRadiobutton", background=[("active", BG_CARD)])

        style.configure(
            "Accent.TButton",
            background=ACCENT_BTN,
            foreground="#FFFFFF",
            font=ui_bold,
            borderwidth=0,
            padding=(12, 7),
        )
        style.map(
            "Accent.TButton",
            background=[("active", ACCENT_HOVER), ("disabled", "#1E3A5F")],
            foreground=[("disabled", "#64748B")],
        )

        style.configure(
            "Secondary.TButton",
            background="#1E293B",
            foreground=TEXT_PRI,
            font=small_font,
            borderwidth=1,
            bordercolor=BORDER_SUBTLE,
            padding=(9, 5),
        )
        style.map("Secondary.TButton", background=[("active", "#283548")])

        style.configure(
            "Danger.TButton",
            background="#991B1B",
            foreground="#FFFFFF",
            font=small_font,
            borderwidth=0,
            padding=(9, 5),
        )
        style.map("Danger.TButton", background=[("active", "#DC2626")])

        style.configure("TNotebook", background=BG_MAIN, borderwidth=0, tabmargins=[0, 0, 0, 0])
        style.configure(
            "TNotebook.Tab",
            background="#131C31",
            foreground=TEXT_SEC,
            font=ui_bold,
            padding=(16, 8),
            borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", ACCENT_BTN), ("active", "#1E293B")],
            foreground=[("selected", "#FFFFFF"), ("active", TEXT_PRI)],
        )

        style.configure(
            "Treeview",
            background=BG_RECESS,
            fieldbackground=BG_RECESS,
            foreground=TEXT_PRI,
            rowheight=26,
            borderwidth=0,
            font=small_font,
        )
        style.configure(
            "Treeview.Heading",
            background="#1E293B",
            foreground=ACCENT,
            font=small_font,
            borderwidth=0,
        )
        style.map("Treeview", background=[("selected", ACCENT_BTN)], foreground=[("selected", "#FFFFFF")])

        style.configure(
            "Blue.Horizontal.TProgressbar",
            troughcolor=BG_RECESS,
            background=ACCENT,
            bordercolor=BORDER_SUBTLE,
            thickness=10,
        )

    def _card(self, parent: tk.Misc, title: str = "") -> ttk.Frame:
        outer = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER_SUBTLE, highlightthickness=1)
        inner = ttk.Frame(outer, style="Card.TFrame", padding=12)
        inner.pack(fill="both", expand=True)
        if title:
            ttk.Label(inner, text=title, style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
        return outer, inner  # type: ignore[return-value]

    def _build_layout(self) -> None:
        # Top Header Bar
        hdr = tk.Frame(self.root, bg="#0F172A", height=56, highlightbackground=BORDER_SUBTLE, highlightthickness=1)
        hdr.pack(fill="x", padx=10, pady=(10, 6))
        hdr.pack_propagate(False)

        left_hdr = tk.Frame(hdr, bg="#0F172A")
        left_hdr.pack(side="left", padx=14, pady=8)

        badge = tk.Label(
            left_hdr,
            text=" G'lamor ",
            bg=ACCENT_BTN,
            fg="#FFFFFF",
            font=("Microsoft YaHei UI", 12, "bold"),
            padx=8,
            pady=2,
        )
        badge.pack(side="left")
        tk.Label(
            left_hdr,
            text=f" v{STUDIO_VERSION}",
            bg="#0F172A",
            fg=TEXT_PRI,
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(side="left", padx=(4, 12))
        tk.Label(
            left_hdr,
            text="G'lam OS 官方开发控制器 · 编译 · ELF 符号预检 · .gla 打包 · 装机管理",
            bg="#0F172A",
            fg=TEXT_SEC,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left")

        right_hdr = tk.Frame(hdr, bg="#0F172A")
        right_hdr.pack(side="right", padx=12)

        self.lbl_gcc_pill = tk.Label(
            right_hdr,
            text="GCC: 检测中",
            bg=WARN_BG,
            fg=WARN_FG,
            font=("Microsoft YaHei UI", 8, "bold"),
            padx=8,
            pady=3,
        )
        self.lbl_gcc_pill.pack(side="left", padx=(0, 8))

        ttk.Button(right_hdr, text="新建应用", command=self._open_new_project_dialog, style="Accent.TButton").pack(
            side="left", padx=4
        )
        ttk.Button(right_hdr, text="打开工程", command=self._browse_project_dir, style="Secondary.TButton").pack(
            side="left", padx=4
        )
        ttk.Button(right_hdr, text="选择编译器", command=self._choose_gcc, style="Secondary.TButton").pack(
            side="left", padx=4
        )

        # Main Vertical Paned Layout (Tabs on top, Console on bottom)
        paned = tk.PanedWindow(self.root, orient="vertical", bg=BG_MAIN, sashwidth=6, sashrelief="flat", bd=0)
        paned.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        top_wrap = ttk.Frame(paned, style="Main.TFrame")
        self.notebook = ttk.Notebook(top_wrap)
        self.notebook.pack(fill="both", expand=True)

        self.tab_build = ttk.Frame(self.notebook, style="Main.TFrame", padding=(0, 8, 0, 0))
        self.tab_install = ttk.Frame(self.notebook, style="Main.TFrame", padding=(0, 8, 0, 0))
        self.tab_device = ttk.Frame(self.notebook, style="Main.TFrame", padding=(0, 8, 0, 0))

        self.notebook.add(self.tab_build, text="  1. 构建 & 打包 (.gla)  ")
        self.notebook.add(self.tab_install, text="  2. 安装到设备  ")
        self.notebook.add(self.tab_device, text="  3. 设备管理 & 实时投屏  ")

        self._build_tab_build()
        self._build_tab_install()
        self._build_tab_device()

        # Bottom Console
        bot_wrap = tk.Frame(paned, bg=BG_CARD, highlightbackground=BORDER_SUBTLE, highlightthickness=1)
        con_hdr = tk.Frame(bot_wrap, bg="#0F172A", height=28)
        con_hdr.pack(fill="x")
        con_hdr.pack_propagate(False)
        tk.Label(
            con_hdr,
            text="  控制台输出日志",
            bg="#0F172A",
            fg=ACCENT,
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(side="left", pady=4)
        ttk.Button(con_hdr, text="清空日志", command=self._clear_log, style="Secondary.TButton").pack(
            side="right", padx=6, pady=2
        )

        con_body = tk.Frame(bot_wrap, bg="#070B14")
        con_body.pack(fill="both", expand=True)
        self.txt_log = tk.Text(
            con_body,
            height=7,
            bg="#070B14",
            fg="#CBD5E1",
            insertbackground=TEXT_PRI,
            relief="flat",
            font=("Consolas", 9),
            wrap="word",
            state="disabled",
            padx=8,
            pady=6,
        )
        sb = ttk.Scrollbar(con_body, orient="vertical", command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt_log.pack(side="left", fill="both", expand=True)

        self.txt_log.tag_configure("ok", foreground=OK_FG)
        self.txt_log.tag_configure("warn", foreground=WARN_FG)
        self.txt_log.tag_configure("err", foreground=ERR_FG)
        self.txt_log.tag_configure("cmd", foreground=ACCENT)

        paned.add(top_wrap, minsize=440, stretch="always")
        paned.add(bot_wrap, minsize=120, stretch="never")

    def _build_tab_build(self) -> None:
        self.tab_build.columnconfigure(0, weight=5)
        self.tab_build.columnconfigure(1, weight=5)
        self.tab_build.rowconfigure(0, weight=1)

        # Left Pane: Source & Manifest Editor + Icon Preview
        left_outer, left = self._card(self.tab_build, "工程源码与 manifest.json 配置")
        left_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        mode_row = ttk.Frame(left, style="Card.TFrame")
        mode_row.pack(fill="x", pady=(0, 6))
        ttk.Radiobutton(
            mode_row,
            text="源码工程模式 (编译 + 打包)",
            variable=self.var_mode,
            value="project",
            command=self._on_mode_change,
        ).pack(side="left", padx=(0, 14))
        ttk.Radiobutton(
            mode_row,
            text="独立 ELF 打包模式 (已有 app.elf)",
            variable=self.var_mode,
            value="elf",
            command=self._on_mode_change,
        ).pack(side="left")

        proj_row = ttk.Frame(left, style="Card.TFrame")
        proj_row.pack(fill="x", pady=3)
        ttk.Label(proj_row, text="工程目录:", style="Field.TLabel", width=10).pack(side="left")
        self.ent_project_dir = ttk.Entry(proj_row, textvariable=self.var_project_dir)
        self.ent_project_dir.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(proj_row, text="浏览...", command=self._browse_project_dir, style="Secondary.TButton").pack(
            side="left"
        )
        ttk.Button(proj_row, text="重载", command=self._reload_current_project, style="Secondary.TButton").pack(
            side="left", padx=(4, 0)
        )

        self.elf_row = ttk.Frame(left, style="Card.TFrame")
        self.elf_row.pack(fill="x", pady=3)
        ttk.Label(self.elf_row, text="ELF 文件:", style="Field.TLabel", width=10).pack(side="left")
        self.ent_elf = ttk.Entry(self.elf_row, textvariable=self.var_standalone_elf)
        self.ent_elf.pack(side="left", fill="x", expand=True, padx=4)
        self.btn_browse_elf = ttk.Button(
            self.elf_row, text="选 app.elf...", command=self._browse_elf_file, style="Secondary.TButton"
        )
        self.btn_browse_elf.pack(side="left")

        self.lbl_src_info = ttk.Label(left, text="未加载工程", style="CardMuted.TLabel")
        self.lbl_src_info.pack(anchor="w", pady=(2, 8))

        # Manifest Form Grid
        form = ttk.Frame(left, style="Card.TFrame")
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        ttk.Label(form, text="应用 ID:", style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(form, textvariable=self.var_id).grid(row=0, column=1, sticky="ew", padx=(4, 10), pady=3)

        ttk.Label(form, text="版本号:", style="Field.TLabel").grid(row=0, column=2, sticky="w", pady=3)
        ttk.Entry(form, textvariable=self.var_version, width=12).grid(row=0, column=3, sticky="ew", padx=(4, 0), pady=3)

        ttk.Label(form, text="显示名称:", style="Field.TLabel").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(form, textvariable=self.var_name).grid(row=1, column=1, sticky="ew", padx=(4, 10), pady=3)

        ttk.Label(form, text="作者:", style="Field.TLabel").grid(row=1, column=2, sticky="w", pady=3)
        ttk.Entry(form, textvariable=self.var_author).grid(row=1, column=3, sticky="ew", padx=(4, 0), pady=3)

        ttk.Label(form, text="分类:", style="Field.TLabel").grid(row=2, column=0, sticky="w", pady=3)
        cb_cat = ttk.Combobox(form, textvariable=self.var_category, values=list(VALID_CATEGORIES), state="readonly")
        cb_cat.grid(row=2, column=1, sticky="ew", padx=(4, 10), pady=3)
        cb_cat.bind("<<ComboboxSelected>>", self._on_category_selected)

        ttk.Label(form, text="后台策略:", style="Field.TLabel").grid(row=2, column=2, sticky="w", pady=3)
        cb_pol = ttk.Combobox(form, textvariable=self.var_bg_policy, values=list(VALID_BG_POLICIES), state="readonly")
        cb_pol.grid(row=2, column=3, sticky="ew", padx=(4, 0), pady=3)
        cb_pol.bind("<<ComboboxSelected>>", lambda _e: self._update_policy_hint())

        self.lbl_policy_hint = ttk.Label(left, text="", style="CardMuted.TLabel")
        self.lbl_policy_hint.pack(anchor="w", pady=(2, 4))

        acc_row = ttk.Frame(left, style="Card.TFrame")
        acc_row.pack(fill="x", pady=3)
        ttk.Label(acc_row, text="主题色:", style="Field.TLabel", width=8).pack(side="left")
        ent_acc = ttk.Entry(acc_row, textvariable=self.var_accent, width=11)
        ent_acc.pack(side="left", padx=4)
        ent_acc.bind("<KeyRelease>", lambda _e: self._refresh_icon_preview())
        self.lbl_accent_swatch = tk.Label(acc_row, width=3, bg="#0EA5E9")
        self.lbl_accent_swatch.pack(side="left", padx=(2, 4))
        ttk.Button(acc_row, text="调色板", command=self._pick_accent_color, style="Secondary.TButton").pack(
            side="left", padx=(0, 12)
        )
        ttk.Label(acc_row, text="简介:", style="Field.TLabel").pack(side="left", padx=(0, 4))
        ttk.Entry(acc_row, textvariable=self.var_desc).pack(side="left", fill="x", expand=True)

        perm_row = ttk.Frame(left, style="Card.TFrame")
        perm_row.pack(fill="x", pady=4)
        ttk.Label(perm_row, text="权限声明:", style="Field.TLabel", width=8).pack(side="left")
        ttk.Checkbutton(perm_row, text="sandbox_data (沙盒存储)", variable=self.var_perm_sandbox).pack(
            side="left", padx=4
        )
        ttk.Checkbutton(perm_row, text="audio (音频)", variable=self.var_perm_audio).pack(side="left", padx=4)
        ttk.Checkbutton(perm_row, text="media_read (媒体读取)", variable=self.var_perm_media).pack(side="left", padx=4)

        # Icon Preview & Manifest Save
        icon_box = tk.Frame(left, bg=BG_RECESS, highlightbackground=BORDER_SUBTLE, highlightthickness=1)
        icon_box.pack(fill="x", pady=(8, 0))
        icon_inner = ttk.Frame(icon_box, style="Recess.TFrame", padding=10)
        icon_inner.pack(fill="x")

        self.cnv_icon = tk.Canvas(icon_inner, width=142, height=72, bg=BG_RECESS, highlightthickness=0)
        self.cnv_icon.pack(side="left", padx=(0, 12))

        icon_meta = ttk.Frame(icon_inner, style="Recess.TFrame")
        icon_meta.pack(side="left", fill="both", expand=True)
        tk.Label(
            icon_meta,
            text="桌面图标预览 (自动缩放裁剪为 40×40 Baseline JPEG 内嵌进 .gla)",
            bg=BG_RECESS,
            fg=TEXT_PRI,
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(anchor="w")
        self.lbl_icon_path = tk.Label(
            icon_meta,
            text="使用系统默认主题色块图标",
            bg=BG_RECESS,
            fg=TEXT_SEC,
            font=("Microsoft YaHei UI", 8),
        )
        self.lbl_icon_path.pack(anchor="w", pady=(3, 6))
        ib_btns = ttk.Frame(icon_meta, style="Recess.TFrame")
        ib_btns.pack(anchor="w")
        ttk.Button(ib_btns, text="选择图标 (PNG/JPG)", command=self._choose_icon, style="Secondary.TButton").pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(ib_btns, text="清除图标", command=self._clear_icon, style="Secondary.TButton").pack(
            side="left", padx=(0, 12)
        )
        ttk.Button(ib_btns, text="保存 manifest.json", command=self._save_manifest_clicked, style="Secondary.TButton").pack(
            side="left"
        )

        # Right Pane: Build/Pack Actions + ELF ABI Diagnostics
        right_outer, right = self._card(self.tab_build, "打包输出 (.gla) 与 ELF ABI 安全体检")
        right_outer.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        out_row = ttk.Frame(right, style="Card.TFrame")
        out_row.pack(fill="x", pady=(0, 6))
        ttk.Label(out_row, text="输出路径:", style="Field.TLabel", width=9).pack(side="left")
        ttk.Entry(out_row, textvariable=self.var_out_pkg).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(out_row, text="另存为...", command=self._browse_out_pkg, style="Secondary.TButton").pack(side="left")

        opt_row = ttk.Frame(right, style="Card.TFrame")
        opt_row.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(
            opt_row,
            text="兼容旧版固件（生成 SWPK 包头；新版 G'lam OS 同时支持 GLAM 与 SWPK）",
            variable=self.var_compat_swpk,
            command=self._sync_output_ext,
        ).pack(anchor="w")

        cta_row = ttk.Frame(right, style="Card.TFrame")
        cta_row.pack(fill="x", pady=(0, 10))
        self.btn_oneclick = ttk.Button(
            cta_row,
            text="一键编译 · 体检 · 打包 (.gla)",
            command=self._action_build_and_pack,
            style="Accent.TButton",
        )
        self.btn_oneclick.pack(side="left", padx=(0, 8))
        ttk.Button(cta_row, text="仅编译 ELF", command=self._action_build_only, style="Secondary.TButton").pack(
            side="left", padx=3
        )
        ttk.Button(cta_row, text="仅 ELF 体检", command=self._action_check_only, style="Secondary.TButton").pack(
            side="left", padx=3
        )
        ttk.Button(cta_row, text="仅打包 .gla", command=self._action_pack_only, style="Secondary.TButton").pack(
            side="left", padx=3
        )

        # ELF Report Card
        rep_box = tk.Frame(right, bg=BG_RECESS, highlightbackground=BORDER_SUBTLE, highlightthickness=1)
        rep_box.pack(fill="both", expand=True)
        rep_inner = ttk.Frame(rep_box, style="Recess.TFrame", padding=10)
        rep_inner.pack(fill="both", expand=True)

        rep_top = ttk.Frame(rep_inner, style="Recess.TFrame")
        rep_top.pack(fill="x", pady=(0, 8))
        self.lbl_elf_badge = tk.Label(
            rep_top,
            text=" 尚未体检 ",
            bg="#1E293B",
            fg=TEXT_SEC,
            font=("Microsoft YaHei UI", 10, "bold"),
            padx=10,
            pady=4,
        )
        self.lbl_elf_badge.pack(side="left")
        self.lbl_elf_summary = tk.Label(
            rep_top,
            text="编译或选择 app.elf 后将自动核验 Xtensa 重定位与 17 项 OS ABI 白名单符号",
            bg=BG_RECESS,
            fg=TEXT_SEC,
            font=("Microsoft YaHei UI", 9),
        )
        self.lbl_elf_summary.pack(side="left", padx=10)

        self.txt_elf_report = tk.Text(
            rep_inner,
            bg="#080E1C",
            fg=TEXT_PRI,
            relief="flat",
            font=("Consolas", 9),
            wrap="word",
            state="disabled",
            padx=8,
            pady=8,
        )
        rep_sb = ttk.Scrollbar(rep_inner, orient="vertical", command=self.txt_elf_report.yview)
        self.txt_elf_report.configure(yscrollcommand=rep_sb.set)
        rep_sb.pack(side="right", fill="y")
        self.txt_elf_report.pack(side="left", fill="both", expand=True)

        self.txt_elf_report.tag_configure("ok", foreground=OK_FG)
        self.txt_elf_report.tag_configure("warn", foreground=WARN_FG)
        self.txt_elf_report.tag_configure("err", foreground=ERR_FG)
        self.txt_elf_report.tag_configure("head", foreground=ACCENT, font=("Consolas", 9, "bold"))

        self._on_mode_change()
        self._update_policy_hint()

    def _build_tab_install(self) -> None:
        self.tab_install.columnconfigure(0, weight=1)
        self.tab_install.columnconfigure(1, weight=1)

        # Top Package Summary Card
        pkg_outer, pkg = self._card(self.tab_install, "待安装应用包 (.gla / 兼容 .spk)")
        pkg_outer.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        prow = ttk.Frame(pkg, style="Card.TFrame")
        prow.pack(fill="x", pady=(0, 8))
        ttk.Label(prow, text="安装包:", style="Field.TLabel", width=8).pack(side="left")
        ttk.Entry(prow, textvariable=self.var_inst_pkg).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(prow, text="选择文件...", command=self._browse_install_pkg, style="Secondary.TButton").pack(
            side="left", padx=4
        )
        ttk.Button(prow, text="校验解析", command=self._verify_selected_pkg, style="Accent.TButton").pack(side="left")

        self.lbl_pkg_meta = tk.Label(
            pkg,
            text="未加载安装包。提示：在“构建 & 打包”页完成打包后会自动填充到此处。",
            bg=BG_RECESS,
            fg=TEXT_SEC,
            font=("Microsoft YaHei UI", 9),
            anchor="w",
            justify="left",
            padx=10,
            pady=8,
        )
        self.lbl_pkg_meta.pack(fill="x")

        # Channels Grid
        ch_left_outer, ch_wifi = self._card(self.tab_install, "渠道一：Wi-Fi 无线推送（推荐，无需数据线）")
        ch_left_outer.grid(row=1, column=0, sticky="nsew", padx=(0, 6))

        wrow = ttk.Frame(ch_wifi, style="Card.TFrame")
        wrow.pack(fill="x", pady=6)
        ttk.Label(wrow, text="设备 IP:", style="Field.TLabel", width=9).pack(side="left")
        ttk.Entry(wrow, textvariable=self.var_wifi_ip).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(wrow, text="打开网页端", command=self._open_web_installer, style="Secondary.TButton").pack(
            side="left"
        )
        ttk.Label(
            ch_wifi,
            text="在设备“设置”或“应用中心”查看局域网 IP；上传后直接写入 TF 卡并刷新桌面。",
            style="CardMuted.TLabel",
            wraplength=440,
        ).pack(anchor="w", pady=(2, 10))
        ttk.Button(
            ch_wifi, text="通过 Wi-Fi 安装到设备", command=self._action_install_wifi, style="Accent.TButton"
        ).pack(anchor="w")

        ch_right_outer, ch_usb_sd = self._card(self.tab_install, "渠道二：USB 数据线直连 / TF 卡离线导入")
        ch_right_outer.grid(row=1, column=1, sticky="nsew", padx=(6, 0))

        srow = ttk.Frame(ch_usb_sd, style="Card.TFrame")
        srow.pack(fill="x", pady=4)
        ttk.Label(srow, text="USB 串口:", style="Field.TLabel", width=9).pack(side="left")
        self.cb_ports = ttk.Combobox(srow, textvariable=self.var_serial_port, width=22)
        self.cb_ports.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Entry(srow, textvariable=self.var_serial_baud, width=8).pack(side="left", padx=(0, 4))
        ttk.Button(srow, text="刷新", command=self._refresh_ports_and_drives, style="Secondary.TButton").pack(
            side="left"
        )

        sopt = ttk.Frame(ch_usb_sd, style="Card.TFrame")
        sopt.pack(fill="x", pady=(2, 8))
        ttk.Button(sopt, text="USB 串口推送安装", command=self._action_install_serial, style="Accent.TButton").pack(
            side="left", padx=(0, 10)
        )
        ttk.Checkbutton(sopt, text="兼容旧固件协议 (spk_*)", variable=self.var_serial_legacy).pack(side="left")

        ttk.Separator(ch_usb_sd, orient="horizontal").pack(fill="x", pady=8)

        drow = ttk.Frame(ch_usb_sd, style="Card.TFrame")
        drow.pack(fill="x", pady=4)
        ttk.Label(drow, text="TF 卡盘符:", style="Field.TLabel", width=9).pack(side="left")
        self.cb_drives = ttk.Combobox(drow, textvariable=self.var_sd_drive, width=18)
        self.cb_drives.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(drow, text="选目录...", command=self._browse_sd_dir, style="Secondary.TButton").pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(
            drow, text="写入 TF 卡 (自动解包)", command=self._action_install_sd, style="Secondary.TButton"
        ).pack(side="left")

        # Bottom Progress Bar
        prog_outer, prog = self._card(self.tab_install, "传输与安装进度（全程仅操作 TF 卡，绝对不触碰片内 Flash OS）")
        prog_outer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.pbar = ttk.Progressbar(prog, style="Blue.Horizontal.TProgressbar", mode="determinate", maximum=100)
        self.pbar.pack(fill="x", pady=(0, 6))
        ttk.Label(prog, textvariable=self.var_inst_status, style="CardMuted.TLabel").pack(anchor="w")

    def _build_tab_device(self) -> None:
        self.tab_device.columnconfigure(0, weight=5)
        self.tab_device.columnconfigure(1, weight=5)
        self.tab_device.rowconfigure(1, weight=1)

        top_outer, top = self._card(self.tab_device, "")
        top_outer.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        bar = ttk.Frame(top, style="Card.TFrame")
        bar.pack(fill="x")
        ttk.Label(bar, text="设备 Wi-Fi IP:", style="Field.TLabel").pack(side="left")
        ttk.Entry(bar, textvariable=self.var_wifi_ip, width=18).pack(side="left", padx=6)
        ttk.Button(bar, text="连接 / 刷新设备", command=self._action_refresh_device, style="Accent.TButton").pack(
            side="left", padx=(0, 14)
        )
        ttk.Label(bar, textvariable=self.var_dev_os, style="TLabel").pack(side="left", padx=(0, 14))
        ttk.Label(bar, textvariable=self.var_dev_mem, style="CardMuted.TLabel").pack(side="left", padx=(0, 14))
        ttk.Label(bar, textvariable=self.var_dev_sd, style="CardMuted.TLabel").pack(side="left")

        # Installed Apps Table
        left_outer, left = self._card(self.tab_device, "TF 卡已安装应用 (/sdcard/apps/)")
        left_outer.grid(row=1, column=0, sticky="nsew", padx=(0, 6))

        cols = ("id", "name", "version", "size")
        self.tree_apps = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        self.tree_apps.heading("id", text="应用 ID")
        self.tree_apps.heading("name", text="名称")
        self.tree_apps.heading("version", text="版本")
        self.tree_apps.heading("size", text="ELF 大小")
        self.tree_apps.column("id", width=160)
        self.tree_apps.column("name", width=110)
        self.tree_apps.column("version", width=60, anchor="center")
        self.tree_apps.column("size", width=80, anchor="e")
        self.tree_apps.pack(fill="both", expand=True, pady=(0, 8))

        tbtns = ttk.Frame(left, style="Card.TFrame")
        tbtns.pack(fill="x")
        ttk.Button(tbtns, text="刷新列表", command=self._action_refresh_device, style="Secondary.TButton").pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(tbtns, text="卸载选中应用", command=self._action_uninstall_selected, style="Danger.TButton").pack(
            side="left"
        )

        # Live Screen Capture
        right_outer, right = self._card(self.tab_device, "设备实时投屏预览 (320×240)")
        right_outer.grid(row=1, column=1, sticky="nsew", padx=(6, 0))

        self.cnv_screen = tk.Canvas(
            right,
            width=420,
            height=315,
            bg="#060A14",
            highlightbackground=BORDER_SUBTLE,
            highlightthickness=1,
        )
        self.cnv_screen.pack(pady=(0, 8))
        self.cnv_screen.create_text(
            210,
            157,
            text="连接 Wi-Fi 后点击“抓取屏幕”\n即可实时查看 G'lam OS 真机画面",
            fill=TEXT_SEC,
            font=("Microsoft YaHei UI", 10),
            justify="center",
        )

        sbtns = ttk.Frame(right, style="Card.TFrame")
        sbtns.pack(fill="x")
        ttk.Button(sbtns, text="抓取屏幕", command=self._action_capture_screen, style="Accent.TButton").pack(
            side="left", padx=(0, 8)
        )
        ttk.Checkbutton(
            sbtns, text="自动刷新 (2秒)", variable=self.var_auto_shot, command=self._toggle_auto_shot
        ).pack(side="left", padx=(0, 10))
        ttk.Button(sbtns, text="保存截图...", command=self._save_screenshot_file, style="Secondary.TButton").pack(
            side="right"
        )

    # ------------------------------------------------------------------
    # Logging & Threading Helpers
    # ------------------------------------------------------------------

    def _log(self, msg: str, tag: str = "") -> None:
        self._log_queue.put((msg, tag))

    def _drain_log_queue(self) -> None:
        try:
            while True:
                msg, tag = self._log_queue.get_nowait()
                ts = time.strftime("%H:%M:%S")
                self.txt_log.configure(state="normal")
                self.txt_log.insert("end", f"[{ts}] {msg}\n", tag or None)
                self.txt_log.see("end")
                self.txt_log.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_log_queue)

    def _clear_log(self) -> None:
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.configure(state="disabled")

    def _run_bg(self, fn: Callable[[], None]) -> None:
        def _worker() -> None:
            try:
                fn()
            except Exception as exc:
                self._log(f"[错误] {exc}", "err")
                self.root.after(0, lambda m=str(exc): messagebox.showerror("操作失败", m, parent=self.root))

        threading.Thread(target=_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Project / Manifest / Icon Handling
    # ------------------------------------------------------------------

    def _refresh_gcc_badge(self) -> None:
        gcc = find_xtensa_gcc(self.var_gcc.get().strip() or None)
        if gcc:
            self.var_gcc.set(gcc)
            self.lbl_gcc_pill.configure(text="GCC: 就绪", bg=OK_BG, fg=OK_FG)
        else:
            self.lbl_gcc_pill.configure(text="GCC: 未找到", bg=ERR_BG, fg=ERR_FG)

    def _choose_gcc(self) -> None:
        p = filedialog.askopenfilename(
            title="选择 xtensa-esp32s3-elf-gcc.exe",
            filetypes=[("GCC Executable", "xtensa-esp32s3-elf-gcc*.exe;*gcc*"), ("All Files", "*.*")],
        )
        if p:
            self.var_gcc.set(p)
            self._refresh_gcc_badge()
            self._log(f"已设置编译器: {p}", "cmd")

    def _open_new_project_dialog(self) -> None:
        default_parent = os.path.join(self.sdk_root, "apps")
        if not os.path.isdir(default_parent):
            default_parent = os.getcwd()
        NewProjectDialog(self.root, default_parent, on_created=self._on_new_project_created)

    def _on_new_project_created(self, proj_dir: str) -> None:
        self._log(f"已创建新应用工程: {proj_dir}", "ok")
        self.var_mode.set("project")
        self._on_mode_change()
        self.load_project(proj_dir)

    def _on_mode_change(self) -> None:
        is_proj = self.var_mode.get() == "project"
        self.ent_project_dir.configure(state="normal" if is_proj else "disabled")
        self.ent_elf.configure(state="disabled" if is_proj else "normal")
        self.btn_browse_elf.configure(state="disabled" if is_proj else "normal")

    def _on_category_selected(self, _e=None) -> None:
        cat = self.var_category.get().strip()
        if cat in CATEGORY_DEFAULT_POLICY:
            self.var_bg_policy.set(CATEGORY_DEFAULT_POLICY[cat])
        self._update_policy_hint()

    def _update_policy_hint(self) -> None:
        pol = self.var_bg_policy.get().strip()
        self.lbl_policy_hint.configure(text=POLICY_HINTS.get(pol, ""))

    def _pick_accent_color(self) -> None:
        res = colorchooser.askcolor(color=self.var_accent.get() or "#0EA5E9", title="选择桌面图标主题色")
        if res and res[1]:
            self.var_accent.set(res[1].upper())
            self._refresh_icon_preview()

    def _browse_project_dir(self) -> None:
        init_d = self.var_project_dir.get().strip() or os.path.join(self.sdk_root, "apps")
        d = filedialog.askdirectory(initialdir=init_d, title="选择 G'lam 应用工程目录")
        if d:
            self.var_mode.set("project")
            self._on_mode_change()
            self.load_project(d)

    def _reload_current_project(self) -> None:
        d = self.var_project_dir.get().strip()
        if d:
            self.load_project(d)

    def _browse_elf_file(self) -> None:
        p = filedialog.askopenfilename(title="选择 app.elf", filetypes=[("ELF Binary", "*.elf"), ("All Files", "*.*")])
        if p:
            self.var_standalone_elf.set(p)
            self._sync_output_ext()
            self._run_elf_check_path(p)

    def load_project(self, proj_dir: str) -> None:
        proj_abs = os.path.abspath(proj_dir)
        self.var_project_dir.set(proj_abs)

        try:
            srcs = discover_sources(proj_abs)
            self.lbl_src_info.configure(
                text=f"检测到 {len(srcs)} 个 C 源文件: {', '.join(os.path.basename(s) for s in srcs[:5])}"
                + (" ..." if len(srcs) > 5 else "")
            )
        except Exception:
            self.lbl_src_info.configure(text="未检测到 .c 源文件")

        manifest_path = os.path.join(proj_abs, "manifest.json")
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as mf:
                    m = json.load(mf)
                self.var_id.set(str(m.get("id", os.path.basename(proj_abs))))
                self.var_name.set(str(m.get("name", self.var_id.get())))
                self.var_version.set(str(m.get("version", "1.0.0")))
                cat = str(m.get("category", "tool")).lower()
                if cat in VALID_CATEGORIES:
                    self.var_category.set(cat)
                pol = str(m.get("bg_policy", CATEGORY_DEFAULT_POLICY.get(self.var_category.get(), "kill_all"))).lower()
                if pol in VALID_BG_POLICIES:
                    self.var_bg_policy.set(pol)
                self.var_accent.set(str(m.get("accent", "#0EA5E9")).upper())
                self.var_author.set(str(m.get("author", "Developer")))
                self.var_desc.set(str(m.get("description", "")))

                perms = set(m.get("permissions") or [])
                self.var_perm_sandbox.set("sandbox_data" in perms or not perms)
                self.var_perm_audio.set("audio" in perms)
                self.var_perm_media.set("media_read" in perms)
            except Exception as exc:
                self._log(f"读取 manifest.json 失败: {exc}", "warn")
        else:
            folder_name = os.path.basename(proj_abs)
            self.var_id.set(folder_name)
            self.var_name.set(folder_name)
            self.var_version.set("1.0.0")

        icon_found = ""
        for cand in ("icon.png", "icon.jpg", "icon.jpeg", "icon.bmp"):
            p = os.path.join(proj_abs, cand)
            if os.path.isfile(p):
                icon_found = p
                break
        self.var_icon_src.set(icon_found)
        self._update_policy_hint()
        self._refresh_icon_preview()
        self._sync_output_ext()

        elf_cand = os.path.join(proj_abs, "app.elf")
        if os.path.isfile(elf_cand):
            self._run_elf_check_path(elf_cand)

    def _collect_manifest_dict(self) -> Dict[str, Any]:
        perms = []
        if self.var_perm_sandbox.get():
            perms.append("sandbox_data")
        if self.var_perm_audio.get():
            perms.append("audio")
        if self.var_perm_media.get():
            perms.append("media_read")

        obj: Dict[str, Any] = {
            "id": self.var_id.get().strip(),
            "name": self.var_name.get().strip(),
            "version": self.var_version.get().strip(),
            "api_level": 1,
            "entry": "app.elf",
            "category": self.var_category.get().strip(),
            "bg_policy": self.var_bg_policy.get().strip(),
            "author": self.var_author.get().strip() or "Developer",
            "accent": self.var_accent.get().strip() or "#0EA5E9",
            "description": self.var_desc.get().strip(),
            "permissions": perms,
        }
        icon_p = self.var_icon_src.get().strip()
        if icon_p and os.path.isfile(icon_p):
            obj["icon"] = os.path.basename(icon_p)
        return validate_manifest_dict(obj)

    def _save_manifest_clicked(self) -> None:
        proj_dir = self.var_project_dir.get().strip()
        if not proj_dir or not os.path.isdir(proj_dir):
            messagebox.showwarning("未选择工程", "请先选择一个有效的工程目录", parent=self.root)
            return
        try:
            obj = self._collect_manifest_dict()
            icon_p = self.var_icon_src.get().strip()
            if icon_p and os.path.isfile(icon_p):
                dst_icon = os.path.join(proj_dir, os.path.basename(icon_p))
                if os.path.abspath(icon_p) != os.path.abspath(dst_icon):
                    shutil.copy2(icon_p, dst_icon)
                    self.var_icon_src.set(dst_icon)
            manifest_path = os.path.join(proj_dir, "manifest.json")
            with open(manifest_path, "w", encoding="utf-8") as mf:
                json.dump(obj, mf, ensure_ascii=False, indent=2)
                mf.write("\n")
            self._sync_output_ext()
            self._refresh_icon_preview()
            self._log(f"已保存 manifest.json -> {manifest_path}", "ok")
        except Exception as exc:
            messagebox.showerror("校验或保存失败", str(exc), parent=self.root)

    def _choose_icon(self) -> None:
        p = filedialog.askopenfilename(
            title="选择应用图标",
            filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp"), ("All Files", "*.*")],
        )
        if p:
            self.var_icon_src.set(p)
            self._refresh_icon_preview()

    def _clear_icon(self) -> None:
        self.var_icon_src.set("")
        self._refresh_icon_preview()

    def _refresh_icon_preview(self) -> None:
        acc = self.var_accent.get().strip()
        if not acc.startswith("#"):
            acc = "#" + acc
        if len(acc) == 7:
            try:
                self.lbl_accent_swatch.configure(bg=acc)
            except Exception:
                acc = "#0EA5E9"
        else:
            acc = "#0EA5E9"

        self.cnv_icon.delete("all")
        icon_p = self.var_icon_src.get().strip()
        if icon_p and os.path.isfile(icon_p):
            self.lbl_icon_path.configure(text=os.path.basename(icon_p))
        else:
            self.lbl_icon_path.configure(text="未选图片（将使用主题色默认磁贴图标）")

        if HAS_PIL:
            try:
                if icon_p and os.path.isfile(icon_p):
                    with Image.open(icon_p) as im:
                        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                            rgba = im.convert("RGBA")
                            bg = Image.new("RGBA", rgba.size, (20, 20, 26, 255))
                            im_rgb = Image.alpha_composite(bg, rgba).convert("RGB")
                        else:
                            im_rgb = im.convert("RGB")
                        im40 = ImageOps.fit(im_rgb, (40, 40), method=Image.Resampling.LANCZOS)
                        im64 = ImageOps.fit(im_rgb, (64, 64), method=Image.Resampling.LANCZOS)
                else:
                    hx = acc.lstrip("#")
                    rgb = (int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16))
                    im64 = Image.new("RGB", (64, 64), rgb)
                    draw = ImageDraw.Draw(im64)
                    ch = (self.var_name.get().strip()[:1] or "G").upper()
                    draw.text((24, 22), ch, fill=(255, 255, 255))
                    im40 = im64.resize((40, 40), Image.Resampling.LANCZOS)

                self._img_icon72 = ImageTk.PhotoImage(im64)
                self._img_icon40 = ImageTk.PhotoImage(im40)
                self.cnv_icon.create_rectangle(2, 2, 70, 70, outline=acc, width=2, fill="#1E293B")
                self.cnv_icon.create_image(36, 36, image=self._img_icon72)
                self.cnv_icon.create_rectangle(84, 16, 128, 60, outline=BORDER_SUBTLE, width=1)
                self.cnv_icon.create_image(106, 38, image=self._img_icon40)
                self.cnv_icon.create_text(106, 67, text="40×40", fill=TEXT_MUTED, font=("Microsoft YaHei UI", 8))
                return
            except Exception:
                pass

        self.cnv_icon.create_rectangle(4, 4, 68, 68, fill=acc, outline="#FFFFFF", width=1)
        self.cnv_icon.create_text(36, 36, text=(self.var_name.get().strip()[:1] or "G"), fill="#FFFFFF")

    def _sync_output_ext(self) -> None:
        app_id = self.var_id.get().strip() or "my_app"
        ext = ".spk" if self.var_compat_swpk.get() else PKG_EXT
        cur = self.var_out_pkg.get().strip()
        if not cur:
            dist_dir = os.path.join(self.sdk_root, "dist")
            self.var_out_pkg.set(os.path.join(dist_dir, f"{app_id}{ext}"))
        else:
            base, _old = os.path.splitext(cur)
            parent = os.path.dirname(base)
            self.var_out_pkg.set(os.path.join(parent, f"{app_id}{ext}"))

    def _browse_out_pkg(self) -> None:
        ext = ".spk" if self.var_compat_swpk.get() else PKG_EXT
        p = filedialog.asksaveasfilename(
            title="保存 G'lam 应用安装包",
            defaultextension=ext,
            initialfile=os.path.basename(self.var_out_pkg.get() or f"app{ext}"),
            filetypes=[("G'lam Package", "*.gla"), ("Legacy SPK", "*.spk"), ("All Files", "*.*")],
        )
        if p:
            self.var_out_pkg.set(p)

    # ------------------------------------------------------------------
    # Build / Check / Pack Actions
    # ------------------------------------------------------------------

    def _render_elf_report(self, report: ElfCheckReport, elf_path: str) -> None:
        if report.ok:
            self.lbl_elf_badge.configure(text=" 体检通过 ", bg=OK_BG, fg=OK_FG)
            self.lbl_elf_summary.configure(
                text=f"ELF {report.elf_size} B | PSRAM {report.psram_footprint} B | 入口 {report.entry_symbol or '0x0'}",
                fg=OK_FG,
            )
        else:
            self.lbl_elf_badge.configure(text=" 体检拦截 ", bg=ERR_BG, fg=ERR_FG)
            self.lbl_elf_summary.configure(
                text=f"发现 {len(report.errors)} 项兼容性/安全问题，已阻止打包",
                fg=ERR_FG,
            )

        self.txt_elf_report.configure(state="normal")
        self.txt_elf_report.delete("1.0", "end")

        self.txt_elf_report.insert("end", f"目标 ELF: {elf_path}\n", "head")
        self.txt_elf_report.insert(
            "end",
            f"大小: {report.elf_size} B  |  PSRAM 内存占用: {report.psram_footprint} B ({report.psram_footprint / 1024:.1f} KB)\n"
            f"入口偏移: 0x{report.e_entry:x} ({report.entry_symbol or '未知'})  |  SHT_RELA 节数: {report.rela_sections}\n\n",
        )

        if report.errors:
            self.txt_elf_report.insert("end", f"[拦截错误 ({len(report.errors)})]\n", "err")
            for err in report.errors:
                self.txt_elf_report.insert("end", f"  ✗ {err}\n", "err")
            self.txt_elf_report.insert("end", "\n")

        if report.warnings:
            self.txt_elf_report.insert("end", f"[警告 ({len(report.warnings)})]\n", "warn")
            for w in report.warnings:
                self.txt_elf_report.insert("end", f"  ! {w}\n", "warn")
            self.txt_elf_report.insert("end", "\n")

        self.txt_elf_report.insert("end", f"[白名单外部符号调用 ({len(report.used_os_symbols)})]\n", "head")
        if report.used_os_symbols:
            self.txt_elf_report.insert("end", "  " + ", ".join(report.used_os_symbols) + "\n\n", "ok")
        else:
            self.txt_elf_report.insert("end", "  (纯 os->* ABI 接口调用，无额外外部符号依赖)\n\n", "ok")

        if report.sections:
            self.txt_elf_report.insert("end", "[SHF_ALLOC 段分布]\n", "head")
            for sec in report.sections:
                self.txt_elf_report.insert(
                    "end",
                    f"  {sec['name']:<14} addr=0x{sec['addr']:06x}  size={sec['size']:>6} B\n",
                )

        self.txt_elf_report.configure(state="disabled")

    def _run_elf_check_path(self, elf_path: str) -> Optional[ElfCheckReport]:
        try:
            rep = check_elf_file(elf_path)
            self._render_elf_report(rep, elf_path)
            return rep
        except Exception as exc:
            self._log(f"ELF 检测异常: {exc}", "err")
            return None

    def _current_elf_path(self) -> str:
        if self.var_mode.get() == "project":
            return os.path.join(self.var_project_dir.get().strip(), "app.elf")
        return self.var_standalone_elf.get().strip()

    def _action_build_only(self) -> None:
        if self.var_mode.get() != "project":
            messagebox.showinfo("提示", "当前为独立 ELF 模式，请直接体检或打包。", parent=self.root)
            return
        proj = self.var_project_dir.get().strip()
        gcc = self.var_gcc.get().strip() or None
        self._log(f"开始编译工程: {proj}", "cmd")

        def task() -> None:
            elf_path, rep = build_project(proj, gcc_path=gcc, log_cb=lambda m: self._log(m))
            self.root.after(0, lambda: self._render_elf_report(rep, elf_path))
            if rep.ok:
                self._log(f"编译与 ABI 体检通过: {elf_path}", "ok")
            else:
                self._log(f"编译完成但 ABI 体检未通过 ({len(rep.errors)} 项问题)", "err")

        self._run_bg(task)

    def _action_check_only(self) -> None:
        elf_path = self._current_elf_path()
        if not elf_path or not os.path.isfile(elf_path):
            messagebox.showwarning("缺少 ELF", f"找不到目标文件: {elf_path}\n请先编译或选择一个 app.elf。", parent=self.root)
            return
        rep = self._run_elf_check_path(elf_path)
        if rep:
            self._log(
                f"ELF 体检完成: {os.path.basename(elf_path)} -> {'PASS' if rep.ok else 'FAIL'}",
                "ok" if rep.ok else "err",
            )

    def _action_pack_only(self) -> None:
        elf_path = self._current_elf_path()
        if not elf_path or not os.path.isfile(elf_path):
            messagebox.showwarning("缺少 ELF", f"找不到 {elf_path}，请先编译生成 app.elf。", parent=self.root)
            return
        try:
            manifest_obj = self._collect_manifest_dict()
        except Exception as exc:
            messagebox.showerror("配置校验失败", str(exc), parent=self.root)
            return

        out_pkg = self.var_out_pkg.get().strip()
        icon_p = self.var_icon_src.get().strip()
        compat = self.var_compat_swpk.get()

        def task() -> None:
            rep = check_elf_file(elf_path)
            self.root.after(0, lambda: self._render_elf_report(rep, elf_path))
            if not rep.ok:
                raise RuntimeError("ELF ABI 体检未通过，已拒绝打包；请先处理右侧红色拦截项。")
            info = pack_package(
                manifest_obj,
                elf_path,
                out_pkg,
                icon_path=icon_p,
                compat_swpk=compat,
                run_elf_check=True,
            )
            self._on_pack_succeeded(info)

        self._run_bg(task)

    def _action_build_and_pack(self) -> None:
        try:
            manifest_obj = self._collect_manifest_dict()
        except Exception as exc:
            messagebox.showerror("manifest 校验失败", str(exc), parent=self.root)
            return

        is_proj = self.var_mode.get() == "project"
        proj = self.var_project_dir.get().strip()
        gcc = self.var_gcc.get().strip() or None
        elf_path = self._current_elf_path()
        out_pkg = self.var_out_pkg.get().strip()
        icon_p = self.var_icon_src.get().strip()
        compat = self.var_compat_swpk.get()

        if is_proj and (not proj or not os.path.isdir(proj)):
            messagebox.showwarning("未选择工程", "请先选择一个有效的工程目录", parent=self.root)
            return

        self._log("开始一键编译、ELF 体检与打包...", "cmd")

        def task() -> None:
            nonlocal elf_path
            if is_proj:
                elf_path, rep = build_project(proj, gcc_path=gcc, log_cb=lambda m: self._log(m))
            else:
                if not elf_path or not os.path.isfile(elf_path):
                    raise FileNotFoundError(f"找不到 app.elf: {elf_path}")
                rep = check_elf_file(elf_path)

            self.root.after(0, lambda: self._render_elf_report(rep, elf_path))
            if not rep.ok:
                raise RuntimeError("ELF 预检未通过，已阻止生成 .gla 安装包，请检查右侧诊断错误。")

            info = pack_package(
                manifest_obj,
                elf_path,
                out_pkg,
                icon_path=icon_p,
                compat_swpk=compat,
                run_elf_check=True,
            )
            self._on_pack_succeeded(info)

        self._run_bg(task)

    def _on_pack_succeeded(self, info: Dict[str, Any]) -> None:
        self._log(
            f"[打包成功] {info['path']} ({info['total_size']} B) | magic={info['magic']} crc32=0x{info['crc32']:08X}",
            "ok",
        )

        def _ui_sync() -> None:
            self.var_inst_pkg.set(info["path"])
            self._inspect_pkg_path(info["path"])
            self._save_config()

        self.root.after(0, _ui_sync)

    # ------------------------------------------------------------------
    # Install Tab Actions
    # ------------------------------------------------------------------

    def _browse_install_pkg(self) -> None:
        p = filedialog.askopenfilename(
            title="选择 G'lam 应用安装包 (.gla / .spk)",
            filetypes=[("G'lam & Legacy Packages", "*.gla;*.spk"), ("All Files", "*.*")],
        )
        if p:
            self.var_inst_pkg.set(p)
            self._inspect_pkg_path(p)

    def _verify_selected_pkg(self) -> None:
        p = self.var_inst_pkg.get().strip()
        if not p or not os.path.isfile(p):
            messagebox.showwarning("文件不存在", "请先选择一个 .gla 或 .spk 安装包", parent=self.root)
            return
        self._inspect_pkg_path(p)

    def _inspect_pkg_path(self, pkg_path: str) -> None:
        try:
            info = verify_package(pkg_path, run_elf_check=True)
            m = info["manifest"]
            self.lbl_pkg_meta.configure(
                text=(
                    f"包头: {info['magic']}   |   ID: {info['id']}   |   名称: {info['name']}   |   版本: v{info['version']}\n"
                    f"总大小: {info['total_size']} B (ELF {info['elf_size']} B)   |   CRC32: 0x{info['crc32']:08X}   |   "
                    f"策略: {m.get('bg_policy', '-')}   |   图标: {'内嵌 40×40 JPG' if info['has_icon'] else '默认'}   |   ELF 体检: 通过"
                ),
                fg=OK_FG,
            )
            self._log(f"安装包校验通过: {os.path.basename(pkg_path)} ({info['id']} v{info['version']})", "ok")
        except Exception as exc:
            self.lbl_pkg_meta.configure(text=f"安装包校验失败: {exc}", fg=ERR_FG)
            self._log(f"安装包校验失败: {exc}", "err")

    def _refresh_ports_and_drives(self) -> None:
        ports = list_serial_ports()
        port_vals = [p["device"] for p in ports]
        self.cb_ports.configure(values=port_vals)
        if port_vals and self.var_serial_port.get().strip() not in port_vals:
            self.var_serial_port.set(port_vals[0])

        drives = list_removable_drives()
        self.cb_drives.configure(values=drives)
        if drives and not self.var_sd_drive.get().strip():
            self.var_sd_drive.set(drives[0])

    def _browse_sd_dir(self) -> None:
        d = filedialog.askdirectory(title="选择 TF 卡根目录")
        if d:
            self.var_sd_drive.set(d)

    def _open_web_installer(self) -> None:
        ip = self.var_wifi_ip.get().strip()
        if not ip:
            messagebox.showwarning("缺少 IP", "请输入设备局域网 IP 地址", parent=self.root)
            return
        url = ip if ip.startswith("http://") else f"http://{ip}/"
        webbrowser.open(url)

    def _action_install_wifi(self) -> None:
        pkg = self.var_inst_pkg.get().strip()
        ip = self.var_wifi_ip.get().strip()
        if not pkg or not os.path.isfile(pkg):
            messagebox.showwarning("缺少安装包", "请先选择有效的 .gla/.spk 安装包", parent=self.root)
            return
        if not ip:
            messagebox.showwarning("缺少 IP", "请输入设备的 Wi-Fi IP 地址", parent=self.root)
            return

        self.pbar.configure(value=20)
        self.var_inst_status.set(f"正在通过 Wi-Fi 上传到 {ip} ...")

        def task() -> None:
            res = install_via_wifi(ip, pkg, log_cb=lambda m: self._log(m))
            self.root.after(0, lambda: self._on_install_done(f"Wi-Fi 安装完成: {res['response']}"))

        self._run_bg(task)

    def _action_install_serial(self) -> None:
        pkg = self.var_inst_pkg.get().strip()
        port = self.var_serial_port.get().strip()
        if not pkg or not os.path.isfile(pkg):
            messagebox.showwarning("缺少安装包", "请先选择有效的 .gla/.spk 安装包", parent=self.root)
            return
        if not port:
            messagebox.showwarning("缺少串口", "请选择或刷新 USB 串口号 (如 COM7)", parent=self.root)
            return
        try:
            baud = int(self.var_serial_baud.get().strip() or "115200")
        except ValueError:
            baud = 115200
        legacy = self.var_serial_legacy.get()

        self.pbar.configure(value=0)
        self.var_inst_status.set(f"正在通过串口 {port} 发送数据包 ...")

        def on_prog(cur: int, total: int) -> None:
            pct = int(cur * 100 / total) if total else 100
            self.root.after(
                0,
                lambda: (
                    self.pbar.configure(value=pct),
                    self.var_inst_status.set(f"USB 串口传输中: {cur}/{total} B ({pct}%)"),
                ),
            )

        def task() -> None:
            info = install_via_serial(
                port,
                pkg,
                baud=baud,
                force_legacy_proto=legacy,
                progress_cb=on_prog,
                log_cb=lambda m: self._log(m),
            )
            self.root.after(0, lambda: self._on_install_done(f"USB 安装成功: {info['id']} (已写 TF 卡)"))

        self._run_bg(task)

    def _action_install_sd(self) -> None:
        pkg = self.var_inst_pkg.get().strip()
        sd = self.var_sd_drive.get().strip()
        if not pkg or not os.path.isfile(pkg):
            messagebox.showwarning("缺少安装包", "请先选择有效的 .gla/.spk 安装包", parent=self.root)
            return
        if not sd:
            messagebox.showwarning("缺少 TF 卡目录", "请选择可移动磁盘盘符或 TF 卡根目录", parent=self.root)
            return

        self.pbar.configure(value=30)
        self.var_inst_status.set(f"正在写入 TF 卡 {sd} ...")

        def task() -> None:
            info = install_via_sdcard(sd, pkg, log_cb=lambda m: self._log(m))
            self.root.after(0, lambda: self._on_install_done(f"TF 卡导入并解包完成: {info['id']}"))

        self._run_bg(task)

    def _on_install_done(self, msg: str) -> None:
        self.pbar.configure(value=100)
        self.var_inst_status.set(msg)
        self._log(msg, "ok")
        self._save_config()

    # ------------------------------------------------------------------
    # Device Manager & Live Screenshot Tab
    # ------------------------------------------------------------------

    def _action_refresh_device(self) -> None:
        ip = self.var_wifi_ip.get().strip()
        if not ip:
            messagebox.showwarning("缺少 IP", "请输入设备局域网 IP 地址", parent=self.root)
            return

        def task() -> None:
            info = wifi_get_info(ip)
            apps = wifi_list_apps(ip)

            def _apply() -> None:
                os_lbl = info.get("os", "G'lam OS")
                if info.get("legacy_firmware"):
                    os_lbl += " (旧固件)"
                self.var_dev_os.set(f"系统: {os_lbl}")
                psram = info.get("free_psram")
                sram = info.get("free_sram")
                if isinstance(psram, (int, float)) and isinstance(sram, (int, float)):
                    self.var_dev_mem.set(f"PSRAM: {psram / 1024:.0f} KB | SRAM: {sram / 1024:.0f} KB")
                else:
                    self.var_dev_mem.set(f"已安装: {len(apps)} 个应用")
                if "sd_mounted" in info:
                    self.var_dev_sd.set("TF 卡: 已挂载" if info["sd_mounted"] else "TF 卡: 未挂载")

                for item in self.tree_apps.get_children():
                    self.tree_apps.delete(item)
                for app in apps:
                    sz = app.get("elf_size", 0)
                    sz_str = f"{sz / 1024:.1f} KB" if sz else "--"
                    self.tree_apps.insert(
                        "",
                        "end",
                        values=(app.get("id", ""), app.get("name", ""), app.get("version", ""), sz_str),
                    )
                self._log(f"已刷新设备 ({ip})，共 {len(apps)} 个动态应用", "ok")

            self.root.after(0, _apply)

        self._run_bg(task)

    def _action_uninstall_selected(self) -> None:
        sel = self.tree_apps.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在左侧列表选中一个要卸载的应用", parent=self.root)
            return
        vals = self.tree_apps.item(sel[0], "values")
        app_id = str(vals[0])
        app_name = str(vals[1])
        ip = self.var_wifi_ip.get().strip()
        if not messagebox.askyesno("确认卸载", f"确定要从设备 TF 卡卸载「{app_name}」({app_id})？", parent=self.root):
            return

        def task() -> None:
            wifi_uninstall_app(ip, app_id)
            self._log(f"已远程卸载应用: {app_id}", "ok")
            self.root.after(0, self._action_refresh_device)

        self._run_bg(task)

    def _action_capture_screen(self) -> None:
        ip = self.var_wifi_ip.get().strip()
        if not ip:
            messagebox.showwarning("缺少 IP", "请输入设备局域网 IP 地址", parent=self.root)
            return

        def task() -> None:
            bmp = wifi_capture_screenshot(ip)
            self._last_bmp_bytes = bmp
            self.root.after(0, lambda b=bmp: self._display_bmp(b))

        self._run_bg(task)

    def _display_bmp(self, bmp_bytes: bytes) -> None:
        if not HAS_PIL:
            self._log("未安装 Pillow，无法直接渲染 BMP 预览，可使用“保存截图...”导出。", "warn")
            return
        try:
            with Image.open(io.BytesIO(bmp_bytes)) as im:
                scaled = im.resize((420, 315), Image.Resampling.NEAREST)
                self._img_screen = ImageTk.PhotoImage(scaled)
            self.cnv_screen.delete("all")
            self.cnv_screen.create_image(210, 157, image=self._img_screen)
        except Exception as exc:
            self._log(f"解码截图失败: {exc}", "err")

    def _toggle_auto_shot(self) -> None:
        if self._auto_shot_job:
            self.root.after_cancel(self._auto_shot_job)
            self._auto_shot_job = None
        if self.var_auto_shot.get():
            self._auto_shot_tick()

    def _auto_shot_tick(self) -> None:
        if not self.var_auto_shot.get():
            return
        ip = self.var_wifi_ip.get().strip()
        if ip:
            def task() -> None:
                try:
                    bmp = wifi_capture_screenshot(ip)
                    self._last_bmp_bytes = bmp
                    self.root.after(0, lambda b=bmp: self._display_bmp(b))
                except Exception:
                    pass

            threading.Thread(target=task, daemon=True).start()
        self._auto_shot_job = self.root.after(2000, self._auto_shot_tick)

    def _save_screenshot_file(self) -> None:
        if not self._last_bmp_bytes:
            messagebox.showinfo("提示", "请先点击“抓取屏幕”获取画面", parent=self.root)
            return
        p = filedialog.asksaveasfilename(
            title="保存设备截图",
            defaultextension=".bmp",
            initialfile="glam_screen.bmp",
            filetypes=[("BMP Image", "*.bmp"), ("PNG Image", "*.png")],
        )
        if not p:
            return
        if p.lower().endswith(".png") and HAS_PIL:
            with Image.open(io.BytesIO(self._last_bmp_bytes)) as im:
                im.save(p, format="PNG")
        else:
            with open(p, "wb") as f:
                f.write(self._last_bmp_bytes)
        self._log(f"截图已保存: {p}", "ok")


def main() -> int:
    _enable_windows_dpi_awareness()
    root = tk.Tk()
    GlamStudioApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
