# CLAUDE.md

## Project Overview

This repo (`esibd_bs`) is a pip-installable Python device library for ESIBD (Electrospray Ion-Beam Deposition) lab equipment. It contains device classes for Arduino sensors, Pfeiffer vacuum equipment, CGC instruments (PSU, AMPR, pA, SW, ESI), chillers, and syringe pumps.

## Architecture

Two-repo approach:

1. **This repo (`esibd_bs`)** — pip-installable device library. All device classes live here under `src/devices/`. Keep device classes Explorer-agnostic.
2. **ESIBD Explorer fork** — Fork of [ioneater/ESIBD-Explorer](https://github.com/ioneater/ESIBD-Explorer). Contains:
   - **Device plugins** under `esibd/devices/` — thin wrappers that inherit from Explorer's Plugin base class and import device classes from this pip-installed package.
   - **Monitoring dashboard** — a standalone web application (separate entry point, NOT an Explorer plugin). Must survive Explorer crashes. Reads real-time housekeeping data from a shared database (DB choice TBD).

## Development Workflow

- **Office PC**: Code and push to GitHub.
- **Lab PC**: `git pull` on this repo + editable install (`pip install -e .` on this repo only). Changes are live immediately after pulling — no reinstall needed (unless `pyproject.toml` dependencies change). The Explorer fork follows its own installation process separately.

## Key Conventions

- Device classes follow a consistent interface: `connect()`, `disconnect()`, `get_status()`, `start_housekeeping()`, `stop_housekeeping()`, `do_housekeeping_cycle()`.
- **All serial families (Arduino, Pfeiffer, Chiller, Syringe Pump) inherit `src/devices/serial_device.py::SerialDeviceBase`** — the single copy of the constructor contract (`device_id, port, baudrate, timeout, logger, sink, test_mode, hk_thread, thread_lock, hk_interval`), logger setup, housekeeping threading, and the canonical log line. Never re-implement these per class.
- **Canonical log line** (user requirement, aligned columns): `device  port  channel  value unit`, one line per measurement via `log_sample()`; lifecycle events via `log_event()`. Simulated devices are marked `[SIM]` in every line.
- **Telemetry**: `src/devices/telemetry.py` — `TelemetrySink` protocol + stdlib `SQLiteSink` (schema per workspace ADR-0002). Devices accept `sink=`; `log_sample()` writes numeric values to it (`sim` flag set from `test_mode`).
- **Test mode**: explicit `test_mode=True` swaps in plausible simulated values on the same channels with the same log format. **Never auto-simulate on a failed connect** — a failed real connect logs an error, returns False, produces no samples.
- CGC devices use a Base + Wrapper pattern and Windows DLLs shipped alongside the wrappers: `*Base` = pure ctypes wrapper (publishable stand-alone), lab class = `Family(CGCDevice, FamilyBase)` on `src/devices/cgc/cgc_device.py::CGCDevice(DeviceBase)` (canonical log line, sink, hk worker + poke, reconnect, explicit test mode; `_check()` → `CGCStatusError`; opt-in `trace_dll_calls()`). **All six families are migrated (AMPR+PA P6.2, ESI P6.5, PSU/SW/SWHR P6.8).** PSU/SW carry the DLL device index in `dll_port` (renamed from the bases' old `port` attribute — `DeviceBase.port` is the "COM15" log label), SWHR in `stream`. The PSU lab layer talks **mA** for output currents (base API is ampere; notebooks 011-023 rely on the mA semantics). SW/SWHR take `skip_sensors=` for the broken temperature sensors (swA s2, swB s0). Switch-campaign safety tooling (PSUWatchdog + recipe-enforcing ramp helpers, 300 mA / 100 W limits) lives in `src/devices/cgc/campaign.py`; campaign notebook = `debugging/notebooks/025_switch_campaign.ipynb` (SIM=True default). `CGCDevice.call_with_retry(fn, *args)` (P6.10) is the purge-retry net for single calls — locks, calls, purges + retries once on nonzero status (EMI -11/-13/-14 under HV switching); callers must NOT already hold `thread_lock`. The PSU sim models NVM-config working sets: `load_current_config(0)` = standby (all off, 0 V), any other slot arms device + outputs at 10 V / 100 mA (campaign-63 semantics) — required so a simulated config bring-up doesn't read 0 V forever. In test mode the vendor DLL is never loaded; raw DLL exports are real-hardware-only. Don't "fix" CGC signatures casually — dmmr8/ampr12 plugins depend on them (ctor stays positionally compatible: `device_id, com, baudrate`). **AMPR quirk:** the COM-AMPR-12 DLL has ONE implicit communication channel per loaded module (no port handles), so `AMPRBase` instances beyond the first load a private copy of the DLL from `%TEMP%/cgc_private_dlls/` — required for two units in one process; PSU/SW/SWHR DLLs carry a device index per export and don't need this.
- All devices support internal (own thread) and external (caller-managed) housekeeping thread modes.
- Tests: `pytest tests/` (mock-serial based, no hardware needed; `tests/test_test_mode.py` covers simulators + never-auto-simulate).
