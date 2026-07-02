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
- CGC devices use a Base + Wrapper pattern (e.g., `PSUBase` → `PSU` with logging) and Windows DLLs shipped alongside the wrappers. **CGC is not yet on the shared base** — its streamlining is deferred to the Explorer-side phase (P6); don't "fix" CGC signatures casually, dmmr8/ampr12 plugins depend on them.
- All devices support internal (own thread) and external (caller-managed) housekeeping thread modes.
- Tests: `pytest tests/` (mock-serial based, no hardware needed; `tests/test_test_mode.py` covers simulators + never-auto-simulate).
