#ifndef __PANDA_BREATH_PINS_H
#define __PANDA_BREATH_PINS_H

// =============================================================================
// Panda Breath (ESP32-C3-MINI-1-H4X) GPIO assignments
//
// Sources: hardware schematic reverse-engineered from real device.
// The schematic uses ESP32-C3-MINI-1 *module pad* numbers (not QFN32 IC package
// pins). Cross-referencing the module datasheet pad layout resolves all GPIOs.
//
// GPIO numbers confirmed via IO-net labels are marked CONFIRMED.
// GPIO numbers inferred from module pad cross-reference are marked INFERRED —
// continuity testing on real hardware is recommended before first flash.
// See research/hardware-schematic.md for full schematic analysis.
// =============================================================================

// -----------------------------------------------------------------------------
// CONFIRMED — derived from schematic IO net labels (e.g. IO03, IO07)
// -----------------------------------------------------------------------------

// TRIAC gate — FAN speed control via phase-angle (BT136-800E via MOC3021S + Q2)
#define GPIO_FAN            3   // IO03, schematic physical pin 7

// AC zero-crossing detector output (TLP785 optocoupler)
// Used to synchronise TRIAC phase-angle firing in fan.c
// GPIO7 is shared with the K1 button net — K1 is permanently unavailable.
// (GPIO0 was investigated as an alternative ZERO source, but GPIO0 is the
// TH0 NTC ADC input — OEM firmware reads stable temperatures from it, which
// rules out 100/120 Hz zero-crossing pulses on that pin.)
#define GPIO_ZERO_CROSS     7   // IO07/ZERO, schematic physical pin 22

// LED-backlit tactile buttons (K6-6140S01)
#define GPIO_K2             0   // IO00, schematic physical pin 15
#define GPIO_K3             2   // IO02, schematic physical pin 6

// Per-button LEDs (active-high via 1K resistors R34/R35/R36)
#define GPIO_LED_K1         6   // IO06, schematic physical pin 21
#define GPIO_LED_K2         5   // IO05, schematic physical pin 20
#define GPIO_LED_K3         4   // IO04, schematic physical pin 19

// UART0 — CH340K USB-C bridge (physical pins 30/31 on the module)
// These are the default UART0 pins on the ESP32-C3-MINI-1; configured in
// sdkconfig.defaults and used by board/console.c (CONFIG_CONSOLE_UART path).
#define GPIO_UART_TX        21  // TXD0
#define GPIO_UART_RX        20  // RXD0

// -----------------------------------------------------------------------------
// INFERRED — resolved by cross-referencing schematic module pad numbers with
// the ESP32-C3-MINI-1 datasheet. Both ADC channels use a single adc_handle
// (ADC1) in the OEM firmware (confirmed from strings), constraining them to
// GPIO0–GPIO4. Continuity testing recommended to confirm before first flash.
// -----------------------------------------------------------------------------

// Chamber NTC thermistor (TH0, module pad 12 = GPIO0 = ADC1_CH0)
// OEM firmware reads this as WAREHOUSE_ADC_CHAN via adc_oneshot.
// GPIO0 is also the IO00/K2 button net — in OEM firmware K2 is a digital
// input with interrupt, while TH0 is read via adc_oneshot (ADC and GPIO can
// coexist if not used simultaneously; the KlipperMCU firmware uses ADC only).
#define GPIO_NTC_CHAMBER    0   // TH0 — INFERRED from module pad 12, continuity test recommended

// PTC heater element NTC thermistor (TH1, module pad 13 = GPIO1 = ADC1_CH1)
// Used internally for PTC overheat detection — NOT exposed to Klipper.
#define GPIO_NTC_PTC        1   // TH1 — INFERRED from module pad 13, continuity test recommended

// PTC relay drive (RLY_MOSFET, module pad 26 = GPIO18)
// Drives Q3 NPN transistor base → MGR-GJ-5-L SSR coil → PTC heater AC switch.
// Klipper configures this as heater_pin via config_digital_out.
// GPIO18 is a general-purpose I/O on the ESP32-C3-MINI-1 (internal flash
// variant does not use GPIO12-17 for SPI, so GPIO18 is free).
#define GPIO_RELAY          18  // RLY_MOSFET — INFERRED from module pad 26, continuity test recommended

#endif // __PANDA_BREATH_PINS_H
