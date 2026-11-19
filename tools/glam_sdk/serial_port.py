"""
Cross-backend Serial Port Discovery and Communication.
Uses pyserial when installed, and falls back to native Windows Win32 APIs (ctypes + winreg)
so standalone Python environments without pyserial can still push .gla/.spk over USB UART.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import re
from typing import Dict, List, Optional


def _com_sort_key(dev: str) -> int:
    m = re.search(r"(\d+)$", dev or "")
    return int(m.group(1)) if m else 9999


def list_serial_ports() -> List[Dict[str, str]]:
    try:
        from serial.tools import list_ports  # type: ignore

        ports = []
        for p in list_ports.comports():
            ports.append(
                {
                    "device": p.device,
                    "description": p.description or p.device,
                }
            )
        ports.sort(key=lambda x: _com_sort_key(x["device"]))
        return ports
    except Exception:
        pass

    if os.name == "nt":
        try:
            import winreg

            ports = []
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM") as key:
                idx = 0
                while True:
                    try:
                        name, val, _ = winreg.EnumValue(key, idx)
                        dev = str(val).strip()
                        if dev:
                            short_name = name.rsplit("\\", 1)[-1]
                            ports.append({"device": dev, "description": f"{dev} ({short_name})"})
                        idx += 1
                    except OSError:
                        break
            ports.sort(key=lambda x: _com_sort_key(x["device"]))
            return ports
        except Exception:
            return []
    return []


if os.name == "nt":
    class _DCB(ctypes.Structure):
        _fields_ = [
            ("DCBlength", wt.DWORD),
            ("BaudRate", wt.DWORD),
            ("fBinary", wt.DWORD, 1),
            ("fParity", wt.DWORD, 1),
            ("fOutxCtsFlow", wt.DWORD, 1),
            ("fOutxDsrFlow", wt.DWORD, 1),
            ("fDtrControl", wt.DWORD, 2),
            ("fDsrSensitivity", wt.DWORD, 1),
            ("fTXContinueOnXoff", wt.DWORD, 1),
            ("fOutX", wt.DWORD, 1),
            ("fInX", wt.DWORD, 1),
            ("fErrorChar", wt.DWORD, 1),
            ("fNull", wt.DWORD, 1),
            ("fRtsControl", wt.DWORD, 2),
            ("fAbortOnError", wt.DWORD, 1),
            ("fDummy2", wt.DWORD, 17),
            ("wReserved", wt.WORD),
            ("XonLim", wt.WORD),
            ("XoffLim", wt.WORD),
            ("ByteSize", wt.BYTE),
            ("Parity", wt.BYTE),
            ("StopBits", wt.BYTE),
            ("XonChar", ctypes.c_char),
            ("XoffChar", ctypes.c_char),
            ("ErrorChar", ctypes.c_char),
            ("EofChar", ctypes.c_char),
            ("EvtChar", ctypes.c_char),
            ("wReserved1", wt.WORD),
        ]

    class _COMMTIMEOUTS(ctypes.Structure):
        _fields_ = [
            ("ReadIntervalTimeout", wt.DWORD),
            ("ReadTotalTimeoutMultiplier", wt.DWORD),
            ("ReadTotalTimeoutConstant", wt.DWORD),
            ("WriteTotalTimeoutMultiplier", wt.DWORD),
            ("WriteTotalTimeoutConstant", wt.DWORD),
        ]

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE]
    _k32.CreateFileW.restype = wt.HANDLE
    _k32.CloseHandle.argtypes = [wt.HANDLE]
    _k32.CloseHandle.restype = wt.BOOL
    _k32.GetCommState.argtypes = [wt.HANDLE, ctypes.POINTER(_DCB)]
    _k32.GetCommState.restype = wt.BOOL
    _k32.SetCommState.argtypes = [wt.HANDLE, ctypes.POINTER(_DCB)]
    _k32.SetCommState.restype = wt.BOOL
    _k32.SetCommTimeouts.argtypes = [wt.HANDLE, ctypes.POINTER(_COMMTIMEOUTS)]
    _k32.SetCommTimeouts.restype = wt.BOOL
    _k32.PurgeComm.argtypes = [wt.HANDLE, wt.DWORD]
    _k32.PurgeComm.restype = wt.BOOL
    _k32.ReadFile.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
    _k32.ReadFile.restype = wt.BOOL
    _k32.WriteFile.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
    _k32.WriteFile.restype = wt.BOOL
    _k32.FlushFileBuffers.argtypes = [wt.HANDLE]
    _k32.FlushFileBuffers.restype = wt.BOOL

    _INVALID_HANDLE = wt.HANDLE(-1).value


class _Win32Serial:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.4):
        if os.name != "nt":
            raise RuntimeError("请安装 pyserial 以在当前操作系统使用串口安装功能")
        self.port = port
        self.baud = baud
        self.timeout_ms = max(20, int(timeout * 1000))
        self.handle: Optional[int] = None
        self._rx_buf = bytearray()

        dev_path = port if port.startswith(r"\\.") else rf"\\.\{port}"
        h = _k32.CreateFileW(dev_path, 0xC0000000, 0, None, 3, 0, None)
        if h == _INVALID_HANDLE or h == 0:
            err = ctypes.get_last_error()
            raise OSError(err, f"无法打开串口 {port} (WinError {err})")
        self.handle = h

        dcb = _DCB()
        dcb.DCBlength = ctypes.sizeof(_DCB)
        if not _k32.GetCommState(h, ctypes.byref(dcb)):
            err = ctypes.get_last_error()
            self.close()
            raise OSError(err, f"GetCommState 失败 (WinError {err})")

        dcb.BaudRate = baud
        dcb.ByteSize = 8
        dcb.Parity = 0
        dcb.StopBits = 0
        dcb.fBinary = 1
        dcb.fParity = 0
        dcb.fOutxCtsFlow = 0
        dcb.fOutxDsrFlow = 0
        dcb.fDtrControl = 0
        dcb.fRtsControl = 0
        dcb.fOutX = 0
        dcb.fInX = 0
        if not _k32.SetCommState(h, ctypes.byref(dcb)):
            err = ctypes.get_last_error()
            self.close()
            raise OSError(err, f"SetCommState 失败 (WinError {err})")

        timeouts = _COMMTIMEOUTS(20, 0, self.timeout_ms, 0, 2000)
        _k32.SetCommTimeouts(h, ctypes.byref(timeouts))

    def reset_input_buffer(self) -> None:
        self._rx_buf.clear()
        if self.handle:
            _k32.PurgeComm(self.handle, 0x0008 | 0x0004)

    def write(self, data: bytes) -> int:
        if not self.handle:
            raise RuntimeError("串口已关闭")
        written = wt.DWORD(0)
        ok = _k32.WriteFile(self.handle, data, len(data), ctypes.byref(written), None)
        if not ok:
            err = ctypes.get_last_error()
            raise OSError(err, f"串口写入失败 (WinError {err})")
        return int(written.value)

    def flush(self) -> None:
        if self.handle:
            _k32.FlushFileBuffers(self.handle)

    def readline(self) -> bytes:
        if not self.handle:
            return b""
        nl = self._rx_buf.find(b"\n")
        if nl != -1:
            line = bytes(self._rx_buf[: nl + 1])
            del self._rx_buf[: nl + 1]
            return line

        chunk = (ctypes.c_char * 512)()
        read_bytes = wt.DWORD(0)
        ok = _k32.ReadFile(self.handle, chunk, 512, ctypes.byref(read_bytes), None)
        if ok and read_bytes.value > 0:
            self._rx_buf.extend(bytes(chunk[: read_bytes.value]))
            nl = self._rx_buf.find(b"\n")
            if nl != -1:
                line = bytes(self._rx_buf[: nl + 1])
                del self._rx_buf[: nl + 1]
                return line
        if not ok:
            return b""
        return b""

    def close(self) -> None:
        if self.handle:
            _k32.CloseHandle(self.handle)
            self.handle = None


class SerialLink:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.4):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self._impl = None

    def __enter__(self):
        try:
            import serial  # type: ignore

            self._impl = serial.Serial(
                self.port,
                baudrate=self.baud,
                timeout=self.timeout,
                write_timeout=2.0,
                dsrdtr=False,
                rtscts=False,
            )
            return self._impl
        except ImportError:
            self._impl = _Win32Serial(self.port, baud=self.baud, timeout=self.timeout)
            return self._impl

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._impl is not None:
            try:
                self._impl.close()
            finally:
                self._impl = None
