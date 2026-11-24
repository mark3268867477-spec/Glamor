"""
Windows PC Execution Engine & Dual-Channel XiaoZhi MCP Bridge for G'lamor.

Supports:
  - Channel A: USB Serial (UART0 / USB-Serial/JTAG) newline-delimited JSON bridge
  - Channel B: Wi-Fi LAN HTTP bridge (/api/pc_mcp/poll & /api/pc_mcp/reply)
  - Full Windows control: apps, windows, browsers, keyboard/mouse, volume/media,
    screenshots, files, clipboard, PowerShell, and external stdio MCP servers.
"""

from __future__ import annotations

import atexit
import base64
import ctypes
import ctypes.wintypes as wt
import datetime
import difflib
import http.client
import ipaddress
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from typing import Any, Callable, Dict, List, Optional, Tuple

from .serial_port import SerialLink, list_serial_ports

_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

DEFAULT_MCP_SERVERS_JSON = json.dumps(
    {
        "mcpServers": {
            # 示例：挂载外部标准 stdio MCP Server（取消注释或新增配置后点击“重载外部 MCP”）
            # "filesystem": {
            #     "command": "npx",
            #     "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:\\Users\\Public"]
            # }
        }
    },
    ensure_ascii=False,
    indent=2,
)

BROWSER_PROCESSES = {
    "msedge.exe",
    "chrome.exe",
    "firefox.exe",
    "brave.exe",
    "opera.exe",
    "vivaldi.exe",
    "360se.exe",
    "360chrome.exe",
    "qqbrowser.exe",
    "sogouexplorer.exe",
}

SITE_SHORTCUTS = {
    "bilibili": "https://www.bilibili.com",
    "b站": "https://www.bilibili.com",
    "哔哩哔哩": "https://www.bilibili.com",
    "baidu": "https://www.baidu.com",
    "百度": "https://www.baidu.com",
    "bing": "https://www.bing.com",
    "必应": "https://www.bing.com",
    "google": "https://www.google.com",
    "谷歌": "https://www.google.com",
    "github": "https://github.com",
    "zhihu": "https://www.zhihu.com",
    "知乎": "https://www.zhihu.com",
    "youtube": "https://www.youtube.com",
    "油管": "https://www.youtube.com",
    "douyin": "https://www.douyin.com",
    "抖音": "https://www.douyin.com",
    "xiaohongshu": "https://www.xiaohongshu.com",
    "小红书": "https://www.xiaohongshu.com",
    "weibo": "https://weibo.com",
    "微博": "https://weibo.com",
    "taobao": "https://www.taobao.com",
    "淘宝": "https://www.taobao.com",
    "jd": "https://www.jd.com",
    "京东": "https://www.jd.com",
    "chatgpt": "https://chatgpt.com",
    "deepseek": "https://chat.deepseek.com",
}

SEARCH_ENGINES = {
    "bing": "https://www.bing.com/search?q={q}",
    "必应": "https://www.bing.com/search?q={q}",
    "baidu": "https://www.baidu.com/s?wd={q}",
    "百度": "https://www.baidu.com/s?wd={q}",
    "google": "https://www.google.com/search?q={q}",
    "谷歌": "https://www.google.com/search?q={q}",
    "bilibili": "https://search.bilibili.com/all?keyword={q}",
    "b站": "https://search.bilibili.com/all?keyword={q}",
    "哔哩哔哩": "https://search.bilibili.com/all?keyword={q}",
    "github": "https://github.com/search?q={q}",
    "zhihu": "https://www.zhihu.com/search?type=content&q={q}",
    "知乎": "https://www.zhihu.com/search?type=content&q={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "油管": "https://www.youtube.com/results?search_query={q}",
    "douyin": "https://www.douyin.com/search/{q}",
    "抖音": "https://www.douyin.com/search/{q}",
}

APP_ALIASES: Dict[str, List[str]] = {
    "记事本": ["notepad.exe", "notepad"],
    "notepad": ["notepad.exe"],
    "计算器": ["calc.exe", "calc"],
    "calc": ["calc.exe"],
    "画图": ["mspaint.exe", "mspaint"],
    "mspaint": ["mspaint.exe"],
    "命令行": ["cmd.exe", "cmd"],
    "cmd": ["cmd.exe"],
    "powershell": ["powershell.exe", "pwsh.exe"],
    "终端": ["wt.exe", "powershell.exe", "cmd.exe"],
    "terminal": ["wt.exe", "powershell.exe"],
    "wt": ["wt.exe"],
    "任务管理器": ["taskmgr.exe"],
    "taskmgr": ["taskmgr.exe"],
    "控制面板": ["control.exe"],
    "control": ["control.exe"],
    "设置": ["ms-settings:"],
    "系统设置": ["ms-settings:"],
    "settings": ["ms-settings:"],
    "资源管理器": ["explorer.exe"],
    "文件管理器": ["explorer.exe"],
    "我的电脑": ["explorer.exe"],
    "explorer": ["explorer.exe"],
    "截图": ["ms-screenclip:"],
    "edge": ["msedge.exe", "microsoft edge"],
    "微软浏览器": ["msedge.exe", "microsoft edge"],
    "chrome": ["chrome.exe", "google chrome"],
    "谷歌浏览器": ["chrome.exe", "google chrome"],
    "firefox": ["firefox.exe", "mozilla firefox"],
    "火狐": ["firefox.exe", "mozilla firefox"],
    "vscode": ["code.exe", "visual studio code", "code"],
    "vs code": ["code.exe", "visual studio code", "code"],
    "code": ["code.exe", "visual studio code", "code"],
    "微信": ["wechat.exe", "weixin.exe", "wechat", "微信"],
    "wechat": ["wechat.exe", "weixin.exe", "wechat", "微信"],
    "qq": ["qq.exe", "qq"],
    "钉钉": ["dingtalk.exe", "dingtalk", "钉钉"],
    "飞书": ["feishu.exe", "lark.exe", "飞书"],
    "企业微信": ["wxwork.exe", "企业微信"],
    "网易云音乐": ["cloudmusic.exe", "网易云音乐"],
    "网易云": ["cloudmusic.exe", "网易云音乐"],
    "qq音乐": ["qqmusic.exe", "qq音乐"],
    "酷狗音乐": ["kugou.exe", "酷狗音乐"],
    "word": ["winword.exe", "word"],
    "excel": ["excel.exe", "excel"],
    "ppt": ["powerpnt.exe", "powerpoint"],
    "powerpoint": ["powerpnt.exe", "powerpoint"],
    "steam": ["steam.exe", "steam"],
    "cursor": ["cursor.exe", "cursor"],
    "trae": ["trae.exe", "trae"],
    "obsidian": ["obsidian.exe", "obsidian"],
    "typora": ["typora.exe", "typora"],
    "potplayer": ["potplayermini64.exe", "potplayer.exe", "potplayer"],
    "vlc": ["vlc.exe", "vlc"],
}


def _truncate_text(text: str, limit: int = 3200) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...(已截断，总长 {len(text)} 字符)"


def _is_lan_url(url: str) -> bool:
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return False
    if not host:
        return False
    low = host.lower()
    if low == "localhost" or low.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


def _http_open(req_or_url: Any, timeout: float):
    url = req_or_url.full_url if isinstance(req_or_url, urllib.request.Request) else str(req_or_url)
    if _is_lan_url(url):
        return _DIRECT_OPENER.open(req_or_url, timeout=timeout)
    return urllib.request.urlopen(req_or_url, timeout=timeout)


def _norm_host(host: str) -> str:
    h = host.strip()
    if not h:
        raise ValueError("设备 Wi-Fi IP 不能为空")
    if not h.startswith("http://") and not h.startswith("https://"):
        h = "http://" + h
    return h.rstrip("/")


# =============================================================================
# Windows Native Win32 Helpers (ctypes)
# =============================================================================

if os.name == "nt":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _ole32 = ctypes.WinDLL("ole32", use_last_error=True)

    # Enable Per-Monitor v2 DPI awareness so physical pixels match UIA & screen capture
    try:
        _user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        _user32.SetProcessDpiAwarenessContext.restype = wt.BOOL
        if not _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            _user32.SetProcessDPIAware()
    except Exception:
        try:
            _user32.SetProcessDPIAware()
        except Exception:
            pass

    # Proper 64-bit safe argtypes / restypes
    _kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    _kernel32.OpenProcess.restype = wt.HANDLE
    _kernel32.GetCurrentThreadId.argtypes = []
    _kernel32.GetCurrentThreadId.restype = wt.DWORD
    _kernel32.CloseHandle.argtypes = [wt.HANDLE]
    _kernel32.CloseHandle.restype = wt.BOOL
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)
    ]
    _kernel32.QueryFullProcessImageNameW.restype = wt.BOOL
    _kernel32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
    _kernel32.GlobalAlloc.restype = wt.HGLOBAL
    _kernel32.GlobalLock.argtypes = [wt.HGLOBAL]
    _kernel32.GlobalLock.restype = ctypes.c_void_p
    _kernel32.GlobalUnlock.argtypes = [wt.HGLOBAL]
    _kernel32.GlobalUnlock.restype = wt.BOOL
    _kernel32.GlobalFree.argtypes = [wt.HGLOBAL]
    _kernel32.GlobalFree.restype = wt.HGLOBAL

    _user32.OpenClipboard.argtypes = [wt.HWND]
    _user32.OpenClipboard.restype = wt.BOOL
    _user32.CloseClipboard.argtypes = []
    _user32.CloseClipboard.restype = wt.BOOL
    _user32.EmptyClipboard.argtypes = []
    _user32.EmptyClipboard.restype = wt.BOOL
    _user32.GetClipboardData.argtypes = [wt.UINT]
    _user32.GetClipboardData.restype = wt.HANDLE
    _user32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
    _user32.SetClipboardData.restype = wt.HANDLE
    _user32.IsClipboardFormatAvailable.argtypes = [wt.UINT]
    _user32.IsClipboardFormatAvailable.restype = wt.BOOL

    _user32.GetForegroundWindow.argtypes = []
    _user32.GetForegroundWindow.restype = wt.HWND
    _user32.SetForegroundWindow.argtypes = [wt.HWND]
    _user32.SetForegroundWindow.restype = wt.BOOL
    _user32.BringWindowToTop.argtypes = [wt.HWND]
    _user32.BringWindowToTop.restype = wt.BOOL
    _user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    _user32.ShowWindow.restype = wt.BOOL
    _user32.IsIconic.argtypes = [wt.HWND]
    _user32.IsIconic.restype = wt.BOOL
    _user32.IsWindowVisible.argtypes = [wt.HWND]
    _user32.IsWindowVisible.restype = wt.BOOL
    _user32.GetWindowTextLengthW.argtypes = [wt.HWND]
    _user32.GetWindowTextLengthW.restype = ctypes.c_int
    _user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    _user32.GetWindowTextW.restype = ctypes.c_int
    _user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wt.DWORD
    _user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
    _user32.AttachThreadInput.restype = wt.BOOL
    _user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    _user32.PostMessageW.restype = wt.BOOL
    _user32.keybd_event.argtypes = [wt.BYTE, wt.BYTE, wt.DWORD, ctypes.c_size_t]
    _user32.keybd_event.restype = None
    _user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    _user32.SetCursorPos.restype = wt.BOOL
    _user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
    _user32.GetCursorPos.restype = wt.BOOL
    _user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    _user32.GetSystemMetrics.restype = ctypes.c_int
    _user32.mouse_event.argtypes = [wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_long, ctypes.c_size_t]
    _user32.mouse_event.restype = None
    _user32.LockWorkStation.argtypes = []
    _user32.LockWorkStation.restype = wt.BOOL

    _ENUM_PROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    _user32.EnumWindows.argtypes = [_ENUM_PROC, wt.LPARAM]
    _user32.EnumWindows.restype = wt.BOOL

    class _MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", wt.DWORD),
            ("dwMemoryLoad", wt.DWORD),
            ("ullTotalPhys", ctypes.c_uint64),
            ("ullAvailPhys", ctypes.c_uint64),
            ("ullTotalPageFile", ctypes.c_uint64),
            ("ullAvailPageFile", ctypes.c_uint64),
            ("ullTotalVirtual", ctypes.c_uint64),
            ("ullAvailVirtual", ctypes.c_uint64),
            ("sullAvailExtendedVirtual", ctypes.c_uint64),
        ]

    class _SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", wt.BYTE),
            ("BatteryFlag", wt.BYTE),
            ("BatteryLifePercent", wt.BYTE),
            ("SystemStatusFlag", wt.BYTE),
            ("BatteryLifeTime", wt.DWORD),
            ("BatteryFullLifeTime", wt.DWORD),
        ]

    _kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(_MEMORYSTATUSEX)]
    _kernel32.GlobalMemoryStatusEx.restype = wt.BOOL
    _kernel32.GetSystemPowerStatus.argtypes = [ctypes.POINTER(_SYSTEM_POWER_STATUS)]
    _kernel32.GetSystemPowerStatus.restype = wt.BOOL

    VK_MAP: Dict[str, int] = {
        "ctrl": 0x11, "control": 0x11, "lctrl": 0xA2, "rctrl": 0xA3,
        "shift": 0x10, "lshift": 0xA0, "rshift": 0xA1,
        "alt": 0x12, "menu": 0x12, "lalt": 0xA4, "ralt": 0xA5,
        "win": 0x5B, "windows": 0x5B, "super": 0x5B, "lwin": 0x5B, "rwin": 0x5C,
        "enter": 0x0D, "return": 0x0D,
        "esc": 0x1B, "escape": 0x1B,
        "tab": 0x09,
        "space": 0x20,
        "backspace": 0x08, "back": 0x08,
        "delete": 0x2E, "del": 0x2E,
        "insert": 0x2D, "ins": 0x2D,
        "home": 0x24, "end": 0x23,
        "pgup": 0x21, "pageup": 0x21, "page_up": 0x21,
        "pgdn": 0x22, "pagedown": 0x22, "page_down": 0x22,
        "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
        "capslock": 0x14, "prtsc": 0x2C, "printscreen": 0x2C,
        "volume_mute": 0xAD, "mute": 0xAD,
        "volume_down": 0xAE, "volume_up": 0xAF,
        "media_next": 0xB0, "media_prev": 0xB1, "media_stop": 0xB2, "media_play_pause": 0xB3,
        "plus": 0xBB, "=": 0xBB, "minus": 0xBD, "-": 0xBD,
        ",": 0xBC, ".": 0xBE, "/": 0xBF, ";": 0xBA, "[": 0xDB, "]": 0xDD,
    }
    for _c in range(ord("a"), ord("z") + 1):
        VK_MAP[chr(_c)] = ord(chr(_c).upper())
    for _d in range(0, 10):
        VK_MAP[str(_d)] = ord(str(_d))
    for _f in range(1, 13):
        VK_MAP[f"f{_f}"] = 0x6F + _f


