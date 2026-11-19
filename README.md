# G'lamor — Zero-Environment PC Controller & C/ELF SDK for G'lam OS

<p align="center">
  <b>让纯 C 开发者免装任何 ESP-IDF 环境，3 分钟写出跑在 ESP32-S3 桌面上的动态应用</b><br>
  <b>Official Zero-Environment PC Controller · C/ELF App SDK · PC-Side 17-Symbol ABI Checker · <code>.gla</code> Packager</b><br><br>
  <a href="#中文开发者手册">🇨🇳 中文开发者手册</a> &nbsp;|&nbsp; <a href="#english-developer-guide">🇺🇸 English Developer Guide</a> &nbsp;|&nbsp;
  <a href="https://github.com/mark3268867477-spec/Glam-OS">🖥️ 配套 OS 内核仓库 (Glam-OS)</a>
</p>

<p align="center">
  <img src="docs/images/glamor_workbench.png" alt="G'lamor v1.0.0 Workbench" width="760">
</p>

---

<a id="中文开发者手册"></a>
# 🇨🇳 中文开发者手册

> 🔗 **配套操作系统固件仓库**：  
> 本项目是 **[G'lam OS (`mark3268867477-spec/Glam-OS`)](https://github.com/mark3268867477-spec/Glam-OS)** 的配套电脑端开发控制器与第三方应用 SDK。  
> 想要了解 ESP32-S3 系统内核、PSRAM ELF32 动态加载器或刷写 OS 底包固件，请访问：  
> 👉 **[G'lam OS 系统固件仓库 (`mark3268867477-spec/Glam-OS`)](https://github.com/mark3268867477-spec/Glam-OS)**

---

## 📖 目录

1. [为什么 G'lamor + G'lam OS 能颠覆传统单片机开发？](#一-为什么-glamor--glam-os-能颠覆传统单片机开发)
2. [第三方开发者 3 分钟零环境上手（免 Python / 免 ESP-IDF）](#二-第三方开发者-3-分钟零环境上手免-python--免-esp-idf)
3. [应用工程目录结构（支持多文件编译）](#三-应用工程目录结构支持多文件编译)
4. [`manifest.json` 完整配置规范与三级后台策略](#四-manifestjson-完整配置规范与三级后台策略)
5. [`glam_os_api.h` (ABI v1) 完整 C 接口手册](#五-glam_os_apih-abi-v1-完整-c-接口手册)
6. [内核 17 项导出符号白名单与传感器调用](#六-内核-17-项导出符号白名单与传感器调用)
7. [`.gla` 二进制安装包格式规范](#七-gla-二进制安装包格式规范)
8. [`glamctl` 命令行参考与 Makefile / CI 集成](#八-glamctl-命令行参考与-makefile--ci-集成)
9. [常见报错排查与性能红线](#九-常见报错排查与性能红线)

---

## 一、 为什么 G'lamor + G'lam OS 能颠覆传统单片机开发？

在 **[G'lam OS](https://github.com/mark3268867477-spec/Glam-OS)** 上，所有第三方应用均以独立可重定位 **Xtensa ELF32 (`app.elf`)** 打包为 **`.gla`** 存放在 TF 卡中，并在点击图标时动态加载到 **8MB Octal PSRAM** 中以原生机器码运行——**全程不触碰片内 Flash、永不刷砖、不用重启设备**。

但传统交叉编译有三大痛点：完整 ESP-IDF 体积数 GB、链接参数苛刻（必须 `-mlongcalls` + `glam_app.ld` 基址 `0x0` + `-Wl,-q` 保留重定位节）、以及误调未导出 `libc` 函数导致上机崩溃。

**G'lamor** 把所有复杂度封进了一个 **38 MB 的零环境 Windows 绿色压缩包**：
* **自带完整便携工具链**：内置精简版 `xtensa-esp32s3-elf-gcc` (55 MB 展开) + Python 3.13 / Tk 运行时，无需安装任何软件，解压即用；
* **PC 端 17 符号 ABI 安全预检 (`elf_check.py`)**：在打包前直接扫描 ELF 重定位节与符号表，对照内核 17 项白名单红字拦截违规调用，杜绝损坏包推上设备；
* **可视化 `.gla` 打包 + 三通道热安装 + 真机 320×240 实时投屏**。

---

## 二、 第三方开发者 3 分钟零环境上手（免 Python / 免 ESP-IDF）

### 第 1 步：下载并打开 G'lamor
* 前往 **[GitHub Releases](https://github.com/mark3268867477-spec/Glamor/releases/latest)** 下载 `Glamor_v1.0.0_Win64_Portable.zip`，解压到任意路径；
* 双击 **`G'lamor.exe`**（源码仓库用户可双击 `启动_Glamor.bat`），顶部显示绿色 **`GCC: 就绪`** 即说明编译器已挂载。

### 第 2 步：新建工程并用任意编辑器编写 `.c`
1. 点击右上角 **「新建应用」**，填写应用 ID（如 `com.dev.hello`）、中文显示名、分类与主题色，点击 **「创建工程」**；
2. 用你顺手的任意编辑器（**VS Code / CLion / Dev-C++ / Notepad++**）打开生成的 `app_main.c` 编写逻辑。**不需要在外部 IDE 点编译，写完保存 `.c` 即可！**

### 第 3 步：一键把 `.c` 编译、体检并打包为 `.gla`
回到 **G'lamor** 的 **「1. 构建 & 打包 (.gla)」** 页：
1. 可选点击 **「选择图标 (PNG/JPG)」** 替换桌面图标（自动居中裁剪为 `40×40` Baseline JPEG 内嵌）；
2. 点击 **「一键编译 · 体检 · 打包 (.gla)」**，右侧实时显示 **`体检通过`**、ELF 体积、预计 PSRAM 占用、入口符号及重定位节数，生成 `<app_id>.gla`。

### 第 4 步：三通道热安装到 G'lam OS（无需刷写 Flash）
切换到 **「2. 安装到设备」** 页，三选一即可直接写入 TF 卡 `/sdcard/apps/<app_id>/`，**板子无需重启，桌面立即出现新图标**：
1. **Wi-Fi 无线推送（推荐）**：输入板端局域网 IP（如 `192.168.1.50`）点击安装，或点「打开网页端」在浏览器上传 `.gla`；
2. **USB 串口热推**：正常开机插上数据线，选串口（如 `COM7`）点击安装；
3. **TF 卡离线直写**：选择读卡器盘符一键解包写入，或把 `.gla` 放入 TF 卡 `/install/` 后在设备「应用中心 / 文件管理」点击安装。

### 第 5 步：设备监控与 320×240 真机实时投屏
在 **「3. 设备管理 & 实时投屏」** 页输入板端 IP，可实时查看 PSRAM / SRAM 占用、一键远程卸载应用、抓取 320×240 真机画面或开启 2 秒自动刷新投屏。

---

## 三、 应用工程目录结构（支持多文件编译）

```text
com.example.myapp/
 ├── manifest.json        # [必填] 应用元数据、分类与后台生命周期声明
 ├── icon.png             # [可选] 自定义桌面图标 (自动转 40x40 Baseline JPEG)
 ├── app_main.c           # [必填] 应用主源码（定义 glam_app_entry 入口）
 ├── include/             # [可选] 工程私有头文件 (.h)
 │    └── game_logic.h
 └── src/                 # [可选] 多模块拆分源码 (.c)，编译时自动合并链接
      └── game_logic.c
```

---

## 四、 `manifest.json` 完整配置规范与三级后台策略

```json
{
  "id": "com.example.myapp",
  "name": "示例应用",
  "version": "1.0.0",
  "api_level": 1,
  "entry": "app.elf",
  "category": "tool",
  "bg_policy": "keep_all",
  "author": "Developer",
  "accent": "#0EA5E9",
  "description": "应用功能简述",
  "permissions": ["sandbox_data"]
}
```

| 字段名 | 类型 | 必填 | 约束说明 |
| :--- | :--- | :---: | :--- |
| `id` | String | 是 | 唯一反向域名，仅允许 `a-zA-Z0-9._-`，禁含 `..`，UTF-8 `< 64B` |
| `name` | String | 是 | 桌面磁贴与后台列表显示名称，UTF-8 `< 64B` |
| `version` | String | 是 | 语义化版本号（如 `"1.0.0"`），`< 16B` |
| `api_level` | Number | 是 | 固定 `1`（对应 `GLAM_OS_API_VERSION = 1`） |
| `entry` | String | 是 | 固定 `"app.elf"` |
| `category` | String | 是 | `"game"` \| `"media"` \| `"service"` \| `"tool"` \| `"system"` |
| `bg_policy` | String | 推荐 | `"kill_all"` \| `"partial_service"` \| `"keep_all"` |
| `accent` | String | 否 | 主题色 `"#RRGGBB"`（默认 `"#3B82F6"`） |
| `permissions` | Array | 否 | 可选 `"sandbox_data"`、`"audio"`、`"media_read"` |

### 三级后台生命周期策略 (`bg_policy`)
| 策略值 | 默认分类 | 返回桌面时的系统行为 |
| :--- | :--- | :--- |
| **`"kill_all"`** | `"game"`, `"system"` | 立即调用 `on_destroy()` 并释放全部 PSRAM，零后台残留 |
| **`"partial_service"`** | `"media"`, `"service"` | 释放前台 UI，仅在音频播放或倒计时运行中保留后台服务槽位 |
| **`"keep_all"`** | `"tool"` | 完整保留 PSRAM 现场并**自动冻结全部定时器（后台 0% CPU）**，切回时 **0 秒瞬时恢复** |

---

## 五、 `glam_os_api.h` (ABI v1) 完整 C 接口手册

* **屏幕视口尺寸**：`GLAM_SCREEN_W = 320`、`GLAM_SCREEN_H = 240`、顶部状态栏 `GLAM_STATUSBAR_H = 24`；传给 `on_create()` 的 `root` 视口尺寸为 **`320×216`**。
* **最小完整 C 代码模板**：

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
    s_os->fmt_snprintf(buf, sizeof(buf), "点击次数: %u", (unsigned)s_ticks);
    s_os->ui_set_label_text(s_lbl, buf);
    s_os->show_toast("已触发按钮点击!");
}

static void on_exit_click(void *user_data) {
    (void)user_data;
    s_os->request_exit();
}

static void on_timer_tick(void *user_data) {
    (void)user_data;
}

static int app_on_create(const glam_os_api_t *os, glam_obj_t root, const char *app_id, const char *data_dir) {
    (void)app_id; (void)data_dir;
    s_os = os;
    s_ticks = 0;
    os->ui_clear_root(root, 0x0B1120U);
    glam_obj_t card = os->ui_create_panel(root, 8, 8, 304, 200, 0x131C31U, 12, 0x0EA5E9U);
    os->ui_create_label(card, "Hello G'lam OS!", 14, 12, 0xF8FAFCU, 16);
    s_lbl = os->ui_create_label(card, "点击次数: 0", 14, 48, 0x38BDF8U, 14);
    os->ui_create_button(card, "点我 +1", 14, 146, 132, 38, 0x0284C7U, on_btn_click, NULL);
    os->ui_create_button(card, "退出应用", 158, 146, 132, 38, 0x334155U, on_exit_click, NULL);
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

const glam_app_desc_t *glam_app_entry(void) {
    return &s_desc;
}
```

### `glam_os_api_t` 全部 API 速查表
| 分类 | 接口签名 | 说明 |
| :--- | :--- | :--- |
| **系统与内存** | `api_version` | ABI 版本（恒为 `1`） |
| | `void (*log_info)(const char *tag, const char *fmt, ...)` | 串口调试日志（替代 `printf`） |
| | `void (*show_toast)(const char *msg)` | 底部 2.4 秒全局悬浮提示 |
| | `void (*request_exit)(void)` | 主动退出并销毁当前应用 |
| | `uint32_t (*get_free_psram)(void)` / `(*get_free_sram)(void)` | 查询剩余 PSRAM / SRAM 字节数 |
| | `void *(*malloc_psram)(size_t size)` / `(*free_psram)(void *ptr)` | PSRAM 动态内存分配/释放 |
| | `int (*fmt_snprintf)(char *buf, size_t size, const char *fmt, ...)` | 安全字符串格式化 |
| **安全 UI 控件** | `void (*ui_clear_root)(glam_obj_t root, uint32_t bg_hex)` | 清空并设置 `320×216` 背景色 |
| | `glam_obj_t (*ui_create_panel)(parent, x, y, w, h, bg_hex, radius, border_hex)` | 创建圆角卡片容器 |
| | `glam_obj_t (*ui_create_label)(parent, text, x, y, color_hex, font_size)` | 文本标签（含中文自动启用 14px CJK 字库） |
| | `void (*ui_set_label_text)(label, text)` / `(*ui_set_label_color)(label, color)` | 更新标签文案与颜色 |
| | `glam_obj_t (*ui_create_button)(parent, text, x, y, w, h, bg_hex, cb, user_data)` | 创建按钮并绑定点击回调 |
| | `glam_obj_t (*ui_create_bar)(parent, x, y, w, h, min_v, max_v, bg_hex, ind_hex)` | 创建进度条 + `ui_set_bar_value(bar, val)` |
| | `glam_obj_t (*ui_create_list)(parent, x, y, w, h, bg_hex)` | 创建滚动列表 + `ui_list_add_btn(...)` |
| | `glam_timer_t (*ui_create_timer)(cb, period_ms, user_data)` / `(*ui_delete_timer)(t)` | 主线程周期定时器（切后台 `keep_all` 自动冻结） |
| **沙盒存储** | `int (*storage_write_text)(app_id, rel_name, content)` | 写入 `/sdcard/data/<app_id>/<rel_name>` |
| | `int (*storage_read_text)(app_id, rel_name, out_buf, max_len)` | 读取沙盒文件（不存在返回 `-1`） |
| **音频与外设** | `audio_play_file` / `pause` / `resume` / `stop` / `is_playing` / `set_volume` / `scan_music` | 后台音频播放控制与 `/sdcard/music/` 扫描 |
| | `wifi_is_connected` / `wifi_get_ip` / `sd_is_mounted` | 查询网络状态、IP 与 TF 卡挂载 |

---

## 六、 内核 17 项导出符号白名单与传感器调用

| 类别 | 允许 `.elf` 直接重定位的 17 个外部符号 |
| :--- | :--- |
| **基础内存与字符串 (8)** | `memcpy`, `memset`, `memmove`, `memcmp`, `strlen`, `strcmp`, `strncmp`, `snprintf` |
| **I2C 传感器总线 (5)** | `bsp_i2c_get_handle`, `i2c_master_bus_add_device`, `i2c_master_bus_rm_device`, `i2c_master_transmit`, `i2c_master_transmit_receive` |
| **LVGL 高频动画辅助 (4)** | `lv_obj_set_pos`, `lv_obj_set_style_bg_color`, `lv_obj_add_flag`, `lv_obj_clear_flag` |

> 💡 完整体感实战参考：`app_sdk_template/apps/com.glam.racer/app_main.c`（760+ 行《极速赛车》，直接通过 I2C 驱动板载 **QMI8658 六轴陀螺仪**）。  
> ❌ 禁调 `printf` / `malloc` / `free` / `fopen`，请分别替换为 `os->log_info`、`os->malloc_psram`、`os->free_psram`、`os->storage_*_text`。

---

## 七、 `.gla` 二进制安装包格式规范

`160 字节定长 Header (<4sHHII64s64s16s) + manifest_bytes + elf_bytes`：
* `0x00 (4B)`：`magic` = `"GLAM"`（兼容旧版 `"SWPK"`）
* `0x04 (2B)`：`version` = `1`；`0x06 (2B)`：`header_len`（JSON 长度）
* `0x08 (4B)`：`elf_size`；`0x0C (4B)`：`crc32`（`manifest_bytes + elf_bytes` 的 IEEE 802.3 CRC32）
* `0x10 (64B)`：`app_id`；`0x50 (64B)`：`app_name`；`0x90 (16B)`：`app_version`

---

## 八、 `glamctl` 命令行参考与 Makefile / CI 集成

```cmd
glamctl.exe devices
glamctl.exe init my_apps\com.dev.demo --id com.dev.demo --name "示例工具" --category tool --accent #0EA5E9
glamctl.exe build my_apps\com.dev.demo
glamctl.exe check my_apps\com.dev.demo\app.elf
glamctl.exe pack my_apps\com.dev.demo --build --out dist\com.dev.demo.gla
glamctl.exe verify dist\com.dev.demo.gla
glamctl.exe install dist\com.dev.demo.gla --wifi 192.168.1.50
glamctl.exe install dist\com.dev.demo.gla --port COM7
glamctl.exe screenshot --wifi 192.168.1.50 --out screen.bmp
```

手动 Makefile 必须携带的编译链接参数：
```makefile
CFLAGS  = -mlongcalls -mtext-section-literals -fno-common -ffunction-sections -fdata-sections -O2 -Wall -Wextra -I<sdk>/include
LDFLAGS = -nostdlib -Wl,-T,<sdk>/ld/glam_app.ld -Wl,-q -Wl,--gc-sections -Wl,--unresolved-symbols=ignore-all -lgcc
```

---

## 九、 常见报错排查与性能红线

1. **违规符号拦截**：使用 `printf` / `malloc` / `sinf` 会被 `elf_check.py` 拦截，请改用 `os->log_info`、`os->malloc_psram` 或自实现轻量辅助函数。
2. **`R_XTENSA_SLOT0_OP` 短调用报错**：因应用运行在 PSRAM (`0x42xxxxxx`) 而内核在 Flash/IRAM (`0x403xxxxx`)，跨区调用必须加 `-mlongcalls`。
3. **缺少重定位表**：链接时必须带 `-Wl,-q` 保留 `SHT_RELA`。
4. **UI 帧率红线**：`ui_create_timer` 回调运行在 LVGL 主线程，**单次耗时不得超过 `10 ms`**，严禁阻塞或 `vTaskDelay`。

---
---

<a id="english-developer-guide"></a>
# 🇺🇸 English Developer Guide

> 🔗 **Companion OS Firmware Repository**:  
> **G'lamor** is the official zero-environment PC controller and C/ELF App SDK for **[G'lam OS (`mark3268867477-spec/Glam-OS`)](https://github.com/mark3268867477-spec/Glam-OS)**.  
> For the ESP32-S3 kernel source, PSRAM ELF32 dynamic loader, and hardware pinouts, visit **[mark3268867477-spec/Glam-OS](https://github.com/mark3268867477-spec/Glam-OS)**.

---

## 1. Why G'lamor + G'lam OS?

On **[G'lam OS](https://github.com/mark3268867477-spec/Glam-OS)**, third-party apps are **native Xtensa ELF32 binaries (`app.elf`)** packaged into **`.gla`** archives on the external TF card and dynamically loaded into **8MB Octal PSRAM** on launch—**zero internal Flash writes, brick-proof installs, and instant desktop refresh without rebooting**.

**G'lamor** eliminates the multi-gigabyte ESP-IDF setup and fragile linker flags by bundling everything into a **38 MB portable Windows x64 package**:
* **Zero-Environment Portable Toolchain**: Embedded slim `xtensa-esp32s3-elf-gcc` (14.2.0) + Python 3.13 / Tk runtime—works out of the box with no Python or ESP-IDF installed;
* **PC-Side 17-Symbol ABI Preflight Checker (`elf_check.py`)**: Inspects ELF relocation sections and symbol tables on your PC before packaging, blocking disallowed calls (`printf`, `malloc`, `fopen`, etc.) immediately;
* **One-Click `.gla` Packager + Triple-Channel Hot Installer + 320×240 Live Screen Mirroring**.

---

## 2. 3-Minute Zero-Environment Quick Start

1. **Download & Launch**: Grab `Glamor_v1.0.0_Win64_Portable.zip` from **[GitHub Releases](https://github.com/mark3268867477-spec/Glamor/releases/latest)**, extract, and double-click **`G'lamor.exe`**. Verify the top-right badge shows **`GCC: 就绪`** (GCC Ready).
2. **Create & Edit**: Click **New App (`新建应用`)**, enter an app ID (e.g. `com.dev.hello`), display name, category, and accent color. Edit `app_main.c` in **any editor** (VS Code, CLion, Notepad++)—just save the `.c` file (do not compile inside your external editor).
3. **Build, Audit & Pack (`.gla`)**: Click **Build · Check · Pack (`.gla`)** in Tab 1. G'lamor compiles all `.c` sources, runs the 17-symbol ABI preflight check, embeds a `40×40` Baseline JPEG icon, and outputs `<app_id>.gla`.
4. **Hot-Install to Device (Tab 2)**: Choose **Wi-Fi Push**, **USB Serial (`COMx`)**, or **TF Card Direct Write**. No Flash erase, no reboot—your app icon appears on the G'lam OS Bento home screen immediately.
5. **Manage & Mirror (Tab 3)**: Inspect live PSRAM/SRAM usage, remotely uninstall apps, or capture/stream 320×240 screenshots over Wi-Fi.

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

## 4. `manifest.json` & 3-Tier Background Lifecycle (`bg_policy`)

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
* **`partial_service`** (default for `media`/`service`): Releases UI widgets while keeping background audio or timer services alive.
* **`keep_all`** (default for `tool`): Keeps full PSRAM state intact and **freezes all app timers (0% background CPU)** for **0-second instant resume**.

---

## 5. `glam_os_api.h` (ABI v1) & 17-Symbol Kernel Whitelist

Apps receive `const glam_os_api_t *os` and a `320×216` `root` container (`GLAM_APP_W=320`, `GLAM_APP_H=216`, below the `24px` OS status bar) in `on_create()`, and must export `const glam_app_desc_t *glam_app_entry(void)`.

* **System & PSRAM**: `log_info`, `show_toast`, `request_exit`, `get_free_psram`, `get_free_sram`, `malloc_psram`, `free_psram`, `fmt_snprintf`
* **Safe UI Widgets**: `ui_clear_root`, `ui_create_panel`, `ui_create_label` (auto-selects 14px CJK font for Chinese), `ui_set_label_text`, `ui_set_label_color`, `ui_create_button`, `ui_create_bar`, `ui_set_bar_value`, `ui_create_list`, `ui_list_add_btn`, `ui_create_timer`, `ui_delete_timer`
* **Sandboxed Storage (`/sdcard/data/<app_id>/`)**: `storage_write_text`, `storage_read_text`
* **Audio & Hardware**: `audio_play_file`, `audio_pause`, `audio_resume`, `audio_stop`, `audio_is_playing`, `audio_set_volume`, `audio_scan_music`, `wifi_is_connected`, `wifi_get_ip`, `sd_is_mounted`

**17 Whitelisted Direct-Link Symbols**:
* **Memory/String (8)**: `memcpy`, `memset`, `memmove`, `memcmp`, `strlen`, `strcmp`, `strncmp`, `snprintf`
* **I2C Sensor Bus (5)**: `bsp_i2c_get_handle`, `i2c_master_bus_add_device`, `i2c_master_bus_rm_device`, `i2c_master_transmit`, `i2c_master_transmit_receive`
* **LVGL Fast Animation (4)**: `lv_obj_set_pos`, `lv_obj_set_style_bg_color`, `lv_obj_add_flag`, `lv_obj_clear_flag`

*(See `app_sdk_template/apps/com.glam.racer/app_main.c` for a full 6-axis QMI8658 IMU motion-controlled game example.)*

---

## 6. `.gla` Binary Format & `glamctl` CLI

A `.gla` package consists of a **160-byte header (`<4sHHII64s64s16s`, magic `"GLAM"`, version `1`, `header_len`, `elf_size`, IEEE 802.3 `crc32`, `app_id`, `app_name`, `app_version`)** + UTF-8 `manifest_bytes` + Xtensa ELF32 `elf_bytes`.

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
