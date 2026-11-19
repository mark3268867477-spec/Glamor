# G'lam OS 应用安装包 (.gla) 与开发打包规范 (v1.0)

> **适用范围**：所有运行在 G'lam OS（ESP32-S3-WROOM-1-N16R8）上的第三方与自研动态 `.elf` 应用。  
> **强制约束**：官方开发控制器 **G'lamor**（`release/Glamor_Portable/G'lamor.exe` / `glamctl.exe` / `启动_Glamor.bat`）会在 PC 端提前校验 ELF 重定位、内存布局与 ABI 白名单符号；G'lam OS 内核安装器 `os_spk_installer` 在装包阶段也会对 `.gla`（并兼容旧版 `.spk`）再次校验。

---

## 一、 开发者快速上手（G'lamor 零环境控制器）

第三方开发者无需安装 Python 或 ESP-IDF，解压 `release/Glamor_v1.0.0_Win64_Portable.zip` 即可使用，也可在仓库根目录双击 `启动_Glamor.bat` 完成 **新建 -> 编译 -> ABI 体检 -> 打包 `.gla` -> 无线/串口/TF卡安装**：

### 1. 图形界面（推荐）
双击 `G'lamor.exe`（或根目录 `启动_Glamor.bat`）打开 **G'lamor**：
* **新建应用**：自动生成标准 `manifest.json`、`app_main.c`（使用 `glam_os_api.h` 与 `glam_app_entry()`）与默认 `icon.png`。
* **构建 & 打包 (`.gla`)**：可视编辑应用信息、预览 40×40 桌面图标、自动多文件编译，并执行 **PC 端 ELF ABI 17 符号白名单预检**。
* **安装到设备**：支持 Wi-Fi 一键推送（并可打开网页安装器）、USB 串口热推包、TF 卡自动解包。
* **设备管理 & 实时投屏**：在线查看已装应用列表、远程卸载、抓取 320×240 设备实时屏幕截图。

### 2. 命令行 (`glamctl.bat` / `tools/glamctl.py`)
```cmd
:: 1. 创建新应用
glamctl.bat init my_apps\com.dev.demo --id com.dev.demo --name "示例应用" --category tool

:: 2. 编译并执行 ABI 预检
glamctl.bat build my_apps\com.dev.demo

:: 3. 打包为 .gla（也可加 --build 一步编译打包）
glamctl.bat pack my_apps\com.dev.demo --build --out dist\com.dev.demo.gla

:: 4. 校验安装包
glamctl.bat verify dist\com.dev.demo.gla

:: 5. 安装到板子（Wi-Fi / USB 串口 / TF 卡三选一，绝不刷写 Flash）
glamctl.bat install dist\com.dev.demo.gla --wifi 192.168.1.50
glamctl.bat install dist\com.dev.demo.gla --port COM7
glamctl.bat install dist\com.dev.demo.gla --sdcard E:\
```

---

## 二、 应用包目录结构

每个独立应用位于工程目录（官方示例位于 `app_sdk_template/apps/<app_id>/`），支持根目录及 `src/` 子目录下的多 `.c` 文件自动发现编译：

```text
<app_id>/
 ├── manifest.json      # 必填：应用元数据与后台策略声明
 ├── app_main.c         # 必填：应用源码（含 glam_app_entry 入口，也可拆分多个 .c/.h）
 └── icon.png           # 可选：应用图标（支持 PNG/JPG/BMP，打包时自动缩放为 40x40 Baseline JPEG）
```

编译打包后生成单一 `.gla` 安装包（`160B GLAM 二进制头 + manifest.json + Xtensa ELF32 + CRC32`；如需兼容早期旧版固件，可开启 `--compat-swpk` 生成 `SWPK` 包头）。

---

## 三、 `manifest.json` 标准字段规范

