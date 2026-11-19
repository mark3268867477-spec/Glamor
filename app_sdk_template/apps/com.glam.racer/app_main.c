/**
 * @file app_main.c
 * @brief 极速赛车 - QMI8658 Six-Axis IMU Tilt Racing Game (Dynamic PSRAM .elf)
 */

#include "glam_os_api.h"

/* Road & Screen Geometry (320 x 216 app viewport) */
#define ROAD_X              (6)
#define ROAD_Y              (4)
#define ROAD_W              (196)
#define ROAD_H              (208)
#define SHOULDER_W          (10)
#define TRACK_MIN_X         (13)
#define TRACK_MAX_X         (ROAD_W - 13)

#define PLAYER_W            (30)
#define PLAYER_H            (44)
#define PLAYER_Y            (ROAD_H - PLAYER_H - 10)

#define ENEMY_COUNT         (3)
#define ENEMY_W             (28)
#define ENEMY_H             (40)
#define LANE_STRIPE_CNT     (5)
#define COIN_SZ             (18)

/* QMI8658 I2C Registers (0x6A on I2C0) */
#define QMI8658_ADDR        (0x6AU)
#define QMI8658_WHO_AM_I    (0x00U)
#define QMI8658_CTRL1       (0x02U)
#define QMI8658_CTRL2       (0x03U)
#define QMI8658_CTRL3       (0x04U)
#define QMI8658_CTRL7       (0x08U)
#define QMI8658_STATUS0     (0x2EU)
#define QMI8658_AX_L        (0x35U)

#define LV_OBJ_FLAG_HIDDEN              (1U << 0)

typedef struct {
    int dev_addr_length;    /* 0 = 7-bit */
    uint16_t device_address;
    uint32_t scl_speed_hz;
    uint32_t scl_wait_us;
    struct {
        uint32_t disable_ack_check : 1;
    } flags;
} app_i2c_dev_cfg_t;

typedef union {
    uint16_t full;
} app_lv_color_t;

extern void *bsp_i2c_get_handle(void);
extern int i2c_master_bus_add_device(void *bus, const app_i2c_dev_cfg_t *cfg, void **ret_dev);
extern int i2c_master_bus_rm_device(void *dev);
extern int i2c_master_transmit(void *dev, const uint8_t *w, size_t wlen, int timeout_ms);
extern int i2c_master_transmit_receive(void *dev, const uint8_t *w, size_t wlen, uint8_t *r, size_t rlen, int timeout_ms);
extern void lv_obj_set_pos(glam_obj_t obj, int16_t x, int16_t y);
extern void lv_obj_set_style_bg_color(glam_obj_t obj, app_lv_color_t color, uint32_t selector);
extern void lv_obj_add_flag(glam_obj_t obj, uint32_t flag);
extern void lv_obj_clear_flag(glam_obj_t obj, uint32_t flag);

typedef void *(*fn_bsp_i2c_get_handle_t)(void);
typedef int (*fn_i2c_bus_add_dev_t)(void *bus, const app_i2c_dev_cfg_t *cfg, void **ret_dev);
typedef int (*fn_i2c_bus_rm_dev_t)(void *dev);
typedef int (*fn_i2c_tx_t)(void *dev, const uint8_t *w, size_t wlen, int timeout_ms);
typedef int (*fn_i2c_txrx_t)(void *dev, const uint8_t *w, size_t wlen, uint8_t *r, size_t rlen, int timeout_ms);
typedef void (*fn_lv_obj_set_pos_t)(glam_obj_t obj, int16_t x, int16_t y);
typedef void (*fn_lv_obj_set_style_bg_t)(glam_obj_t obj, app_lv_color_t color, uint32_t selector);
typedef void (*fn_lv_obj_flag_t)(glam_obj_t obj, uint32_t flag);

typedef struct {
    glam_obj_t obj;
    int16_t x;
    int16_t y;
    uint8_t lane;
    uint8_t speed_extra;
} enemy_car_t;