def _win32_get_process_name(pid: int) -> str:
    if os.name != "nt" or not pid:
        return ""
    h = _kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        sz = wt.DWORD(512)
        if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(sz)):
            return os.path.basename(buf.value)
        return ""
    finally:
        _kernel32.CloseHandle(h)


def win32_list_windows() -> List[Dict[str, Any]]:
    if os.name != "nt":
        return []
    items: List[Dict[str, Any]] = []

    def _cb(hwnd, _lparam) -> bool:
        if not _user32.IsWindowVisible(hwnd):
            return True
        length = _user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title or title in ("Program Manager", "Windows Input Experience"):
            return True
        pid = wt.DWORD(0)
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc = _win32_get_process_name(int(pid.value))
        items.append({
            "hwnd": int(hwnd),
            "title": title,
            "pid": int(pid.value),
            "process": proc,
        })
        return True

    proc_cb = _ENUM_PROC(_cb)
    _user32.EnumWindows(proc_cb, 0)
    return items


def win32_get_foreground_info() -> Dict[str, Any]:
    if os.name != "nt":
        return {"title": "", "process": "", "hwnd": 0}
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return {"title": "", "process": "", "hwnd": 0}
    length = _user32.GetWindowTextLengthW(hwnd)
    title = ""
    if length > 0:
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
    pid = wt.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return {
        "hwnd": int(hwnd),
        "title": title,
        "pid": int(pid.value),
        "process": _win32_get_process_name(int(pid.value)),
    }


def win32_focus_window(hwnd: int) -> bool:
    if os.name != "nt" or not hwnd:
        return False
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    fg = _user32.GetForegroundWindow()
    cur_tid = _kernel32.GetCurrentThreadId()
    fg_tid = _user32.GetWindowThreadProcessId(fg, None) if fg else 0
    tgt_tid = _user32.GetWindowThreadProcessId(hwnd, None)
    if fg_tid and fg_tid != cur_tid:
        _user32.AttachThreadInput(fg_tid, cur_tid, True)
    if tgt_tid and tgt_tid != cur_tid:
        _user32.AttachThreadInput(tgt_tid, cur_tid, True)
    try:
        _user32.BringWindowToTop(hwnd)
        ok = bool(_user32.SetForegroundWindow(hwnd))
        if not ok:
            # Alt tap bypasses Windows foreground lock if needed
            _user32.keybd_event(0x12, 0, 0, 0)
            _user32.keybd_event(0x12, 0, 2, 0)
            ok = bool(_user32.SetForegroundWindow(hwnd))
        return ok
    finally:
        if fg_tid and fg_tid != cur_tid:
            _user32.AttachThreadInput(fg_tid, cur_tid, False)
        if tgt_tid and tgt_tid != cur_tid:
            _user32.AttachThreadInput(tgt_tid, cur_tid, False)


def win32_get_clipboard() -> str:
    if os.name != "nt":
        return ""
    CF_UNICODETEXT = 13
    for _ in range(5):
        if _user32.OpenClipboard(None):
            try:
                if not _user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                    return ""
                h = _user32.GetClipboardData(CF_UNICODETEXT)
                if not h:
                    return ""
                ptr = _kernel32.GlobalLock(h)
                if not ptr:
                    return ""
                try:
                    return ctypes.wstring_at(ptr)
                finally:
                    _kernel32.GlobalUnlock(h)
            finally:
                _user32.CloseClipboard()
        time.sleep(0.02)
    return ""


def win32_set_clipboard(text: str) -> bool:
    if os.name != "nt":
        return False
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    data = (text + "\x00").encode("utf-16-le")
    for _ in range(5):
        if _user32.OpenClipboard(None):
            try:
                _user32.EmptyClipboard()
                hmem = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
                if not hmem:
                    return False
                ptr = _kernel32.GlobalLock(hmem)
                if not ptr:
                    _kernel32.GlobalFree(hmem)
                    return False
                try:
                    ctypes.memmove(ptr, data, len(data))
                finally:
                    _kernel32.GlobalUnlock(hmem)
                if not _user32.SetClipboardData(CF_UNICODETEXT, hmem):
                    _kernel32.GlobalFree(hmem)
                    return False
                return True
            finally:
                _user32.CloseClipboard()
        time.sleep(0.02)
    return False


def win32_send_hotkey(keys_str: str) -> None:
    if os.name != "nt":
        return
    parts = [p.strip().lower() for p in re.split(r"[+\s]+", keys_str.strip()) if p.strip()]
    if not parts:
        raise ValueError("按键序列不能为空")
    vks: List[int] = []
    for p in parts:
        if p not in VK_MAP:
            raise ValueError(f"不支持的按键名: {p}")
        vks.append(VK_MAP[p])
    EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5C, 0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3}
    for vk in vks:
        flags = 0x0001 if vk in EXTENDED_VKS else 0
        _user32.keybd_event(vk, 0, flags, 0)
        time.sleep(0.015)
    time.sleep(0.025)
    for vk in reversed(vks):
        flags = (0x0001 if vk in EXTENDED_VKS else 0) | 0x0002
        _user32.keybd_event(vk, 0, flags, 0)
        time.sleep(0.015)


def win32_type_text(text: str, press_enter: bool = False) -> None:
    if os.name != "nt":
        return
    old_clip = win32_get_clipboard()
    if win32_set_clipboard(text):
        time.sleep(0.03)
        win32_send_hotkey("ctrl+v")
        time.sleep(0.14)
        if old_clip:
            win32_set_clipboard(old_clip)
    if press_enter:
        time.sleep(0.04)
        win32_send_hotkey("enter")


def win32_get_screen_size() -> Tuple[int, int]:
    if os.name != "nt":
        return 1920, 1080
    w = int(_user32.GetSystemMetrics(0) or 1920)
    h = int(_user32.GetSystemMetrics(1) or 1080)
    return max(w, 1), max(h, 1)


def win32_get_cursor_pos() -> Optional[Tuple[int, int]]:
    if os.name != "nt":
        return None
    pt = wt.POINT()
    if _user32.GetCursorPos(ctypes.byref(pt)):
        return int(pt.x), int(pt.y)
    return None


def norm_to_screen_xy(nx: float, ny: float) -> Tuple[int, int]:
    sw, sh = win32_get_screen_size()
    cx = max(0.0, min(1000.0, float(nx)))
    cy = max(0.0, min(1000.0, float(ny)))
    px = int(round((cx / 1000.0) * max(sw - 1, 1)))
    py = int(round((cy / 1000.0) * max(sh - 1, 1)))
    return px, py


def _run_ps_encoded(script: str, timeout: float = 8.0) -> str:
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", encoding="utf-8-sig", delete=False) as tf:
            tf.write("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n" + script)
            tmp_path = tf.name
        kwargs: Dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "timeout": timeout,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", tmp_path],
            **kwargs,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(err or f"PowerShell exited {proc.returncode}")
        return (proc.stdout or "").strip()
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


