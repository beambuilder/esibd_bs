# esibd_bs

Python device-control library for the instruments used on our ESIBD setup.
One package per manufacturer, a common serial/base-device layer underneath,
and per-device wrappers that expose a plain Python API for scripts, notebooks
and the lab's monitoring services.

Status: work in progress. Interfaces still change; devices are added as they
are commissioned.

## Supported devices

- Pfeiffer Vacuum: HiScroll 12, OmniControl 300 + HiPace 300/450,
  OmniControl 200 + HiPace 80, TPG 366, A100 L and A200 L roots pumps
- CGC Instruments: ESI-CTRL, PSU, pA meter, AMPR, switch units
- Lauda: chiller E420S
- Chemyx: syringe pump
- Arduino

## Layout

    src/devices/      device drivers, grouped by manufacturer
    tests/            pytest suite
    debugging/        notebooks and logs from bring-up and diagnostics
    docs/             notes on threading and other cross-cutting topics

## Install

    pip install -e .[dev]

Requires Python 3.8 or newer.

## Tests

    pytest

Hardware-backed tests are skipped unless the device is reachable; the rest run
against the drivers' test mode.

## License

MIT
