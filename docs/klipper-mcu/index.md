# KlipperMCU Firmware

A third alternative to the OEM and ESPHome paths: replace the Panda Breath's ESP32-C3 firmware with a custom [ESP-IDF](https://idf.espressif.com/) build that speaks the native **Klipper MCU binary protocol** over USB serial (via the onboard CH340K bridge).

!!! warning "GPIO verification required before flashing"
    Three GPIO pin assignments in `klipper-firmware/components/klipper/board/panda_breath_pins.h` are unconfirmed placeholders. The schematic gives physical IC package pin numbers, not GPIO numbers. **Do not flash until these are resolved** — wrong values risk driving the relay or NTC ADC on incorrect pins. See [Unconfirmed GPIO pins](#unconfirmed-gpio-pins) below.

!!! tip "No `panda_breath.py` needed"
    With this path, Klipper connects to the Panda Breath directly as a native `[mcu panda_breath]`. No Python extras module, no MQTT broker, no WiFi required — just a USB cable.

---

## Why KlipperMCU?

| Concern | OEM firmware | ESPHome | KlipperMCU |
|---|---|---|---|
| Thermal runaway | Present in v0.0.0; **removed in v1.0.2** | Configurable | **Klipper's own `verify_heater`** |
| PID control | Device-managed | ESPHome bang-bang | **Klipper PID — fully tunable** |
| Klipper extras module | Required | Required | **Not needed** |
| MQTT broker | Not needed | Required | Not needed |
| WiFi | Required | Optional (MQTT) | **Not needed** |
| Transport | WebSocket (WiFi) | MQTT (WiFi) | **USB serial** |
| Fan speed | Device-managed | Configurable | Internal firmware — follows heater relay |
| OTA updates | BTT releases only | ESPHome OTA | Serial flash (USB) |

The primary advantages are simplicity and reliability: a single USB cable replaces WiFi dependency and MQTT infrastructure, and Klipper's native PID and thermal safety apply directly without any glue code.

---

## How it works

The custom firmware (`klipper-firmware/`) is an ESP-IDF 5.x project that compiles the [Klipper MCU C core](https://github.com/Klipper3d/klipper) (the same code that runs on printer mainboards) with a Panda Breath-specific board HAL.

```
Klipper host (U1)
      │
      │  USB-C cable
      ▼
  CH340K (USB-to-serial)
      │
      │  UART0 @ 250000 baud
      ▼
  ESP32-C3 — klipper-firmware
      ├── Klipper MCU binary protocol (HDLC framing)
      ├── NTC chamber temperature → Klipper ADC
      ├── PTC relay → Klipper digital_out (heater_pin)
      ├── TRIAC fan → internal FreeRTOS task (not visible to Klipper)
      └── Buttons / LEDs → Klipper GPIOs
```

**Fan control** is handled entirely inside the firmware: a FreeRTOS task watches the relay GPIO that Klipper sets, and drives the TRIAC via a zero-crossing ISR and phase-angle timer. Klipper never sees the fans — it only sees the relay (heater pin) and temperature sensor.

---

## Hardware mapping

| Hardware | GPIO | Klipper reference | Notes |
|---|---|---|---|
| Chamber NTC thermistor (TH0) | `GPIO1` ⚠ | `panda_breath:gpio1` | **Unconfirmed** — physical IC pin 12 |
| PTC element NTC (TH1) | `GPIO8` ⚠ | Internal only | **Unconfirmed** — not exposed to Klipper |
| PTC heater relay (RLY_MOSFET) | `GPIO10` ⚠ | `panda_breath:gpio10` | **Unconfirmed** — physical IC pin 26 |
| Fan TRIAC gate (IO03) | `GPIO3` ✓ | Internal only | Confirmed from schematic IO label |
| Zero-crossing detector (IO07) | `GPIO7` ✓ | Internal only | Confirmed from schematic IO label |
| K2 button (IO00) | `GPIO0` ✓ | `panda_breath:gpio0` | Confirmed |
| K3 button (IO02) | `GPIO2` ✓ | `panda_breath:gpio2` | Confirmed |
| K1-LED (IO06) | `GPIO6` ✓ | `panda_breath:gpio6` | Confirmed |
| K2-LED (IO05) | `GPIO5` ✓ | `panda_breath:gpio5` | Confirmed |
| K3-LED (IO04) | `GPIO4` ✓ | `panda_breath:gpio4` | Confirmed |
| UART0 TX | `GPIO21` ✓ | — | CH340K bridge, confirmed |
| UART0 RX | `GPIO20` ✓ | — | CH340K bridge, confirmed |

### Unconfirmed GPIO pins

Three pins require hardware continuity testing before first flash:

| Pin name | Placeholder GPIO | Physical IC pin | How to verify |
|---|---|---|---|
| `GPIO_NTC_CHAMBER` (TH0) | `GPIO1` | 12 | Continuity from TH0 PCB pad to ESP32-C3 module castellation |
| `GPIO_NTC_PTC` (TH1) | `GPIO8` | 13 | Continuity from TH1 PCB pad to module castellation |
| `GPIO_RELAY` (RLY_MOSFET) | `GPIO10` | 26 | Continuity from RLY_MOSFET pad to module castellation |

Edit `klipper-firmware/components/klipper/board/panda_breath_pins.h` once values are confirmed.

!!! note "GPIO7 / K1 button conflict"
    GPIO7 is dedicated to the TRIAC zero-crossing interrupt. The K1 button (also on GPIO7 in the OEM schematic) is unavailable unless GPIO0 also carries the zero-crossing signal — verify with an oscilloscope before reassigning.

---

## Build

**Prerequisites:** [ESP-IDF v5.x](https://docs.espressif.com/projects/esp-idf/en/stable/esp32c3/get-started/index.html) installed and activated (`idf.py` on `PATH`).

The Klipper source is included as a git submodule. Initialise it first:

```sh
cd klipper-firmware
git submodule update --init --recursive
```

Build:

```sh
idf.py set-target esp32c3
idf.py build
```

A successful build produces:
- `build/panda_breath.bin` — the firmware image
- `build/klipper/klipper.dict` — the Klipper command dictionary (required by the host)

---

## Flash

Connect the Panda Breath via USB-C. The CH340K bridge will enumerate as `/dev/ttyUSBx` on Linux or `/dev/cu.wchusbserial*` on macOS.

```sh
idf.py -p /dev/cu.wchusbserial* flash
```

Copy the command dictionary to the Klipper host:

```sh
scp build/klipper/klipper.dict lava@<u1-ip>:/home/lava/klipper/
```

The Klipper host needs this file to decode the MCU protocol. Specify its path in `printer.cfg` (see below).

---

## `printer.cfg`

```ini
[mcu panda_breath]
serial: /dev/ttyUSB0        # adjust port — check: ls /dev/ttyUSB*
baud: 250000

[heater_generic chamber]
heater_pin: panda_breath:gpio10          # placeholder — verify GPIO_RELAY
sensor_type: NTC 100K beta 3950
sensor_pin: panda_breath:gpio1           # placeholder — verify GPIO_NTC_CHAMBER
control: pid
pid_kp: 10
pid_ki: 0.1
pid_kd: 100
min_temp: 0
max_temp: 60

[verify_heater chamber]
max_error: 200
check_gain_time: 300
hysteresis: 5
heating_gain: 1
```

!!! tip "PID tuning"
    After hardware verification, run Klipper's built-in PID calibration:
    ```
    PID_CALIBRATE HEATER=chamber TARGET=40
    ```
    Replace the placeholder `pid_kp/ki/kd` values with the output.

---

## Differences from the Python extras paths

The KlipperMCU path makes the Panda Breath look like any other Klipper MCU (printer mainboard). This means:

- `[heater_generic chamber]` is configured directly in `printer.cfg` — no `[panda_breath]` section
- `panda_breath.py` is **not needed** and should not be loaded
- Klipper's own PID, `verify_heater`, and thermal safety apply directly
- The device must be connected via USB — WiFi is not used at runtime

The fan is not visible to Klipper. It operates autonomously: active at 40% phase angle while the relay is on, then holds at 25% for a 60-second cooldown after the relay goes low.

---

## Recovery

If something goes wrong, the original v0.0.0 OEM firmware can be restored from the full flash dump included in the repository:

```sh
esptool.py --chip esp32c3 \
  --port /dev/cu.wchusbserial* \
  --baud 460800 \
  write-flash 0x00000 Panda_Breath/Firmware/0.0.0/0.0.0.0_clean.bin
```

This is a complete flash write — it restores the bootloader, partition table, application, and clears NVS (WiFi credentials will need to be re-entered).
