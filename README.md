# pandabreath-klipper

Klipper extras module for the **BIQU Panda Breath** smart chamber heater and air filter. Primary target: **Snapmaker U1**.

---

## What is this?

The [BIQU Panda Breath](https://biqu.equipment/products/biqu-panda-breath-smart-air-filtration-and-heating-system-with-precise-temperature-regulation) is a 300W PTC chamber heater and HEPA/carbon air filter with WiFi control, designed for enclosed 3D printers. It has native Bambu Lab integration but no Klipper support.

This project reverse-engineers its WebSocket API and wraps it in a standard Klipper `extras/` module, exposing the Panda Breath as a `heater_generic` — no custom GCodes, no special macros. Orca Slicer and other tools already know how to set chamber temperature via `SET_HEATER_TEMPERATURE`; this module makes that work.

---

## Status

**Research and protocol documentation phase complete. Klipper integration is functional!**

- [x] Protocol reverse-engineered from firmware strings (v1.0.1, v1.0.2) and embedded JS (v0.0.0 full flash dump)
- [x] Hardware schematic analyzed (ESP32-C3, relay heater, TRIAC fan, NTC thermistors)
- [x] Protocol documented: [docs/protocol.md](docs/protocol.md)
- [x] Klipper extras module (`panda_breath.py`)
- [x] Standalone WebSocket test tool (`test_ws.py`)
- [x] Installation guide / overlay for Snapmaker U1 (`docs/klipper/install.md`)
- [x] Safety-first lifecycle handling (forced off on connect/disconnect/shutdown/end/cancel/error)
- [x] Optional automatic start mapping (filament type via Moonraker metadata and/or bed target ranges)

---

## Integration approach

The module will:

1. Maintain a persistent WebSocket connection to the device at `ws://<ip>/ws`
2. Set `work_mode: 2` (always-on) — the device's native auto mode requires a Bambu MQTT connection, which doesn't exist in a Klipper environment
3. For `TARGET > 0`, send `work_mode`, then `set_temp`, then `work_on: true`
4. For `TARGET = 0`, send `work_on: false`
5. Report `cal_warehouse_temp` (calibrated NTC ADC reading) as the current temperature
6. Reconnect automatically on connection drop and re-send the last target

For firmware V1.0.3, `work_on` must be sent as JSON booleans (`true` / `false`) for reliable behavior.

The device handles all heater duty-cycling and fan speed control internally. The module only tells it to be on or off.

### Safety lifecycle defaults

By default, Panda Breath is forced off at these times:

- Klipper connect / restart
- Klipper disconnect
- Klipper shutdown
- Print complete
- Print cancelled
- Print error

These defaults are intentionally conservative.

### Optional automatic print-start mapping

You can enable automatic targets at print start using filament type and/or bed target maps.

```ini
[panda_breath]
auto_on_print_start: true
auto_off_on_print_end: true
auto_off_on_cancel: true
auto_off_on_error: true

# Mapping strategy: filament_then_bed | filament_only | bed_only
auto_priority: filament_then_bed

# If no map match: keep | off
unknown_filament_action: keep

# Filament mapping (Moonraker metadata filament_type)
filament_map: ABS:50,ASA:60,PETG:0,PLA:0

# Bed target mapping (heater_bed target ranges)
bed_map: 0-60:0,80-110:60

# Moonraker metadata lookup (filament mapping source)
moonraker_url: http://127.0.0.1:7125
metadata_timeout: 1.5
```

Notes:

- Filament mapping uses Moonraker metadata only. If metadata is unavailable, filament mapping is skipped.
- Mapping targets are validated against the configured Panda Breath heater min/max range. Invalid values cause a clear config error.

### `printer.cfg`

```ini
[panda_breath]
host: PandaBreath.local   # or IP address
port: 80

[heater_generic panda_breath]
heater_pin: panda_breath:pwm
sensor_type: panda_breath
control: watermark
max_delta: 0.5
min_temp: 15
max_temp: 80

[verify_heater panda_breath]
check_gain_time: 360
hysteresis: 5
heating_gain: 1

[gcode_macro M141]
description: Set chamber temperature (Panda Breath)
gcode:
    {% set s = params.S|default(0)|float %}
    SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET={s}

[gcode_macro M191]
description: Wait for chamber temperature (Panda Breath)
gcode:
    {% set s = params.S|default(0)|float %}
    M141 S{s}
    {% if s > 0 %}
        TEMPERATURE_WAIT SENSOR="heater_generic panda_breath" MINIMUM={s}
    {% endif %}
```

### KlipperScreen panel (optional)

The repository includes a dedicated KlipperScreen panel at `KlipperScreen/panda_breath.py`.

Install it by linking the panel file into KlipperScreen's panels directory:

```sh
ln -sf ~/pandabreath-klipper/KlipperScreen/panda_breath.py ~/KlipperScreen/panels/panda_breath.py
sudo systemctl restart KlipperScreen
```

Add menu entries so the panel is visible both while idle and during a print. Edit your KlipperScreen config (typically `/home/pi/printer_data/config/KlipperScreen.conf`) and add:

```ini
[menu __main panda_breath]
name: Panda Breath
icon: heater
panel: panda_breath

[menu __print panda_breath]
name: Panda Breath
icon: heater
panel: panda_breath
```

The panel provides two pages:

- Climate: chamber target set/on/off
- Drying: temp + hours controls, material presets (PLA/PETG/ABS/ASA), start/stop, and remaining time

---

## Protocol summary

The device speaks JSON over WebSocket. All messages use a root key identifying the subsystem:

```json
{ "settings": { "work_on": true, "work_mode": 2, "set_temp": 45 } }
{ "settings": { "warehouse_temper": 38.5 } }
```

See [docs/protocol.md](docs/protocol.md) for the full reference.

> No official API documentation exists from BTT. All protocol knowledge is derived from reverse engineering. See [research/](research/) for methodology and raw findings.

---

## Target platform: Snapmaker U1

The Snapmaker U1 runs a modified Klipper + Moonraker stack. The BIQU Panda Breath is officially listed as U1-compatible. The U1 has no built-in active chamber heater — the Panda Breath fills that gap, and this module makes it scriptable.

- Klipper extras path on U1: `/home/lava/klipper/klippy/extras/`
- Community extended firmware (SSH access, opkg): [snapmakeru1-extended-firmware.pages.dev](https://snapmakeru1-extended-firmware.pages.dev)

---

## Research

| File | Contents |
|---|---|
| [research/firmware-analysis.md](research/firmware-analysis.md) | Binary metadata, strings extraction, RTOS tasks, HTTP endpoints, v1.0.1→v1.0.2 diff |
| [research/protocol-from-v0.0.0.md](research/protocol-from-v0.0.0.md) | Definitive protocol reference extracted from embedded JS in v0.0.0 full flash dump |
| [research/hardware-schematic.md](research/hardware-schematic.md) | Schematic analysis: GPIO map, heater/fan circuits, thermistor circuits, power chain |

---

## Device notes

- Firmware V0.0.0 (Aug 2025) is the only confirmed stable release; V1.0.1+ have thermal regression bugs
- Firmware V1.0.3 in the field accepts `set_temp` writes and requires boolean `work_on` writes for reliable on/off control
- WebSocket has no authentication — LAN use only
- Button/UI state changes do **not** push WebSocket messages (confirmed v0.0.0)
- No confirmed state-query command; temperature arrives periodically from the device's internal `temp_task`

---

[![Buy Me A Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/wildtang3nt)

## License

This project (Klipper module and documentation) is MIT licensed.

The BIQU Panda Breath hardware and firmware are © 2025 BIQU, licensed CC-BY-NC-ND-4.0.