typedef struct {
    const glam_os_api_t *os;
    glam_timer_t timer;

    /* Kernel Direct Bridges */
    fn_bsp_i2c_get_handle_t k_i2c_get_bus;
    fn_i2c_bus_add_dev_t k_i2c_add_dev;
    fn_i2c_bus_rm_dev_t k_i2c_rm_dev;
    fn_i2c_tx_t k_i2c_tx;
    fn_i2c_txrx_t k_i2c_txrx;
    fn_lv_obj_set_pos_t k_set_pos;
    fn_lv_obj_set_style_bg_t k_set_bg_color;
    fn_lv_obj_flag_t k_add_flag;
    fn_lv_obj_flag_t k_clear_flag;

    /* QMI8658 State */
    void *i2c_dev;
    bool imu_ok;
    int16_t raw_ax;
    int16_t raw_ay;
    int16_t raw_az;
    int16_t raw_gx;
    int16_t raw_gy;
    int16_t raw_gz;
    int16_t cal_ax;
    int16_t cal_ay;
    int32_t filt_steer;
    int32_t filt_pitch;
    uint8_t axis_mode;      /* 0: Y+, 1: Y-, 2: X+, 3: X- */
    bool need_cal;

    /* Game Entities */
    glam_obj_t road;
    glam_obj_t stripes_l[LANE_STRIPE_CNT];
    glam_obj_t stripes_r[LANE_STRIPE_CNT];
    glam_obj_t player_obj;
    glam_obj_t coin_obj;
    glam_obj_t crash_box;
    glam_obj_t lbl_crash;
    enemy_car_t enemies[ENEMY_COUNT];

    /* HUD Telemetry */
    glam_obj_t lbl_score;
    glam_obj_t lbl_speed;
    glam_obj_t tilt_bar;
    glam_obj_t lbl_imu;

    /* Game Physics & Score */
    int32_t player_x_fp;    /* Fixed-point x * 16 */
    int16_t touch_nudge;
    int16_t coin_x;
    int16_t coin_y;
    int16_t stripe_offset;
    uint32_t score;
    uint32_t best_score;
    uint32_t frame_cnt;
    uint32_t rng_state;
    int16_t turbo_ticks;
    int16_t crash_ticks;
    bool game_over;
    bool new_best_toasted;
} racer_state_t;

static racer_state_t s_racer;

/* Standalone implementations for -nostdlib GCC struct copy / zero-init builtins */
__attribute__((used)) void *memcpy(void *dst, const void *src, size_t n)
{
    uint8_t *d = (uint8_t *)dst;
    const uint8_t *s = (const uint8_t *)src;
    while (n--) *d++ = *s++;
    return dst;
}

__attribute__((used)) void *memset(void *dst, int c, size_t n)
{
    uint8_t *d = (uint8_t *)dst;
    while (n--) *d++ = (uint8_t)c;
    return dst;
}

static const int16_t k_lane_x[3] = { 24, 83, 143 };
static const uint32_t k_enemy_colors[ENEMY_COUNT] = { 0x38BDF8U, 0xF59E0BU, 0xA855F7U };
static const char *k_axis_names[4] = { "Y+", "Y-", "X+", "X-" };

static inline app_lv_color_t make_lv_color(uint32_t c)
{
    app_lv_color_t r;
    r.full = (uint16_t)(((c & 0xF80000U) >> 16) |
                        ((c & 0xFC00U) >> 13) |
                        ((c & 0x1C00U) << 3) |
                        ((c & 0xF8U) << 5));
    return r;
}

static uint32_t next_rand(void)
{
    uint32_t x = s_racer.rng_state;
    if (x == 0) x = 0x13579BDFU;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    s_racer.rng_state = x;
    return x;
}

static int16_t clamp_i16(int32_t v, int16_t lo, int16_t hi)
{
    if (v < lo) return lo;
    if (v > hi) return hi;
    return (int16_t)v;
}

static uint32_t parse_u32_str(const char *s)
{
    uint32_t val = 0;
    if (!s) return 0;
    while (*s) {
        if (*s >= '0' && *s <= '9') {
            val = val * 10U + (uint32_t)(*s - '0');
        } else if (val > 0) {
            break;
        }
        s++;
    }
    return val;
}

static void save_best_score(void)
{
    if (!s_racer.os || !s_racer.os->storage_write_text) return;
    char buf[24];
    s_racer.os->fmt_snprintf(buf, sizeof(buf), "%u", (unsigned)s_racer.best_score);
    s_racer.os->storage_write_text("com.glam.racer", "best.txt", buf);
}

static bool qmi_write_reg(uint8_t reg, uint8_t val)
{
    if (!s_racer.i2c_dev || !s_racer.k_i2c_tx) return false;
    uint8_t buf[2] = { reg, val };
    return (s_racer.k_i2c_tx(s_racer.i2c_dev, buf, sizeof(buf), 80) == 0);
}

