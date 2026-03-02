// Panda Breath KlipperMCU firmware — entry point
//
// Adapts klipper_esp32 (nikhil-robinson) for the BIQU Panda Breath (ESP32-C3).
// Transport: UART0 via onboard CH340K USB-C bridge → Klipper MCU binary protocol.
// Fan control: internal TRIAC phase-angle (see board/fan.c), not exposed to Klipper.
//
// Copyright (C) 2024  Nikhil Robinson <nikhil@techprogeny.com> (original ESP32 port)
// ESP32-C3 / Panda Breath adaptation: see project contributors
//
// This file may be distributed under the terms of the GNU GPLv3 license.

#include "command.h"   // DECL_CONSTANT_STR, DECL_COMMAND_FLAGS, shutdown
#include "internal.h"  // console_setup
#include "sched.h"     // sched_main, sched_is_shutdown
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

// Declare the fan init function from board/fan.c
void fan_init(void);

// MCU identifier reported to Klipper host during dictionary negotiation
DECL_CONSTANT_STR("MCU", "esp32c3");

// Allow the Klipper host to reset the MCU (only valid when already shutdown)
void command_config_reset(uint32_t *args)
{
    if (!sched_is_shutdown())
        shutdown("config_reset only available when shutdown");
    esp_restart();
}
DECL_COMMAND_FLAGS(command_config_reset, HF_IN_SHUTDOWN, "config_reset");

static void main_task(void *pvparameters)
{
    // Start internal TRIAC fan control before Klipper scheduler.
    // The fan monitors the heater relay GPIO and runs a phase-angle duty
    // cycle via the zero-crossing detector — entirely invisible to Klipper.
    fan_init();

    console_setup(NULL);

    for (;;) {
        sched_main();
    }

    vTaskDelete(NULL);
}

void app_main(void)
{
    // ESP32-C3 is single-core; pinToCore=0 is the only valid option
    xTaskCreatePinnedToCore(main_task, "main_task", 4096, NULL, 20, NULL, 0);
}
