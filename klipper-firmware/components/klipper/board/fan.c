// Internal TRIAC phase-angle fan control for BIQU Panda Breath
//
// The two 75x75x30mm AC fans are driven by a BT136-800E TRIAC via MOC3021S
// optocoupler. A TLP785 zero-crossing detector on GPIO_ZERO_CROSS fires an
// ISR every AC half-cycle (nominally every ~8.3ms at 60Hz or ~10ms at 50Hz).
// The ISR arms a one-shot esp_timer; when the timer fires it pulses
// GPIO_FAN high for GATE_PULSE_US, triggering the TRIAC gate at the desired
// phase angle. Duty 1.0 = fire immediately after ZCD (full power); 0.0 = off.
//
// Fan speed is managed internally by a FreeRTOS task that watches the relay
// GPIO state set by Klipper. Klipper never sees the fan — it only controls
// heater_pin (the relay). The fan follows:
//   heater on  → fan at FAN_DUTY_ACTIVE
//   heater off → fan at FAN_DUTY_COOLDOWN for FAN_COOLDOWN_MS, then off
//
// NOT part of the Klipper MCU command protocol.
//
// This file may be distributed under the terms of the GNU GPLv3 license.

#include "panda_breath_pins.h"

#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "fan";

// Fan duty when heater relay is active (0.0–1.0, phase angle)
#define FAN_DUTY_ACTIVE     0.40f
// Fan duty during post-heater cooldown
#define FAN_DUTY_COOLDOWN   0.25f
// Cooldown period after relay goes low before fan stops (ms)
#define FAN_COOLDOWN_MS     60000
// TRIAC gate pulse width — long enough to latch, short enough to avoid overheating
#define GATE_PULSE_US       150
// Minimum phase-angle delay after ZCD (prevents firing too close to zero)
#define MIN_PHASE_DELAY_US  500

// ---------------------------------------------------------------------------
// Shared state — written by ISR / timer callbacks, read by fan_task
// ---------------------------------------------------------------------------
static volatile float     s_duty = 0.0f;
static volatile uint32_t  s_half_cycle_us = 8333; // 60 Hz default
static volatile uint64_t  s_last_zcd_us   = 0;

static esp_timer_handle_t s_gate_fire_timer = NULL;
static esp_timer_handle_t s_gate_off_timer  = NULL;

// ---------------------------------------------------------------------------
// Timer callbacks (run in high-priority esp_timer task context)
// ---------------------------------------------------------------------------

static void gate_off_cb(void *arg)
{
    gpio_set_level(GPIO_FAN, 0);
}

static void gate_fire_cb(void *arg)
{
    gpio_set_level(GPIO_FAN, 1);
    // Schedule gate pulse end
    esp_timer_start_once(s_gate_off_timer, GATE_PULSE_US);
}

// ---------------------------------------------------------------------------
// Zero-crossing ISR (IRAM — runs every AC half-cycle)
// ---------------------------------------------------------------------------

static void IRAM_ATTR zcd_isr(void *arg)
{
    uint64_t now = esp_timer_get_time();

    if (s_last_zcd_us > 0) {
        uint32_t period = (uint32_t)(now - s_last_zcd_us);
        // Sanity check: 50–120 Hz range → 4167–10000 µs half-cycles
        if (period >= 4000 && period <= 12000) {
            s_half_cycle_us = period;
        }
    }
    s_last_zcd_us = now;

    float duty = s_duty;
    if (duty <= 0.0f)
        return;

    // Phase-angle delay: full duty = fire immediately, low duty = fire late
    uint32_t delay_us = (uint32_t)((1.0f - duty) * (float)s_half_cycle_us);
    if (delay_us < MIN_PHASE_DELAY_US)
        delay_us = MIN_PHASE_DELAY_US;

    // Cancel any pending fire from the previous half-cycle and reschedule.
    // esp_timer_stop is safe to call from ISR context.
    esp_timer_stop(s_gate_fire_timer);
    esp_timer_start_once(s_gate_fire_timer, delay_us);
}