static bool qmi_read_reg(uint8_t reg, uint8_t *out, size_t len)
{
    if (!s_racer.i2c_dev || !s_racer.k_i2c_txrx || !out || len == 0) return false;
    return (s_racer.k_i2c_txrx(s_racer.i2c_dev, &reg, 1, out, len, 80) == 0);
}

static void qmi_init_sensor(void)
{
    s_racer.imu_ok = false;
    s_racer.i2c_dev = NULL;
    if (!s_racer.k_i2c_get_bus || !s_racer.k_i2c_add_dev) return;

    void *bus = s_racer.k_i2c_get_bus();
    if (!bus) return;

    app_i2c_dev_cfg_t cfg = {
        .dev_addr_length = 0, /* I2C_ADDR_BIT_LEN_7 */
        .device_address = QMI8658_ADDR,
        .scl_speed_hz = 100000U,
        .scl_wait_us = 0,
        .flags = { .disable_ack_check = 0 },
    };

    if (s_racer.k_i2c_add_dev(bus, &cfg, &s_racer.i2c_dev) != 0 || !s_racer.i2c_dev) {
        return;
    }

    uint8_t who = 0;
    for (int retry = 0; retry < 3; retry++) {
        if (qmi_read_reg(QMI8658_WHO_AM_I, &who, 1) && who == 0x05U) {
            break;
        }
    }
    if (who != 0x05U) {
        s_racer.os->log_info("racer", "QMI8658 WHO_AM_I mismatch: 0x%02x", (unsigned)who);
        return;
    }

    /* Auto-increment, +-4g @ 250Hz Accel, +-512dps @ 250Hz Gyro, Enable Accel+Gyro */
    qmi_write_reg(QMI8658_CTRL1, 0x40U);
    qmi_write_reg(QMI8658_CTRL2, 0x95U);
    qmi_write_reg(QMI8658_CTRL3, 0xD5U);
    qmi_write_reg(QMI8658_CTRL7, 0x03U);
    s_racer.imu_ok = true;
    s_racer.need_cal = true;
    s_racer.os->log_info("racer", "QMI8658 6-axis IMU active @ 0x6A");
}

static bool qmi_poll_sensor(void)
{
    if (!s_racer.imu_ok) return false;

    uint8_t st = 0;
    if (!qmi_read_reg(QMI8658_STATUS0, &st, 1)) return false;
    if ((st & 0x03U) == 0U) return false;

    uint8_t raw[12];
    if (!qmi_read_reg(QMI8658_AX_L, raw, sizeof(raw))) return false;

    s_racer.raw_ax = (int16_t)((uint16_t)raw[0] | ((uint16_t)raw[1] << 8));
    s_racer.raw_ay = (int16_t)((uint16_t)raw[2] | ((uint16_t)raw[3] << 8));
    s_racer.raw_az = (int16_t)((uint16_t)raw[4] | ((uint16_t)raw[5] << 8));
    s_racer.raw_gx = (int16_t)((uint16_t)raw[6] | ((uint16_t)raw[7] << 8));
    s_racer.raw_gy = (int16_t)((uint16_t)raw[8] | ((uint16_t)raw[9] << 8));
    s_racer.raw_gz = (int16_t)((uint16_t)raw[10] | ((uint16_t)raw[11] << 8));

    if (s_racer.need_cal) {
        s_racer.cal_ax = s_racer.raw_ax;
        s_racer.cal_ay = s_racer.raw_ay;
        s_racer.filt_steer = 0;
        s_racer.filt_pitch = 0;
        s_racer.need_cal = false;
    }
    return true;
}

#define SAFE_ROW_GAP_Y      (90)

static int pick_free_lane(int16_t spawn_y)
{
    uint32_t r = next_rand();
    for (int k = 0; k < 3; k++) {
        int lane = (int)((r + (uint32_t)k) % 3U);
        bool blocked = false;
        for (int e = 0; e < ENEMY_COUNT; e++) {
            int16_t dy = s_racer.enemies[e].y - spawn_y;
            if (dy < 0) dy = -dy;
            if (dy < 56 && s_racer.enemies[e].lane == (uint8_t)lane) {
                blocked = true;
                break;
            }
        }
        if (!blocked) return lane;
    }
    return (int)(r % 3U);
}

