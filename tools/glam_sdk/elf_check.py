"""
PC-side Xtensa ELF32 Preflight Validator for G'lam OS.
Mirrors os_firmware/components/swift_abi/src/swift_elf_loader.c and swift_os_abi.c
so missing compiler flags or disallowed external symbols are caught before flashing/installing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import struct
from typing import List


EI_CLASS = 4
EI_DATA = 5
ELFCLASS32 = 1
ELFDATA2LSB = 1
ET_EXEC = 2
ET_DYN = 3
EM_XTENSA = 94

SHT_NULL = 0
SHT_PROGBITS = 1
SHT_SYMTAB = 2
SHT_STRTAB = 3
SHT_RELA = 4
SHT_NOBITS = 8

SHF_WRITE = 0x1
SHF_ALLOC = 0x2
SHF_EXECINSTR = 0x4
SHN_UNDEF = 0

R_XTENSA_NONE = 0
R_XTENSA_32 = 1
R_XTENSA_RTLD = 2
R_XTENSA_JMP_SLOT = 4
R_XTENSA_RELATIVE = 5
R_XTENSA_SLOT0_OP = 20

MAX_ELF_FILE_SIZE = 2 * 1024 * 1024
MAX_IMAGE_SIZE = 2 * 1024 * 1024

ABI_WHITELIST_SYMBOLS = frozenset({
    "memcpy",
    "memset",
    "memmove",
    "memcmp",
    "strlen",
    "strcmp",
    "strncmp",
    "snprintf",
    "bsp_i2c_get_handle",
    "i2c_master_bus_add_device",
    "i2c_master_bus_rm_device",
    "i2c_master_transmit",
    "i2c_master_transmit_receive",
    "lv_obj_set_pos",
    "lv_obj_set_style_bg_color",
    "lv_obj_add_flag",
    "lv_obj_clear_flag",
})


@dataclass
class ElfCheckReport:
    ok: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    elf_size: int = 0
    psram_footprint: int = 0
    e_type: int = 0
    e_entry: int = 0
    entry_symbol: str = ""
    rela_sections: int = 0
    sections: List[dict] = field(default_factory=list)
    used_os_symbols: List[str] = field(default_factory=list)
    blocked_symbols: List[str] = field(default_factory=list)


def _read_cstr(buf: bytes, offset: int) -> str:
    if offset < 0 or offset >= len(buf):
        return ""
    end = buf.find(b"\x00", offset)
    if end == -1:
        end = len(buf)
    return buf[offset:end].decode("utf-8", errors="replace")


def check_elf_bytes(elf_bytes: bytes) -> ElfCheckReport:
    report = ElfCheckReport(elf_size=len(elf_bytes))

    if len(elf_bytes) < 52:
        report.errors.append("ELF 文件过小 (< 52 字节)")
        return report
    if len(elf_bytes) > MAX_ELF_FILE_SIZE:
        report.errors.append(f"ELF 体积超出 2MB 上限 ({len(elf_bytes)} B)")
        return report
    if elf_bytes[:4] != b"\x7fELF":
        report.errors.append("无效 ELF 魔数 (期望 \\x7fELF)")
        return report
    if elf_bytes[EI_CLASS] != ELFCLASS32 or elf_bytes[EI_DATA] != ELFDATA2LSB:
        report.errors.append("仅支持 32 位小端序 (ELF32 LSB) 目标文件")
        return report

    (
        e_type,
        e_machine,
        _e_version,
        e_entry,
        _e_phoff,
        e_shoff,
        _e_flags,
        _e_ehsize,
        _e_phentsize,
        _e_phnum,
        e_shentsize,
        e_shnum,
        e_shstrndx,
    ) = struct.unpack_from("<HHIIIIIHHHHHH", elf_bytes, 16)

    report.e_type = e_type
    report.e_entry = e_entry

    if e_machine != EM_XTENSA:
        report.errors.append(f"非 ESP32-S3 Xtensa 架构 (e_machine={e_machine}, 期望 {EM_XTENSA})")
        return report
    if e_type not in (ET_EXEC, ET_DYN):
        report.errors.append(f"不支持的 ELF 类型 e_type={e_type} (请用链接器并添加 -Wl,-q)")
        return report
    if e_shentsize != 40 or e_shnum == 0 or e_shoff >= len(elf_bytes):
        report.errors.append("ELF 节头表 (Section Header) 损坏或为空")
        return report
    if e_shoff + e_shnum * 40 > len(elf_bytes):
        report.errors.append("ELF 节头表越界")
        return report

    shdrs = [struct.unpack_from("<IIIIIIIIII", elf_bytes, e_shoff + i * 40) for i in range(e_shnum)]

    shstr_data = b""
    if e_shstrndx < e_shnum:
        shstr_off, shstr_sz = shdrs[e_shstrndx][4], shdrs[e_shstrndx][5]
        if shstr_off + shstr_sz <= len(elf_bytes):
            shstr_data = elf_bytes[shstr_off : shstr_off + shstr_sz]

    min_vaddr = 0xFFFFFFFF
    max_vaddr = 0

    for sh in shdrs:
        sh_name_off, sh_type, sh_flags, sh_addr, sh_offset, sh_size, _sh_link, _sh_info, _sh_align, _sh_entsize = sh
        sec_name = _read_cstr(shstr_data, sh_name_off) if shstr_data else ""
        if sh_flags & SHF_ALLOC:
            report.sections.append(
                {
                    "name": sec_name,
                    "type": sh_type,
                    "flags": sh_flags,
                    "addr": sh_addr,
                    "size": sh_size,
                }
            )
            if sh_addr < min_vaddr:
                min_vaddr = sh_addr
            end_vaddr = sh_addr + sh_size
            if end_vaddr > max_vaddr:
                max_vaddr = end_vaddr
            if sh_type != SHT_NOBITS and sh_size > 0 and sh_offset + sh_size > len(elf_bytes):
                report.errors.append(f"段 {sec_name or '<unnamed>'} 数据超出 ELF 文件结尾")

    if min_vaddr != 0 or max_vaddr == 0 or max_vaddr > MAX_IMAGE_SIZE:
        report.errors.append(
            f"ELF 内存布局错误 (min_vaddr=0x{min_vaddr:x}, max_vaddr=0x{max_vaddr:x})，必须使用专属链接脚本从 0x0 开始"
        )
        return report

    alloc_size = (max_vaddr + 63) & ~63
    report.psram_footprint = alloc_size

    if e_entry >= max_vaddr:
        report.errors.append(f"入口地址 e_entry=0x{e_entry:x} 超出镜像范围 0x{max_vaddr:x}")

    # Resolve entry symbol name & verify SHT_RELA relocations
    entry_candidates = []
    used_os = set()
    blocked = set()

    for sh in shdrs:
        if sh[1] == SHT_SYMTAB and sh[6] < e_shnum:
            sym_off, sym_sz = sh[4], sh[5]
            str_sh = shdrs[sh[6]]
            if sym_off + sym_sz <= len(elf_bytes) and str_sh[4] + str_sh[5] <= len(elf_bytes):
                strtab = elf_bytes[str_sh[4] : str_sh[4] + str_sh[5]]
                sym_count = sym_sz // 16
                for idx in range(sym_count):
                    st_name, st_value, _st_sz, _st_info, _st_other, st_shndx = struct.unpack_from(
                        "<IIIBBH", elf_bytes, sym_off + idx * 16
                    )
                    if st_shndx != SHN_UNDEF and st_shndx < e_shnum and st_value == e_entry:
                        nm = _read_cstr(strtab, st_name)
                        if nm:
                            entry_candidates.append(nm)

    for preferred in ("glam_app_entry", "swift_app_entry"):
        if preferred in entry_candidates:
            report.entry_symbol = preferred
            break
    if not report.entry_symbol and entry_candidates:
        report.entry_symbol = entry_candidates[0]

    if not report.entry_symbol:
        report.warnings.append(f"未在符号表识别到入口符号名 (e_entry=0x{e_entry:x})")
    elif report.entry_symbol not in ("glam_app_entry", "swift_app_entry"):
        report.warnings.append(
            f"入口函数为 '{report.entry_symbol}'，推荐使用 glam_app_entry (或兼容名称 swift_app_entry)"
        )

    for sh in shdrs:
        if sh[1] != SHT_RELA:
            continue
        target_idx = sh[7]
        symtab_idx = sh[6]
        if target_idx >= e_shnum or symtab_idx >= e_shnum:
            report.errors.append("RELA 重定位节索引越界")
            continue
        target_sh = shdrs[target_idx]
        if (target_sh[2] & SHF_ALLOC) == 0:
            continue

        report.rela_sections += 1
        sym_sh = shdrs[symtab_idx]
        strtab_idx = sym_sh[6]
        if (
            strtab_idx >= e_shnum
            or sh[4] + sh[5] > len(elf_bytes)
            or sym_sh[4] + sym_sh[5] > len(elf_bytes)
            or shdrs[strtab_idx][4] + shdrs[strtab_idx][5] > len(elf_bytes)
        ):
            report.errors.append("symtab/strtab 边界损坏")
            continue

        sym_count = sym_sh[5] // 16
        strtab = elf_bytes[shdrs[strtab_idx][4] : shdrs[strtab_idx][4] + shdrs[strtab_idx][5]]
        rela_count = sh[5] // 12

        for j in range(rela_count):
            r_off, r_info, _r_addend = struct.unpack_from("<IIi", elf_bytes, sh[4] + j * 12)
            r_type = r_info & 0xFF
            r_sym = r_info >> 8

            if r_type == R_XTENSA_NONE:
                continue
            if r_sym >= sym_count:
                report.errors.append(f"重定位符号索引越界: {r_sym} >= {sym_count}")
                continue

            st_name, _st_val, _st_sz, _st_info, _st_other, st_shndx = struct.unpack_from(
                "<IIIBBH", elf_bytes, sym_sh[4] + r_sym * 16
            )

            if r_type == R_XTENSA_SLOT0_OP:
                if st_shndx == SHN_UNDEF:
                    sym_name = _read_cstr(strtab, st_name) or "<unnamed>"
                    report.errors.append(
                        f"外部符号 '{sym_name}' 使用了短调用 R_XTENSA_SLOT0_OP，请务必使用 -mlongcalls 编译"
                    )
                continue

            if r_off + 4 > max_vaddr:
                report.errors.append(f"重定位偏移越界: 0x{r_off:x} > 0x{max_vaddr:x}")
                continue

            if r_type in (R_XTENSA_32, R_XTENSA_JMP_SLOT, R_XTENSA_RELATIVE):
                if st_shndx == SHN_UNDEF:
                    if st_name >= len(strtab):
                        report.errors.append("外部符号名称偏移越界")
                        continue
                    sym_name = _read_cstr(strtab, st_name)
                    if sym_name in ABI_WHITELIST_SYMBOLS:
                        used_os.add(sym_name)
                    else:
                        if sym_name not in blocked:
                            blocked.add(sym_name)
                            report.errors.append(
                                f"禁止或未导出的外部符号 '{sym_name or '<empty>'}'（G'lam OS ABI 仅允许白名单符号；请改用 os->* 系统接口）"
                            )
                elif st_shndx >= e_shnum:
                    report.errors.append(f"非法符号段索引 st_shndx={st_shndx}")
            else:
                report.errors.append(f"不支持的 Xtensa 重定位类型 r_type={r_type}")

    if report.rela_sections == 0:
        report.errors.append("缺少 SHF_ALLOC 重定位表 (SHT_RELA)，链接时必须添加 -Wl,-q")

    report.used_os_symbols = sorted(used_os)
    report.blocked_symbols = sorted(blocked)
    report.ok = len(report.errors) == 0
    return report


def check_elf_file(elf_path: str) -> ElfCheckReport:
    with open(elf_path, "rb") as f:
        data = f.read()
    return check_elf_bytes(data)
