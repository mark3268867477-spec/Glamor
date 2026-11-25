# G'lamor — Zero-Environment PC Controller & C/ELF SDK for G'lam OS

<p align="center">
  <b>Official Zero-Environment PC Controller, C/ELF App SDK, ABI Preflight Auditor &amp; <code>.gla</code> Packager</b><br>
  <b>G'lam OS 官方零环境开发控制器 · C/ELF 动态应用 SDK · PC 端 17 符号 ABI 静态体检 · <code>.gla</code> 打包与热装机工作台</b><br><br>
  <a href="#english-developer-guide">English Developer Guide</a> &nbsp;|&nbsp; <a href="#中文开发者手册">中文开发者手册</a> &nbsp;|&nbsp;
  <a href="CHANGELOG.md">Changelog / 更新日志</a> &nbsp;|&nbsp;
  <a href="https://github.com/mark3268867477-spec/Glam-OS">Companion OS Kernel Repository (Glam-OS)</a>
</p>

<p align="center">
  <img src="docs/images/glamor_workbench.png" alt="G'lamor v1.0.0 Workbench" width="760">
</p>

---

<a id="english-developer-guide"></a>
# English Developer Guide

> **Companion OS Firmware Repository**:  
> **G'lamor** is the official zero-environment PC controller and C/ELF App SDK for **[G'lam OS (`mark3268867477-spec/Glam-OS`)](https://github.com/mark3268867477-spec/Glam-OS)**.  
> For the ESP32-S3 kernel source, PSRAM ELF32 dual-bus loader, and adaptive multi-board BSP, visit **[mark3268867477-spec/Glam-OS](https://github.com/mark3268867477-spec/Glam-OS)**.

---

## Table of Contents

1. [Technical Overview](#1-technical-overview)
2. [Zero-Environment Quick Start (No Python / No ESP-IDF)](#2-zero-environment-quick-start-no-python--no-esp-idf)
3. [App Project Layout (Multi-File Supported)](#3-app-project-layout-multi-file-supported)
4. [`manifest.json` & Three-Tier Background Lifecycle (`bg_policy`)](#4-manifestjson--three-tier-background-lifecycle-bg_policy)
5. [`glam_os_api.h` (ABI v1) C API Reference](#5-glam_os_apih-abi-v1-c-api-reference)
6. [17-Symbol Kernel Whitelist & Sensor Access](#6-17-symbol-kernel-whitelist--sensor-access)
7. [`.gla` Binary Package Format](#7-gla-binary-package-format)
8. [`glamctl` CLI & Custom Makefile Flags](#8-glamctl-cli--custom-makefile-flags)
9. [Troubleshooting & Performance Guardrails](#9-troubleshooting--performance-guardrails)

---

## 1. Technical Overview

On **[G'lam OS](https://github.com/mark3268867477-spec/Glam-OS)**, applications are decoupled from the internal Flash kernel: third-party programs are compiled into relocatable **Xtensa ELF32 (`app.elf`)** binaries, packaged into **`.gla`** archives on the external TF card, and dynamically loaded into **8MB Octal PSRAM** (`DBUS 0x3Cxxxxxx` / `IBUS 0x42xxxxxx`) to execute as native machine code with zero Flash wear and no device reboot.

**G'lamor** packages the complete cross-compilation and verification pipeline into a **38 MB portable Windows x64 bundle**:
* **Embedded Toolchain & Runtime**: Ships with a slim `xtensa-esp32s3-elf-gcc` (14.2.0) and Python 3.13 / Tk runtime—no Python or ESP-IDF installation required;
* **PC-Side 17-Symbol ABI Preflight Checker (`elf_check.py`)**: Inspects ELF32 relocation sections and undefined symbols on the host before packaging, blocking short-call relocations (`R_XTENSA_SLOT0_OP`) and unexported libc calls (`printf`, `malloc`, `fopen`);
* **`.gla` Packager + Triple-Channel Hot Installer + 320×240 Framebuffer Capture**.

---

## 2. Zero-Environment Quick Start (No Python / No ESP-IDF)

1. **Download & Launch**: Download `Glamor_v1.0.0_Win64_Portable.zip` from **[GitHub Releases](https://github.com/mark3268867477-spec/Glamor/releases/latest)**, extract, and run **`G'lamor.exe`**. Confirm the top-right status badge shows **`GCC: 就绪`** (GCC Ready).
2. **Create & Edit**: Click **New App**, enter a reverse-domain ID (e.g. `com.dev.hello`), display name, category, and accent color. Edit `app_main.c` in any external editor (VS Code, CLion, Notepad++) and save—do not compile inside the external editor.
3. **Build, Audit & Pack (`.gla`)**: Click **Build · Check · Pack (`.gla`)** in Tab 1. G'lamor compiles all `.c` sources, runs the 17-symbol ABI preflight check, embeds a `40×40` Baseline JPEG icon, and outputs `<app_id>.gla`.
4. **Hot-Install to Device (Tab 2)**: Deploy via **Wi-Fi HTTP**, **USB Serial (`COMx`)**, or **TF Card Direct Write**. No SPI Flash erase and no reboot required.
5. **Telemetry & Screen Capture (Tab 3)**: Monitor free PSRAM/SRAM, remotely uninstall apps, and capture 320×240 BMP screenshots over Wi-Fi.

---

## 3. App Project Layout (Multi-File Supported)

```text
com.example.myapp/
 ├── manifest.json        # [Required] App metadata, category & bg_policy
 ├── icon.png             # [Optional] Custom icon (auto-cropped to 40x40 Baseline JPEG)
 ├── app_main.c           # [Required] Entry source defining glam_app_entry()
 ├── include/             # [Optional] Private headers (.h)
 └── src/                 # [Optional] Additional .c modules (auto-compiled & linked)
```

---

## 4. `manifest.json` & Three-Tier Background Lifecycle (`bg_policy`)

| Field | Required | Rules |
| :--- | :---: | :--- |
| `id` | Yes | Reverse-domain ID (`a-zA-Z0-9._-`, no `..`, `< 64B`) |
| `name` | Yes | Launcher & task manager display name (`< 64B` UTF-8) |
| `version` | Yes | SemVer string e.g. `"1.0.0"` (`< 16B`) |
| `api_level` | Yes | Must be `1` (`GLAM_OS_API_VERSION`) |
| `entry` | Yes | Must be `"app.elf"` |
| `category` | Yes | `"game"` \| `"media"` \| `"service"` \| `"tool"` \| `"system"` |
| `bg_policy` | Rec. | `"kill_all"` \| `"partial_service"` \| `"keep_all"` |
| `accent` | No | Hex tile color `"#RRGGBB"` |

* **`kill_all`** (default for `game`/`system`): Calls `on_destroy()` and frees all PSRAM immediately on exit.
* **`partial_service`** (default for `media`/`service`): Releases UI widgets while retaining a background slot only while audio playback or a timer is active.
* **`keep_all`** (default for `tool`): Retains full PSRAM state and **suspends all app timers (0% background CPU)** for instant zero-latency resumption.

---

## 5. `glam_os_api.h` (ABI v1) C API Reference

Apps receive `const glam_os_api_t *os` and a `320×216` `root` container (`GLAM_APP_W=320`, `GLAM_APP_H=216`, below the `24px` OS status bar) in `on_create()`, and must export `const glam_app_desc_t *glam_app_entry(void)`.

```c
#include "glam_os_api.h"

static const glam_os_api_t *s_os = NULL;
static glam_obj_t s_lbl = NULL;
static glam_timer_t s_timer = NULL;
static uint32_t s_ticks = 0;

static void on_btn_click(void *user_data) {
    (void)user_data;
    s_ticks++;
    char buf[64];
    s_os->fmt_snprintf(buf, sizeof(buf), "Clicks: %u", (unsigned)s_ticks);
    s_os->ui_set_label_text(s_lbl, buf);
    s_os->show_toast("Button clicked!");
}

static void on_exit_click(void *user_data) {
    (void)user_data;
    s_os->request_exit();
}

static void on_timer_tick(void *user_data) { (void)user_data; }

static int app_on_create(const glam_os_api_t *os, glam_obj_t root, const char *app_id, const char *data_dir) {
    (void)app_id; (void)data_dir;
    s_os = os;
    s_ticks = 0;
    os->ui_clear_root(root, 0x0B1120U);
    glam_obj_t card = os->ui_create_panel(root, 8, 8, 304, 200, 0x131C31U, 12, 0x0EA5E9U);
    os->ui_create_label(card, "Hello G'lam OS!", 14, 12, 0xF8FAFCU, 16);
    s_lbl = os->ui_create_label(card, "Clicks: 0", 14, 48, 0x38BDF8U, 14);
    os->ui_create_button(card, "+1", 14, 146, 132, 38, 0x0284C7U, on_btn_click, NULL);
    os->ui_create_button(card, "Exit", 158, 146, 132, 38, 0x334155U, on_exit_click, NULL);
    s_timer = os->ui_create_timer(on_timer_tick, 1000, NULL);
    return 0;
}

static void app_on_destroy(void) {
    if (s_timer && s_os) {
        s_os->ui_delete_timer(s_timer);
        s_timer = NULL;
    }
}

static const glam_app_desc_t s_desc = {
    .on_create  = app_on_create,
    .on_destroy = app_on_destroy,
};

const glam_app_desc_t *glam_app_entry(void) { return &s_desc; }
```

* **System & PSRAM**: `api_version`, `log_info`, `show_toast`, `request_exit`, `get_free_psram`, `get_free_sram`, `malloc_psram`, `free_psram`, `fmt_snprintf`
* **Safe UI Widgets**: `ui_clear_root`, `ui_create_panel`, `ui_create_label`, `ui_set_label_text`, `ui_set_label_color`, `ui_create_button`, `ui_create_bar`, `ui_set_bar_value`, `ui_create_list`, `ui_list_add_btn`, `ui_create_timer`, `ui_delete_timer`
* **Sandboxed Storage (`/sdcard/data/<app_id>/`)**: `storage_write_text`, `storage_read_text`
* **Audio & Hardware**: `audio_play_file`, `audio_pause`, `audio_resume`, `audio_stop`, `audio_is_playing`, `audio_set_volume`, `audio_scan_music`, `wifi_is_connected`, `wifi_get_ip`, `sd_is_mounted`

---

## 6. 17-Symbol Kernel Whitelist & Sensor Access

* **Memory/String (8)**: `memcpy`, `memset`, `memmove`, `memcmp`, `strlen`, `strcmp`, `strncmp`, `snprintf`
* **I2C Sensor Bus (5)**: `bsp_i2c_get_handle`, `i2c_master_bus_add_device`, `i2c_master_bus_rm_device`, `i2c_master_transmit`, `i2c_master_transmit_receive`
* **LVGL Fast Animation (4)**: `lv_obj_set_pos`, `lv_obj_set_style_bg_color`, `lv_obj_add_flag`, `lv_obj_clear_flag`

*(Refer to `app_sdk_template/apps/com.glam.racer/app_main.c` for a full 6-axis QMI8658 IMU example. Replace `printf` / `malloc` / `free` / `fopen` with `os->log_info` / `os->malloc_psram` / `os->free_psram` / `os->storage_*_text`.)*

---

## 7. `.gla` Binary Package Format

`160-byte fixed Header (<4sHHII64s64s16s) + manifest_bytes + elf_bytes`:
* `0x00 (4B)`: `magic` = `"GLAM"` (or `"SWPK"` in legacy mode)
* `0x04 (2B)`: `version` = `1`; `0x06 (2B)`: `header_len`
* `0x08 (4B)`: `elf_size`; `0x0C (4B)`: IEEE 802.3 `crc32` over `manifest_bytes + elf_bytes`
* `0x10 (64B)`: `app_id`; `0x50 (64B)`: `app_name`; `0x90 (16B)`: `app_version`

---

## 8. `glamctl` CLI & Custom Makefile Flags

```cmd
glamctl.exe devices
glamctl.exe init my_apps\com.dev.demo --id com.dev.demo --name "Demo" --category tool --accent #0EA5E9
glamctl.exe pack my_apps\com.dev.demo --build --out dist\com.dev.demo.gla
glamctl.exe verify dist\com.dev.demo.gla
glamctl.exe install dist\com.dev.demo.gla --wifi 192.168.1.50
glamctl.exe install dist\com.dev.demo.gla --port COM7
glamctl.exe screenshot --wifi 192.168.1.50 --out screen.bmp
```

**Required GCC Flags for Custom Makefiles**:
```makefile
CFLAGS  = -mlongcalls -mtext-section-literals -fno-common -ffunction-sections -fdata-sections -O2 -Wall -Wextra -I<sdk>/include
LDFLAGS = -nostdlib -Wl,-T,<sdk>/ld/glam_app.ld -Wl,-q -Wl,--gc-sections -Wl,--unresolved-symbols=ignore-all -lgcc
```

---

## 9. Troubleshooting & Performance Guardrails

1. **Disallowed symbol error**: Calling `printf`, `malloc`, `sinf`, etc. fails `elf_check.py`; use `os->log_info`, `os->malloc_psram`, or self-contained helpers.
2. **`R_XTENSA_SLOT0_OP` short-call error**: Always pass `-mlongcalls` because PSRAM (`0x42xxxxxx`) and Flash/IRAM (`0x403xxxxx`) exceed the 512KB call range.
3. **Missing relocation table**: Always link with `-Wl,-q`.
4. **UI thread budget**: Keep `ui_create_timer` callbacks under `10 ms`; never block or call `vTaskDelay`.

---
---

<a id="中文开发者手册"></a>
# 中文开发者手册

> **配套操作系统固件仓库**：  
> 本项目是 **[G'lam OS (`mark3268867477-spec/Glam-OS`)](https://github.com/mark3268867477-spec/Glam-OS)** 的配套电脑端开发控制器与第三方应用 SDK。  
> 欲了解 ESP32-S3 系统内核、PSRAM ELF32 双总线加载器与多板卡自适应 BSP，请访问 **[mark3268867477-spec/Glam-OS](https://github.com/mark3268867477-spec/Glam-OS)**。

---

## 一、 技术背景：G'lamor 如何打通动态应用开发闭环

在 **[G'lam OS](https://github.com/mark3268867477-spec/Glam-OS)** 中，应用与操作系统内核在物理存储与链接空间上完全解耦：所有第三方应用均编译为可重定位 **Xtensa ELF32 (`app.elf`)**，打包为 **`.gla`** 安装包后写入外部 TF 卡，由内核动态加载至 **8MB Octal PSRAM**（`DBUS 0x3C` / `IBUS 0x42`）以原生机器码运行。

**G'lamor** 将上述交叉编译与安全审计复杂度封装进 **38 MB 的零环境 Windows 64 位绿色压缩包**：
* **内置完整便携工具链**：集成精简版 `xtensa-esp32s3-elf-gcc` (14.2.0) 与独立 Python 3.13 / Tk 运行时，免装 Python 与 ESP-IDF；
* **PC 端 ELF ABI 静态预检 (`elf_check.py`)**：在打包阶段直接解析 ELF32 节表、重定位表与未定义符号，对照内核 **17 项安全白名单** 拦截短调用与非法符号；
* **一键 `.gla` 打包 + 三通道热安装 + 320×240 实时抓屏监控**。

---

## 二、 零环境快速上手（免 Python / 免 ESP-IDF）

1. **下载并启动**：前往 **[GitHub Releases](https://github.com/mark3268867477-spec/Glamor/releases/latest)** 下载 `Glamor_v1.0.0_Win64_Portable.zip`，解压后双击 **`G'lamor.exe`**，顶部显示绿色 **`GCC: 就绪`** 即说明编译器挂载成功。
2. **新建并编辑 `.c`**：点击 **「新建应用」** 创建模板后，用 **VS Code / CLion / Dev-C++ / Notepad++** 打开 `app_main.c` 编写逻辑并保存（不要在外部编辑器中自行编译）。
3. **一键编译、体检并打包 `.gla`**：在 **「1. 构建 & 打包 (.gla)」** 页点击 **「一键编译 · 体检 · 打包 (.gla)」**，右侧实时输出体检结果、ELF 体积、预计 PSRAM 占用及重定位节数，生成 `<app_id>.gla`。
4. **三通道热安装（绝不刷写 Flash）**：在 **「2. 安装到设备」** 页任选 **Wi-Fi 无线推送**、**USB 串口热推 (`COMx`)** 或 **TF 卡离线直写**，无需重启即可在设备桌面看到新图标。
5. **设备监控与投屏**：在 **「3. 设备管理 & 实时投屏」** 页输入设备 IP，可查看 PSRAM/SRAM 水位、远程卸载应用与实时抓取 320×240 画面。

---

## 三、 应用工程目录结构与 `manifest.json` 规范

```text
com.example.myapp/
 ├── manifest.json        # [必填] 应用元数据、分类与后台生命周期策略
 ├── icon.png             # [可选] 自定义图标 (自动转 40x40 Baseline JPEG)
 ├── app_main.c           # [必填] 应用主源码（定义 glam_app_entry 入口）
 ├── include/             # [可选] 工程私有头文件 (.h)
 └── src/                 # [可选] 多模块拆分源码 (.c)，编译时自动合并链接
```

| 字段名 | 类型 | 必填 | 约束说明 |
| :--- | :--- | :---: | :--- |
| `id` | String | 是 | 唯一反向域名标识，仅允许 `a-zA-Z0-9._-`，禁含 `..`，UTF-8 `< 64B` |
| `name` | String | 是 | 桌面磁贴与后台列表显示名称，UTF-8 `< 64B` |
| `version` | String | 是 | 语义化版本号（如 `"1.0.0"`），`< 16B` |
| `api_level` | Number | 是 | 固定 `1`（对应 `GLAM_OS_API_VERSION = 1`） |
| `entry` | String | 是 | 固定 `"app.elf"` |
| `category` | String | 是 | `"game"` \| `"media"` \| `"service"` \| `"tool"` \| `"system"` |
| `bg_policy` | String | 推荐 | `"kill_all"`（退出即销毁） \| `"partial_service"`（服务保活） \| `"keep_all"`（挂起且 0% CPU 冻结定时器） |
| `accent` | String | 否 | 主题色 `"#RRGGBB"` |

---

## 四、 `glam_os_api.h` (ABI v1) 与 17 项导出符号白名单

* **系统与内存**：`api_version`、`log_info`、`show_toast`、`request_exit`、`get_free_psram`、`get_free_sram`、`malloc_psram`、`free_psram`、`fmt_snprintf`
* **安全 UI 控件 (`320×216` 视口)**：`ui_clear_root`、`ui_create_panel`、`ui_create_label`、`ui_set_label_text`、`ui_set_label_color`、`ui_create_button`、`ui_create_bar`、`ui_set_bar_value`、`ui_create_list`、`ui_list_add_btn`、`ui_create_timer`、`ui_delete_timer`
* **沙盒存储 (`/sdcard/data/<app_id>/`)**：`storage_write_text`、`storage_read_text`
* **音频与外设**：`audio_play_file`、`audio_pause`、`audio_resume`、`audio_stop`、`audio_is_playing`、`audio_set_volume`、`audio_scan_music`、`wifi_is_connected`、`wifi_get_ip`、`sd_is_mounted`
* **17 项直接重定位白名单符号**：
  * 内存与字符串 (8)：`memcpy`, `memset`, `memmove`, `memcmp`, `strlen`, `strcmp`, `strncmp`, `snprintf`
  * I2C 传感器总线 (5)：`bsp_i2c_get_handle`, `i2c_master_bus_add_device`, `i2c_master_bus_rm_device`, `i2c_master_transmit`, `i2c_master_transmit_receive`
  * LVGL 辅助 (4)：`lv_obj_set_pos`, `lv_obj_set_style_bg_color`, `lv_obj_add_flag`, `lv_obj_clear_flag`

---

## 五、 `glamctl` 命令行参考与手动 Makefile 参数

```cmd
glamctl.exe devices
glamctl.exe init my_apps\com.dev.demo --id com.dev.demo --name "示例工具" --category tool --accent #0EA5E9
glamctl.exe pack my_apps\com.dev.demo --build --out dist\com.dev.demo.gla
glamctl.exe verify dist\com.dev.demo.gla
glamctl.exe install dist\com.dev.demo.gla --wifi 192.168.1.50
glamctl.exe install dist\com.dev.demo.gla --port COM7
glamctl.exe screenshot --wifi 192.168.1.50 --out screen.bmp
```

手动 Makefile 必须携带的参数：
```makefile
CFLAGS  = -mlongcalls -mtext-section-literals -fno-common -ffunction-sections -fdata-sections -O2 -Wall -Wextra -I<sdk>/include
LDFLAGS = -nostdlib -Wl,-T,<sdk>/ld/glam_app.ld -Wl,-q -Wl,--gc-sections -Wl,--unresolved-symbols=ignore-all -lgcc
```
