# Changelog

## v0.1.0 — 2026-07-04

Initial public release.

* `vram.py`: read true GPU VRAM from the display-class registry key
  (`HardwareInformation.qwMemorySize`), working around the
  `Win32_VideoController.AdapterRAM` uint32 4 GB cap