_PS_UIA_PREAMBLE = r'''
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,WindowsBase,System.Drawing,System.Windows.Forms
$refs = @(
    ([System.Windows.Automation.AutomationElement].Assembly.Location),
    ([System.Windows.Automation.ControlType].Assembly.Location),
    ([System.Drawing.Bitmap].Assembly.Location),
    ([System.Windows.Forms.Screen].Assembly.Location),
    ([System.Windows.Rect].Assembly.Location)
) | Select-Object -Unique
$cs = @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows;
using System.Windows.Automation;

public static class GlamUiaBridge {
    [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr val);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int nIndex);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();

    public static void EnsureDpi() {
        try {
            if (!SetProcessDpiAwarenessContext(new IntPtr(-4))) SetProcessDPIAware();
        } catch {
            try { SetProcessDPIAware(); } catch {}
        }
    }

    private static string Esc(string s) {
        if (string.IsNullOrEmpty(s)) return "";
        StringBuilder sb = new StringBuilder(s.Length + 8);
        foreach (char c in s) {
            if (c == '\\') sb.Append("\\\\");
            else if (c == '"') sb.Append("\\\"");
            else if (c == '\r' || c == '\n' || c == '\t') sb.Append(' ');
            else if (c < 32) continue;
            else sb.Append(c);
        }
        return sb.ToString();
    }

    private sealed class Item {
        public string Role;
        public string Name;
        public int X1, Y1, X2, Y2;
    }

    private static List<Item> CollectItems(AutomationElement root, int sw, int sh, int maxItems, int budgetMs, out string winTitle) {
        winTitle = "";
        try { winTitle = root.Current.Name ?? ""; } catch {}

        var allowed = new HashSet<string>(StringComparer.OrdinalIgnoreCase) {
            "Button", "Edit", "MenuItem", "TabItem", "CheckBox",
            "RadioButton", "ComboBox", "Hyperlink", "ListItem",
            "TreeItem", "Document", "Slider", "Spinner", "SplitButton"
        };

        var items = new List<Item>();
        var q = new Queue<KeyValuePair<AutomationElement, int>>();
        q.Enqueue(new KeyValuePair<AutomationElement, int>(root, 0));
        TreeWalker walker = TreeWalker.ControlViewWalker;
        Stopwatch watch = Stopwatch.StartNew();
        int visited = 0;

        while (q.Count > 0 && visited < 380 && watch.ElapsedMilliseconds < budgetMs && items.Count < maxItems * 3) {
            var cur = q.Dequeue();
            AutomationElement el = cur.Key;
            int depth = cur.Value;
            visited++;

            try {
                if (el != root) {
                    var info = el.Current;
                    if (!info.IsOffscreen && info.IsEnabled) {
                        string role = info.ControlType != null ? (info.ControlType.ProgrammaticName ?? "") : "";
                        if (role.StartsWith("ControlType.")) role = role.Substring(12);
                        if (allowed.Contains(role)) {
                            Rect r = info.BoundingRectangle;
                            if (!r.IsEmpty && !double.IsNaN(r.Left) && !double.IsInfinity(r.Left) &&
                                !double.IsNaN(r.Top) && !double.IsInfinity(r.Top) &&
                                !double.IsNaN(r.Width) && !double.IsInfinity(r.Width) &&
                                !double.IsNaN(r.Height) && !double.IsInfinity(r.Height) &&
                                r.Width >= 8 && r.Height >= 8) {
                                int x1 = Math.Max(0, (int)Math.Round(r.Left));
                                int y1 = Math.Max(0, (int)Math.Round(r.Top));
                                int x2 = Math.Min(sw, (int)Math.Round(r.Right));
                                int y2 = Math.Min(sh, (int)Math.Round(r.Bottom));
                                int rw = x2 - x1, rh = y2 - y1;
                                bool tooBig = (rw > sw * 0.96 && rh > sh * 0.95 && role != "Edit" && role != "Document");
                                if (rw >= 8 && rh >= 8 && !tooBig) {
                                    string nm = (info.Name ?? "").Trim();
                                    bool isInput = (role == "Edit" || role == "Document" || role == "ComboBox" || role == "CheckBox");
                                    if (!string.IsNullOrEmpty(nm) || isInput) {
                                        if (string.IsNullOrEmpty(nm)) nm = role == "ComboBox" ? "下拉框" : "输入框";
                                        if (nm.Length > 48) nm = nm.Substring(0, 48);
                                        int cx = (x1 + x2) / 2, cy = (y1 + y2) / 2;
                                        bool dup = false;
                                        for (int j = items.Count - 1; j >= 0 && j >= items.Count - 12; j--) {
                                            int ocx = (items[j].X1 + items[j].X2) / 2;
                                            int ocy = (items[j].Y1 + items[j].Y2) / 2;
                                            if (Math.Abs(cx - ocx) <= 6 && Math.Abs(cy - ocy) <= 6 && items[j].Role == role) {
                                                dup = true; break;
                                            }
                                        }
                                        if (!dup) {
                                            items.Add(new Item { Role = role, Name = nm, X1 = x1, Y1 = y1, X2 = x2, Y2 = y2 });
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            } catch {}

            if (depth >= 9) continue;
            try {
                AutomationElement child = walker.GetFirstChild(el);
                int childCount = 0;
                while (child != null && childCount < 40 && watch.ElapsedMilliseconds < budgetMs) {
                    q.Enqueue(new KeyValuePair<AutomationElement, int>(child, depth + 1));
                    childCount++;
                    child = walker.GetNextSibling(child);
                }
            } catch {}
        }

        items.Sort((a, b) => {
            int ya = a.Y1 / 24, yb = b.Y1 / 24;
            if (ya != yb) return ya.CompareTo(yb);
            return a.X1.CompareTo(b.X1);
        });
        if (items.Count > maxItems) items.RemoveRange(maxItems, items.Count - maxItems);
        return items;
    }

    private static string ItemsToJson(string winTitle, int sw, int sh, List<Item> items) {
        StringBuilder outSb = new StringBuilder(2048);
        outSb.Append("{\"title\":\"").Append(Esc(winTitle)).Append("\",\"sw\":").Append(sw).Append(",\"sh\":").Append(sh).Append(",\"elements\":[");
        for (int i = 0; i < items.Count; i++) {
            Item it = items[i];
            int cx = (it.X1 + it.X2) / 2, cy = (it.Y1 + it.Y2) / 2;
            int nx = (int)Math.Round(cx * 1000.0 / sw);
            int ny = (int)Math.Round(cy * 1000.0 / sh);
            if (i > 0) outSb.Append(',');
            outSb.Append("{\"id\":").Append(i + 1)
                 .Append(",\"role\":\"").Append(Esc(it.Role)).Append('"')
                 .Append(",\"name\":\"").Append(Esc(it.Name)).Append('"')
                 .Append(",\"rect\":[").Append(it.X1).Append(',').Append(it.Y1).Append(',').Append(it.X2).Append(',').Append(it.Y2).Append(']')
                 .Append(",\"cx\":").Append(cx).Append(",\"cy\":").Append(cy)
                 .Append(",\"nx\":").Append(nx).Append(",\"ny\":").Append(ny)
                 .Append('}');
        }
        outSb.Append("]}");
        return outSb.ToString();
    }

    public static string Inspect(long hwndVal, int maxItems, int budgetMs) {
        EnsureDpi();
        int sw = Math.Max(GetSystemMetrics(0), 1);
        int sh = Math.Max(GetSystemMetrics(1), 1);
        IntPtr hwnd = hwndVal != 0 ? new IntPtr(hwndVal) : GetForegroundWindow();
        if (hwnd == IntPtr.Zero) {
            return "{\"title\":\"\",\"sw\":" + sw + ",\"sh\":" + sh + ",\"elements\":[]}";
        }
        AutomationElement root = AutomationElement.FromHandle(hwnd);
        if (root == null) {
            return "{\"title\":\"\",\"sw\":" + sw + ",\"sh\":" + sh + ",\"elements\":[]}";
        }
        string winTitle;
        var items = CollectItems(root, sw, sh, maxItems, budgetMs, out winTitle);
        return ItemsToJson(winTitle, sw, sh, items);
    }

    public static string InspectAndCapture(long hwndVal, int maxItems, int budgetMs, int maxWidth, int quality) {
        EnsureDpi();
        int sw = Math.Max(GetSystemMetrics(0), 1);
        int sh = Math.Max(GetSystemMetrics(1), 1);
        string jsonPart = "{\"title\":\"\",\"sw\":" + sw + ",\"sh\":" + sh + ",\"elements\":[]}";
        StringBuilder rectSb = new StringBuilder();
        try {
            IntPtr hwnd = hwndVal != 0 ? new IntPtr(hwndVal) : GetForegroundWindow();
            if (hwnd != IntPtr.Zero) {
                AutomationElement root = AutomationElement.FromHandle(hwnd);
                if (root != null) {
                    string winTitle;
                    var items = CollectItems(root, sw, sh, maxItems, budgetMs, out winTitle);
                    jsonPart = ItemsToJson(winTitle, sw, sh, items);
                    for (int i = 0; i < items.Count; i++) {
                        Item it = items[i];
                        if (i > 0) rectSb.Append(';');
                        rectSb.Append(i + 1).Append(',').Append(it.X1).Append(',').Append(it.Y1).Append(',').Append(it.X2).Append(',').Append(it.Y2);
                    }
                }
            }
        } catch {}
        string somPart;
        try {
            somPart = CaptureSom(rectSb.ToString(), maxWidth, quality);
        } catch (Exception ex) {
            somPart = "ERR:" + (ex.Message ?? "capture failed").Replace('\r', ' ').Replace('\n', ' ');
        }
        return jsonPart + "\t" + somPart;
    }

    public static string EncodeSomBitmap(Bitmap raw, int sw, int sh, string rectsSpec, int maxWidth, int quality) {
        using (Graphics g = Graphics.FromImage(raw)) {
            if (!string.IsNullOrEmpty(rectsSpec)) {
                using (Pen pen = new Pen(Color.FromArgb(230, 239, 68, 68), 2.0f))
                using (SolidBrush badgeBg = new SolidBrush(Color.FromArgb(225, 220, 38, 38)))
                using (SolidBrush badgeFg = new SolidBrush(Color.White))
                using (Font font = new Font("Consolas", 11.0f, System.Drawing.FontStyle.Bold)) {
                    string[] parts = rectsSpec.Split(';');
                    foreach (string part in parts) {
                        if (string.IsNullOrWhiteSpace(part)) continue;
                        string[] tok = part.Split(',');
                        if (tok.Length < 5) continue;
                        int id, x1, y1, x2, y2;
                        if (!int.TryParse(tok[0], out id) || !int.TryParse(tok[1], out x1) ||
                            !int.TryParse(tok[2], out y1) || !int.TryParse(tok[3], out x2) || !int.TryParse(tok[4], out y2)) continue;
                        int w = Math.Max(2, x2 - x1), h = Math.Max(2, y2 - y1);
                        g.DrawRectangle(pen, x1, y1, w, h);
                        string lbl = "[" + id + "]";
                        SizeF sz = g.MeasureString(lbl, font);
                        int bx = Math.Max(0, Math.Min(sw - (int)sz.Width - 4, x1));
                        int by = y1 >= (int)sz.Height ? (y1 - (int)sz.Height) : y1;
                        g.FillRectangle(badgeBg, bx, by, (int)sz.Width + 2, (int)sz.Height);
                        g.DrawString(lbl, font, badgeFg, bx + 1, by);
                    }
                }
            }
        }
        int tw = sw, th = sh;
        if (maxWidth > 0 && sw > maxWidth) {
            tw = maxWidth;
            th = Math.Max(1, (int)Math.Round(sh * (tw / (double)sw)));
        }
        Bitmap finalBmp = raw;
        Bitmap resized = null;
        if (tw != sw) {
            resized = new Bitmap(tw, th, PixelFormat.Format24bppRgb);
            using (Graphics rg = Graphics.FromImage(resized)) {
                rg.InterpolationMode = InterpolationMode.HighQualityBicubic;
                rg.DrawImage(raw, 0, 0, tw, th);
            }
            finalBmp = resized;
        }
        try {
            ImageCodecInfo jpgCodec = null;
            foreach (var c in ImageCodecInfo.GetImageEncoders()) {
                if (c.MimeType == "image/jpeg") { jpgCodec = c; break; }
            }
            using (MemoryStream ms = new MemoryStream()) {
                if (jpgCodec != null) {
                    using (EncoderParameters ep = new EncoderParameters(1)) {
                        ep.Param[0] = new EncoderParameter(System.Drawing.Imaging.Encoder.Quality, (long)Math.Max(30, Math.Min(95, quality)));
                        finalBmp.Save(ms, jpgCodec, ep);
                    }
                } else {
                    finalBmp.Save(ms, ImageFormat.Jpeg);
                }
                string b64 = Convert.ToBase64String(ms.ToArray());
                return sw + "|" + sh + "|" + b64;
            }
        } finally {
            if (resized != null) resized.Dispose();
        }
    }

    public static string CaptureSom(string rectsSpec, int maxWidth, int quality) {
        EnsureDpi();
        int sw = Math.Max(GetSystemMetrics(0), 1);
        int sh = Math.Max(GetSystemMetrics(1), 1);
        using (Bitmap raw = new Bitmap(sw, sh, PixelFormat.Format24bppRgb)) {
            using (Graphics g = Graphics.FromImage(raw)) {
                g.CopyFromScreen(0, 0, 0, 0, new System.Drawing.Size(sw, sh), CopyPixelOperation.SourceCopy);
            }
            return EncodeSomBitmap(raw, sw, sh, rectsSpec, maxWidth, quality);
        }
    }
}
'@
Add-Type -ReferencedAssemblies $refs -TypeDefinition $cs
'''


class _PersistentUiaWorker:
    """Keeps one PowerShell + compiled C# UIA/SoM process alive across steps (~120ms vs 2500ms)."""

    _LOOP_TAIL = r'''
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Write-Output "__GLAM_READY__"
[Console]::Out.Flush()
while (($line = [Console]::In.ReadLine()) -ne $null) {
    $line = $line.Trim()
    if (-not $line) { continue }
    if ($line -eq "QUIT") { break }
    $parts = $line.Split('|', 5)
    $op = $parts[0]
    try {
        if ($op -eq "INSPECT") {
            $res = [GlamUiaBridge]::Inspect([long]$parts[1], [int]$parts[2], 650)
            Write-Output ("OK:" + $res)
        } elseif ($op -eq "CAPTURE") {
            $rects = if ($parts.Length -ge 4) { $parts[3] } else { "" }
            $res = [GlamUiaBridge]::CaptureSom($rects, [int]$parts[1], [int]$parts[2])
            Write-Output ("OK:" + $res)
        } elseif ($op -eq "BOTH") {
            $res = [GlamUiaBridge]::InspectAndCapture([long]$parts[1], [int]$parts[2], 650, [int]$parts[3], [int]$parts[4])
            Write-Output ("OK:" + $res)
        } else {
            Write-Output ("ERR:Unknown op " + $op)
        }
    } catch {
        $msg = ($_.Exception.Message -replace "[\r\n]+", " ")
        Write-Output ("ERR:" + $msg)
    }
    [Console]::Out.Flush()
}
'''

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen[str]] = None
        self._ps1_path: str = ""

    def _kill_proc(self) -> None:
        p = self._proc
        self._proc = None
        if p is not None:
            try:
                p.kill()
            except Exception:
                pass
        if self._ps1_path and os.path.exists(self._ps1_path):
            try:
                os.unlink(self._ps1_path)
            except OSError:
                pass
            self._ps1_path = ""

    def _ensure_started(self) -> subprocess.Popen[str]:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        self._kill_proc()
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", encoding="utf-8-sig", delete=False) as tf:
            tf.write(_PS_UIA_PREAMBLE + "\n" + self._LOOP_TAIL)
            self._ps1_path = tf.name
        kwargs: Dict[str, Any] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "bufsize": 1,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        self._proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", self._ps1_path],
            **kwargs,
        )
        timer = threading.Timer(12.0, self._kill_proc)
        timer.start()
        boot_lines: List[str] = []
        try:
            assert self._proc.stdout is not None
            while True:
                line = self._proc.stdout.readline()
                if not line:
                    raise RuntimeError("UIA worker exited during startup: " + " | ".join(boot_lines[-4:]))
                s = line.strip()
                if s == "__GLAM_READY__":
                    break
                if s:
                    boot_lines.append(s)
        finally:
            timer.cancel()
        return self._proc

    def call(self, cmd_line: str, timeout: float = 6.0) -> str:
        with self._lock:
            for attempt in range(2):
                try:
                    proc = self._ensure_started()
                    assert proc.stdin is not None and proc.stdout is not None
                    proc.stdin.write(cmd_line.replace("\r", " ").replace("\n", " ") + "\n")
                    proc.stdin.flush()
                    timer = threading.Timer(timeout, self._kill_proc)
                    timer.start()
                    try:
                        while True:
                            line = proc.stdout.readline()
                            if not line:
                                raise RuntimeError("UIA worker pipe closed")
                            s = line.strip()
                            if s.startswith("OK:"):
                                return s[3:]
                            if s.startswith("ERR:"):
                                raise RuntimeError(s[4:])
                    finally:
                        timer.cancel()
                except Exception:
                    self._kill_proc()
                    if attempt == 1:
                        raise
            raise RuntimeError("UIA worker unreachable")


_UIA_WORKER = _PersistentUiaWorker()
atexit.register(_UIA_WORKER._kill_proc)


