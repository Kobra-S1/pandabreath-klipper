# Snapmaker U1 Klipper Fork Heuristics

During the integration of the Panda Breath system on the Snapmaker U1, we discovered that the U1 runs a heavily customized fork of Klipper. This fork imposes stricter duck-typing requirements on `Heater` proxy objects injected via Klipper extras than the official, mainline Klipper repository.

## The Differences

In Mainline Klipper, a generic heater injected into the `heaters` list only strictly requires implementing:
- `set_temp(degrees)`
- `get_temp(eventtime)`

However, the Snapmaker U1's `klippy/extras/heaters.py` intercepts `# Handle extruder heating` and power-loss recovery, unconditionally trying to access methods and attributes on the heater object whenever `SET_HEATER_TEMPERATURE` is called. 

Specifically, the U1 adds the following strict requirements:

### 1. `get_name()`
The U1 calls `heater_name = heater.get_name()` immediately at the start of its `set_temperature` routine. If this method is absent (as it usually is on custom minimal sensors), Klipper throws an `AttributeError` and crashes into an `Internal error` state.

### 2. `short_name` attribute
For printing power-loss recovery, the U1 attempts to serialize the current heater targets via `virtual_sdcard.record_pl_print_temperature_env({heater.short_name: temp})`. If the injected heater object does not have `self.short_name` explicitly assigned during its `__init__`, Klipper will crash.

### 3. `check_busy(eventtime)`
While `check_busy` is theoretically needed in mainline Klipper to support `TEMPERATURE_WAIT`, the U1 explicitly enforces blocking temperatures during active extrusion queues via `self._wait_for_temperature(heater)`. Without `check_busy()`, waiting operations will fault.

## Unified Architecture

The fixes implemented in `panda_breath.py` (adding `get_name()`, `short_name`, and `check_busy()`) fulfill the U1's strict typing requirements. Fortunately, because these methods match the standard `Heater` class methods in `klippy/extras/heaters.py`, adding them does **not** break Mainline Klipper. The current `panda_breath.py` acts as a universal module fully compatible with both platforms.

*(Note: The change from the JSON key `"temp": 45` to `"set_temp": 45` was an undocumented requirement of the stock Panda Breath firmware itself, not Klipper, so it is necessary on both mainline and the U1.)*
