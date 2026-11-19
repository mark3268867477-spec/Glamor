# G'lamor — Zero-Environment PC Controller & App SDK for G'lam OS

<p align="center">
  <b>G'lam OS 官方零环境开发控制器 · C/ELF 动态应用 SDK · PC 端 ABI 安全体检 · <code>.gla</code> 打包与装机工作台</b><br>
  免装 Python · 免装 ESP-IDF · 一键把 <code>.c</code> 源码编译打包为 <code>.gla</code> 并推送至 ESP32-S3 设备
</p>

> 🔗 **配套操作系统固件仓库**：  
> 本项目是 **[G'lam OS (`mark3268867477-spec/Glam-OS`)](https://github.com/mark3268867477-spec/Glam-OS)** 的配套电脑端开发控制器与第三方应用 SDK。  
> 想要了解 ESP32-S3 系统内核、ELF 动态加载器实现或刷写底包固件，请访问：  
> 👉 **[G'lam OS 系统固件仓库 (`mark3268867477-spec/Glam-OS`)](https://github.com/mark3268867477-spec/Glam-OS)**

---

## 📖 目录 (Table of Contents)

1. [为什么需要 G'lamor？](#一-为什么需要-glamor)
2. [第三方开发者 3 分钟零环境上手](#二-第三方开发者-3-分钟零环境上手免-python--免-esp-idf)
3. [应用工程目录结构](#三-应用工程目录结构支持多文件编译)
4. [`manifest.json` 完整配置规范与后台策略](#四-manifestjson-完整配置规范与后台策略)
5. [`glam_os_api.h` (ABI v1) 完整 C 接口手册](#五-glam_os_apih-abi-v1-完整-c-接口手册)
6. [内核 17 项导出符号白名单与硬件传感器调用](#六-内核-17-项导出符号白名单与硬件传感器调用)
7. [`.gla` 二进制安装包格式规范](#七-gla-二进制安装包格式规范)
8. [`glamctl` 命令行参考与 Makefile / CI 集成](#八-glamctl-命令行参考与-makefile--ci-集成)
9. [常见报错排查与性能红线](#九-常见报错排查与性能红线)

---

## 一、 为什么需要 G'lamor？

在 **[G'lam OS](https://github.com/mark3268867477-spec/Glam-OS)** 上，所有第三方应用均以独立 **Xtensa ELF32 (`app.elf`)** 形式存放在 TF 卡中，并在点击图标时动态加载到 **8MB Octal PSRAM** 中运行。

如果第三方开发者用普通编译软件直接写 `.c` 文件，会遇到三个门槛：
1. **交叉编译工具链庞大**：完整版 ESP-IDF 动辄数 GB；
2. **编译与链接参数苛刻**：必须使用 `-mlongcalls`、`-mtext-section-literals`、专属链接脚本 `glam_app.ld`（基址 `0x0`）以及 `-Wl,-q` 保留重定位表；漏掉任何一个参数，编译不会报错，但上机无法启动；
3. **未导出符号隐患**：链接时开启了 `--unresolved-symbols=ignore-all`，如果开发者顺手调用了 `printf`、`malloc`、`fopen` 等未导出的标准库函数，传统打包脚本会静默放行，直到推上板子才报错拦截。

**G'lamor** 把以上所有复杂性封装成了一个 **38 MB 的零环境 Windows 绿色包**：
* **内置精简版 `xtensa-esp32s3-elf-gcc` 交叉编译器（55 MB）+ Python 3.13 + Tk GUI 运行时（44 MB）**，电脑上什么都没装也能开箱即用；
* **PC 端 ELF ABI 安全预检 (`elf_check.py`)**：在电脑上直接解析 ELF 重定位节与符号表，对照内核 17 项白名单提前拦截非法调用；
* **可视化 `.gla` 打包 + 三通道安全装机 + 320×240 真机实时投屏**。

---

## 二、 第三方开发者 3 分钟零环境上手（免 Python / 免 ESP-IDF）

### 第 1 步：下载并打开 G'lamor
* 前往 **[GitHub Releases](https://github.com/mark3268867477-spec/Glamor/releases/latest)** 下载 `Glamor_v1.0.0_Win64_Portable.zip`，解压到任意目录；
* 双击运行 **`G'lamor.exe`**（若已克隆本仓库，也可双击根目录 `启动_Glamor.bat`）。
* 顶部状态栏会显示绿色 **`GCC: 就绪`** 徽章（已自动挂载内置的 `toolchain/bin/xtensa-esp32s3-elf-gcc.exe`）。

### 第 2 步：新建应用并用任意编辑器写 `.c` 代码
1. 点击右上角 **「新建应用」**，填写：
   * **应用 ID**：反向域名格式，如 `com.dev.hello`
   * **显示名称**：桌面磁贴显示的中文名，如 `我的应用`
   * **应用分类**：`tool` / `game` / `media` / `service` / `system`
   * **主题颜色**：如 `#0EA5E9`
2. 点击 **「创建工程」** 后，G'lamor 会自动生成标准目录：
   * `manifest.json`（应用清单）
   * `app_main.c`（带点击计数、沙盒存档读写、PSRAM 状态显示的完整可运行模板）
   * `icon.png`（自动生成的 64×64 默认图标）
3. 用你熟悉的任何代码编辑器（**VS Code、CLion、Dev-C++、Sublime、Notepad++** 等）打开该目录下的 `.c` 文件编写逻辑。**切记：不要在外部编辑器里点编译，保存 `.c` 文件即可！**

### 第 3 步：一键把 `.c` 转换成 `.gla` 安装包
回到 **G'lamor** 的 **「1. 构建 & 打包 (.gla)」** 页：
1. 可在左侧表单直接修改名称、版本号、后台策略，或点击 **「选择图标 (PNG/JPG)」** 更换自定义图标（打包时自动居中裁剪为 `40×40` Baseline JPEG 内嵌进包内）；
2. 点击蓝色主按钮 **「一键编译 · 体检 · 打包 (.gla)」**：
   * 自动编译工程根目录与 `src/` 下所有 `.c` 文件生成 `app.elf`；
   * 右侧 **ELF ABI 安全体检面板** 实时展示：`体检通过` 徽章、ELF 大小、预计 PSRAM 占用、入口符号 `glam_app_entry`、重定位节数以及所调用的内核白名单符号；
   * 若手滑调用了 `printf` / `malloc` 等禁止符号，体检面板会直接红字点名报错并阻止生成损坏的安装包；
   * 体检通过后输出单一的 **`<app_id>.gla`** 安装包，并自动填入「2. 安装到设备」页。

### 第 4 步：安装到 G'lam OS 设备（3 种通道任选，绝不刷写 Flash）
切换到 **「2. 安装到设备」** 页，任选一种方式即可将 `.gla` 装入设备 TF 卡 `/sdcard/apps/<app_id>/`，**无需重启设备，桌面立即刷新出新图标**：
1. **渠道一：Wi-Fi 无线推送（推荐）**
   * 在板端「设置」或「应用中心」查看局域网 IP（如 `192.168.1.50`），填入 G'lamor 点击 **「通过 Wi-Fi 安装到设备」**；
   * 或点击 **「打开网页端」**，直接用浏览器上传 `.gla` 文件。
2. **渠道二：USB 数据线串口直连**
   * 用 USB 线连接板子（保持正常开机，不要进下载模式），选择串口（如 `COM7`），点击 **「USB 串口推送安装」**。
3. **渠道三：TF 卡离线导入**
   * 插上读卡器，选择 TF 卡盘符点击 **「写入 TF 卡 (自动解包)」**；
   * 或直接把 `.gla` 拷入 TF 卡 `/install/` 目录，插回板子开机或在「应用中心」点“扫描安装包” / 在「文件管理」直接点击 `.gla` 文件安装。

### 第 5 步：设备管理与实时投屏验证
切换到 **「3. 设备管理 & 实时投屏」** 页，输入板子 Wi-Fi IP：
* 查看设备实时可用 PSRAM / SRAM、TF 卡状态与已安装应用列表，支持一键 **远程卸载**；
* 点击 **「抓取屏幕」** 或勾选 **「自动刷新 (2秒)」**，即可在电脑上实时预览 320×240 真机画面并导出 PNG/BMP 截图！

---

## 三、 应用工程目录结构（支持多文件编译）

G'lamor 会自动扫描工程根目录与 `src/` 子目录下的所有 `.c` 源文件，并自动把工程根目录、`include/`、`src/` 及 SDK `include/` 加入头文件搜索路径：

```text
com.example.myapp/
 ├── manifest.json        # [必填] 应用元数据、分类与后台生命周期声明
 ├── icon.png             # [可选] 自定义桌面图标 (支持 PNG/JPG/BMP，自动转 40x40 Baseline JPEG)
 ├── app_main.c           # [必填] 应用主源码（定义 glam_app_entry 入口）
 ├── include/             # [可选] 工程私有头文件 (.h)
 │    └── game_logic.h
 └── src/                 # [可选] 多模块拆分源码 (.c)，编译时自动合并链接
      └── game_logic.c
```

---

## 四、 `manifest.json` 完整配置规范与后台策略

### 标准示例
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

### 字段校验规则表

| 字段名 | 类型 | 必填 | 约束说明 |
| :--- | :--- | :---: | :--- |
| `id` | String | 是 | 唯一反向域名标识，仅允许 `a-zA-Z0-9._-`，禁止包含 `..`，UTF-8 长度 `< 64` 字节 |
| `name` | String | 是 | 桌面磁贴与后台列表显示名称，UTF-8 长度 `< 64` 字节 |
| `version` | String | 是 | 语义化版本号，如 `"1.0.0"`，长度 `< 16` 字节 |
| `api_level` | Number | 是 | 固定为 `1`（对应 `GLAM_OS_API_VERSION = 1`） |
| `entry` | String | 是 | 固定为 `"app.elf"` |
| `category` | String | 是 | 枚举值：`"game"` \| `"media"` \| `"service"` \| `"tool"` \| `"system"` |
| `bg_policy` | String | 推荐 | 枚举值：`"kill_all"` \| `"partial_service"` \| `"keep_all"`（未填时按 `category` 自动推导） |
| `accent` | String | 否 | 桌面磁贴主题色，格式 `"#RRGGBB"`（默认 `"#3B82F6"`） |
| `author` | String | 否 | 开发者或团队名称 |
| `description` | String | 否 | 应用简介 |
| `permissions` | Array | 否 | 权限声明数组，可选 `"sandbox_data"`、`"audio"`、`"media_read"` |

### 三种后台生命周期策略 (`bg_policy`) 详解

| 策略值 | 默认适用分类 | 用户点击右上角「桌面」或按下 Home 键时的系统行为 | 开发者注意事项 |
| :--- | :--- | :--- | :--- |
| **`"kill_all"`** | `"game"`, `"system"` | **立即销毁并卸载**：调用 `on_destroy()`，清理所有定时器和 UI 控件，**直接释放占用的全部 PSRAM**，不留在后台列表中。 | 必须在得分变化或 `on_destroy()` 中通过 `os->storage_write_text()` 保存数据，并释放申请的外设/内存句柄。 |
| **`"partial_service"`** | `"media"`, `"service"` | **释放 UI，保留核心服务**：隐藏/释放前台图形界面，仅当音频正在播放或计时器正在运行时保留后台条目；空闲时自动移除。 | 适合调用系统后台音频服务 (`os->audio_*`) 的应用。 |
| **`"keep_all"`** | `"tool"` | **整应用挂起保留**：代码段、全局变量与 UI 树完整保留在 PSRAM 中；内核自动**冻结该应用的所有定时器（后台 0% CPU 占用）**。用户从桌面或底部上滑“后台管理”点击切回时 **0 秒瞬时恢复现场**。 | 若用户在应用内主动点击退出按钮（调用 `os->request_exit()`）或在后台管理器点击「结束」，则会执行 `on_destroy()` 并彻底释放 PSRAM。 |

---

## 五、 `glam_os_api.h` (ABI v1) 完整 C 接口手册

所有动态应用只需包含 `#include "glam_os_api.h"`（位于 `app_sdk_template/include/glam_os_api.h`）。

### 1. 屏幕尺寸常量与生命周期入口

* **屏幕与视口尺寸**：
  * `GLAM_SCREEN_W` = `320`，`GLAM_SCREEN_H` = `240`
  * `GLAM_STATUSBAR_H` = `24`（顶部系统状态栏由 OS 托管）
  * **`GLAM_APP_W` = `320`，`GLAM_APP_H` = `216`**（传给应用 `on_create` 的 `root` 容器尺寸为 `320×216`，所有坐标 `(x, y)` 均相对于该 `320×216` 视口左上角 `(0, 0)`）
* **最小完整 C 代码模板**：

```c
#include "glam_os_api.h"

static const glam_os_api_t *s_os = NULL;
static glam_obj_t s_lbl = NULL;
static glam_timer_t s_timer = NULL;
static uint32_t s_ticks = 0;

static void on_btn_click(void *user_data)
{
    (void)user_data;
    s_ticks++;
    char buf[64];
    s_os->fmt_snprintf(buf, sizeof(buf), "点击次数: %u", (unsigned)s_ticks);
    s_os->ui_set_label_text(s_lbl, buf);
    s_os->show_toast("已触发按钮点击!");
}

static void on_exit_click(void *user_data)
{
    (void)user_data;
    s_os->request_exit(); /* 主动请求退出并销毁应用 */
}

static void on_timer_tick(void *user_data)
{
    (void)user_data;
    /* 每 1000ms 触发一次（切后台 keep_all 时由内核自动暂停） */
}

static int app_on_create(const glam_os_api_t *os, glam_obj_t root, const char *app_id, const char *data_dir)
{
    (void)app_id;
    (void)data_dir;
    s_os = os;
    s_ticks = 0;

    /* 1. 设置 320x216 根容器背景色 */
    os->ui_clear_root(root, 0x0B1120U);

    /* 2. 创建圆角卡片面板 (x=8, y=8, w=304, h=200, bg=0x131C31, radius=12, border=0x0EA5E9) */
    glam_obj_t card = os->ui_create_panel(root, 8, 8, 304, 200, 0x131C31U, 12, 0x0EA5E9U);

    /* 3. 创建中英文文本标签 (支持 12/14/16/20/24/32 字号，含中文自动启用 14px CJK 字库) */
    os->ui_create_label(card, "Hello G'lam OS!", 14, 12, 0xF8FAFCU, 16);
    s_lbl = os->ui_create_label(card, "点击次数: 0", 14, 48, 0x38BDF8U, 14);

    /* 4. 创建按钮 */
    os->ui_create_button(card, "点我 +1", 14, 146, 132, 38, 0x0284C7U, on_btn_click, NULL);
    os->ui_create_button(card, "退出应用", 158, 146, 132, 38, 0x334155U, on_exit_click, NULL);

    /* 5. 创建周期定时器 (1000ms) */
    s_timer = os->ui_create_timer(on_timer_tick, 1000, NULL);
    return 0; /* 返回 0 表示启动成功；返回非 0 将中止启动并回退桌面 */
}

static void app_on_destroy(void)
{
    if (s_timer && s_os) {
        s_os->ui_delete_timer(s_timer);
        s_timer = NULL;
    }
}

static const glam_app_desc_t s_desc = {
    .on_create  = app_on_create,
    .on_destroy = app_on_destroy,
};

/* 必须导出的唯一入口符号 (与 glam_app.ld 中的 ENTRY(glam_app_entry) 对应) */
const glam_app_desc_t *glam_app_entry(void)
{
    return &s_desc;
}
```

### 2. `glam_os_api_t` 全部接口分类速查表

#### (1) 系统、日志与 PSRAM 内存接口
| 函数指针签名 | 功能说明 |
| :--- | :--- |
| `uint32_t api_version` | 当前内核 ABI 版本号（恒为 `1`） |
| `void (*log_info)(const char *tag, const char *fmt, ...)` | 向串口输出格式化日志（替代被禁止的 `printf`） |
| `void (*show_toast)(const char *msg)` | 在屏幕底部弹出全局悬浮提示框（2.4 秒自动渐隐） |
| `void (*request_exit)(void)` | 应用主动请求退出并返回主桌面（即使是 `keep_all` 也会彻底卸载） |
| `uint32_t (*get_free_psram)(void)` | 获取当前剩余可用扩展内存（PSRAM）字节数 |
| `uint32_t (*get_free_sram)(void)` | 获取当前剩余可用片内高速内存（Internal SRAM）字节数 |
| `void *(*malloc_psram)(size_t size)` | 从 8MB PSRAM 中动态分配内存（替代 `malloc`） |
| `void (*free_psram)(void *ptr)` | 释放 `malloc_psram` 分配的内存（替代 `free`） |
| `int (*fmt_snprintf)(char *buf, size_t size, const char *fmt, ...)` | 安全格式化字符串到缓冲区 |

#### (2) 安全 UI 图形控件接口（最高支持 64 个点击槽位 + 16 个定时器槽位）
| 函数指针签名 | 功能说明 |
| :--- | :--- |
| `void (*ui_clear_root)(glam_obj_t root, uint32_t bg_hex)` | 清空 `root` 下所有子控件并设置背景色（如 `0x0B1120U`） |
| `glam_obj_t (*ui_create_panel)(glam_obj_t parent, int x, int y, int w, int h, uint32_t bg_hex, int radius, uint32_t border_hex)` | 创建矩形/圆角卡片容器（`border_hex=0` 时无边框） |
| `glam_obj_t (*ui_create_label)(glam_obj_t parent, const char *text, int x, int y, uint32_t color_hex, int font_size)` | 创建文本标签（含中文字符时自动切换 `ui_font_cjk_14`） |
| `void (*ui_set_label_text)(glam_obj_t label, const char *text)` | 动态更新标签文本 |
| `void (*ui_set_label_color)(glam_obj_t label, uint32_t color_hex)` | 动态更新标签文字颜色 |
| `glam_obj_t (*ui_create_button)(glam_obj_t parent, const char *text, int x, int y, int w, int h, uint32_t bg_hex, glam_click_cb_t on_click, void *user_data)` | 创建圆角按钮并绑定点击回调 `void cb(void *user_data)` |
| `glam_obj_t (*ui_create_bar)(glam_obj_t parent, int x, int y, int w, int h, int32_t min_v, int32_t max_v, uint32_t bg_hex, uint32_t ind_hex)` | 创建进度条/指示条控件 |
| `void (*ui_set_bar_value)(glam_obj_t bar, int32_t val)` | 更新进度条当前数值 |
| `glam_obj_t (*ui_create_list)(glam_obj_t parent, int x, int y, int w, int h, uint32_t bg_hex)` | 创建可纵向滚动的列表容器 |
| `glam_obj_t (*ui_list_add_btn)(glam_obj_t list, const char *text, glam_click_cb_t on_click, void *user_data)` | 向列表容器中添加一行可点击条目 |
| `glam_timer_t (*ui_create_timer)(glam_timer_cb_t cb, uint32_t period_ms, void *user_data)` | 创建 LVGL 主线程周期定时器（退出应用时内核亦会自动兜底清理） |
| `void (*ui_delete_timer)(glam_timer_t timer)` | 手动销毁指定定时器 |

#### (3) 沙盒持久化存储接口（自动隔离在 `/sdcard/data/<app_id>/`）
| 函数指针签名 | 功能说明 |
| :--- | :--- |
| `int (*storage_write_text)(const char *app_id, const char *rel_name, const char *content)` | 将字符串写入沙盒文件 `/sdcard/data/<app_id>/<rel_name>`（成功返回 `0`） |
| `int (*storage_read_text)(const char *app_id, const char *rel_name, char *out_buf, size_t max_len)` | 读取沙盒文件到 `out_buf`（成功返回 `0`，文件不存在返回 `-1`） |

#### (4) 系统后台音频与硬件状态接口
| 函数指针签名 | 功能说明 |
| :--- | :--- |
| `int (*audio_play_file)(const char *path)` | 播放 TF 卡上的 `.mp3` / `.wav` 文件（如 `"/sdcard/music/song.mp3"`） |
| `int (*audio_pause)(void)` / `int (*audio_resume)(void)` / `int (*audio_stop)(void)` | 暂停 / 恢复 / 停止音频播放 |
| `bool (*audio_is_playing)(void)` / `bool (*audio_is_paused)(void)` | 查询当前播放状态 |
| `int (*audio_get_progress)(uint32_t *cur_ms, uint32_t *total_ms)` | 获取当前播放进度毫秒数与总时长 |
| `int (*audio_set_volume)(uint8_t vol)` / `uint8_t (*audio_get_volume)(void)` | 设置或获取系统音量（`0` ~ `100`） |
| `const char *(*audio_get_current_file)(void)` | 获取当前正在播放的文件路径 |
| `int (*audio_scan_music)(char out_paths[][256], char out_titles[][64], int max_items)` | 扫描 `/sdcard/music/` 下的音频文件列表 |
| `bool (*wifi_is_connected)(void)` / `void (*wifi_get_ip)(char *out_ip, size_t max_len)` | 查询 Wi-Fi 连接状态与本机 IP 字符串 |
| `bool (*sd_is_mounted)(void)` | 查询外部 TF 卡是否已挂载 |

---

## 六、 内核 17 项导出符号白名单与硬件传感器调用

除了通过 `os->xxx(...)` 函数表调用外，G'lam OS 内核在动态链接阶段还允许 `.elf` 直接重定位以下 **17 个白名单外部符号**（G'lamor 的 `elf_check.py` 会严格按此名单预检）：

| 类别 | 允许直接调用的外部符号（共 17 个） |
| :--- | :--- |
| **基础内存与字符串 (8)** | `memcpy`, `memset`, `memmove`, `memcmp`, `strlen`, `strcmp`, `strncmp`, `snprintf` |
| **I2C 传感器总线 (5)** | `bsp_i2c_get_handle`, `i2c_master_bus_add_device`, `i2c_master_bus_rm_device`, `i2c_master_transmit`, `i2c_master_transmit_receive` |
| **LVGL 高频动画辅助 (4)** | `lv_obj_set_pos`, `lv_obj_set_style_bg_color`, `lv_obj_add_flag`, `lv_obj_clear_flag` |

> 💡 **进阶实战示例**：想要直接读取板载 **QMI8658 六轴陀螺仪** 或以 30 FPS 高频移动赛车精灵？请直接参考本仓库 `app_sdk_template/apps/com.glam.racer/app_main.c`（《极速赛车》完整源码），展示了如何通过上述 5 个 I2C 符号与 4 个 LVGL 符号实现零卡顿体感游戏！

### 常见违规符号替代对照表
| ❌ 禁止直接调用的 libc 函数 | ✅ G'lam OS 正确替代方案 |
| :--- | :--- |
| `printf(...)` / `puts(...)` | `os->log_info("my_app", "val=%d", v)` |
| `malloc(sz)` / `calloc(n, sz)` | `os->malloc_psram(sz)` |
| `free(ptr)` | `os->free_psram(ptr)` |
| `fopen(...)` / `fread(...)` / `fwrite(...)` | `os->storage_read_text(...)` / `os->storage_write_text(...)` |

---

## 七、 `.gla` 二进制安装包格式规范

每个 `.gla` 文件由 **160 字节定长二进制头 (`<4sHHII64s64s16s`) + 紧凑 `manifest.json` 字节流 + Xtensa ELF32 二进制流** 组成：

```text
Offset  Size   Type       Field           Description
------  -----  ---------  --------------  --------------------------------------------------------
0x00    4B     char[4]    magic           固定魔数 "GLAM" (兼容模式下为 "SWPK")
0x04    2B     uint16_le  version         包格式版本，当前固定为 1
0x06    2B     uint16_le  header_len      紧随其后的 manifest JSON 字节长度
0x08    4B     uint32_le  elf_size        app.elf 二进制字节长度
0x0C    4B     uint32_le  crc32           对 (manifest_bytes + elf_bytes) 计算的 IEEE 802.3 CRC32
0x10    64B    char[64]   app_id          UTF-8 应用 ID (不足补 \0)
0x50    64B    char[64]   app_name        UTF-8 应用名称 (不足补 \0)
0x90    16B    char[16]   app_version     UTF-8 版本号 (不足补 \0)
0xA0    N      uint8[]    manifest_bytes  UTF-8 编码的 manifest.json（若含自定义图标则内嵌 icon_jpg_b64）
0xA0+N  M      uint8[]    elf_bytes       32-bit LSB Xtensa ELF (EM_XTENSA=94, ET_EXEC/ET_DYN)
```

---

## 八、 `glamctl` 命令行参考与 Makefile / CI 集成

除了图形界面 `G'lamor.exe` 外，便携包还提供命令行工具 **`glamctl.exe`**（源码版可直接运行 `glamctl.bat` 或 `python tools/glamctl.py`）：

```cmd
:: 1. 查看本机编译器、串口与 TF 卡盘符
glamctl.exe devices

:: 2. 初始化新应用工程模板
glamctl.exe init my_apps\com.dev.demo --id com.dev.demo --name "示例工具" --category tool --accent #0EA5E9

:: 3. 编译工程并执行 PC 端 ELF ABI 17 符号白名单体检
glamctl.exe build my_apps\com.dev.demo

:: 4. 单独对某个 app.elf 执行 ABI 体检
glamctl.exe check my_apps\com.dev.demo\app.elf

:: 5. 编译并打包为 .gla（带 --build 会先自动编译）
glamctl.exe pack my_apps\com.dev.demo --build --out dist\com.dev.demo.gla

:: 6. 校验现有 .gla 安装包完整性与内部 ELF
glamctl.exe verify dist\com.dev.demo.gla

:: 7. 批量编译打包目录下所有应用
glamctl.exe build-all app_sdk_template\apps --dist app_sdk_template\dist

:: 8. 三通道安全安装至设备 TF 卡（三选一）
glamctl.exe install dist\com.dev.demo.gla --wifi 192.168.1.50
glamctl.exe install dist\com.dev.demo.gla --port COM7
glamctl.exe install dist\com.dev.demo.gla --sdcard E:\

:: 9. 远程设备管理与实时抓屏 (Wi-Fi)
glamctl.exe info --wifi 192.168.1.50
glamctl.exe apps --wifi 192.168.1.50
glamctl.exe uninstall --wifi 192.168.1.50 com.dev.demo
glamctl.exe screenshot --wifi 192.168.1.50 --out screen.bmp
```

### 自定义 Makefile 手动调用 GCC 参数参考
如果你希望在自己的构建系统中手动调用 `xtensa-esp32s3-elf-gcc` 编译 `app.elf`，必须使用以下参数：
```makefile
CFLAGS  = -mlongcalls -mtext-section-literals -fno-common -ffunction-sections -fdata-sections -O2 -Wall -Wextra -I<path_to_sdk>/include
LDFLAGS = -nostdlib -Wl,-T,<path_to_sdk>/ld/glam_app.ld -Wl,-q -Wl,--gc-sections -Wl,--unresolved-symbols=ignore-all -lgcc
```

---

## 九、 常见报错排查与性能红线

1. **`禁止或未导出的外部符号 'xxx'`**：
   * 说明代码中调用了不在 17 项白名单内的外部函数（如 `printf`、`malloc`、`sinf`、`rand`）。请改用 `os->log_info`、`os->malloc_psram`，或自行在 `.c` 文件内实现轻量数学/随机数辅助函数（可参考 `com.glam.racer` 中的 LCG 随机数实现）。
2. **`外部符号使用了短调用 R_XTENSA_SLOT0_OP，请务必使用 -mlongcalls 编译`**：
   * 第三方自建 Makefile 漏加了 `-mlongcalls`。因应用运行在 PSRAM (`0x42xxxxxx`)，内核运行在 Flash/IRAM (`0x403xxxxx`)，跨区调用距离超过 512KB，必须启用 `-mlongcalls`。
3. **`缺少 SHF_ALLOC 重定位表 (SHT_RELA)`**：
   * 链接时漏加了 `-Wl,-q`，导致生成的 ELF 不含动态重定位信息。
4. **UI 线程不卡顿红线**：
   * `os->ui_create_timer()` 回调运行在 LVGL 主线程中，**单次回调执行耗时不得超过 `10 ms`**，严禁在回调中编写死循环、`vTaskDelay` 或阻塞式网络请求。

---

## 十、 仓库目录结构

```text
Glamor/
├── app_sdk_template/             # G'lam OS 官方 C/ELF 应用 SDK 与示例工程
│   ├── include/
│   │   ├── glam_os_api.h         # G'lam OS ABI v1 核心头文件
│   │   └── swift_os_api.h        # 向下兼容别名头文件
│   ├── ld/
│   │   ├── glam_app.ld           # 动态 PSRAM ELF 链接脚本 (ENTRY=glam_app_entry, base=0x0)
│   │   └── swift_app.ld          # 向下兼容链接脚本
│   ├── apps/                     # 官方示例应用源码
│   │   ├── com.glam.music/       # G'lam 音乐启动桥接器
│   │   ├── com.glam.racer/       # 极速赛车 (QMI8658 六轴陀螺仪体感游戏，760+ 行完整示例)
│   │   ├── com.glam.sysmon/      # 内存检测 (PSRAM 读写校验与实时监控)
│   │   └── com.dev.hello/        # 最小入门计数器示例
│   ├── dist/                     # 编译产出的 .gla 安装包
│   ├── build_apps.bat            # 一键批量编译打包脚本
│   └── install.bat               # 一键批量安装脚本
├── tools/                        # G'lamor 控制器核心源码
│   ├── glam_sdk/                 # 核心 Python SDK 模块 (elf_check / pkg / toolchain / transport / serial_port)
│   ├── glam_studio.py            # G'lamor 桌面可视化控制器 GUI
│   ├── glamctl.py                # glamctl 命令行工具
│   ├── build_glamor_release.py   # 零环境 Win64 便携包 (G'lamor.exe + 精简 GCC/Python) 自动构建脚本
│   └── glamor.ico                # G'lamor 应用图标
├── docs/                         # 详细开发规范与刷写操作规范
├── glamctl.bat                   # Windows CLI 快捷入口
└── 启动_Glamor.bat                # 双击启动 G'lamor 图形界面
```