def win32_inspect_ui(max_items: int = 35, hwnd: int = 0) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Enumerate visible interactive UI Automation controls on the foreground window."""
    if os.name != "nt":
        return {"title": "", "sw": 1920, "sh": 1080}, []
    fg = win32_get_foreground_info()
    target_hwnd = int(hwnd or fg.get("hwnd", 0) or 0)
    if target_hwnd == 0:
        wins = win32_list_windows()
        if wins:
            target_hwnd = int(wins[0].get("hwnd", 0) or 0)
    raw = _UIA_WORKER.call(f"INSPECT|{target_hwnd}|{int(max_items)}", timeout=6.0)
    data = json.loads(raw)
    elements = data.get("elements") if isinstance(data.get("elements"), list) else []
    win_info = {
        "hwnd": target_hwnd,
        "title": str(data.get("title") or fg.get("title") or ""),
        "process": str(fg.get("process") or ""),
        "sw": int(data.get("sw") or win32_get_screen_size()[0]),
        "sh": int(data.get("sh") or win32_get_screen_size()[1]),
    }
    return win_info, elements


def win32_capture_som_jpeg(
    elements: Optional[List[Dict[str, Any]]] = None,
    max_width: int = 960,
    quality: int = 68,
) -> Tuple[str, int, int]:
    """Capture DPI-aware desktop screenshot with optional Set-of-Mark boxes as base64 JPEG."""
    if os.name != "nt":
        raise RuntimeError("仅支持 Windows 桌面截图")
    specs: List[str] = []
    for el in elements or []:
        r = el.get("rect")
        eid = el.get("id")
        if eid and isinstance(r, (list, tuple)) and len(r) == 4:
            specs.append(f"{int(eid)},{int(r[0])},{int(r[1])},{int(r[2])},{int(r[3])}")
    spec_str = ";".join(specs).replace("'", "")
    out = _UIA_WORKER.call(f"CAPTURE|{int(max_width)}|{int(quality)}|{spec_str}", timeout=6.0)
    sw_s, sh_s, b64 = out.split("|", 2)
    return b64, int(sw_s), int(sh_s)


def win32_inspect_and_capture_som(
    max_items: int = 30,
    max_width: int = 960,
    quality: int = 68,
    hwnd: int = 0,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Optional[str]]:
    """Fast single-roundtrip UIA inspect + SoM screenshot capture via persistent worker."""
    if os.name != "nt":
        return {"title": "", "sw": 1920, "sh": 1080}, [], None
    fg = win32_get_foreground_info()
    target_hwnd = int(hwnd or fg.get("hwnd", 0) or 0)
    if target_hwnd == 0:
        wins = win32_list_windows()
        if wins:
            target_hwnd = int(wins[0].get("hwnd", 0) or 0)
    out = _UIA_WORKER.call(f"BOTH|{target_hwnd}|{int(max_items)}|{int(max_width)}|{int(quality)}", timeout=7.0)
    json_part, som_part = out.split("\t", 1)
    data = json.loads(json_part)
    elements = data.get("elements") if isinstance(data.get("elements"), list) else []
    win_info = {
        "hwnd": target_hwnd,
        "title": str(data.get("title") or fg.get("title") or ""),
        "process": str(fg.get("process") or ""),
        "sw": int(data.get("sw") or win32_get_screen_size()[0]),
        "sh": int(data.get("sh") or win32_get_screen_size()[1]),
    }
    img_b64: Optional[str] = None
    if som_part and not som_part.startswith("ERR:") and "|" in som_part:
        sw_s, sh_s, b64 = som_part.split("|", 2)
        win_info["sw"], win_info["sh"] = int(sw_s), int(sh_s)
        img_b64 = b64
    return win_info, elements, img_b64


def win32_set_master_volume(percent: int) -> Tuple[bool, str]:
    """Set Windows master output volume (0..100) using IAudioEndpointVolume COM via ctypes."""
    percent = max(0, min(100, int(percent)))
    if os.name != "nt":
        return False, "仅支持 Windows"
    # Use a fast PowerShell inline C# COM call? Actually ctypes COM vtable or powershell?
    # Let's do pure ctypes COM IAudioEndpointVolume (zero subprocess overhead, <5ms)!
    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wt.DWORD),
            ("Data2", wt.WORD),
            ("Data3", wt.WORD),
            ("Data4", wt.BYTE * 8),
        ]

    def _guid(s: str) -> GUID:
        g = GUID()
        _ole32.IIDFromString(wt.LPCWSTR(s), ctypes.byref(g))
        return g

    _ole32.CoInitialize.argtypes = [ctypes.c_void_p]
    _ole32.CoInitialize.restype = ctypes.c_long
    _ole32.CoUninitialize.argtypes = []
    _ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(GUID), ctypes.c_void_p, wt.DWORD, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)
    ]
    _ole32.CoCreateInstance.restype = ctypes.c_long
    _ole32.IIDFromString.argtypes = [wt.LPCWSTR, ctypes.POINTER(GUID)]
    _ole32.IIDFromString.restype = ctypes.c_long

    CLSID_MMDeviceEnumerator = _guid("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
    IID_IMMDeviceEnumerator = _guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
    IID_IAudioEndpointVolume = _guid("{5CDF2C82-841E-4546-9722-0CF74078229A}")

    def _vcall(obj_ptr: int, index: int, restype, argtypes, *args):
        vtbl = ctypes.cast(obj_ptr, ctypes.POINTER(ctypes.c_void_p)).contents.value
        fn_addr = ctypes.cast(vtbl, ctypes.POINTER(ctypes.c_void_p))[index]
        fn_type = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
        return fn_type(fn_addr)(obj_ptr, *args)

    hr_init = _ole32.CoInitialize(None)
    enumerator = ctypes.c_void_p()
    device = ctypes.c_void_p()
    endpoint = ctypes.c_void_p()
    try:
        hr = _ole32.CoCreateInstance(
            ctypes.byref(CLSID_MMDeviceEnumerator),
            None,
            1 | 4,  # CLSCTX_INPROC_SERVER | CLSCTX_LOCAL_SERVER
            ctypes.byref(IID_IMMDeviceEnumerator),
            ctypes.byref(enumerator),
        )
        if hr != 0 or not enumerator.value:
            return False, f"CoCreateInstance failed: 0x{hr & 0xFFFFFFFF:x}"

        # IMMDeviceEnumerator::GetDefaultAudioEndpoint (vtable idx 4) (eRender=0, eConsole=0)
        hr = _vcall(
            enumerator.value, 4, ctypes.c_long,
            [wt.DWORD, wt.DWORD, ctypes.POINTER(ctypes.c_void_p)],
            0, 0, ctypes.byref(device),
        )
        if hr != 0 or not device.value:
            return False, f"GetDefaultAudioEndpoint failed: 0x{hr & 0xFFFFFFFF:x}"

        # IMMDevice::Activate (vtable idx 3)
        hr = _vcall(
            device.value, 3, ctypes.c_long,
            [ctypes.POINTER(GUID), wt.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
            ctypes.byref(IID_IAudioEndpointVolume), 1 | 4, None, ctypes.byref(endpoint),
        )
        if hr != 0 or not endpoint.value:
            return False, f"Activate IAudioEndpointVolume failed: 0x{hr & 0xFFFFFFFF:x}"

        # IAudioEndpointVolume::SetMasterVolumeLevelScalar (vtable idx 7)
        scalar = ctypes.c_float(percent / 100.0)
        hr = _vcall(
            endpoint.value, 7, ctypes.c_long,
            [ctypes.c_float, ctypes.c_void_p],
            scalar, None,
        )
        if hr != 0:
            return False, f"SetMasterVolumeLevelScalar failed: 0x{hr & 0xFFFFFFFF:x}"
        # Also ensure unmuted if percent > 0: SetMute (vtable idx 14)
        if percent > 0:
            _vcall(endpoint.value, 14, ctypes.c_long, [wt.BOOL, ctypes.c_void_p], False, None)
        return True, f"电脑系统音量已设为 {percent}%"
    finally:
        for ptr in (endpoint, device, enumerator):
            if ptr.value:
                try:
                    _vcall(ptr.value, 2, wt.ULONG, [])  # IUnknown::Release
                except Exception:
                    pass
        if hr_init in (0, 1):
            _ole32.CoUninitialize()


# =============================================================================
# External Stdio MCP Host Manager (Claude/Cursor mcpServers compatible)
# =============================================================================

class _StdioMcpClient:
    def __init__(self, name: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None):
        self.name = name
        self.command = command
        self.args = args
        self.env = env or {}
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._next_id = 1
        self._pending: Dict[int, Dict[str, Any]] = {}
        self._tools: List[Dict[str, Any]] = []
        self._running = False

    def start(self) -> None:
        merged_env = os.environ.copy()
        merged_env.update({str(k): str(v) for k, v in self.env.items()})
        kwargs: Dict[str, Any] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "env": merged_env,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        self._proc = subprocess.Popen([self.command, *self.args], **kwargs)
        self._running = True
        threading.Thread(target=self._reader_loop, daemon=True).start()

        # Perform MCP initialize handshake
        self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "Glamor-PC-Bridge", "version": "1.0.0"},
            },
            timeout=6.0,
        )
        self.notify("notifications/initialized", {})
        res = self.request("tools/list", {}, timeout=6.0)
        tools = res.get("tools", []) if isinstance(res, dict) else []
        self._tools = tools if isinstance(tools, list) else []

    def _reader_loop(self) -> None:
        assert self._proc and self._proc.stdout
        while self._running:
            line = self._proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            rid = msg.get("id")
            if rid is not None:
                with self._lock:
                    slot = self._pending.get(int(rid))
                    if slot is not None:
                        slot["msg"] = msg
                        slot["ev"].set()

    def notify(self, method: str, params: Dict[str, Any]) -> None:
        if not self._proc or not self._proc.stdin:
            return
        payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params}, ensure_ascii=False)
        with self._lock:
            self._proc.stdin.write(payload + "\n")
            self._proc.stdin.flush()

    def request(self, method: str, params: Dict[str, Any], timeout: float = 8.0) -> Any:
        if not self._proc or not self._proc.stdin or self._proc.poll() is not None:
            raise RuntimeError(f"外部 MCP 服务 {self.name} 未运行")
        ev = threading.Event()
        with self._lock:
            rid = self._next_id
            self._next_id += 1
            self._pending[rid] = {"ev": ev, "msg": None}
            payload = json.dumps(
                {"jsonrpc": "2.0", "id": rid, "method": method, "params": params},
                ensure_ascii=False,
            )
            self._proc.stdin.write(payload + "\n")
            self._proc.stdin.flush()

        if not ev.wait(timeout):
            with self._lock:
                self._pending.pop(rid, None)
            raise TimeoutError(f"外部 MCP {self.name}.{method} 超时")

        with self._lock:
            slot = self._pending.pop(rid, {})
        msg = slot.get("msg") or {}
        if "error" in msg and msg["error"]:
            raise RuntimeError(str(msg["error"]))
        return msg.get("result")

    def list_tools(self) -> List[Dict[str, Any]]:
        return list(self._tools)

    def call_tool(self, tool_name: str, arguments: Dict[str, Any], timeout: float = 9.0) -> str:
        res = self.request("tools/call", {"name": tool_name, "arguments": arguments}, timeout=timeout)
        if isinstance(res, dict) and isinstance(res.get("content"), list):
            parts = []
            for item in res["content"]:
                if isinstance(item, dict) and item.get("text"):
                    parts.append(str(item["text"]))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            return "\n".join(parts) if parts else json.dumps(res, ensure_ascii=False)
        return json.dumps(res, ensure_ascii=False)

    def stop(self) -> None:
        self._running = False
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=1.5)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None


class ExternalMcpManager:
    def __init__(self, log_cb: Optional[Callable[[str, str], None]] = None):
        self._clients: Dict[str, _StdioMcpClient] = {}
        self._lock = threading.Lock()
        self._log_cb = log_cb

    def _log(self, msg: str, level: str = "") -> None:
        if self._log_cb:
            self._log_cb(msg, level)

    def stop_all(self) -> None:
        with self._lock:
            clients = list(self._clients.values())
            self._clients.clear()
        for c in clients:
            c.stop()

    def reload_from_json(self, json_text: str) -> Dict[str, Any]:
        self.stop_all()
        cfg = json.loads(json_text) if json_text.strip() else {}
        servers = cfg.get("mcpServers", cfg) if isinstance(cfg, dict) else {}
        if not isinstance(servers, dict):
            raise ValueError("mcpServers 配置必须是 JSON 对象")

        loaded: Dict[str, int] = {}
        errors: Dict[str, str] = {}
        for name, spec in servers.items():
            if not isinstance(spec, dict) or spec.get("disabled"):
                continue
            cmd = str(spec.get("command", "")).strip()
            if not cmd:
                continue
            args = [str(a) for a in (spec.get("args") or [])]
            env = spec.get("env") if isinstance(spec.get("env"), dict) else None
            client = _StdioMcpClient(name, cmd, args, env=env)
            try:
                client.start()
                with self._lock:
                    self._clients[name] = client
                loaded[name] = len(client.list_tools())
                self._log(f"[外部 MCP] 已加载 {name} ({loaded[name]} 个工具)", "ok")
            except Exception as exc:
                client.stop()
                errors[name] = str(exc)
                self._log(f"[外部 MCP] 加载 {name} 失败: {exc}", "err")
        return {"loaded": loaded, "errors": errors}

    def list_all_tools(self) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        with self._lock:
            items = list(self._clients.items())
        for srv_name, client in items:
            for t in client.list_tools():
                tname = str(t.get("name", ""))
                out.append({
                    "full_name": f"{srv_name}.{tname}",
                    "server": srv_name,
                    "tool": tname,
                    "description": str(t.get("description", ""))[:120],
                })
        return out

    def call_tool(self, full_or_short_name: str, arguments: Dict[str, Any]) -> str:
        name = full_or_short_name.strip()
        with self._lock:
            clients = dict(self._clients)
        if not clients:
            raise RuntimeError("当前未挂载任何外部 MCP Server，请先在 G'lamor 中配置并重载 mcpServers。")

        if "." in name:
            srv, tname = name.split(".", 1)
            if srv in clients:
                return clients[srv].call_tool(tname, arguments)

        for srv, client in clients.items():
            for t in client.list_tools():
                if t.get("name") == name:
                    return client.call_tool(name, arguments)
        raise ValueError(f"未找到外部 MCP 工具: {name}")


# =============================================================================
# Windows PC Tool Executor
# =============================================================================

L1_READ_ACTIONS_MAP = {
    ("pc.get_status", ""): True,
    ("pc.get_status", "get_status"): True,
    ("pc.system_input", "get_status"): True,
    ("pc.system_input", "screenshot"): True,
    ("pc.system.control", "screenshot"): True,
    ("pc.app_browser", "list_windows"): True,
    ("pc.app_browser", "inspect_ui"): True,
    ("pc.app.control", "list_windows"): True,
    ("pc.file_shell", "list_dir"): True,
    ("pc.file_shell", "search_file"): True,
    ("pc.file_shell", "search"): True,
    ("pc.file_shell", "read_text"): True,
    ("pc.file_shell", "get_clipboard"): True,
    ("pc.file_shell", "get"): True,
    ("pc.file_shell", "list_ext_tools"): True,
    ("pc.file.control", "list_dir"): True,
    ("pc.file.control", "search"): True,
    ("pc.file.control", "search_file"): True,
    ("pc.file.control", "read_text"): True,
    ("pc.clipboard.control", "get"): True,
    ("pc.clipboard.control", "get_clipboard"): True,
    ("pc.mcp.call", "list_ext_tools"): True,
    ("pc.ext_mcp", "list"): True,
    ("pc.ext_mcp", "list_ext_tools"): True,
    ("pc.solidworks", ""): True,
    ("pc.solidworks", "get_status"): True,
    ("pc.solidworks", "view"): True,
    ("pc.solidworks", "rebuild"): True,
}

L3_HIGH_RISK_ACTIONS = {
    "shell", "write_text", "close_app", "close",
    "lock_screen", "sleep", "call_ext_tool", "call",
}


def _sanitize_llm_args(args: Any) -> Dict[str, Any]:
    """Recover arguments when an LLM accidentally serializes <arg_key>k</arg_key><arg_value>v inside a field."""
    if not isinstance(args, dict):
        return {}
    out = dict(args)
    for k, v in list(out.items()):
        if not isinstance(v, str) or "<arg_key>" not in v:
            continue
        clean_prefix = v.split("<arg_key>", 1)[0].strip()
        out[k] = clean_prefix
        pairs = re.findall(
            r"<arg_key>\s*([^<]+?)\s*</arg_key>\s*<arg_value>\s*(.*?)\s*(?:</arg_value>|(?=<arg_key>)|$)",
            v,
            flags=re.DOTALL | re.IGNORECASE,
        )
        for pk, pv in pairs:
            pk_clean = pk.strip()
            pv_clean = pv.replace("</arg_value>", "").strip()
            if pk_clean and (pk_clean not in out or not out[pk_clean]):
                out[pk_clean] = pv_clean
    return out


class PcToolExecutor:
    def __init__(
        self,
        ext_mcp: Optional[ExternalMcpManager] = None,
        log_cb: Optional[Callable[[str, str], None]] = None,
        on_perm_mode: Optional[Callable[[str], None]] = None,
    ):
        self.ext_mcp = ext_mcp or ExternalMcpManager(log_cb=log_cb)
        self._log_cb = log_cb
        self._on_perm_mode = on_perm_mode
        self.permissions: Dict[str, bool] = {
            "app_browser": True,
            "input_system": True,
            "file_clipboard": True,
            "shell_mcp": True,
        }
        self.device_perm_mode: str = "partial"
        self.ai_agent_config: Dict[str, Any] = {}
        self.cancel_event = threading.Event()
        self._start_cursor_in_corner: bool = False
        self._pending_confirms: Dict[str, Dict[str, Any]] = {}
        self._ui_elements_cache: Dict[int, Dict[str, Any]] = {}
        self._ui_cache_win_title: str = ""
        self._ai_task_lock = threading.Lock()
        self._ai_task_state: Dict[str, Any] = {
            "running": False,
            "goal": "",
            "step": 0,
            "last_msg": "",
            "result": "",
        }
        self._shortcut_cache: Dict[str, str] = {}
        self._shortcut_cache_ts: float = 0.0

    def set_permissions(self, **kwargs: bool) -> None:
        for k, v in kwargs.items():
            if k in self.permissions:
                self.permissions[k] = bool(v)

    def set_device_perm_mode(self, mode: str) -> None:
        m = str(mode or "").strip().lower()
        if m not in ("full", "partial", "ask_every"):
            m = "partial"
        changed = (m != self.device_perm_mode)
        self.device_perm_mode = m
        if changed and self._on_perm_mode:
            self._on_perm_mode(m)

    def set_ai_agent_config(self, cfg: Optional[Dict[str, Any]]) -> None:
        self.ai_agent_config = dict(cfg) if isinstance(cfg, dict) else {}

    def request_cancel(self) -> None:
        self.cancel_event.set()

    def clear_cancel(self) -> None:
        self.cancel_event.clear()
        pos = win32_get_cursor_pos()
        self._start_cursor_in_corner = bool(pos is not None and pos[0] <= 4 and pos[1] <= 4)

    def check_failsafe(self) -> bool:
        if self.cancel_event.is_set():
            return True
        if os.name == "nt":
            pos = win32_get_cursor_pos()
            if pos is not None:
                x, y = pos
                if x <= 4 and y <= 4:
                    if not self._start_cursor_in_corner:
                        self.cancel_event.set()
                        return True
                else:
                    self._start_cursor_in_corner = False
        return False

    def _classify_risk(self, resolved_tool: str, act: str) -> str:
        if L1_READ_ACTIONS_MAP.get((resolved_tool, act)):
            return "L1"
        if act in L3_HIGH_RISK_ACTIONS:
            return "L3"
        return "L2"

    def _observe_foreground(self, delay_s: float = 0.05) -> str:
        if delay_s > 0:
            time.sleep(delay_s)
        fg = win32_get_foreground_info()
        title = (fg.get("title") or "").strip()
        proc = (fg.get("process") or "").strip()
        if not title and not proc:
            return ""
        short_t = (title[:52] + "…") if len(title) > 52 else title
        label = f"{short_t} ({proc})" if proc and short_t else (short_t or proc)
        return f" | 当前窗口: {label[:80]}"

    def _require_perm(self, key: str, label: str) -> None:
        if not self.permissions.get(key, True):
            raise PermissionError(f"已在 G'lamor 安全策略中禁用「{label}」权限")

    # ------------------------------------------------------------------
    # App Indexing & Resolution
    # ------------------------------------------------------------------

    def _scan_shortcuts(self) -> Dict[str, str]:
        now = time.monotonic()
        if self._shortcut_cache and (now - self._shortcut_cache_ts) < 60.0:
            return self._shortcut_cache

        found: Dict[str, str] = {}
        dirs = [
            os.path.join(os.path.expanduser("~"), "Desktop"),
            os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Desktop"),
            os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), r"Microsoft\Windows\Start Menu\Programs"),
        ]
        for base in dirs:
            if not base or not os.path.isdir(base):
                continue
            for root, _d, files in os.walk(base):
                for fn in files:
                    low = fn.lower()
                    if low.endswith((".lnk", ".url", ".appref-ms")):
                        stem = os.path.splitext(fn)[0].strip().lower()
                        if stem and stem not in found:
                            found[stem] = os.path.join(root, fn)

        if os.name == "nt":
            try:
                import winreg

                for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                    sub = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
                    try:
                        with winreg.OpenKey(hive, sub) as k:
                            idx = 0
                            while True:
                                try:
                                    app_exe = winreg.EnumKey(k, idx)
                                    idx += 1
                                    with winreg.OpenKey(k, app_exe) as ak:
                                        val, _ = winreg.QueryValueEx(ak, "")
                                        exe_path = str(val).strip().strip('"')
                                        if exe_path and os.path.exists(exe_path):
                                            stem = os.path.splitext(app_exe)[0].lower()
                                            found.setdefault(stem, exe_path)
                                            found.setdefault(app_exe.lower(), exe_path)
                                except OSError:
                                    break
                    except OSError:
                        pass
            except Exception:
                pass

        self._shortcut_cache = found
        self._shortcut_cache_ts = now
        return found

    def _resolve_app_target(self, query: str) -> Optional[str]:
        q = query.strip()
        if not q:
            return None
        if os.path.exists(q) or q.startswith("ms-"):
            return q

        ql = q.lower()
        candidates = list(APP_ALIASES.get(ql, [])) + [q, ql]
        shortcuts = self._scan_shortcuts()

        # 1. Exact alias / path / URI / PATH binary
        for cand in candidates:
            cl = cand.lower()
            if cl.startswith("ms-"):
                return cand
            if cl in shortcuts:
                return shortcuts[cl]
            if cl.endswith(".exe") and os.path.splitext(cl)[0] in shortcuts:
                return shortcuts[os.path.splitext(cl)[0]]
            which_hit = shutil.which(cand)
            if which_hit:
                return which_hit

        # 2. Substring match on shortcut names
        for name, path in shortcuts.items():
            for cand in candidates:
                cl = cand.lower().replace(".exe", "")
                if cl and cl in name:
                    return path

        # 3. Fuzzy match
        if shortcuts:
            best = difflib.get_close_matches(ql, list(shortcuts.keys()), n=1, cutoff=0.62)
            if best:
                return shortcuts[best[0]]
        return None

    def _find_matching_window(self, query: str) -> Optional[Dict[str, Any]]:
        q = query.strip().lower()
        if not q:
            return None
        wins = win32_list_windows()
        alias_cands = [a.lower().replace(".exe", "") for a in APP_ALIASES.get(q, [])]
        terms = [q] + alias_cands

        for w in wins:
            t = w["title"].lower()
            p = w["process"].lower().replace(".exe", "")
            for term in terms:
                if term and (term == p or term in t or term in p):
                    return w
        return None

    def _resolve_path_alias(self, p: str) -> str:
        raw = (p or "").strip()
        home = os.path.expanduser("~")
        aliases = {
            "desktop": os.path.join(home, "Desktop"),
            "桌面": os.path.join(home, "Desktop"),
            "downloads": os.path.join(home, "Downloads"),
            "下载": os.path.join(home, "Downloads"),
            "documents": os.path.join(home, "Documents"),
            "文档": os.path.join(home, "Documents"),
            "pictures": os.path.join(home, "Pictures"),
            "图片": os.path.join(home, "Pictures"),
            "music": os.path.join(home, "Music"),
            "音乐": os.path.join(home, "Music"),
            "home": home,
            "~": home,
        }
        low = raw.lower()
        if not raw:
            return aliases["desktop"]
        if low in aliases:
            return aliases[low]
        for k, base in aliases.items():
            if low.startswith(k + "\\") or low.startswith(k + "/"):
                rest = raw[len(k) + 1 :]
                return os.path.join(base, rest)
        return os.path.expandvars(os.path.expanduser(raw))

    # ------------------------------------------------------------------
    # Tool Handlers
    # ------------------------------------------------------------------

    def _resolve_tool_route(self, tool_name: str, act: str) -> str:
        if tool_name == "pc.control":
            if act in (
                "open_app", "open", "close_app", "close", "focus_window", "focus",
                "min_window", "minimize", "max_window", "maximize", "list_windows",
                "inspect_ui", "click_element", "type_element",
                "open_url", "search_web", "search", "new_tab", "close_tab", "next_tab",
                "prev_tab", "refresh", "back", "forward", "scroll_down", "scroll_up",
                "fullscreen", "zoom_in", "zoom_out", "address_bar",
            ):
                return "pc.app_browser"
            if act in (
                "get_clipboard", "set_clipboard", "get", "set", "open_path",
                "list_dir", "search_file", "read_text", "write_text",
                "shell", "list_ext_tools", "call_ext_tool",
            ):
                return "pc.file_shell"
            return "pc.system_input"
        return tool_name

    def _check_confirm_gate(
        self,
        orig_tool: str,
        resolved_tool: str,
        act: str,
        args: Dict[str, Any],
        perm_mode: str,
    ) -> Optional[str]:
        risk = self._classify_risk(resolved_tool, act)
        need_confirm = False
        if perm_mode == "ask_every" and risk in ("L2", "L3"):
            need_confirm = True
        elif perm_mode == "partial" and risk == "L3":
            need_confirm = True
        if not need_confirm:
            return None

        now = time.monotonic()
        expired = [k for k, v in self._pending_confirms.items() if now > float(v.get("exp", 0))]
        for k in expired:
            self._pending_confirms.pop(k, None)

        cid = str(args.get("confirm_id", "")).strip()
        if cid and cid in self._pending_confirms:
            entry = self._pending_confirms[cid]
            if entry.get("tool") == resolved_tool and entry.get("act") == act:
                self._pending_confirms.pop(cid, None)
                return None

        code = f"{random.randint(1000, 9999)}"
        while code in self._pending_confirms:
            code = f"{random.randint(1000, 9999)}"
        target = str(args.get("goal") or args.get("target") or args.get("tool") or args.get("command") or args.get("path") or args.get("text") or "").strip()
        summary = f"{act or resolved_tool}" + (f"({target[:48]})" if target else "")
        self._pending_confirms[code] = {"tool": resolved_tool, "act": act, "exp": now + 60.0}
        mode_cn = "每次都问" if perm_mode == "ask_every" else "部分访问(高危需确认)"
        return (
            f"【需要用户确认】当前小智电脑权限为「{mode_cn}」，即将执行({risk}): {summary}。"
            f"请先向用户口头确认是否同意；用户同意后再次调用 {orig_tool} 并附带参数 confirm_id=\"{code}\"。"
        )

    def _tool_inspect_ui(self, args: Dict[str, Any]) -> str:
        max_items = int(args.get("max_items", 35) or 35)
        win_info, elements = win32_inspect_ui(max_items=max_items)
        self._ui_elements_cache = {int(el["id"]): el for el in elements if "id" in el}
        self._ui_cache_win_title = win_info.get("title", "")
        if not elements:
            return (
                f"当前窗口: {win_info.get('title') or '(无标题)'} ({win_info.get('process') or 'app'}), "
                f"屏幕 {win_info['sw']}x{win_info['sh']}。未枚举到标准 UIA 控件，可改用 auto_task 视觉代理或 hotkey/mouse_click。"
            )
        lines = [
            f"[{el['id']}] {el['name']} ({el['role']}) @norm({el['nx']},{el['ny']})"
            for el in elements
        ]
        return (
            f"当前窗口: {win_info.get('title') or '(无标题)'} ({win_info.get('process') or 'app'}) "
            f"[{win_info['sw']}x{win_info['sh']}], 共 {len(elements)} 个控件:\n" + "\n".join(lines)
        )

    def _lookup_cached_element(self, target: str) -> Dict[str, Any]:
        t = target.strip()
        if not t:
            raise ValueError("缺少控件编号 id 或控件名称 target")
        if t.isdigit():
            eid = int(t)
            if eid in self._ui_elements_cache:
                return self._ui_elements_cache[eid]
            raise LookupError(f"未找到编号 [{eid}] 的控件缓存，请先调用 inspect_ui 刷新当前窗口控件")
        if not self._ui_elements_cache:
            self._tool_inspect_ui({"max_items": 35})
        low = t.lower()
        for el in self._ui_elements_cache.values():
            if low in str(el.get("name", "")).lower():
                return el
        raise LookupError(f"未找到包含「{t}」的 UI 控件，请先调用 inspect_ui 查看编号")

    def _tool_click_element(self, args: Dict[str, Any]) -> str:
        target = str(args.get("target") or args.get("id") or "").strip()
        el = self._lookup_cached_element(target)
        cx, cy = int(el["cx"]), int(el["cy"])
        _user32.SetCursorPos(cx, cy)
        time.sleep(0.025)
        btn = str(args.get("button", "left")).strip().lower()
        if btn == "right":
            _user32.mouse_event(0x0008, 0, 0, 0, 0)
            _user32.mouse_event(0x0010, 0, 0, 0, 0)
        elif btn == "double":
            for _ in range(2):
                _user32.mouse_event(0x0002, 0, 0, 0, 0)
                _user32.mouse_event(0x0004, 0, 0, 0, 0)
                time.sleep(0.04)
        else:
            _user32.mouse_event(0x0002, 0, 0, 0, 0)
            _user32.mouse_event(0x0004, 0, 0, 0, 0)
        return f"已点击控件 [{el['id']}] {el['name']} ({cx},{cy})" + self._observe_foreground(0.10)

    def _tool_type_element(self, args: Dict[str, Any]) -> str:
        target = str(args.get("target") or args.get("id") or "").strip()
        text = str(args.get("extra") or args.get("text") or args.get("content") or "")
        if not text:
            raise ValueError("缺少要输入的文本（请放在 extra 或 text 中）")
        el = self._lookup_cached_element(target)
        cx, cy = int(el["cx"]), int(el["cy"])
        _user32.SetCursorPos(cx, cy)
        time.sleep(0.025)
        _user32.mouse_event(0x0002, 0, 0, 0, 0)
        _user32.mouse_event(0x0004, 0, 0, 0, 0)
        time.sleep(0.08)
        press_enter = bool(args.get("press_enter", False))
        win32_type_text(text, press_enter=press_enter)
        return f"已在控件 [{el['id']}] {el['name']} 输入 {len(text)} 个字符" + self._observe_foreground(0.06)

    def _tool_solidworks_control(self, args: Dict[str, Any]) -> str:
        from .sw_agent import execute_solidworks_action

        act = str(args.get("action") or "get_status").strip().lower()
        if act != "ai_model":
            return execute_solidworks_action(args, ai_cfg=self.ai_agent_config, log_cb=self._log_cb)

        goal = str(args.get("goal") or args.get("target") or args.get("extra") or "").strip()
        done_evt = threading.Event()
        holder: Dict[str, str] = {}

        def _sw_worker() -> None:
            try:
                holder["res"] = execute_solidworks_action(args, ai_cfg=self.ai_agent_config, log_cb=self._log_cb)
            except Exception as exc:
                holder["err"] = str(exc)
            finally:
                if "res" in holder and self._log_cb:
                    self._log_cb(f"[SolidWorks AI 完成] {holder['res']}", "ok")
                elif "err" in holder and self._log_cb:
                    self._log_cb(f"[SolidWorks AI 失败] {holder['err']}", "err")
                done_evt.set()

        threading.Thread(target=_sw_worker, daemon=True).start()
        if done_evt.wait(timeout=16.0):
            if "err" in holder:
                raise RuntimeError(holder["err"])
            return holder.get("res") or "已完成 SolidWorks AI 建模"
        return (
            f"已接手并在后台运行 SolidWorks AI 建模「{goal[:36]}」（避免语音超时），"
            "完成后会自动呈现在 SolidWorks 窗口中并在 G'lamor 日志汇报。"
        )

    def _tool_auto_task(self, args: Dict[str, Any], perm_mode: str) -> str:
        goal = str(args.get("goal") or args.get("target") or args.get("extra") or "").strip()
        if not goal:
            raise ValueError("缺少要执行的任务描述 goal / target")
        low = goal.lower()
        if low in ("status", "progress", "进度", "查看进度", "状态"):
            with self._ai_task_lock:
                st = dict(self._ai_task_state)
            if st["running"]:
                return f"正在后台执行「{st['goal']}」（第{st['step']}步: {st['last_msg']}）。"
            if st["result"]:
                return f"最近任务「{st['goal']}」已结束：{st['result']}"
            return "当前没有正在运行的桌面 AI 任务。"
        if low in ("stop", "cancel", "停止", "取消", "中止"):
            self.request_cancel()
            with self._ai_task_lock:
                g = self._ai_task_state.get("goal", "")
            return f"已通知停止当前桌面 AI 任务" + (f"「{g}」" if g else "") + "。"

        with self._ai_task_lock:
            if self._ai_task_state.get("running"):
                cur = dict(self._ai_task_state)
                return (
                    f"上一项任务「{cur['goal']}」正在第{cur['step']}步执行（{cur['last_msg']}），"
                    "请稍后再试或对我说“停止AI任务”。"
                )
            self._ai_task_state = {
                "running": True,
                "goal": goal,
                "step": 0,
                "last_msg": "初始化中",
                "result": "",
            }

        from .vision_agent import LocalComputerUseAgent

        done_evt = threading.Event()
        holder: Dict[str, str] = {}

        def _on_prog(step: int, msg: str) -> None:
            with self._ai_task_lock:
                self._ai_task_state["step"] = step
                self._ai_task_state["last_msg"] = msg

        def _worker() -> None:
            try:
                agent = LocalComputerUseAgent(self.ai_agent_config, log_cb=self._log_cb)
                res = agent.run_task(goal=goal, executor=self, perm_mode=perm_mode, progress_cb=_on_prog)
            except Exception as exc:
                res = f"AI 任务异常: {exc}"
            finally:
                with self._ai_task_lock:
                    self._ai_task_state["running"] = False
                    self._ai_task_state["result"] = res
                holder["result"] = res
                done_evt.set()

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        if done_evt.wait(timeout=12.0):
            return holder.get("result") or "已完成"

        with self._ai_task_lock:
            st = dict(self._ai_task_state)
        return (
            f"正在后台快速执行「{goal[:36]}」（已到第{st['step']}步：{st['last_msg']}），"
            "完成后会自动留在屏幕上，不会超时；随时可问我进度或说停止。"
        )

    def execute(
        self,
        tool_name: str,
        args: Optional[Dict[str, Any]] = None,
        perm_mode: Optional[str] = None,
        bypass_confirm: bool = False,
    ) -> Tuple[bool, str]:
        args = _sanitize_llm_args(args)
        orig_tool = tool_name
        act = str(args.get("action", "")).strip().lower()
        effective_perm = str(perm_mode or self.device_perm_mode or "partial").strip().lower()
        if effective_perm not in ("full", "partial", "ask_every"):
            effective_perm = "partial"

        if "extra" in args and args["extra"]:
            ext_val = args["extra"]
            args.setdefault("engine", ext_val)
            args.setdefault("text", ext_val)
            args.setdefault("content", ext_val)
            args.setdefault("query", ext_val)
            args.setdefault("arguments_json", ext_val)
        try:
            # 0. Unified single-tool routing (pc.control)
            tool_name = self._resolve_tool_route(tool_name, act)

            # 0.5 Device-level risk tier confirmation gate
            if not bypass_confirm:
                confirm_msg = self._check_confirm_gate(orig_tool, tool_name, act, args, effective_perm)
                if confirm_msg:
                    return True, confirm_msg

            if tool_name == "pc.ai_agent":
                self._require_perm("input_system", "键鼠模拟与系统多媒体")
                return True, self._tool_auto_task(args, effective_perm)

            if tool_name == "pc.solidworks":
                self._require_perm("app_browser", "应用与浏览器控制")
                return True, self._tool_solidworks_control(args)

            if tool_name == "pc.ext_mcp":
                self._require_perm("shell_mcp", "PowerShell 终端与外部 MCP")
                if act in ("list", "list_ext_tools", ""):
                    args["action"] = "list_ext_tools"
                elif act in ("call", "call_ext_tool"):
                    args["action"] = "call_ext_tool"
                    if not args.get("command") and (args.get("tool") or args.get("target")):
                        args["command"] = args.get("tool") or args.get("target")
                return True, self._tool_mcp_call(args)

            # 1. Consolidated 3-tool routing (pc.app_browser, pc.system_input, pc.file_shell)
            if tool_name == "pc.app_browser":
                self._require_perm("app_browser", "应用与浏览器控制")
                if act == "inspect_ui":
                    return True, self._tool_inspect_ui(args)
                if act == "click_element":
                    return True, self._tool_click_element(args)
                if act == "type_element":
                    return True, self._tool_type_element(args)
                app_map = {
                    "open_app": "open", "open": "open",
                    "close_app": "close", "close": "close",
                    "focus_window": "focus", "focus": "focus",
                    "min_window": "minimize", "minimize": "minimize",
                    "max_window": "maximize", "maximize": "maximize",
                    "list_windows": "list_windows",
                }
                if act in app_map:
                    args["action"] = app_map[act]
                    return True, self._tool_app_control(args)
                if act == "search_web":
                    args["action"] = "search"
                return True, self._tool_browser_control(args)

            if tool_name == "pc.system_input":
                if act == "get_status":
                    return True, self._tool_get_status()
                self._require_perm("input_system", "键鼠模拟与系统多媒体")
                if act == "auto_task":
                    return True, self._tool_auto_task(args, effective_perm)
                if act in ("hotkey", "press_key", "type_text", "mouse_click", "mouse_move", "mouse_scroll"):
                    if act in ("hotkey", "press_key") and not args.get("keys") and args.get("target"):
                        args["keys"] = args["target"]
                    if act == "type_text" and not args.get("text") and args.get("target"):
                        args["text"] = args["target"]
                    if act == "mouse_scroll" and "scroll" not in args and args.get("target"):
                        try:
                            args["scroll"] = int(args["target"])
                        except ValueError:
                            pass
                    return True, self._tool_input_control(args)
                if not args.get("value") and args.get("target"):
                    args["value"] = args["target"]
                return True, self._tool_system_control(args)

            if tool_name == "pc.file_shell":
                if act in ("get_clipboard", "set_clipboard", "get", "set"):
                    self._require_perm("file_clipboard", "文件浏览与剪贴板读写")
                    args["action"] = "get" if act in ("get_clipboard", "get") else "set"
                    if not args.get("text") and args.get("target"):
                        args["text"] = args["target"]
                    return True, self._tool_clipboard_control(args)
                if act in ("open_path", "list_dir", "search_file", "search", "read_text", "write_text"):
                    self._require_perm("file_clipboard", "文件浏览与剪贴板读写")
                    if act == "search_file":
                        args["action"] = "search"
                    if not args.get("path") and args.get("target"):
                        args["path"] = args["target"]
                    if not args.get("query") and args.get("text"):
                        args["query"] = args["text"]
                    if not args.get("content") and args.get("text"):
                        args["content"] = args["text"]
                    return True, self._tool_file_control(args)
                if act in ("shell", "list_ext_tools", "call_ext_tool"):
                    self._require_perm("shell_mcp", "PowerShell 终端与外部 MCP")
                    if not args.get("command") and args.get("target"):
                        args["command"] = args["target"]
                    if not args.get("arguments_json") and args.get("text"):
                        args["arguments_json"] = args["text"]
                    return True, self._tool_mcp_call(args)

            # 2. Direct 8-tool routing (backward & local self-test compatible)
            if tool_name == "pc.get_status":
                return True, self._tool_get_status()
            if tool_name == "pc.app.control":
                self._require_perm("app_browser", "应用与浏览器控制")
                return True, self._tool_app_control(args)
            if tool_name == "pc.browser.control":
                self._require_perm("app_browser", "应用与浏览器控制")
                return True, self._tool_browser_control(args)
            if tool_name == "pc.input.control":
                self._require_perm("input_system", "键鼠模拟与系统多媒体")
                return True, self._tool_input_control(args)
            if tool_name == "pc.system.control":
                self._require_perm("input_system", "键鼠模拟与系统多媒体")
                return True, self._tool_system_control(args)
            if tool_name == "pc.file.control":
                self._require_perm("file_clipboard", "文件浏览与剪贴板读写")
                return True, self._tool_file_control(args)
            if tool_name == "pc.clipboard.control":
                self._require_perm("file_clipboard", "文件浏览与剪贴板读写")
                return True, self._tool_clipboard_control(args)
            if tool_name == "pc.mcp.call":
                self._require_perm("shell_mcp", "PowerShell 终端与外部 MCP")
                return True, self._tool_mcp_call(args)
            return False, f"未知 PC 工具: {tool_name}"
        except Exception as exc:
            return False, f"执行失败: {exc}"

    def _tool_get_status(self) -> str:
        fg = win32_get_foreground_info()
        wins = win32_list_windows()
        ram_pct = None
        avail_gb = None
        total_gb = None
        bat_pct = None
        ac_online = None
        if os.name == "nt":
            ms = _MEMORYSTATUSEX()
            ms.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            if _kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
                ram_pct = int(ms.dwMemoryLoad)
                avail_gb = round(ms.ullAvailPhys / (1024 ** 3), 1)
                total_gb = round(ms.ullTotalPhys / (1024 ** 3), 1)
            ps = _SYSTEM_POWER_STATUS()
            if _kernel32.GetSystemPowerStatus(ctypes.byref(ps)):
                if ps.BatteryLifePercent <= 100:
                    bat_pct = int(ps.BatteryLifePercent)
                if ps.ACLineStatus in (0, 1):
                    ac_online = (ps.ACLineStatus == 1)

        clip = win32_get_clipboard() if self.permissions.get("file_clipboard", True) else ""
        clip_preview = (clip[:120] + "...") if len(clip) > 120 else clip
        top_apps = []
        seen_proc = set()
        for w in wins:
            p = w["process"] or w["title"][:20]
            if p not in seen_proc:
                seen_proc.add(p)
                top_apps.append(f"{p}({w['title'][:24]})")
            if len(top_apps) >= 10:
                break

        data = {
            "os": "Windows",
            "computer": os.environ.get("COMPUTERNAME", ""),
            "user": os.environ.get("USERNAME", ""),
            "active_window": fg["title"],
            "active_process": fg["process"],
            "ram_used_pct": ram_pct,
            "ram_avail_gb": avail_gb,
            "ram_total_gb": total_gb,
            "battery_pct": bat_pct,
            "ac_plugged": ac_online,
            "open_windows_count": len(wins),
            "top_windows": top_apps,
            "clipboard_preview": clip_preview,
            "ext_mcp_tools": len(self.ext_mcp.list_all_tools()),
        }
        return json.dumps(data, ensure_ascii=False)

    def _tool_app_control(self, args: Dict[str, Any]) -> str:
        action = str(args.get("action", "")).strip().lower()
        target = str(args.get("target", "")).strip()
        extra_args = str(args.get("args", "")).strip()

        if action == "list_windows":
            wins = win32_list_windows()
            lines = [f"- [{w['process'] or 'app'}] {w['title'][:60]}" for w in wins[:25]]
            return f"当前打开窗口 ({len(wins)} 个):\n" + ("\n".join(lines) if lines else "(无可见窗口)")

        if not target:
            raise ValueError("缺少 target 参数（应用名或窗口标题）")

        if action == "open":
            # 1. Resolve application executable or shortcut
            resolved = self._resolve_app_target(target)
            if resolved:
                if os.name == "nt":
                    if resolved.lower().endswith((".lnk", ".url", ".appref-ms")) or resolved.startswith("ms-") or not extra_args:
                        os.startfile(resolved)  # type: ignore[attr-defined]
                    else:
                        subprocess.Popen(
                            [resolved, *extra_args.split()],
                            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0x00000008),
                        )
                return f"已打开应用: {target} ({os.path.basename(resolved) or resolved})" + self._observe_foreground(0.18)
            # 2. If already open as a window, focus it
            win = self._find_matching_window(target)
            if win and win32_focus_window(win["hwnd"]):
                return f"已切换到已运行窗口: {win['title']}" + self._observe_foreground(0.08)
            raise FileNotFoundError(f"未能找到应用「{target}」，可尝试用完整程序名或浏览器打开")

        win = self._find_matching_window(target)
        if not win:
            raise LookupError(f"未找到匹配的运行中窗口: {target}")

        hwnd = win["hwnd"]
        if action == "focus":
            win32_focus_window(hwnd)
            return f"已切换聚焦到窗口: {win['title']}" + self._observe_foreground(0.08)
        if action == "minimize":
            _user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
            return f"已最小化窗口: {win['title']}"
        if action == "maximize":
            win32_focus_window(hwnd)
            _user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
            return f"已最大化窗口: {win['title']}"
        if action == "close":
            _user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
            return f"已发送关闭指令给窗口: {win['title']}"
        raise ValueError(f"不支持的 app.control action: {action}")

    def _ensure_browser_focused(self) -> None:
        fg = win32_get_foreground_info()
        if fg["process"].lower() in BROWSER_PROCESSES:
            return
        for w in win32_list_windows():
            if w["process"].lower() in BROWSER_PROCESSES:
                win32_focus_window(w["hwnd"])
                time.sleep(0.12)
                return

    def _tool_browser_control(self, args: Dict[str, Any]) -> str:
        action = str(args.get("action", "")).strip().lower()
        target = str(args.get("target", "")).strip()
        engine = str(args.get("engine", "bing")).strip().lower() or "bing"

        if action == "open_url":
            if not target:
                raise ValueError("缺少 target（网址或站点名称）")
            low = target.lower()
            url = SITE_SHORTCUTS.get(low, target)
            if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
                url = "https://" + url
            webbrowser.open(url, new=2)
            return f"已在浏览器打开: {url}" + self._observe_foreground(0.18)

        if action == "search":
            if not target:
                raise ValueError("缺少搜索关键词 target")
            tmpl = SEARCH_ENGINES.get(engine, SEARCH_ENGINES["bing"])
            url = tmpl.format(q=urllib.parse.quote(target))
            webbrowser.open(url, new=2)
            return f"已在浏览器使用 {engine} 搜索「{target}」" + self._observe_foreground(0.18)

        self._ensure_browser_focused()
        shortcut_map = {
            "new_tab": "ctrl+t",
            "close_tab": "ctrl+w",
            "next_tab": "ctrl+tab",
            "prev_tab": "ctrl+shift+tab",
            "refresh": "f5",
            "back": "alt+left",
            "forward": "alt+right",
            "fullscreen": "f11",
            "play_pause": "space",
        }
        if action in shortcut_map:
            win32_send_hotkey(shortcut_map[action])
            return f"已向浏览器发送指令: {action}" + self._observe_foreground(0.06)
        if action == "scroll_down":
            _user32.mouse_event(0x0800, 0, 0, -600, 0)
            return "浏览器已向下滚动"
        if action == "scroll_up":
            _user32.mouse_event(0x0800, 0, 0, 600, 0)
            return "浏览器已向上滚动"
        raise ValueError(f"不支持的 browser.control action: {action}")

    def _tool_input_control(self, args: Dict[str, Any]) -> str:
        action = str(args.get("action", "")).strip().lower()
        if action in ("hotkey", "press_key"):
            keys = str(args.get("keys", "")).strip()
            win32_send_hotkey(keys)
            return f"已发送按键: {keys}" + self._observe_foreground(0.06)
        if action == "type_text":
            text = str(args.get("text", ""))
            if not text:
                raise ValueError("缺少要输入的 text")
            press_enter = bool(args.get("press_enter", False))
            win32_type_text(text, press_enter=press_enter)
            return f"已在当前光标输入 {len(text)} 个字符" + (" 并回车" if press_enter else "") + self._observe_foreground(0.04)
        if action == "mouse_move":
            if bool(args.get("norm")) or str(args.get("coord_mode", "")).lower() == "norm":
                x, y = norm_to_screen_xy(float(args.get("x", 0)), float(args.get("y", 0)))
            else:
                x, y = int(args.get("x", 0)), int(args.get("y", 0))
            _user32.SetCursorPos(x, y)
            return f"鼠标已移动至 ({x}, {y})"
        if action == "mouse_click":
            if "x" in args and "y" in args:
                if bool(args.get("norm")) or str(args.get("coord_mode", "")).lower() == "norm":
                    cx, cy = norm_to_screen_xy(float(args["x"]), float(args["y"]))
                else:
                    cx, cy = int(args["x"]), int(args["y"])
                _user32.SetCursorPos(cx, cy)
                time.sleep(0.02)
            elif args.get("target") and "," in str(args.get("target")):
                parts = [p.strip() for p in str(args["target"]).split(",", 1)]
                nx, ny = float(parts[0]), float(parts[1])
                cx, cy = norm_to_screen_xy(nx, ny) if (nx <= 1000 and ny <= 1000) else (int(nx), int(ny))
                _user32.SetCursorPos(cx, cy)
                time.sleep(0.02)
            btn = str(args.get("button", "left")).strip().lower()
            if btn == "right":
                _user32.mouse_event(0x0008, 0, 0, 0, 0)
                _user32.mouse_event(0x0010, 0, 0, 0, 0)
            elif btn == "double":
                for _ in range(2):
                    _user32.mouse_event(0x0002, 0, 0, 0, 0)
                    _user32.mouse_event(0x0004, 0, 0, 0, 0)
                    time.sleep(0.05)
            else:
                _user32.mouse_event(0x0002, 0, 0, 0, 0)
                _user32.mouse_event(0x0004, 0, 0, 0, 0)
            return f"已执行鼠标点击 ({btn})" + self._observe_foreground(0.08)
        if action == "mouse_scroll":
            notches = int(args.get("scroll", -5))
            _user32.mouse_event(0x0800, 0, 0, notches * 120, 0)
            return f"鼠标滚轮已滚动 {notches} 格"
        raise ValueError(f"不支持的 input.control action: {action}")

    def _tool_system_control(self, args: Dict[str, Any]) -> str:
        action = str(args.get("action", "")).strip().lower()
        val = str(args.get("value", "")).strip()

        if action == "set_volume":
            if not val:
                raise ValueError("缺少音量值 value (0-100)")
            pct = int(float(val))
            ok, msg = win32_set_master_volume(pct)
            if not ok:
                raise RuntimeError(msg)
            return msg
        if action == "volume_up":
            for _ in range(4):
                win32_send_hotkey("volume_up")
            return "电脑音量已调高"
        if action == "volume_down":
            for _ in range(4):
                win32_send_hotkey("volume_down")
            return "电脑音量已调低"
        if action == "mute":
            win32_send_hotkey("volume_mute")
            return "已切换电脑静音状态"
        if action == "media_play_pause":
            win32_send_hotkey("media_play_pause")
            return "已发送多媒体播放/暂停键"
        if action == "media_next":
            win32_send_hotkey("media_next")
            return "已发送下一曲按键"
        if action == "media_prev":
            win32_send_hotkey("media_prev")
            return "已发送上一曲按键"
        if action == "show_desktop":
            win32_send_hotkey("win+d")
            return "已显示桌面"
        if action == "lock_screen":
            if os.name == "nt":
                _user32.LockWorkStation()
            return "电脑已锁屏"
        if action == "sleep":
            def _do_sleep():
                time.sleep(0.35)
                subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])

            threading.Thread(target=_do_sleep, daemon=True).start()
            return "电脑即将在 0.3 秒后进入睡眠"
        if action == "screenshot":
            save_dir = os.path.join(os.path.expanduser("~"), "Pictures", "Glamor_Screenshots")
            os.makedirs(save_dir, exist_ok=True)
            out_path = os.path.join(
                save_dir, f"pc_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            )
            try:
                from PIL import ImageGrab  # type: ignore

                img = ImageGrab.grab(all_screens=True)
                img.save(out_path, format="PNG")
                return f"已完成电脑截屏并保存至: {out_path}"
            except Exception:
                ps_cmd = (
                    "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
                    "$b = [System.Windows.Forms.SystemInformation]::VirtualScreen; "
                    "$bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height); "
                    "$g = [System.Drawing.Graphics]::FromImage($bmp); "
                    "$g.CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size); "
                    f"$bmp.Save('{out_path.replace(chr(39), chr(39)*2)}', [System.Drawing.Imaging.ImageFormat]::Png);"
                )
                subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], timeout=6, check=True)
                return f"已完成电脑截屏并保存至: {out_path}"
        if action == "notify":
            if self._log_cb:
                self._log_cb(f"[小智通知] {val or '完成'}", "ok")
            return f"已推送通知: {val or '完成'}"
        raise ValueError(f"不支持的 system.control action: {action}")

    def _tool_file_control(self, args: Dict[str, Any]) -> str:
        action = str(args.get("action", "")).strip().lower()
        raw_path = str(args.get("path", "")).strip()
        target_path = self._resolve_path_alias(raw_path)

        if action == "open_path":
            if not os.path.exists(target_path):
                raise FileNotFoundError(f"路径不存在: {target_path}")
            if os.name == "nt":
                os.startfile(target_path)  # type: ignore[attr-defined]
            return f"已在电脑上打开: {target_path}"

        if action == "list_dir":
            if not os.path.isdir(target_path):
                raise NotADirectoryError(f"目录不存在: {target_path}")
            entries = sorted(os.listdir(target_path), key=lambda n: (not os.path.isdir(os.path.join(target_path, n)), n.lower()))
            lines = []
            for n in entries[:50]:
                full = os.path.join(target_path, n)
                if os.path.isdir(full):
                    lines.append(f"[目录] {n}")
                else:
                    try:
                        sz = os.path.getsize(full)
                        lines.append(f"[文件] {n} ({sz} B)")
                    except OSError:
                        lines.append(f"[文件] {n}")
            extra = f"\n...(共 {len(entries)} 项)" if len(entries) > 50 else ""
            return f"目录 {target_path}:\n" + ("\n".join(lines) if lines else "(空目录)") + extra

        if action == "search":
            query = str(args.get("query", "")).strip().lower()
            if not query:
                raise ValueError("缺少搜索关键词 query")
            if not os.path.isdir(target_path):
                target_path = self._resolve_path_alias("Desktop")
            hits: List[str] = []
            skip_dirs = {".git", "node_modules", "__pycache__", "$recycle.bin", "windows"}
            base_depth = target_path.rstrip("\\/").count(os.sep)
            for root, dirs, files in os.walk(target_path):
                dirs[:] = [d for d in dirs if d.lower() not in skip_dirs]
                if root.rstrip("\\/").count(os.sep) - base_depth >= 4:
                    dirs[:] = []
                for name in files + dirs:
                    if query in name.lower():
                        hits.append(os.path.join(root, name))
                        if len(hits) >= 25:
                            break
                if len(hits) >= 25:
                    break
            return f"在 {target_path} 搜索「{query}」找到 {len(hits)} 项:\n" + ("\n".join(hits) if hits else "(未找到)")

        if action == "read_text":
            if not os.path.isfile(target_path):
                raise FileNotFoundError(f"文件不存在: {target_path}")
            raw_bytes = open(target_path, "rb").read(16384)
            text = ""
            for enc in ("utf-8-sig", "utf-8", "gbk", "utf-16"):
                try:
                    text = raw_bytes.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            if not text:
                text = raw_bytes.decode("utf-8", errors="replace")
            return _truncate_text(text, 2400)

        if action == "write_text":
            content = str(args.get("content", ""))
            if not raw_path:
                raise ValueError("缺少目标文件路径 path")
            if not os.path.isabs(target_path):
                target_path = os.path.join(self._resolve_path_alias("Desktop"), raw_path)
            parent = os.path.dirname(target_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"已写入文件 ({len(content)} 字符): {target_path}"

        raise ValueError(f"不支持的 file.control action: {action}")

    def _tool_clipboard_control(self, args: Dict[str, Any]) -> str:
        action = str(args.get("action", "get")).strip().lower()
        if action == "get":
            txt = win32_get_clipboard()
            if not txt:
                return "(电脑剪贴板当前为空或非纯文本)"
            return _truncate_text(txt, 2400)
        if action == "set":
            txt = str(args.get("text", ""))
            if not win32_set_clipboard(txt):
                raise RuntimeError("写入剪贴板失败")
            return f"已将 {len(txt)} 字符写入电脑剪贴板"
        raise ValueError(f"不支持的 clipboard.control action: {action}")

    def _tool_mcp_call(self, args: Dict[str, Any]) -> str:
        action = str(args.get("action", "shell")).strip().lower()
        cmd = str(args.get("command", "")).strip()
        if action == "list_ext_tools":
            tools = self.ext_mcp.list_all_tools()
            return json.dumps(tools, ensure_ascii=False)
        if action == "call_ext_tool":
            if not cmd:
                raise ValueError("缺少外部 MCP 工具名 command")
            raw_args = args.get("arguments_json", "{}")
            if isinstance(raw_args, dict):
                parsed = raw_args
            elif isinstance(raw_args, str) and raw_args.strip():
                parsed = json.loads(raw_args)
            else:
                parsed = {}
            res = self.ext_mcp.call_tool(cmd, parsed)
            return _truncate_text(res, 2800)
        if action == "shell":
            if not cmd:
                raise ValueError("缺少要执行的 PowerShell 命令 command")
            ps_script = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; " + cmd
            kwargs: Dict[str, Any] = {
                "capture_output": True,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "timeout": 8.5,
            }
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script], **kwargs)
            out = (proc.stdout or "").strip()
            err = (proc.stderr or "").strip()
            combined = out if not err else (f"{out}\n[stderr] {err}" if out else f"[stderr] {err}")
            if proc.returncode != 0 and not combined:
                combined = f"命令退出码: {proc.returncode}"
            return _truncate_text(combined or "执行完成 (无输出)", 2600)
        raise ValueError(f"不支持的 pc.mcp.call action: {action}")


# =============================================================================
# Dual-Channel Bridge Daemon (USB Serial + Wi-Fi HTTP)
# =============================================================================

class GlamorPcBridge:
    def __init__(
        self,
        executor: Optional[PcToolExecutor] = None,
        on_log: Optional[Callable[[str, str], None]] = None,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_status: Optional[Callable[[str, bool], None]] = None,
    ):
        self.executor = executor or PcToolExecutor(log_cb=on_log)
        self._on_log = on_log
        self._on_event = on_event
        self._on_status = on_status

        self._running = False
        self._mode = "auto"  # "auto" | "serial" | "wifi"
        self._port = ""
        self._baud = 115200
        self._wifi_ip = ""

        self._serial_paused = threading.Event()
        self._serial_pause_ack = threading.Event()
        self._dedup_lock = threading.Lock()
        self._seen_ids: List[int] = []

        self._serial_connected = False
        self._wifi_connected = False
        self._threads: List[threading.Thread] = []

    def is_running(self) -> bool:
        return self._running

    def _log(self, msg: str, tag: str = "") -> None:
        if self._on_log:
            self._on_log(msg, tag)

    def _emit_status(self) -> None:
        if not self._on_status:
            return
        if not self._running:
            self._on_status("已停止", False)
            return
        chans = []
        if self._serial_connected:
            chans.append(f"USB({self._port})")
        if self._wifi_connected:
            chans.append(f"Wi-Fi({self._wifi_ip})")
        if chans:
            self._on_status("运行中 · " + " + ".join(chans), True)
        else:
            self._on_status("运行中 · 等待设备握手...", True)

    def start(self, mode: str = "auto", port: str = "", baud: int = 115200, wifi_ip: str = "") -> None:
        if self._running:
            self.stop()
        self._mode = mode if mode in ("auto", "serial", "wifi") else "auto"
        self._port = port.strip()
        self._baud = int(baud or 115200)
        self._wifi_ip = wifi_ip.strip()
        self._serial_paused.clear()
        self._serial_pause_ack.clear()
        self._serial_connected = False
        self._wifi_connected = False
        self._running = True
        self._threads = []

        if self._mode in ("auto", "serial"):
            t_ser = threading.Thread(target=self._serial_worker, daemon=True)
            t_ser.start()
            self._threads.append(t_ser)
        if self._mode in ("auto", "wifi"):
            t_wifi = threading.Thread(target=self._wifi_worker, daemon=True)
            t_wifi.start()
            self._threads.append(t_wifi)

        self._emit_status()
        self._log(f"[PC桥接] 已启动 (模式={self._mode}, 串口={self._port or '自动'}, Wi-Fi={self._wifi_ip or '未填'})", "cmd")

    def stop(self) -> None:
        self._running = False
        self._serial_paused.clear()
        for t in self._threads:
            t.join(timeout=1.2)
        self._threads.clear()
        self._serial_connected = False
        self._wifi_connected = False
        self._emit_status()
        self._log("[PC桥接] 已停止", "warn")

    def pause_serial_for_flash(self, timeout: float = 2.0) -> None:
        """Temporarily release COM port so Tab 2 .gla serial installer can use it."""
        if not self._running:
            return
        self._serial_pause_ack.clear()
        self._serial_paused.set()
        self._serial_pause_ack.wait(timeout=timeout)

    def resume_serial_after_flash(self) -> None:
        self._serial_paused.clear()

    def _claim_req_id(self, req_id: int) -> bool:
        with self._dedup_lock:
            if req_id in self._seen_ids:
                return False
            self._seen_ids.append(req_id)
            if len(self._seen_ids) > 128:
                del self._seen_ids[:64]
            return True

    def _handle_request(self, req: Dict[str, Any], channel: str) -> Dict[str, Any]:
        req_id = int(req.get("id", 0))
        tool = str(req.get("tool", "")).strip()
        args = req.get("args") if isinstance(req.get("args"), dict) else {}
        perm_mode = str(req.get("perm_mode") or "").strip().lower()
        if perm_mode:
            self.executor.set_device_perm_mode(perm_mode)
        t0 = time.monotonic()
        ok, res_text = self.executor.execute(tool, args, perm_mode=perm_mode or None)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        ev = {
            "time": time.strftime("%H:%M:%S"),
            "channel": channel,
            "id": req_id,
            "tool": tool,
            "args": json.dumps(args, ensure_ascii=False),
            "ok": ok,
            "result": res_text,
            "elapsed_ms": elapsed_ms,
        }
        if self._on_event:
            self._on_event(ev)
        self._log(
            f"[PC MCP:{channel}] {tool} -> {'OK' if ok else 'ERR'} ({elapsed_ms}ms): {res_text[:120]}",
            "ok" if ok else "err",
        )
        return {"type": "pc_mcp_resp", "id": req_id, "ok": ok, "result": res_text}

    def _pick_serial_port(self) -> str:
        if self._port:
            return self._port
        ports = list_serial_ports()
        return ports[0]["device"] if ports else ""

    def _serial_worker(self) -> None:
        last_err_msg = ""
        while self._running:
            if self._serial_paused.is_set():
                self._serial_connected = False
                self._emit_status()
                self._serial_pause_ack.set()
                time.sleep(0.2)
                continue

            port = self._pick_serial_port()
            if not port:
                self._serial_connected = False
                self._emit_status()
                time.sleep(1.5)
                continue

            try:
                with SerialLink(port, baud=self._baud, timeout=0.2) as ser:
                    self._port = port
                    self._serial_connected = True
                    self._emit_status()
                    last_err_msg = ""
                    ser.write(b'\n{"type":"pc_hello"}\n')
                    ser.flush()
                    last_hb = time.monotonic()

                    while self._running and not self._serial_paused.is_set():
                        now = time.monotonic()
                        if now - last_hb >= 3.0:
                            ser.write(b'{"type":"pc_hb"}\n')
                            ser.flush()
                            last_hb = now

                        raw = ser.readline()
                        if not raw:
                            continue
                        line = raw.decode("utf-8", errors="replace").strip()
                        if not line:
                            continue
                        # Extract JSON object even if preceded by ESP-IDF log prefix
                        idx = line.find('{"type":')
                        if idx < 0:
                            continue
                        try:
                            obj = json.loads(line[idx:])
                        except Exception:
                            continue
                        if not isinstance(obj, dict):
                            continue
                        if obj.get("type") == "pc_mcp_req":
                            req_id = int(obj.get("id", 0))
                            if not self._claim_req_id(req_id):
                                continue
                            resp = self._handle_request(obj, "USB")
                            out = ("\n" + json.dumps(resp, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
                            ser.write(out)
                            ser.flush()
            except Exception as exc:
                self._serial_connected = False
                self._emit_status()
                msg = str(exc)
                if msg != last_err_msg and not self._serial_paused.is_set():
                    last_err_msg = msg
                    self._log(f"[PC桥接:USB] {port} 暂不可用: {msg}", "warn")
                if self._serial_paused.is_set():
                    self._serial_pause_ack.set()
                time.sleep(1.5)

    def _wifi_worker(self) -> None:
        last_err_msg = ""
        conn: Optional[http.client.HTTPConnection] = None
        conn_target = ""

        def _close_conn() -> None:
            nonlocal conn, conn_target
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
                conn = None
                conn_target = ""

        while self._running:
            # In auto mode, if USB Serial is already connected, do zero Wi-Fi polling
            # so ESP32 2.4GHz Wi-Fi has 100% bandwidth for real-time Opus voice streaming.
            if self._mode == "auto" and self._serial_connected:
                _close_conn()
                if self._wifi_connected:
                    self._wifi_connected = False
                    self._emit_status()
                time.sleep(1.0)
                continue

            ip = self._wifi_ip.strip()
            if not ip:
                _close_conn()
                self._wifi_connected = False
                self._emit_status()
                time.sleep(1.0)
                continue

            try:
                base = _norm_host(ip)
                parsed = urllib.parse.urlparse(base)
                host = parsed.hostname or ip
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                target_key = f"{parsed.scheme}://{host}:{port}"

                if conn is None or conn_target != target_key:
                    _close_conn()
                    if parsed.scheme == "https":
                        conn = http.client.HTTPSConnection(host, port, timeout=2.5)
                    else:
                        conn = http.client.HTTPConnection(host, port, timeout=2.5)
                    conn_target = target_key

                conn.request("GET", "/api/pc_mcp/poll", headers={"Connection": "keep-alive"})
                resp = conn.getresponse()
                raw_bytes = resp.read()
                if resp.status != 200:
                    raise http.client.HTTPException(f"HTTP {resp.status}")
                raw = raw_bytes.decode("utf-8", errors="replace").strip()

                if not self._wifi_connected:
                    self._wifi_connected = True
                    self._emit_status()
                    last_err_msg = ""

                if raw.startswith("{"):
                    obj = json.loads(raw)
                    if isinstance(obj, dict) and obj.get("type") == "pc_mcp_req":
                        req_id = int(obj.get("id", 0))
                        if self._claim_req_id(req_id):
                            resp_obj = self._handle_request(obj, "Wi-Fi")
                            body = json.dumps(resp_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                            conn.request(
                                "POST",
                                "/api/pc_mcp/reply",
                                body=body,
                                headers={
                                    "Content-Type": "application/json; charset=utf-8",
                                    "Connection": "keep-alive",
                                },
                            )
                            r2 = conn.getresponse()
                            r2.read()
                        continue
                time.sleep(0.75)
            except Exception as exc:
                _close_conn()
                self._wifi_connected = False
                self._emit_status()
                msg = str(exc)
                if msg != last_err_msg:
                    last_err_msg = msg
                    self._log(f"[PC桥接:Wi-Fi] 连接 {ip} 等待中: {msg}", "warn")
                time.sleep(1.5)

        _close_conn()
