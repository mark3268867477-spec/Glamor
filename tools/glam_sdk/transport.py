"""
G'lam OS Dual-Channel Safe App Installer & Wi-Fi Device Manager Client.
Never touches internal ESP32-S3 Flash; installs .gla (and legacy .spk) packages to TF card only.
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wt
import ipaddress
import json
import os
import shutil
import time
from typing import Any, Callable, Dict, List, Optional, Union
import urllib.error
import urllib.parse
import urllib.request
import zlib

from .pkg import unpack_package_to_dir, verify_package
from .serial_port import SerialLink

LogFn = Optional[Callable[[str], None]]
ProgressFn = Optional[Callable[[int, int], None]]

_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _is_local_or_lan_url(url: str) -> bool:
    try:
        hostname = urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return False
    if not hostname:
        return False
    lower = hostname.lower()
    if lower == "localhost" or lower.endswith(".local"):
        return True
    try:
        ip_obj = ipaddress.ip_address(hostname)
        return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local
    except ValueError:
        return False


def _open_url(req_or_url: Union[str, urllib.request.Request], timeout: float):
    url = req_or_url.full_url if isinstance(req_or_url, urllib.request.Request) else str(req_or_url)
    # Bypass VPN / system HTTP proxy for LAN / private device IPs
    if _is_local_or_lan_url(url):
        return _DIRECT_OPENER.open(req_or_url, timeout=timeout)
    return urllib.request.urlopen(req_or_url, timeout=timeout)


def _log(log_cb: LogFn, msg: str) -> None:
    if log_cb:
        log_cb(msg)


def _norm_host(host: str) -> str:
    h = host.strip()
    if not h:
        raise ValueError("设备 IP 地址不能为空")
    if not h.startswith("http://") and not h.startswith("https://"):
        h = "http://" + h
    return h.rstrip("/")


def list_removable_drives() -> List[str]:
    if os.name != "nt":
        return []
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetLogicalDriveStringsW.argtypes = [wt.DWORD, wt.LPWSTR]
        k32.GetLogicalDriveStringsW.restype = wt.DWORD
        k32.GetDriveTypeW.argtypes = [wt.LPCWSTR]
        k32.GetDriveTypeW.restype = wt.UINT

        buf = ctypes.create_unicode_buffer(512)
        n = k32.GetLogicalDriveStringsW(512, buf)
        if n == 0:
            return []
        drives = [d for d in buf.value.split("\x00") if d]
        return [d for d in drives if k32.GetDriveTypeW(d) == 2]
    except Exception:
        return []


def install_via_sdcard(sd_root: str, pkg_path: str, log_cb: LogFn = None) -> Dict[str, Any]:
    info = verify_package(pkg_path)
    app_id = info["id"]
    ext = os.path.splitext(pkg_path)[1].lower()
    if ext not in (".gla", ".spk"):
        ext = ".gla"

    sd_root = os.path.abspath(sd_root)
    if not os.path.isdir(sd_root):
        raise FileNotFoundError(f"TF 卡路径不存在: {sd_root}")

    install_dir = os.path.join(sd_root, "install")
    app_dir = os.path.join(sd_root, "apps", app_id)
    os.makedirs(install_dir, exist_ok=True)
    os.makedirs(app_dir, exist_ok=True)

    dst_pkg = os.path.join(install_dir, f"{app_id}{ext}")
    shutil.copy2(pkg_path, dst_pkg)
    unpack_package_to_dir(pkg_path, app_dir)

    _log(log_cb, f"[SDCARD OK] 已拷贝到 {dst_pkg} 并解包到 {app_dir}")
    return info


def install_via_wifi(host: str, pkg_path: str, log_cb: LogFn = None) -> Dict[str, Any]:
    info = verify_package(pkg_path)
    with open(pkg_path, "rb") as f:
        data = f.read()

    url = _norm_host(host) + "/api/install"
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/octet-stream",
            "X-Glam-App-Id": info["id"],
            "X-Swift-App-Id": info["id"],
        },
        method="POST",
    )
    _log(log_cb, f"[WIFI] 正在上传 {info['id']} ({len(data)} B) 到 {url} ...")
    try:
        with _open_url(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            _log(log_cb, f"[WIFI OK] HTTP {resp.status}: {body}")
            return {"status": resp.status, "response": body, "package": info}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc


def wifi_list_apps(host: str) -> List[Dict[str, Any]]:
    url = _norm_host(host) + "/api/apps"
    with _open_url(url, timeout=8) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    return data if isinstance(data, list) else []


def wifi_get_info(host: str) -> Dict[str, Any]:
    base = _norm_host(host)
    try:
        with _open_url(base + "/api/info", timeout=6) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            apps = wifi_list_apps(host)
            return {
                "os": "G'lam / Legacy OS",
                "abi_version": 1,
                "package_ext": ".gla/.spk",
                "legacy_firmware": True,
                "app_count": len(apps),
            }
        raise


def wifi_uninstall_app(host: str, app_id: str) -> Dict[str, Any]:
    url = _norm_host(host) + "/api/uninstall?id=" + urllib.parse.quote(app_id, safe="")
    req = urllib.request.Request(url, data=b"", method="POST")
    try:
        with _open_url(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body) if body.strip().startswith("{") else {"ok": True, "raw": body}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RuntimeError("设备固件版本较旧，尚未支持远程卸载接口 (/api/uninstall)，请在板端应用中心卸载或更新 OS 固件。") from exc
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc


def wifi_capture_screenshot(host: str) -> bytes:
    url = _norm_host(host) + "/api/screenshot"
    with _open_url(url, timeout=10) as resp:
        return resp.read()


def _wait_serial_tag(ser, tags: tuple, timeout_sec: float, log_cb: LogFn = None) -> str:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        raw = ser.readline()
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        if not line.startswith("GLA_ACK") and not line.startswith("SPK_ACK"):
            _log(log_cb, f"  [DEV] {line}")
        for tag in tags:
            if tag in line:
                return line
        if "GLA_ERR" in line or "SPK_ERR" in line:
            raise RuntimeError(f"设备拒绝数据包: {line}")
    raise TimeoutError(f"等待设备响应超时: {tags}")


def install_via_serial(
    port: str,
    pkg_path: str,
    baud: int = 115200,
    force_legacy_proto: bool = False,
    progress_cb: ProgressFn = None,
    log_cb: LogFn = None,
) -> Dict[str, Any]:
    info = verify_package(pkg_path)
    with open(pkg_path, "rb") as f:
        data = f.read()
    pkg_crc = zlib.crc32(data) & 0xFFFFFFFF

    use_legacy = force_legacy_proto or (info["magic"] == "SWPK")
    prefix = "spk" if use_legacy else "gla"
    tag_prefix = "SPK_" if use_legacy else "GLA_"

    _log(log_cb, f"[SERIAL] 打开 {port} @ {baud}bps，发送 {info['id']} ({len(data)} B, 协议={prefix}_*)...")
    with SerialLink(port, baud=baud, timeout=0.4) as ser:
        time.sleep(0.05)
        ser.reset_input_buffer()

        begin_msg = json.dumps(
            {
                "cmd": f"{prefix}_begin",
                "id": info["id"],
                "size": len(data),
                "crc32": f"{pkg_crc:08x}",
            },
            separators=(",", ":"),
        )
        ser.write((begin_msg + "\n").encode("utf-8"))
        ser.flush()
        _wait_serial_tag(ser, (f"{tag_prefix}READY",), timeout_sec=5.0, log_cb=log_cb)

        chunk_raw = 512
        seq = 0
        offset = 0
        if progress_cb:
            progress_cb(0, len(data))

        while offset < len(data):
            piece = data[offset : offset + chunk_raw]
            b64 = base64.b64encode(piece).decode("ascii")
            chunk_msg = json.dumps(
                {"cmd": f"{prefix}_chunk", "seq": seq, "data": b64},
                separators=(",", ":"),
            )
            ser.write((chunk_msg + "\n").encode("utf-8"))
            ser.flush()
            _wait_serial_tag(ser, (f"{tag_prefix}ACK",), timeout_sec=3.0, log_cb=log_cb)
            offset += len(piece)
            seq += 1
            if progress_cb:
                progress_cb(offset, len(data))

        end_msg = json.dumps({"cmd": f"{prefix}_end"}, separators=(",", ":"))
        ser.write((end_msg + "\n").encode("utf-8"))
        ser.flush()
        _wait_serial_tag(ser, (f"{tag_prefix}INSTALL_OK",), timeout_sec=8.0, log_cb=log_cb)
        _log(log_cb, f"[SERIAL OK] {info['id']} 已安全安装至设备 TF 卡！")
        return info
