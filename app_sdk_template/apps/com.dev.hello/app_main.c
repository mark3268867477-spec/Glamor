/**
 * @file app_main.c
 * @brief 我的应用 (com.dev.hello) - G'lam OS Dynamic PSRAM App
 */

#include "glam_os_api.h"

typedef struct {
    const glam_os_api_t *os;
    char app_id[64];
    glam_obj_t lbl_count;
    glam_obj_t lbl_mem;
    glam_timer_t timer;
    uint32_t clicks;
} app_state_t;

static app_state_t s_app;

static void update_labels(void)
{
    const glam_os_api_t *os = s_app.os;
    if (!os) return;

    char buf[96];
    os->fmt_snprintf(buf, sizeof(buf), "已点击计数: %u", (unsigned)s_app.clicks);
    os->ui_set_label_text(s_app.lbl_count, buf);

    os->fmt_snprintf(
        buf,
        sizeof(buf),
        "PSRAM 可用: %u KB  |  SRAM: %u KB",
        (unsigned)(os->get_free_psram() / 1024U),
        (unsigned)(os->get_free_sram() / 1024U)
    );
    os->ui_set_label_text(s_app.lbl_mem, buf);
}

static void on_add_click(void *user_data)
{
    (void)user_data;
    s_app.clicks++;
    update_labels();

    if (s_app.os && s_app.os->storage_write_text) {
        char val[24];
        s_app.os->fmt_snprintf(val, sizeof(val), "%u", (unsigned)s_app.clicks);
        s_app.os->storage_write_text(s_app.app_id, "clicks.txt", val);
    }
}

static void on_exit_click(void *user_data)
{
    (void)user_data;
    if (s_app.os && s_app.os->request_exit) {
        s_app.os->request_exit();
    }
}

static void on_tick(void *user_data)
{
    (void)user_data;
    update_labels();
}

static uint32_t parse_uint(const char *s)
{
    uint32_t v = 0;
    if (!s) return 0;
    while (*s >= '0' && *s <= '9') {
        v = v * 10U + (uint32_t)(*s - '0');
        s++;
    }
    return v;
}

static int app_on_create(const glam_os_api_t *os, glam_obj_t root, const char *app_id, const char *data_dir)
{
    (void)data_dir;
    uint8_t *raw = (uint8_t *)&s_app;
    for (size_t i = 0; i < sizeof(s_app); i++) {
        raw[i] = 0;
    }
    s_app.os = os;
    os->fmt_snprintf(s_app.app_id, sizeof(s_app.app_id), "%s", app_id ? app_id : "com.dev.hello");

    char saved[24] = {0};
    if (os->storage_read_text(s_app.app_id, "clicks.txt", saved, sizeof(saved)) == 0) {
        s_app.clicks = parse_uint(saved);
    }

    os->ui_clear_root(root, 0x0B1120U);
    glam_obj_t card = os->ui_create_panel(root, 8, 8, 304, 200, 0x131C31U, 12, 0x0EA5E9U);

    os->ui_create_label(card, "我的应用", 14, 12, 0xF8FAFCU, 16);
    os->ui_create_label(card, "运行于 G'lam OS 扩展内存 (.gla 动态应用)", 14, 38, 0x94A3B8U, 12);

    s_app.lbl_count = os->ui_create_label(card, "已点击计数: 0", 14, 72, 0x38BDF8U, 14);
    s_app.lbl_mem = os->ui_create_label(card, "...", 14, 102, 0xA7F3D0U, 12);

    os->ui_create_button(card, "点我 +1", 14, 146, 132, 38, 0x0EA5E9U, on_add_click, NULL);
    os->ui_create_button(card, "退出应用", 158, 146, 132, 38, 0x334155U, on_exit_click, NULL);

    s_app.timer = os->ui_create_timer(on_tick, 1000, NULL);
    update_labels();
    return 0;
}

static void app_on_destroy(void)
{
    if (s_app.timer && s_app.os) {
        s_app.os->ui_delete_timer(s_app.timer);
        s_app.timer = NULL;
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
