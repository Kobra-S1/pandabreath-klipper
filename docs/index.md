# pandabreath-klipper

Klipper extras module for the **BIQU Panda Breath** smart chamber heater and air filter.
Primary target: **Snapmaker U1**.

!!! tip "Status: Three integration paths implemented — hardware testing in progress"
    `panda_breath.py` (WebSocket/MQTT) is ready to deploy — copy the file and restart Klipper. Alternatively, the KlipperMCU firmware (`klipper-firmware/`) replaces the OEM firmware entirely and makes the device a native Klipper MCU over USB, with no extras module needed.

---

## What is this?

The [BIQU Panda Breath](https://biqu.equipment/products/biqu-panda-breath-smart-air-filtration-and-heating-system-with-precise-temperature-regulation) is a 300W PTC chamber heater and HEPA/carbon air filter with WiFi control, designed for enclosed 3D printers. It integrates natively with Bambu Lab printers but has **no Klipper support**.

This project provides a Klipper `extras/` module that exposes the Panda Breath as a standard `heater_generic`. No custom GCodes, no special macros — Orca Slicer and other tools already know how to set chamber temperature via `SET_HEATER_TEMPERATURE`, and this module makes that work.

Three integration paths are supported:

| Path | Device firmware | Transport | Klipper interface | Notes |
|---|---|---|---|---|
| **Stock** | OEM v0.0.0 | WebSocket JSON | `extras/` module | Minimal risk; keep original firmware |
| **ESPHome** | ESPHome (reflash) | MQTT | `extras/` module | Better reliability; restores thermal runaway protection |
| **KlipperMCU** | Custom ESP-IDF (reflash) | USB serial | Native `[mcu]` | No extras module; Klipper PID and safety apply directly |

The Stock and ESPHome paths use `panda_breath.py` and are identical from the GCode side. The KlipperMCU path skips the extras module entirely — the device appears as a native MCU.

---

## Progress

- [x] Protocol reverse-engineered from firmware strings (v1.0.1, v1.0.2) and embedded JS (v0.0.0 full flash dump)
- [x] Hardware schematic analyzed (ESP32-C3, relay heater, TRIAC fan, NTC thermistors)
- [x] Protocol documented — see [Protocol](protocol.md)
- [x] Klipper extras module (`panda_breath.py`) — stock WebSocket + ESPHome MQTT, stdlib only
- [x] ESPHome configuration (`esphome/panda_breath.yaml`) — GPIO verification pending on hardware
- [x] KlipperMCU firmware (`klipper-firmware/`) — custom ESP-IDF firmware, native Klipper MCU protocol over USB
- [ ] Standalone WebSocket test tool (`test_ws.py`)
- [ ] Hardware validation on Snapmaker U1
- [ ] GPIO pin mapping verified on real hardware (all three paths blocked on TH0, TH1, RLY_MOSFET)

---

## Quick start

=== "Stock firmware (OEM v0.0.0)"

    ```ini
    [panda_breath]
    firmware: stock
    host: PandaBreath.local   # or IP address
    port: 80
    ```

    Copy `panda_breath.py` to `/home/lava/klipper/klippy/extras/` and restart Klipper. No other install steps — the module uses Python standard library only.

    See [Install on U1](klipper/install.md) for the full procedure.

=== "ESPHome firmware"

    ```ini
    [panda_breath]
    firmware: esphome
    mqtt_broker: 192.168.1.x
    mqtt_port: 1883
    mqtt_topic_prefix: panda-breath
    ```

    Copy `panda_breath.py` to `/home/lava/klipper/klippy/extras/` and restart Klipper. Requires a local MQTT broker and ESPHome firmware flashed to the device.

    See [ESPHome Firmware](esphome/index.md) for the full procedure.

=== "KlipperMCU firmware (USB)"

    ```ini
    [mcu panda_breath]
    serial: /dev/ttyUSB0        # adjust port

    [heater_generic chamber]
    heater_pin: panda_breath:gpio10      # placeholder — verify GPIO_RELAY
    sensor_type: NTC 100K beta 3950
    sensor_pin: panda_breath:gpio1       # placeholder — verify GPIO_NTC_CHAMBER
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

    Connect via USB-C cable. No `panda_breath.py` needed — Klipper controls the device directly as a native MCU. Requires building and flashing the custom ESP-IDF firmware first.

    See [KlipperMCU Firmware](klipper-mcu/index.md) for build and flash steps.

---

## Target platform: Snapmaker U1

The Snapmaker U1 runs a modified Klipper + Moonraker stack. The BIQU Panda Breath is officially listed as U1-compatible. The U1 has no built-in active chamber heater — the Panda Breath fills that gap, and this module makes it scriptable.

- Klipper extras path on U1: `/home/lava/klipper/klippy/extras/`
- Community extended firmware: [snapmakeru1-extended-firmware.pages.dev](https://snapmakeru1-extended-firmware.pages.dev)

---

## Quick links

| Topic | Page |
|---|---|
| Klipper module architecture (Stock/ESPHome) | [Klipper Integration](klipper/index.md) |
| Install on Snapmaker U1 | [Install on U1](klipper/install.md) |
| `printer.cfg` reference (Stock/ESPHome) | [printer.cfg Reference](klipper/printer-cfg.md) |
| ESPHome firmware (reflash alternative) | [ESPHome](esphome/index.md) |
| KlipperMCU firmware (native MCU, USB) | [KlipperMCU](klipper-mcu/index.md) |
| Multi-instance bridging (KlipperMCU) | [Klipper Router](https://github.com/paxx12/klipper-router) |
| WebSocket API reference | [Protocol](protocol.md) |
| Hardware schematic analysis | [Hardware](hardware.md) |
| Firmware binary analysis | [Firmware](firmware.md) |
| How the protocol was reverse-engineered | [Research Methodology](research/methodology.md) |

---

## Device notes

- Firmware V0.0.0 (Aug 2025) is the only confirmed stable OEM release; V1.0.1+ have thermal regression bugs — see [Firmware](firmware.md)
- V1.0.2 silently removed PTC thermal runaway detection — the ESPHome path restores this
- WebSocket has no authentication — LAN use only
- Button/UI state changes do **not** push WebSocket messages (confirmed v0.0.0)
- No confirmed state-query command; temperature arrives periodically from the device's internal `temp_task`

---

[![Buy Me A Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/wildtang3nt)

*All protocol knowledge is derived from reverse engineering. No official API documentation exists from BTT. See [Research Methodology](research/methodology.md) for full provenance.*
