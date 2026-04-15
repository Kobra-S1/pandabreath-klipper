# printer.cfg Reference

## Configuration options

=== "Stock firmware"

    ```ini
    [panda_breath]
    firmware: stock
    host: PandaBreath.local   # mDNS hostname or IP address
    port: 80                  # WebSocket port (default: 80)
    ```

    | Option | Type | Default | Description |
    |---|---|---|---|
    | `firmware` | string | `stock` | Transport to use: `stock` or `esphome` |
    | `host` | string | — | **Required.** Hostname or IP of the Panda Breath |
    | `port` | int | `80` | WebSocket port |
    | `auto_on_print_start` | bool | `false` | Enable automatic target selection at print start |
    | `auto_off_on_print_end` | bool | `true` | Force Panda Breath off on print complete |
    | `auto_off_on_cancel` | bool | `true` | Force Panda Breath off on print cancel |
    | `auto_off_on_error` | bool | `true` | Force Panda Breath off on print error |
    | `auto_priority` | string | `filament_then_bed` | Auto target strategy: `filament_then_bed`, `filament_only`, `bed_only` |
    | `unknown_filament_action` | string | `keep` | No-match behavior: `keep` or `off` |
    | `filament_map` | string | empty | Filament mapping: `KEY:VALUE,KEY2:VALUE2` |
    | `bed_map` | string | empty | Bed mapping: `MIN-MAX:VALUE,...` |
    | `moonraker_url` | string | `http://127.0.0.1:7125` | Moonraker base URL for filament metadata |
    | `metadata_timeout` | float | `1.5` | Moonraker metadata timeout (seconds) |

=== "ESPHome firmware"

    ```ini
    [panda_breath]
    firmware: esphome
    mqtt_broker: 192.168.1.x     # IP of your MQTT broker
    mqtt_port: 1883              # MQTT port (default: 1883)
    mqtt_topic_prefix: panda-breath   # ESPHome topic prefix (default: panda-breath)
    ```

    | Option | Type | Default | Description |
    |---|---|---|---|
    | `firmware` | string | `stock` | Transport to use: `stock` or `esphome` |
    | `mqtt_broker` | string | — | **Required.** IP address of the MQTT broker |
    | `mqtt_port` | int | `1883` | MQTT broker port |
    | `mqtt_topic_prefix` | string | `panda-breath` | Must match `topic_prefix` in ESPHome YAML |

You still need a standard `[heater_generic panda_breath]` section and optionally `[verify_heater panda_breath]` in `printer.cfg`.

---

## Behaviour

=== "Stock firmware"

    | Condition | Action |
    |---|---|
    | Klipper sets `TARGET > 0` | Sends `{"settings": {"work_mode": 2}}`, then `{"settings": {"set_temp": TARGET}}`, then `{"settings": {"work_on": true}}` |
    | Klipper sets `TARGET = 0` | Sends `{"settings": {"work_on": false}}` |
    | `cal_warehouse_temp` received | Reported as current temperature (preferred) |
    | `warehouse_temper` received | Reported as current temperature (fallback) |
    | WebSocket drops | Reconnects; resends last command |

    On firmware V1.0.3, `work_on` control is reliable when sent as JSON booleans (`true` / `false`).

=== "ESPHome firmware"

    | Condition | Action |
    |---|---|
    | Klipper sets `TARGET > 0` | Publishes `TARGET` to `…/climate/chamber/target_temperature/set` and `heat` to `…/climate/chamber/mode/set` |
    | Klipper sets `TARGET = 0` | Publishes `off` to `…/climate/chamber/mode/set` |
    | `…/sensor/chamber_temperature/state` received | Reported as current temperature |
    | MQTT connection drops | Reconnects; republishes last command |

The device manages all heater duty-cycling and fan speed control internally. The module only tells it to be on or off and at what target temperature.

---

## Safety lifecycle defaults

By default, the module forces Panda Breath off on:

- Klipper connect/restart
- Klipper disconnect
- Klipper shutdown
- Print complete
- Print cancelled
- Print error

The print-end/cancel/error behavior is controlled by:

- `auto_off_on_print_end`
- `auto_off_on_cancel`
- `auto_off_on_error`

---

## Automatic print-start mapping

When `auto_on_print_start: true`, the module can choose a start target from maps.

Order is controlled by `auto_priority`:

- `filament_then_bed`
- `filament_only`
- `bed_only`

Filament mapping uses Moonraker metadata (`filament_type`) only. If metadata is unavailable, filament mapping is skipped.

Filament map format:

