# Changelog

## v0.1.1 — 2026-07-05

Passive update notice (opt-out, cached, zero new deps).

* On a normal run `vram.py` now makes a best-effort check for a newer GitHub release and prints **one** stderr line if the running version is behind (`>> A new version ... is available: vX.Y.Z (you have A.B.C) — <releases URL>`). No auto-update, no nagging, and it never delays or breaks the real command. Pure `urllib` (2 s timeout), fail-silent on offline/timeout/rate-limit/JSON changes.
* Hits GitHub **at most once per 24h** via a small JSON cache under `%LOCALAPPDATA%`/`$XDG_CACHE_HOME`/`~/.cache`; a fresh cache is compared without any network call.
* New opt-out: set `AMD_VRAM_NO_UPDATE_CHECK=1` to disable the check entirely.
* Added a `__version__ = "0.1.1"` constant to `vram.py` (the check compares against it) and `tests/test_update_check.py` (stdlib regression for semver compare, fail-silent, and opt-out; never touches the network), wired into CI.

## v0.1.0 — 2026-07-04

Initial public release.

* `vram.py`: read true GPU VRAM from the display-class registry key
  (`HardwareInformation.qwMemorySize`), working around the
  `Win32_VideoController.AdapterRAM` uint32 4 GB cap
