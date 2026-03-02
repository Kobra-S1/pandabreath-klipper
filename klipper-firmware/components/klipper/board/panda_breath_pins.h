#ifndef __PANDA_BREATH_PINS_H
#define __PANDA_BREATH_PINS_H

// =============================================================================
// Panda Breath (ESP32-C3-MINI-1-H4X) GPIO assignments
//
// Sources: hardware schematic reverse-engineered from real device.
// The schematic uses IC *package* pin numbers, not GPIO numbers.
// GPIO numbers confirmed via IO-net labels in the schematic are marked CONFIRMED.
// GPIO numbers for TH0, TH1, and RLY_MOSFET are UNVERIFIED — determine by
// continuity testing from PCB pad to ESP32-C3-MINI castellations before use.
// See research/hardware-schematic.md for full schematic analysis.
// =============================================================================

// -----------------------------------------------------------------------------
// CONFIRMED — derived from schematic IO net labels (e.g. IO03, IO07)
// -----------------------------------------------------------------------------

// TRIAC gate — FAN speed control via phase-angle (BT136-800E via MOC3021S + Q2)
#define GPIO_FAN            3   // IO03, schematic physical pin 7

// AC zero-crossing detector output (TLP785 optocoupler)
// Used to synchronise TRIAC phase-angle firing in fan.c
// NOTE: IO07 is shared with the K1 button net — K1 is unavailable unless
//       GPIO0 also carries ZERO (verify with oscilloscope before reassigning)
#define GPIO_ZERO_CROSS     7   // IO07/ZERO, schematic physical pin 22

// LED-backlit tactile buttons (K6-6140S01)
#define GPIO_K2             0   // IO00, schematic physical pin 15 (also ZERO candidate)
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
// UNVERIFIED — schematic gives IC package pin number only.
// !! DO NOT FLASH until confirmed by continuity testing !!
// Map physical package pin → module castellation → GPIO using the
// ESP32-C3-MINI-1 datasheet module pad layout.
// -----------------------------------------------------------------------------

// Chamber NTC thermistor (TH0, schematic physical pin 12)
// Must be an ADC-capable pin. ADC1 channels on ESP32-C3: GPIO0–GPIO4.
// GPIO1 (ADC1_CH1) is the only ADC pin not otherwise assigned — best guess.
#define GPIO_NTC_CHAMBER    1   // TH0 — !! UNVERIFIED, continuity test required !!

// PTC heater element NTC thermistor (TH1, schematic physical pin 13)
// Used internally for PTC overheat detection — NOT exposed to Klipper.
// No confirmed ADC-capable candidate; placeholder only.
#define GPIO_NTC_PTC        8   // TH1 — !! UNVERIFIED, almost certainly wrong !!

// PTC relay drive (RLY_MOSFET, schematic physical pin 26)
// Drives Q3 NPN transistor base → MGR-GJ-5-L SSR coil → PTC heater AC switch.
// Klipper configures this as heater_pin via config_digital_out.
// IO10 is "TBD" in the schematic — plausible candidate for pin 26 area.
#define GPIO_RELAY          10  // RLY_MOSFET — !! UNVERIFIED, continuity test required !!

#endif // __PANDA_BREATH_PINS_H