/* Guarantee at least 1 of the 3 lanes stays open in every SAFE_ROW_GAP_Y band */
static int pick_passable_enemy_lane(int self_idx, int16_t *io_spawn_y)
{
    int16_t sy = *io_spawn_y;
    for (int attempt = 0; attempt < 8; attempt++) {
        bool lane_busy[3] = { false, false, false };
        for (int e = 0; e < ENEMY_COUNT; e++) {
            if (e == self_idx) continue;
            int16_t dy = s_racer.enemies[e].y - sy;
            if (dy < 0) dy = -dy;
            if (dy < SAFE_ROW_GAP_Y) {
                lane_busy[s_racer.enemies[e].lane % 3U] = true;
            }
        }
        int free_lanes[3];
        int free_cnt = 0;
        for (int l = 0; l < 3; l++) {
            if (!lane_busy[l]) free_lanes[free_cnt++] = l;
        }
        /* Require at least 2 free lanes before placing this car, leaving >=1 open escape lane */
        if (free_cnt >= 2) {
            *io_spawn_y = sy;
            return free_lanes[next_rand() % (uint32_t)free_cnt];
        }
        sy -= SAFE_ROW_GAP_Y;
    }
    *io_spawn_y = sy;
    return (int)(next_rand() % 3U);
}

static void reset_race(bool recalibrate)
{
    if (recalibrate) {
        s_racer.need_cal = true;
    }
    s_racer.game_over = false;
    s_racer.new_best_toasted = false;
    s_racer.score = 0;
    s_racer.frame_cnt = 0;
    s_racer.turbo_ticks = 0;
    s_racer.crash_ticks = 0;
    s_racer.touch_nudge = 0;
    s_racer.player_x_fp = ((ROAD_W - PLAYER_W) / 2) * 16;

    if (s_racer.k_set_pos && s_racer.player_obj) {
        s_racer.k_set_pos(s_racer.player_obj, (int16_t)(s_racer.player_x_fp >> 4), PLAYER_Y);
    }

    uint32_t lane_shift = next_rand() % 3U;
    for (int i = 0; i < ENEMY_COUNT; i++) {
        uint8_t lane = (uint8_t)((i + lane_shift) % 3U);
        s_racer.enemies[i].lane = lane;
        s_racer.enemies[i].x = k_lane_x[lane];
        s_racer.enemies[i].y = (int16_t)(-50 - i * 105);
        s_racer.enemies[i].speed_extra = 0;
        if (s_racer.k_set_pos && s_racer.enemies[i].obj) {
            s_racer.k_set_pos(s_racer.enemies[i].obj, s_racer.enemies[i].x, s_racer.enemies[i].y);
        }
    }

    uint8_t coin_lane = (uint8_t)(next_rand() % 3U);
    s_racer.coin_x = k_lane_x[coin_lane] + (ENEMY_W - COIN_SZ) / 2;
    s_racer.coin_y = -110;
    if (s_racer.k_set_pos && s_racer.coin_obj) {
        s_racer.k_set_pos(s_racer.coin_obj, s_racer.coin_x, s_racer.coin_y);
    }

    if (s_racer.k_add_flag && s_racer.crash_box) {
        s_racer.k_add_flag(s_racer.crash_box, LV_OBJ_FLAG_HIDDEN);
    }
    if (s_racer.k_set_bg_color && s_racer.player_obj) {
        s_racer.k_set_bg_color(s_racer.player_obj, make_lv_color(0xEF4444U), 0);
    }
}

static bool boxes_overlap(int16_t ax, int16_t ay, int16_t aw, int16_t ah,
                          int16_t bx, int16_t by, int16_t bw, int16_t bh)
{
    return (ax < bx + bw) && (ax + aw > bx) && (ay < by + bh) && (ay + ah > by);
}

static void on_cal_restart_click(void *user_data)
{
    (void)user_data;
    bool was_over = s_racer.game_over;
    reset_race(true);
    s_racer.os->show_toast(was_over ? "重新发车 & 零点已校准!" : "已校准水平零点!");
}

static void on_axis_switch_click(void *user_data)
{
    (void)user_data;
    s_racer.axis_mode = (uint8_t)((s_racer.axis_mode + 1U) & 3U);
    s_racer.need_cal = true;
    char msg[40];
    s_racer.os->fmt_snprintf(msg, sizeof(msg), "转向轴已切换: %s", k_axis_names[s_racer.axis_mode]);
    s_racer.os->show_toast(msg);
}