```ini
filament_map: ABS:50,ASA:60,PETG:0,PLA:0
```

Bed map format:

```ini
bed_map: 0-60:0,80-110:60
```

If no map matches, `unknown_filament_action` decides whether to keep the current target or force off.

All non-zero mapping targets are validated against `[heater_generic panda_breath]` min/max. Out-of-range values raise a clear startup config error.

Print-start timing flow with mapping enabled:

1. Print enters `printing` state.
2. Module selects a chamber target from `filament_map` and/or `bed_map`.
3. Module applies that target to `heater_generic panda_breath`.
4. Your start macro runs a chamber wait (`TEMPERATURE_WAIT`) before continuing.

If your slicer also sends a chamber target, the last command wins. Prefer one source of truth (mapping or slicer-set value) and then do a single wait step.

---

## Sample macros

### Wait for mapped chamber target (recommended)

```ini
[gcode_macro PB_WAIT_FOR_MAPPED_CHAMBER]
description: Wait for Panda Breath only if a non-zero target is active
gcode:
    # Small settle delay so print-start auto mapping can apply target first
    {% set settle_s = params.SETTLE|default(2)|int %}
    {% if settle_s > 0 %}
        G4 S{settle_s}
    {% endif %}

    {% set t = printer["heater_generic panda_breath"].target|float %}
    {% if t > 0 %}
        RESPOND MSG="Panda Breath preheat wait: target={t|round(1)}C"
        TEMPERATURE_WAIT SENSOR="heater_generic panda_breath" MINIMUM={t}
    {% else %}
        RESPOND MSG="Panda Breath preheat wait skipped (target=0)"
    {% endif %}
```

Use in your `PRINT_START` after your initial heat commands:

```ini
[gcode_macro PRINT_START]
gcode:
    # ... existing start sequence (bed/nozzle heat, homing, etc.)
    PB_WAIT_FOR_MAPPED_CHAMBER SETTLE=2
    # ... continue with purge and print
```

!!! tip "If Klipper reports a template parse error"
    Use Jinja filters in macro expressions, not Python format specifiers.
    
    Correct:
    
    ```ini
    RESPOND MSG="Panda Breath preheat wait: target={t|round(1)}C"
    ```
    
    Incorrect (will fail with `expected token 'end of print statement', got ':'`):
    
    ```ini
    RESPOND MSG="Panda Breath preheat wait: target={t:.1f}C"
    ```
    
    After fixing `printer.cfg`, run `RESTART` in Klipper.

### Pre-heat chamber before print

```ini
[gcode_macro PREHEAT_CHAMBER]
description: Pre-heat chamber to target and wait
gcode:
    {% set TARGET = params.TEMP|default(45)|int %}
    SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET={TARGET}
    TEMPERATURE_WAIT SENSOR="heater_generic panda_breath" MINIMUM={TARGET - 2}
    M117 Chamber ready
```

Usage from slicer start GCode:
```gcode
PREHEAT_CHAMBER TEMP=45
```

### Filament drying

```ini
[gcode_macro DRY_FILAMENT]
description: Run filament drying at target temp
gcode:
    {% set TEMP = params.TEMP|default(55)|int %}
    {% set HOURS = params.HOURS|default(6)|int %}
    SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET={TEMP}
    TEMPERATURE_WAIT SENSOR="heater_generic panda_breath" MINIMUM={TEMP - 2}
    M117 Drying filament at {TEMP}C for {HOURS}h
```

!!! note
    The Panda Breath's built-in filament drying mode (with countdown timer) uses `work_mode: 3` internally. Via Klipper, the simplest approach is to use always-on mode and let a macro or timer handle duration.

### Chamber cooldown / print end

```ini
[gcode_macro CHAMBER_OFF]
description: Turn off Panda Breath
gcode:
    SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET=0
```

---

## Orca Slicer integration

Orca Slicer sets chamber temperature automatically based on the filament profile. Set the **Chamber temperature** field in your filament profile. Orca will emit:

```gcode
SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET=<temp>
```

at the start of prints that require chamber heating, and `TARGET=0` at the end. No custom slicer GCode is needed.

---

## Safety notes

- The Panda Breath reaches up to 60°C chamber temperature
- **Stock firmware (v0.0.0):** PTC thermal runaway detection is present in the device firmware. v1.0.2 removed this — use v0.0.0 only
- **ESPHome firmware:** thermal runaway protection is implemented directly in the ESPHome config (`esphome/panda_breath.yaml`) and does not depend on BTT firmware
- The stock WebSocket has no authentication — LAN use only
- Always disconnect mains AC before servicing the device
