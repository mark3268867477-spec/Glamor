/**
 * @file swift_os_api.h
 * @brief Backward-compatible alias header for G'lam OS ABI v1 (glam_os_api.h)
 */

#pragma once

#include "glam_os_api.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SWIFT_OS_API_VERSION        GLAM_OS_API_VERSION

#define SWIFT_SCREEN_W              GLAM_SCREEN_W
#define SWIFT_SCREEN_H              GLAM_SCREEN_H
#define SWIFT_STATUSBAR_H           GLAM_STATUSBAR_H
#define SWIFT_APP_W                 GLAM_APP_W
#define SWIFT_APP_H                 GLAM_APP_H

typedef glam_obj_t                  swift_obj_t;
typedef glam_timer_t                swift_timer_t;
typedef glam_click_cb_t             swift_click_cb_t;
typedef glam_timer_cb_t             swift_timer_cb_t;
typedef glam_os_api_t               swift_os_api_t;
typedef glam_app_desc_t             swift_app_desc_t;
typedef glam_app_entry_fn_t         swift_app_entry_fn_t;

#ifdef __cplusplus
}
#endif