static void on_exit_click(void *user_data)
{
    (void)user_data;
    s_racer.os->request_exit();
}

static void on_left_click(void *user_data)
{
    (void)user_data;
    s_racer.touch_nudge -= 18;
}

static void on_right_click(void *user_data)
{
    (void)user_data;
    s_racer.touch_nudge += 18;
}

static void update_hud(int32_t steer_val, int32_t speed_px)
{
    const glam_os_api_t *os = s_racer.os;
    char buf[64];

    os->fmt_snprintf(buf, sizeof(buf), "得分: %u\n最高: %u",
                     (unsigned)s_racer.score, (unsigned)s_racer.best_score);
    os->ui_set_label_text(s_racer.lbl_score, buf);

    int kmh = 95 + (int)speed_px * 18 + (s_racer.turbo_ticks > 0 ? 45 : 0);
    os->fmt_snprintf(buf, sizeof(buf), "%s %d km/h",
                     (s_racer.turbo_ticks > 0) ? "加速" : "时速", kmh);
    os->ui_set_label_text(s_racer.lbl_speed, buf);

    int32_t bar_v = 50 + (steer_val * 50) / 3500;
    os->ui_set_bar_value(s_racer.tilt_bar, (int32_t)clamp_i16(bar_v, 0, 100));

    if (s_racer.imu_ok) {
        os->fmt_snprintf(buf, sizeof(buf), "X:%d Y:%d\n轴:%s %s",
                         (int)(s_racer.raw_ax / 100),
                         (int)(s_racer.raw_ay / 100),
                         k_axis_names[s_racer.axis_mode],
                         s_racer.game_over ? "撞车" : "体感中");
    } else {
        os->fmt_snprintf(buf, sizeof(buf), "IMU未连接\n请用 < > 操控");
    }
    os->ui_set_label_text(s_racer.lbl_imu, buf);
}