```json
{
  "id": "com.example.myapp",
  "name": "示例应用",
  "version": "1.0.0",
  "api_level": 1,
  "entry": "app.elf",
  "category": "tool",
  "bg_policy": "keep_all",
  "accent": "#0EA5E9",
  "author": "Developer",
  "description": "应用简述",
  "permissions": ["sandbox_data"]
}
```

### 字段说明与校验规则

| 字段名 | 类型 | 必填 | 约束说明 |
| :--- | :--- | :--- | :--- |
| `id` | String | 是 | 反向域名格式（仅允许 `a-zA-Z0-9._-`，不含 `..`，长度 `< 64` 字节），如 `com.glam.racer` |
| `name` | String | 是 | 桌面显示名称（UTF-8 长度 `< 64` 字节，建议使用通俗中文） |
| `version` | String | 是 | 语义化版本号（长度 `< 16` 字节），如 `"1.0.0"` |
| `api_level` | Number | 是 | 固定为 `1`（对应 `GLAM_OS_API_VERSION = 1`） |
| `entry` | String | 是 | 固定为 `"app.elf"` |
| `category` | String | 是 | 仅允许 `"game"` / `"media"` / `"service"` / `"tool"` / `"system"` |
| `bg_policy` | String | 推荐 | 仅允许 `"kill_all"` / `"partial_service"` / `"keep_all"`（缺省按 `category` 自动推导） |
| `accent` | String | 否 | 桌面图标主题色（`#RRGGBB`），默认 `#3B82F6` |
| `permissions`| Array | 否 | 可选 `"sandbox_data"`、`"audio"`、`"media_read"` |

---

## 四、 编译链接约束与 ABI 白名单（17 个导出符号）

动态 `.elf` 运行在 ESP32-S3 扩展内存（PSRAM）中，系统 API 通过 `glam_os_api_t *os` 传入 `on_create()`。

1. **必须使用的编译器与链接选项**（`G'lamor` 与 `glamctl` 已自动注入）：
   * 编译：`-mlongcalls -mtext-section-literals -fno-common -ffunction-sections -fdata-sections -O2`
   * 链接：`-nostdlib -Wl,-T,app_sdk_template/ld/glam_app.ld -Wl,-q -Wl,--gc-sections -Wl,--unresolved-symbols=ignore-all -lgcc`
   * 兼容旧代码：`swift_os_api.h` 与 `swift_app.ld`（`swift_app_entry`）继续保持二进制向后兼容。
2. **内核白名单外部符号（共 17 个，其余外部符号一律被拦截）**：
   * 标准内存/字符串：`memcpy`, `memset`, `memmove`, `memcmp`, `strlen`, `strcmp`, `strncmp`, `snprintf`
   * I2C 传感器总线：`bsp_i2c_get_handle`, `i2c_master_bus_add_device`, `i2c_master_bus_rm_device`, `i2c_master_transmit`, `i2c_master_transmit_receive`
   * LVGL 高频动画辅助：`lv_obj_set_pos`, `lv_obj_set_style_bg_color`, `lv_obj_add_flag`, `lv_obj_clear_flag`
   * *注意：禁止调用 `printf`、`malloc`、`free`、`fopen` 等未导出 libc 函数，请改用 `os->log_info`、`os->malloc_psram`、`os->free_psram`、`os->storage_write_text` 等 `glam_os_api_t` 接口。*

---

## 五、 后台生命周期策略 (`bg_policy`) 与系统红线

1. **`"kill_all"`**：退出即销毁（游戏/一次性工具），离开时立即调用 `on_destroy()` 并释放 PSRAM。
2. **`"partial_service"`**：仅保留后台音频或计时服务（媒体/计时类），释放前台 UI。
3. **`"keep_all"`**：整应用挂起在 PSRAM 中并自动冻结定时器（0% CPU），支持底部上滑“后台管理”秒切回。
4. **系统防卡顿红线**：最多保留 5 个后台槽位；低于安全内存水位时按 LRU 自动释放挂起应用；严禁直接擦写片内 Flash；UI 定时回调单次耗时 `< 10ms`。
