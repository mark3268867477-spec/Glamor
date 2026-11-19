/**
 * @file app_main.c
 * @brief G'lam 音乐 - Dynamic .elf Launcher Bridge for 1:1 Music Hub UI
 */

#include "glam_os_api.h"

static const glam_os_api_t *s_os = NULL;

static int app_on_create(const glam_os_api_t *os, glam_obj_t root, const char *app_id, const char *data_dir)
{
    (void)root;
    (void)app_id;
    (void)data_dir;
    s_os = os;
    if (s_os && s_os->open_music_hub) {
        s_os->log_info("music_elf", "Opening G'lam Music Hub UI from PSRAM ELF");
        s_os->open_music_hub();
        return 0;
    }
    return -1;
}

static void app_on_destroy(void)
{
    if (s_os && s_os->close_music_hub) {
        s_os->close_music_hub();
    }
    s_os = NULL;
}

static const glam_app_desc_t s_desc = {
    .on_create = app_on_create,
    .on_destroy = app_on_destroy,
};

const glam_app_desc_t *glam_app_entry(void)
{
    return &s_desc;
}