static void on_game_tick(void *user_data)
{
    (void)user_data;
    s_racer.frame_cnt++;

    qmi_poll_sensor();

    int32_t dx = (int32_t)s_racer.raw_ax - (int32_t)s_racer.cal_ax;
    int32_t dy = (int32_t)s_racer.raw_ay - (int32_t)s_racer.cal_ay;
    int32_t raw_steer = 0;
    int32_t raw_pitch = 0;
    int32_t gyro_assist = 0;

    switch (s_racer.axis_mode) {
        case 0:
            raw_steer = dy;
            raw_pitch = dx;
            gyro_assist = (int32_t)s_racer.raw_gx / 12;
            break;
        case 1:
            raw_steer = -dy;
            raw_pitch = -dx;
            gyro_assist = -(int32_t)s_racer.raw_gx / 12;
            break;
        case 2:
            raw_steer = dx;
            raw_pitch = dy;
            gyro_assist = -(int32_t)s_racer.raw_gy / 12;
            break;
        default:
            raw_steer = -dx;
            raw_pitch = -dy;
            gyro_assist = (int32_t)s_racer.raw_gy / 12;
            break;
    }

    s_racer.filt_steer = (s_racer.filt_steer * 2 + raw_steer + gyro_assist) / 3;
    s_racer.filt_pitch = (s_racer.filt_pitch * 3 + raw_pitch) / 4;

    if (s_racer.game_over) {
        if (s_racer.crash_ticks > 0) {
            s_racer.crash_ticks--;
        } else if (s_racer.imu_ok && (s_racer.raw_gz > 16000 || s_racer.raw_gz < -16000)) {
            reset_race(false);
            s_racer.os->show_toast("甩动重新发车!");
        }
        if ((s_racer.frame_cnt & 3U) == 0U) {
            update_hud(s_racer.filt_steer, 0);
        }
        return;
    }

    /* Deadzone +-160 LSB (~1.1 deg) prevents stationary drift */
    int32_t eff_steer = 0;
    if (s_racer.filt_steer > 160) eff_steer = s_racer.filt_steer - 160;
    else if (s_racer.filt_steer < -160) eff_steer = s_racer.filt_steer + 160;

    /* Lateral speed in fixed-point x16 pixels/frame (plus touch nudge decay) */
    int32_t vx_fp = (eff_steer * 7) / 140;
    if (vx_fp > 128) vx_fp = 128;
    if (vx_fp < -128) vx_fp = -128;

    s_racer.player_x_fp += vx_fp + ((int32_t)s_racer.touch_nudge * 8);
    if (s_racer.touch_nudge > 3) s_racer.touch_nudge -= 3;
    else if (s_racer.touch_nudge < -3) s_racer.touch_nudge += 3;
    else s_racer.touch_nudge = 0;

    int32_t min_fp = (int32_t)TRACK_MIN_X * 16;
    int32_t max_fp = (int32_t)(TRACK_MAX_X - PLAYER_W) * 16;
    if (s_racer.player_x_fp < min_fp) s_racer.player_x_fp = min_fp;
    if (s_racer.player_x_fp > max_fp) s_racer.player_x_fp = max_fp;

    int16_t px = (int16_t)(s_racer.player_x_fp >> 4);
    if (s_racer.k_set_pos) {
        s_racer.k_set_pos(s_racer.player_obj, px, PLAYER_Y);
    }

    /* Forward road speed scales with score + forward pitch + Nitro boost */
    int32_t base_spd = 3 + (int32_t)(s_racer.score / 280U);
    if (base_spd > 8) base_spd = 8;
    if (s_racer.filt_pitch < -1200) base_spd += 2;
    else if (s_racer.filt_pitch > 1400 && base_spd > 2) base_spd -= 1;
    if (s_racer.turbo_ticks > 0) {
        base_spd += 3;
        s_racer.turbo_ticks--;
    }

    /* Scroll road lane dividers */
    s_racer.stripe_offset = (int16_t)((s_racer.stripe_offset + base_spd) % 44);
    if (s_racer.k_set_pos) {
        for (int i = 0; i < LANE_STRIPE_CNT; i++) {
            int16_t sy = (int16_t)(i * 44 + s_racer.stripe_offset - 22);
            s_racer.k_set_pos(s_racer.stripes_l[i], 68, sy);
            s_racer.k_set_pos(s_racer.stripes_r[i], 126, sy);
        }
    }

    /* Move Nitro star pickup */
    s_racer.coin_y += (int16_t)base_spd;
    if (boxes_overlap((int16_t)(px + 2), PLAYER_Y + 3, PLAYER_W - 4, PLAYER_H - 6,
                      s_racer.coin_x, s_racer.coin_y, COIN_SZ, COIN_SZ)) {
        s_racer.score += 50U;
        s_racer.turbo_ticks = 45;
        uint8_t cl = (uint8_t)pick_free_lane(-70);
        s_racer.coin_x = k_lane_x[cl] + (ENEMY_W - COIN_SZ) / 2;
        s_racer.coin_y = -85;
        s_racer.os->show_toast("氮气加速 +50!");
    } else if (s_racer.coin_y > ROAD_H + 10) {
        uint8_t cl = (uint8_t)pick_free_lane(-70);
        s_racer.coin_x = k_lane_x[cl] + (ENEMY_W - COIN_SZ) / 2;
        s_racer.coin_y = -60 - (int16_t)(next_rand() % 60U);
    }
    if (s_racer.k_set_pos) {
        s_racer.k_set_pos(s_racer.coin_obj, s_racer.coin_x, s_racer.coin_y);
    }

    /* Move Enemy Traffic & Check Forgiving Hitbox */
    for (int i = 0; i < ENEMY_COUNT; i++) {
        enemy_car_t *en = &s_racer.enemies[i];
        en->y += (int16_t)base_spd;
        if (en->y > ROAD_H + 12) {
            int16_t spawn_y = (int16_t)(-48 - (int16_t)(next_rand() % 44U));
            int lane = pick_passable_enemy_lane(i, &spawn_y);
            en->lane = (uint8_t)lane;
            en->x = k_lane_x[lane];
            en->y = spawn_y;
            en->speed_extra = 0;
            s_racer.score += 15U;
        }
        if (s_racer.k_set_pos) {
            s_racer.k_set_pos(en->obj, en->x, en->y);
        }

        if (boxes_overlap((int16_t)(px + 4), PLAYER_Y + 4, PLAYER_W - 8, PLAYER_H - 8,
                          (int16_t)(en->x + 3), (int16_t)(en->y + 4), ENEMY_W - 6, ENEMY_H - 8)) {
            s_racer.game_over = true;
            s_racer.crash_ticks = 18;
            if (s_racer.score > s_racer.best_score) {
                s_racer.best_score = s_racer.score;
                save_best_score();
            }
            if (s_racer.k_set_bg_color && s_racer.player_obj) {
                s_racer.k_set_bg_color(s_racer.player_obj, make_lv_color(0x991B1BU), 0);
            }
            if (s_racer.crash_box && s_racer.k_clear_flag) {
                char msg[64];
                s_racer.os->fmt_snprintf(msg, sizeof(msg),
                                         "发生碰撞! 得分 %u\n点[校准/重玩]或甩动续玩",
                                         (unsigned)s_racer.score);
                s_racer.os->ui_set_label_text(s_racer.lbl_crash, msg);
                s_racer.k_clear_flag(s_racer.crash_box, LV_OBJ_FLAG_HIDDEN);
            }
            break;
        }
    }

    if (!s_racer.game_over) {
        s_racer.score += (s_racer.turbo_ticks > 0) ? 2U : 1U;
        if (s_racer.score > s_racer.best_score) {
            if (!s_racer.new_best_toasted && s_racer.best_score > 0) {
                s_racer.new_best_toasted = true;
                s_racer.os->show_toast("打破最高纪录!");
            }
            s_racer.best_score = s_racer.score;
        }
    }

    if ((s_racer.frame_cnt & 1U) == 0U) {
        update_hud(s_racer.filt_steer, base_spd);
    }
}

