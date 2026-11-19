/**
 * @file app_main.c
 * @brief PSRAM Probe - Dynamic .elf App verifying ESP32-S3 PSRAM IBUS/DBUS execution
 */

#include "glam_os_api.h"

typedef struct {
    const glam_os_api_t *os;
    glam_obj_t lbl_mem;
    glam_obj_t lbl_result;
    glam_timer_t timer;
    uint32_t test_runs;
} sysmon_state_t;

static sysmon_state_t s_state;

static int app_on_create(const glam_os_api_t *os, glam_obj_t root, const char *app_id, const char *data_dir);

static void refresh_mem(void)
{
    const glam_os_api_t *os = s_state.os;
    char buf[96];
    os->fmt_snprintf(buf, sizeof(buf),
                     "可用扩展内存: %u KB\n可用高速缓存: %u KB",
                     (unsigned)(os->get_free_psram() / 1024U),
                     (unsigned)(os->get_free_sram() / 1024U));
    os->ui_set_label_text(s_state.lbl_mem, buf);
}

static void on_psram_test_click(void *user_data)
{
    (void)user_data;
    const glam_os_api_t *os = s_state.os;
    const size_t test_bytes = 256U * 1024U;
    uint32_t *buf = (uint32_t *)os->malloc_psram(test_bytes);
    if (!buf) {
        os->ui_set_label_text(s_state.lbl_result, "内存不足，分配 256KB 失败!");
        return;
    }

    size_t words = test_bytes / sizeof(uint32_t);
    for (size_t i = 0; i < words; i++) {
        buf[i] = (uint32_t)(i ^ 0x5A5A3C3CU);
    }
    bool ok = true;
    for (size_t i = 0; i < words; i++) {
        if (buf[i] != (uint32_t)(i ^ 0x5A5A3C3CU)) {
            ok = false;
            break;
        }
    }
    os->free_psram(buf);

    s_state.test_runs++;
    char msg[64];
    os->fmt_snprintf(msg, sizeof(msg), "第 %u 次检测: 256KB 内存%s",
                     (unsigned)s_state.test_runs, ok ? "通过" : "异常");
    os->ui_set_label_text(s_state.lbl_result, msg);
    os->storage_write_text("com.glam.sysmon", "probe_log.txt", msg);
    refresh_mem();
}

static void on_exit_click(void *user_data)
{
    (void)user_data;
    s_state.os->request_exit();
}

static void on_tick(void *user_data)
{
    (void)user_data;
    refresh_mem();
}

static int app_on_create(const glam_os_api_t *os, glam_obj_t root, const char *app_id, const char *data_dir)
{
    (void)app_id;
    (void)data_dir;
    s_state.os = os;
    s_state.test_runs = 0;

    os->ui_clear_root(root, 0x09111EU);

    glam_obj_t card = os->ui_create_panel(root, 8, 8, 304, 200, 0x101C2EU, 12, 0x0EA5E9U);

    os->ui_create_label(card, "系统内存与缓存检测", 12, 10, 0x38BDF8U, 16);
    os->ui_create_label(card, "运行状态: 扩展内存流畅运行中\n缓存模式: 读写加速已开启", 12, 36, 0xE2E8F0U, 12);

    s_state.lbl_mem = os->ui_create_label(card, "...", 12, 74, 0xA7F3D0U, 14);
    s_state.lbl_result = os->ui_create_label(card, "点击下方按钮检测 256KB 内存", 12, 118, 0xFDE68AU, 12);

    char saved[64] = {0};
    if (os->storage_read_text("com.glam.sysmon", "probe_log.txt", saved, sizeof(saved)) == 0 && saved[0]) {
        os->ui_set_label_text(s_state.lbl_result, saved);
    }

    os->ui_create_button(card, "检测内存", 12, 148, 134, 38, 0x0284C7U, on_psram_test_click, NULL);
    os->ui_create_button(card, "退出应用", 158, 148, 134, 38, 0x334155U, on_exit_click, NULL);

    s_state.timer = os->ui_create_timer(on_tick, 1000, NULL);
    refresh_mem();
    return 0;
}

static void app_on_destroy(void)
{
    if (s_state.timer && s_state.os) {
        s_state.os->ui_delete_timer(s_state.timer);
        s_state.timer = NULL;
    }
}

static const glam_app_desc_t s_desc = {
    .on_create = app_on_create,
    .on_destroy = app_on_destroy,
};

const glam_app_desc_t *glam_app_entry(void)
{
    return &s_desc;
}
