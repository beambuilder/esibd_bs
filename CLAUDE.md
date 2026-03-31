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
- CGC devices use a Base + Wrapper pattern (e.g., `PSUBase` → `PSU` with logging).
- CGC devices depend on Windows DLLs shipped alongside the Python wrappers.
- Serial devices (Arduino, Pfeiffer, Chiller, Syringe Pump) use pyserial.
- All devices support internal (own thread) and external (caller-managed) housekeeping thread modes.