static void build_game_ui(glam_obj_t root)
{
    const glam_os_api_t *os = s_racer.os;
    os->ui_clear_root(root, 0x070B14U);

    /* Left Road Track Panel (196 x 208) */
    s_racer.road = os->ui_create_panel(root, ROAD_X, ROAD_Y, ROAD_W, ROAD_H, 0x111827U, 10, 0x334155U);

    /* Left & right road shoulders */
    os->ui_create_panel(s_racer.road, 0, 0, SHOULDER_W, ROAD_H, 0x991B1BU, 0, 0);
    os->ui_create_panel(s_racer.road, ROAD_W - SHOULDER_W, 0, SHOULDER_W, ROAD_H, 0x991B1BU, 0, 0);

    /* Dashed lane dividers */
    for (int i = 0; i < LANE_STRIPE_CNT; i++) {
        int y = i * 44 - 22;
        s_racer.stripes_l[i] = os->ui_create_panel(s_racer.road, 68, y, 4, 22, 0x64748BU, 2, 0);
        s_racer.stripes_r[i] = os->ui_create_panel(s_racer.road, 126, y, 4, 22, 0x64748BU, 2, 0);
    }

    /* Nitro gold pickup */
    s_racer.coin_obj = os->ui_create_panel(s_racer.road, k_lane_x[1] + 5, -90,
                                           COIN_SZ, COIN_SZ, 0xFACC15U, 9, 0xFEF08AU);

    /* Enemy traffic cars */
    for (int i = 0; i < ENEMY_COUNT; i++) {
        glam_obj_t car = os->ui_create_panel(s_racer.road, k_lane_x[i], -60 - i * 80,
                                              ENEMY_W, ENEMY_H, k_enemy_colors[i], 6, 0xE2E8F0U);
        os->ui_create_panel(car, 5, 19, ENEMY_W - 10, 10, 0x0F172AU, 2, 0);
        os->ui_create_panel(car, 4, ENEMY_H - 6, 6, 4, 0xFCA5A5U, 1, 0);
        os->ui_create_panel(car, ENEMY_W - 10, ENEMY_H - 6, 6, 4, 0xFCA5A5U, 1, 0);
        s_racer.enemies[i].obj = car;
    }

    /* Player sports car */
    s_racer.player_obj = os->ui_create_panel(s_racer.road, (ROAD_W - PLAYER_W) / 2, PLAYER_Y,
                                             PLAYER_W, PLAYER_H, 0xEF4444U, 7, 0xFCA5A5U);
    os->ui_create_panel(s_racer.player_obj, 4, 2, 6, 5, 0xFEF08AU, 2, 0);
    os->ui_create_panel(s_racer.player_obj, PLAYER_W - 10, 2, 6, 5, 0xFEF08AU, 2, 0);
    os->ui_create_panel(s_racer.player_obj, 5, 11, PLAYER_W - 10, 12, 0x0F172AU, 3, 0);
    os->ui_create_panel(s_racer.player_obj, 3, PLAYER_H - 7, PLAYER_W - 6, 5, 0x7F1D1DU, 2, 0);

    /* Crash Overlay Banner (initially hidden) */
    s_racer.crash_box = os->ui_create_panel(s_racer.road, 12, 58, ROAD_W - 24, 78, 0x090D16U, 10, 0xEF4444U);
    s_racer.lbl_crash = os->ui_create_label(s_racer.crash_box, "", 10, 14, 0xF8FAFCU, 12);
    if (s_racer.k_add_flag) {
        s_racer.k_add_flag(s_racer.crash_box, LV_OBJ_FLAG_HIDDEN);
    }

    /* Right Telemetry & Controls Panel (108 x 208) */
    glam_obj_t hud = os->ui_create_panel(root, 206, 4, 108, 208, 0x0F172AU, 10, 0x1E293BU);
    os->ui_create_label(hud, "极速赛车 6轴", 8, 6, 0xF97316U, 14);
    s_racer.lbl_score = os->ui_create_label(hud, "得分: 0\n最高: 0", 8, 27, 0xF8FAFCU, 12);
    s_racer.lbl_speed = os->ui_create_label(hud, "时速 149 km/h", 8, 61, 0x38BDF8U, 12);
    s_racer.tilt_bar = os->ui_create_bar(hud, 8, 80, 92, 10, 0, 100, 0x1E293BU, 0xF97316U);
    os->ui_set_bar_value(s_racer.tilt_bar, 50);
    s_racer.lbl_imu = os->ui_create_label(hud, "传感器校准中...", 8, 95, 0x94A3B8U, 12);

    os->ui_create_button(hud, "校准/重玩", 8, 130, 92, 27, 0xEA580CU, on_cal_restart_click, NULL);
    os->ui_create_button(hud, "切轴", 8, 161, 44, 21, 0x334155U, on_axis_switch_click, NULL);
    os->ui_create_button(hud, "退出", 56, 161, 44, 21, 0x475569U, on_exit_click, NULL);
    os->ui_create_button(hud, "<", 8, 185, 44, 19, 0x1D4ED8U, on_left_click, NULL);
    os->ui_create_button(hud, ">", 56, 185, 44, 19, 0x1D4ED8U, on_right_click, NULL);
}

