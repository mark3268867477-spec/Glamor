/**
 * @file glam_os_api.h
 * @brief G'lam OS Application Binary Interface (ABI v1)
 *
 * Shared between G'lam OS kernel (Flash) and dynamic .elf Apps (TF Card -> PSRAM).
 * Apps MUST NOT directly access Flash write APIs or re-initialize hardware peripherals;
 * all UI, Audio, Storage, and System functions are accessed safely via glam_os_api_t.
 */

#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GLAM_OS_API_VERSION         (1U)

#define GLAM_SCREEN_W               (320)
#define GLAM_SCREEN_H               (240)
#define GLAM_STATUSBAR_H            (24)
#define GLAM_APP_W                  (320)
#define GLAM_APP_H                  (216)

typedef void *glam_obj_t;
typedef void *glam_timer_t;

typedef void (*glam_click_cb_t)(void *user_data);
typedef void (*glam_timer_cb_t)(void *user_data);

typedef struct {
    uint32_t api_version;

    /* System & Memory */
    void (*log_info)(const char *tag, const char *fmt, ...);
    void (*show_toast)(const char *msg);
    void (*request_exit)(void);
    uint32_t (*get_free_psram)(void);
    uint32_t (*get_free_sram)(void);
    void *(*malloc_psram)(size_t size);
    void (*free_psram)(void *ptr);
    int (*fmt_snprintf)(char *buf, size_t size, const char *fmt, ...);

    /* Safe UI Primitives (rendered inside 320x216 app_root) */
    void (*ui_clear_root)(glam_obj_t root, uint32_t bg_hex);
    glam_obj_t (*ui_create_panel)(glam_obj_t parent, int x, int y, int w, int h,
                                  uint32_t bg_hex, int radius, uint32_t border_hex);
    glam_obj_t (*ui_create_label)(glam_obj_t parent, const char *text, int x, int y,
                                  uint32_t color_hex, int font_size);
    void (*ui_set_label_text)(glam_obj_t label, const char *text);
    void (*ui_set_label_color)(glam_obj_t label, uint32_t color_hex);
    glam_obj_t (*ui_create_button)(glam_obj_t parent, const char *text, int x, int y,
                                   int w, int h, uint32_t bg_hex,
                                   glam_click_cb_t on_click, void *user_data);
    glam_obj_t (*ui_create_bar)(glam_obj_t parent, int x, int y, int w, int h,
                                int32_t min_v, int32_t max_v,
                                uint32_t bg_hex, uint32_t ind_hex);
    void (*ui_set_bar_value)(glam_obj_t bar, int32_t val);
    glam_obj_t (*ui_create_list)(glam_obj_t parent, int x, int y, int w, int h,
                                 uint32_t bg_hex);
    glam_obj_t (*ui_list_add_btn)(glam_obj_t list, const char *text,
                                  glam_click_cb_t on_click, void *user_data);
    glam_timer_t (*ui_create_timer)(glam_timer_cb_t cb, uint32_t period_ms, void *user_data);
    void (*ui_delete_timer)(glam_timer_t timer);

    /* OS Background Audio Service (ES8311 DAC + NS4150B PA) */
    int (*audio_play_file)(const char *path);
    int (*audio_pause)(void);
    int (*audio_resume)(void);
    int (*audio_stop)(void);
    bool (*audio_is_playing)(void);
    bool (*audio_is_paused)(void);
    int (*audio_get_progress)(uint32_t *cur_ms, uint32_t *total_ms);
    int (*audio_set_volume)(uint8_t vol);
    uint8_t (*audio_get_volume)(void);
    const char *(*audio_get_current_file)(void);
    int (*audio_scan_music)(char out_paths[][256], char out_titles[][64], int max_items);

    /* Sandboxed Storage (/sdcard/data/<app_id>/) */
    int (*storage_write_text)(const char *app_id, const char *rel_name, const char *content);
    int (*storage_read_text)(const char *app_id, const char *rel_name, char *out_buf, size_t max_len);

    /* Connectivity & Hardware Status */
    bool (*wifi_is_connected)(void);
    void (*wifi_get_ip)(char *out_ip, size_t max_len);
    bool (*sd_is_mounted)(void);

    /* Bundled 1:1 Music Hub Bridge */
    void (*open_music_hub)(void);
    void (*close_music_hub)(void);
} glam_os_api_t;

typedef struct {
    int  (*on_create)(const glam_os_api_t *os, glam_obj_t root, const char *app_id, const char *data_dir);
    void (*on_destroy)(void);
} glam_app_desc_t;

typedef const glam_app_desc_t *(*glam_app_entry_fn_t)(void);

#ifdef __cplusplus
}
#endif
