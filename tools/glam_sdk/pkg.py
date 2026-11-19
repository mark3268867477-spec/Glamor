"""
G'lam OS Package Builder, Verifier, and Unpacker (.gla / compat .spk).

Binary layout (160-byte header + manifest JSON + Xtensa ELF32):
  magic[4]       = b"GLAM" (default) or b"SWPK" (legacy compat)
  version        = uint16 LE (1)
  header_len     = uint16 LE (manifest JSON byte length)
  elf_size       = uint32 LE (ELF binary byte length)
  crc32          = uint32 LE (CRC32 over manifest_bytes + elf_bytes)
  app_id[64]     = UTF-8 null-padded
  app_name[64]   = UTF-8 null-padded
  app_version[16]= UTF-8 null-padded
  manifest_bytes = header_len bytes
  elf_bytes      = elf_size bytes
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import struct
from typing import Any, Dict, List, Optional, Union
import zlib

from . import GLA_MAGIC, LEGACY_SPK_MAGIC, PKG_VERSION
from .elf_check import check_elf_bytes

HEADER_FMT = "<4sHHII64s64s16s"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
VALID_MAGICS = (GLA_MAGIC, LEGACY_SPK_MAGIC)

VALID_ID_RE = re.compile(r"^[a-zA-Z0-9._-]+$")
VALID_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
VALID_CATEGORIES = ("game", "tool", "media", "service", "system")
VALID_BG_POLICIES = ("kill_all", "keep_all", "partial_service")
VALID_PERMISSIONS = ("sandbox_data", "audio", "media_read")

CATEGORY_DEFAULT_POLICY = {
    "game": "kill_all",
    "media": "partial_service",
    "service": "partial_service",
    "tool": "keep_all",
    "system": "kill_all",
}


def encode_icon_to_jpeg(icon_src_path: str) -> Optional[bytes]:
    if not icon_src_path or not os.path.isfile(icon_src_path):
        return None
    ext = os.path.splitext(icon_src_path)[1].lower()
    try:
        from PIL import Image, ImageOps

        with Image.open(icon_src_path) as im:
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                rgba = im.convert("RGBA")
                bg = Image.new("RGBA", rgba.size, (20, 20, 26, 255))
                im_rgb = Image.alpha_composite(bg, rgba).convert("RGB")
            else:
                im_rgb = im.convert("RGB")
            im_fit = ImageOps.fit(im_rgb, (40, 40), method=Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            im_fit.save(buf, format="JPEG", quality=88, subsampling=0)
            return buf.getvalue()
    except Exception:
        if ext in (".jpg", ".jpeg"):
            with open(icon_src_path, "rb") as f:
                raw = f.read()
            if 16 < len(raw) <= 32768:
                return raw
    return None


def validate_manifest_dict(manifest_in: Dict[str, Any]) -> Dict[str, Any]:
    manifest_obj = dict(manifest_in)

    app_id = str(manifest_obj.get("id", "")).strip()
    app_name = str(manifest_obj.get("name", app_id)).strip()
    app_version = str(manifest_obj.get("version", "1.0.0")).strip()

    if not app_id or not VALID_ID_RE.match(app_id) or ".." in app_id or len(app_id.encode("utf-8")) >= 64:
        raise ValueError(f"非法应用 ID: {app_id!r}（仅允许字母/数字/._-，无 '..'，长度 < 64B）")
    if not app_name or len(app_name.encode("utf-8")) >= 64:
        raise ValueError(f"应用名称不能为空且需 < 64 字节: {app_name!r}")
    if not app_version or len(app_version.encode("utf-8")) >= 16:
        raise ValueError(f"版本号不能为空且需 < 16 字节: {app_version!r}")

    manifest_obj["id"] = app_id
    manifest_obj["name"] = app_name
    manifest_obj["version"] = app_version
    manifest_obj.setdefault("api_level", 1)
    manifest_obj.setdefault("entry", "app.elf")

    category = str(manifest_obj.get("category", "tool")).strip().lower()
    if category not in VALID_CATEGORIES:
        raise ValueError(f"非法分类 category={category!r}；可选: {', '.join(VALID_CATEGORIES)}")
    manifest_obj["category"] = category

    bg_policy = str(manifest_obj.get("bg_policy", "")).strip().lower()
    if not bg_policy:
        bg_policy = CATEGORY_DEFAULT_POLICY[category]
    if bg_policy not in VALID_BG_POLICIES:
        raise ValueError(f"非法后台策略 bg_policy={bg_policy!r}；可选: {', '.join(VALID_BG_POLICIES)}")
    manifest_obj["bg_policy"] = bg_policy

    accent = str(manifest_obj.get("accent", "#3B82F6")).strip()
    if accent and not accent.startswith("#"):
        accent = "#" + accent
    if accent and not VALID_HEX_COLOR_RE.match(accent):
        raise ValueError(f"非法主题色 accent={accent!r}（期望 #RRGGBB）")
    if accent:
        manifest_obj["accent"] = accent.upper()

    return manifest_obj


def _find_icon_source(manifest_obj: Dict[str, Any], base_dir: Optional[str], icon_path: Optional[str]) -> Optional[str]:
    if icon_path == "":
        return None
    if icon_path:
        if os.path.isfile(icon_path):
            return icon_path
        raise FileNotFoundError(f"指定的图标文件不存在: {icon_path}")

    if not base_dir or not os.path.isdir(base_dir):
        return None

    candidates: List[str] = []
    declared_icon = str(manifest_obj.get("icon", "")).strip()
    if declared_icon and ".." not in declared_icon and "/" not in declared_icon and "\\" not in declared_icon:
        candidates.append(declared_icon)
    for fallback_name in ("icon.jpg", "icon.jpeg", "icon.png", "icon.bmp"):
        if fallback_name not in candidates:
            candidates.append(fallback_name)

    for cand_name in candidates:
        cand_path = os.path.join(base_dir, cand_name)
        if os.path.isfile(cand_path):
            return cand_path
    return None


def pack_package(
    manifest_src: Union[str, Dict[str, Any]],
    elf_path: str,
    out_path: str,
    icon_path: Optional[str] = None,
    compat_swpk: bool = False,
    run_elf_check: bool = True,
) -> Dict[str, Any]:
    if isinstance(manifest_src, str):
        base_dir = os.path.dirname(os.path.abspath(manifest_src))
        with open(manifest_src, "r", encoding="utf-8") as f:
            raw_manifest = json.load(f)
    else:
        base_dir = os.path.dirname(os.path.abspath(elf_path))
        raw_manifest = dict(manifest_src)

    manifest_obj = validate_manifest_dict(raw_manifest)
    manifest_obj.pop("icon_jpg_b64", None)

    icon_src_path = _find_icon_source(manifest_obj, base_dir, icon_path)
    if icon_src_path is not None:
        jpg_bytes = encode_icon_to_jpeg(icon_src_path)
        if jpg_bytes:
            manifest_obj["icon"] = "icon.jpg"
            manifest_obj["icon_jpg_b64"] = base64.b64encode(jpg_bytes).decode("ascii")
        elif "icon" in manifest_obj and not icon_path:
            manifest_obj.pop("icon", None)
    elif manifest_obj.get("icon") == "icon.jpg":
        manifest_obj.pop("icon", None)

    with open(elf_path, "rb") as f:
        elf_bytes = f.read()

    elf_report = check_elf_bytes(elf_bytes)
    if run_elf_check and not elf_report.ok:
        raise ValueError("ELF 预检未通过:\n  - " + "\n  - ".join(elf_report.errors))

    manifest_bytes = json.dumps(manifest_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(manifest_bytes) > 65535:
        raise ValueError("Manifest JSON 过大 (> 65535 bytes)")

    magic = LEGACY_SPK_MAGIC if compat_swpk else GLA_MAGIC
    crc32 = zlib.crc32(manifest_bytes + elf_bytes) & 0xFFFFFFFF
    header = struct.pack(
        HEADER_FMT,
        magic,
        PKG_VERSION,
        len(manifest_bytes),
        len(elf_bytes),
        crc32,
        manifest_obj["id"].encode("utf-8"),
        manifest_obj["name"].encode("utf-8"),
        manifest_obj["version"].encode("utf-8"),
    )
    pkg = header + manifest_bytes + elf_bytes

    out_abs = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_abs), exist_ok=True)
    with open(out_abs, "wb") as f:
        f.write(pkg)

    return verify_package(out_abs, run_elf_check=run_elf_check)


def verify_package(pkg_path: str, run_elf_check: bool = True) -> Dict[str, Any]:
    with open(pkg_path, "rb") as f:
        data = f.read()
    if len(data) < HEADER_SIZE:
        raise ValueError("安装包长度小于 160B 文件头")

    magic, version, hdr_len, elf_size, crc32, raw_id, raw_name, raw_ver = struct.unpack_from(HEADER_FMT, data, 0)
    if magic not in VALID_MAGICS:
        raise ValueError(f"非法安装包魔数: {magic!r}（期望 b'GLAM' 或兼容 b'SWPK'）")
    if version != PKG_VERSION:
        raise ValueError(f"不支持的安装包版本: {version}")

    expected_total = HEADER_SIZE + hdr_len + elf_size
    if len(data) != expected_total:
        raise ValueError(f"安装包长度不匹配: 实际 {len(data)}B, 期望 {expected_total}B")

    payload = data[HEADER_SIZE:]
    actual_crc = zlib.crc32(payload) & 0xFFFFFFFF
    if actual_crc != crc32:
        raise ValueError(f"CRC32 校验失败: 期望 0x{crc32:08X}, 实际 0x{actual_crc:08X}")

    manifest_bytes = payload[:hdr_len]
    elf_bytes = payload[hdr_len:]
    manifest_obj = json.loads(manifest_bytes.decode("utf-8"))

    elf_report = check_elf_bytes(elf_bytes)
    if run_elf_check and not elf_report.ok:
        raise ValueError("包内 ELF 预检失败:\n  - " + "\n  - ".join(elf_report.errors))

    icon_bytes = b""
    b64_str = manifest_obj.get("icon_jpg_b64")
    if isinstance(b64_str, str) and b64_str:
        try:
            icon_bytes = base64.b64decode(b64_str)
        except Exception:
            icon_bytes = b""

    app_id = raw_id.split(b"\x00", 1)[0].decode("utf-8")
    app_name = raw_name.split(b"\x00", 1)[0].decode("utf-8")
    app_ver = raw_ver.split(b"\x00", 1)[0].decode("utf-8")

    return {
        "path": os.path.abspath(pkg_path),
        "magic": magic.decode("ascii"),
        "id": app_id,
        "name": app_name,
        "version": app_ver,
        "elf_size": elf_size,
        "total_size": len(data),
        "crc32": crc32,
        "manifest": manifest_obj,
        "has_icon": len(icon_bytes) > 16,
        "icon_bytes": icon_bytes,
        "elf_report": elf_report,
    }


def unpack_package_to_dir(pkg_path: str, app_dir: str) -> Dict[str, Any]:
    info = verify_package(pkg_path, run_elf_check=False)
    with open(pkg_path, "rb") as f:
        raw = f.read()

    hdr_len = int.from_bytes(raw[6:8], "little")
    manifest_bytes = raw[HEADER_SIZE : HEADER_SIZE + hdr_len]
    elf_bytes = raw[HEADER_SIZE + hdr_len :]

    os.makedirs(app_dir, exist_ok=True)
    manifest_obj = json.loads(manifest_bytes.decode("utf-8"))
    b64 = manifest_obj.pop("icon_jpg_b64", None)
    if isinstance(b64, str) and len(b64) > 16:
        icon_name = str(manifest_obj.get("icon", "icon.jpg")).strip() or "icon.jpg"
        if ".." in icon_name or "/" in icon_name or "\\" in icon_name:
            icon_name = "icon.jpg"
        try:
            icon_raw = base64.b64decode(b64)
            if len(icon_raw) > 16:
                with open(os.path.join(app_dir, icon_name), "wb") as icon_f:
                    icon_f.write(icon_raw)
        except Exception:
            pass

    trimmed_manifest = json.dumps(manifest_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with open(os.path.join(app_dir, "manifest.json"), "wb") as mf:
        mf.write(trimmed_manifest)

    tmp_elf = os.path.join(app_dir, "app.elf.tmp")
    dst_elf = os.path.join(app_dir, "app.elf")
    with open(tmp_elf, "wb") as ef:
        ef.write(elf_bytes)
    os.replace(tmp_elf, dst_elf)

    return info


def generate_c_header(pkg_paths: List[str], out_header: str) -> None:
    lines = [
        "#pragma once",
        "#include <stddef.h>",
        "#include <stdint.h>",
        "",
        "typedef struct {",
        "    const char *id;",
        "    const char *name;",
        "    const uint8_t *data;",
        "    size_t len;",
        "} os_spk_seed_item_t;",
        "",
    ]
    entries = []
    for idx, pkg_path in enumerate(pkg_paths):
        info = verify_package(pkg_path)
        with open(pkg_path, "rb") as f:
            raw = f.read()
        var_name = f"s_seed_spk_{idx}"
        lines.append(f"/* {info['id']} ({info['name']}) v{info['version']} - {len(raw)} bytes */")
        lines.append(f"static const uint8_t {var_name}[] = {{")
        for i in range(0, len(raw), 16):
            chunk = ", ".join(f"0x{b:02x}" for b in raw[i : i + 16])
            lines.append(f"    {chunk},")
        lines.append("};")
        lines.append("")
        entries.append((info["id"], info["name"], var_name, len(raw)))

    lines.append(f"#define OS_SPK_SEED_COUNT ({len(entries)})")
    lines.append("static const os_spk_seed_item_t g_os_spk_seeds[] = {")
    for app_id, app_name, var_name, length in entries:
        esc_name = app_name.replace('"', '\\"')
        lines.append(f'    {{ "{app_id}", "{esc_name}", {var_name}, {length} }},')
    lines.append("};")
    lines.append("")

    os.makedirs(os.path.dirname(os.path.abspath(out_header)), exist_ok=True)
    with open(out_header, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