static int app_on_create(const glam_os_api_t *os, glam_obj_t root, const char *app_id, const char *data_dir)
{
    (void)app_id;
    (void)data_dir;

    uint8_t *p = (uint8_t *)&s_racer;
    for (size_t i = 0; i < sizeof(s_racer); i++) {
        p[i] = 0;
    }

    s_racer.os = os;
    s_racer.axis_mode = 0; /* Default Y+ */
    s_racer.k_i2c_get_bus = bsp_i2c_get_handle;
    s_racer.k_i2c_add_dev = i2c_master_bus_add_device;
    s_racer.k_i2c_rm_dev = i2c_master_bus_rm_device;
    s_racer.k_i2c_tx = i2c_master_transmit;
    s_racer.k_i2c_txrx = i2c_master_transmit_receive;
    s_racer.k_set_pos = lv_obj_set_pos;
    s_racer.k_set_bg_color = lv_obj_set_style_bg_color;
    s_racer.k_add_flag = lv_obj_add_flag;
    s_racer.k_clear_flag = lv_obj_clear_flag;

    char best_buf[24] = {0};
    if (os->storage_read_text("com.glam.racer", "best.txt", best_buf, sizeof(best_buf)) == 0) {
        s_racer.best_score = parse_u32_str(best_buf);
    }

    s_racer.rng_state = (uint32_t)(uintptr_t)root ^ os->get_free_psram() ^ s_racer.best_score ^ 0xA55A1234U;

    qmi_init_sensor();
    build_game_ui(root);
    reset_race(true);
    update_hud(0, 3);

    s_racer.timer = os->ui_create_timer(on_game_tick, 35, NULL);
    os->show_toast(s_racer.imu_ok ? "左右倾斜操控赛车!" : "点击 < > 按键操控赛车!");
    return 0;
}

static void app_on_destroy(void)
{
    if (s_racer.timer && s_racer.os) {
        s_racer.os->ui_delete_timer(s_racer.timer);
        s_racer.timer = NULL;
    }
    if (s_racer.best_score > 0) {
        save_best_score();
    }
    if (s_racer.i2c_dev && s_racer.k_i2c_rm_dev) {
        s_racer.k_i2c_rm_dev(s_racer.i2c_dev);
        s_racer.i2c_dev = NULL;
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