// ---------------------------------------------------------------------------
// Fan duty management task — monitors relay GPIO, adjusts duty
// ---------------------------------------------------------------------------

static void fan_task(void *pvParameters)
{
    int      heater_was_on   = 0;
    uint32_t heater_off_tick = 0;

    for (;;) {
        // Read the relay GPIO level that Klipper set via queue_digital_out.
        // gpio_get_level works on output-configured pins (level is looped back
        // through the ESP32-C3 input register even when configured as output).
        int heater_on = gpio_get_level(GPIO_RELAY);

        if (heater_on) {
            if (!heater_was_on) {
                ESP_LOGI(TAG, "Heater on — fan active (duty %.0f%%)",
                         FAN_DUTY_ACTIVE * 100.0f);
            }
            heater_was_on = 1;
            s_duty = FAN_DUTY_ACTIVE;

        } else if (heater_was_on) {
            // Heater just turned off — start cooldown
            ESP_LOGI(TAG, "Heater off — fan cooldown for %d s",
                     FAN_COOLDOWN_MS / 1000);
            heater_was_on  = 0;
            heater_off_tick = xTaskGetTickCount();
            s_duty = FAN_DUTY_COOLDOWN;

        } else if (s_duty > 0.0f) {
            // In cooldown — check elapsed time
            uint32_t elapsed_ms =
                (xTaskGetTickCount() - heater_off_tick) * portTICK_PERIOD_MS;
            if (elapsed_ms >= FAN_COOLDOWN_MS) {
                ESP_LOGI(TAG, "Cooldown complete — fan off");
                s_duty = 0.0f;
            }
        }

        vTaskDelay(pdMS_TO_TICKS(500));
    }
}

// ---------------------------------------------------------------------------
// Public init — called from main.c before Klipper scheduler starts
// ---------------------------------------------------------------------------

void fan_init(void)
{
    // Configure FAN GPIO as output, initially low
    gpio_config_t fan_cfg = {
        .pin_bit_mask  = (1ULL << GPIO_FAN),
        .mode          = GPIO_MODE_OUTPUT,
        .pull_up_en    = GPIO_PULLUP_DISABLE,
        .pull_down_en  = GPIO_PULLDOWN_DISABLE,
        .intr_type     = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&fan_cfg));
    gpio_set_level(GPIO_FAN, 0);

    // Configure ZCD GPIO as input, interrupt on rising edge
    // (TLP785 output goes high at each AC zero-crossing)
    gpio_config_t zcd_cfg = {
        .pin_bit_mask  = (1ULL << GPIO_ZERO_CROSS),
        .mode          = GPIO_MODE_INPUT,
        .pull_up_en    = GPIO_PULLUP_DISABLE,
        .pull_down_en  = GPIO_PULLDOWN_DISABLE,
        .intr_type     = GPIO_INTR_POSEDGE,
    };
    ESP_ERROR_CHECK(gpio_config(&zcd_cfg));

    // Install ISR service (allow per-pin handlers)
    // ESP_ERR_INVALID_STATE means it's already installed — that's fine.
    esp_err_t err = gpio_install_isr_service(0);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_ERROR_CHECK(err);
    }
    ESP_ERROR_CHECK(gpio_isr_handler_add(GPIO_ZERO_CROSS, zcd_isr, NULL));

    // Create TRIAC gate-fire one-shot timer
    esp_timer_create_args_t fire_args = {
        .callback = gate_fire_cb,
        .name     = "triac_fire",
    };
    ESP_ERROR_CHECK(esp_timer_create(&fire_args, &s_gate_fire_timer));

    // Create gate-off one-shot timer (ends the gate pulse)
    esp_timer_create_args_t off_args = {
        .callback = gate_off_cb,
        .name     = "triac_off",
    };
    ESP_ERROR_CHECK(esp_timer_create(&off_args, &s_gate_off_timer));

    // Start fan supervision task
    xTaskCreate(fan_task, "fan_task", 2048, NULL, 5, NULL);

    ESP_LOGI(TAG, "Fan control initialised (ZCD GPIO%d, FAN GPIO%d)",
             GPIO_ZERO_CROSS, GPIO_FAN);
}
