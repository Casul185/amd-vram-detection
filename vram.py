#!/usr/bin/env python
"""Read the TRUE VRAM size of a GPU on Windows — working around the WMI 4 GB cap.

The problem
-----------
The obvious way to read VRAM in Python is WMI/CIM:

    Get-CimInstance Win32_VideoController | Select AdapterRAM

But ``Win32_VideoController.AdapterRAM`` is a **uint32**, so it saturates at
4,293,918,720 bytes (~4 GB). Every modern GPU with more than 4 GB of VRAM —
an RX 6600 XT with 8 GB, an RX 7900 XTX with 24 GB — reports 4 GB (or garbage).
NVIDIA users can shell out to ``nvidia-smi``/NVML; AMD offers no equivalent
that is reliably installed, so on AMD boxes WMI simply lies to you.

The workaround
--------------
The display driver writes the real value to the GPU's *display class* registry
key as a **QWORD**:

    HKLM\\SYSTEM\\CurrentControlSet\\Control\\Class\\
        {4d36e968-e325-11ce-bfc1-08002be10318}\\<0000, 0001, ...>\\
            HardwareInformation.qwMemorySize   (REG_QWORD, bytes)

Each numbered subkey is one display adapter; ``DriverDesc`` inside it is the
human GPU name. This module enumerates those subkeys and returns the 64-bit
value, which is correct for >4 GB cards. Verified on AMD (Adrenalin) hardware;
the key is written by NVIDIA/Intel drivers as well, but older drivers may only
provide the legacy 32-bit ``HardwareInformation.MemorySize`` value instead
(also read here as a fallback).

Stdlib only (winreg). Windows only — importing the registry functions on
another OS raises a clear error, but ``--help`` works anywhere.

Usage
-----
    python vram.py              # list every display adapter + true VRAM
    python vram.py "RX 6600"    # only adapters whose name contains the string

Or as a library:

    from vram import list_display_adapters, get_vram_bytes
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

__version__ = "0.1.1"

_DISPLAY_CLASS = (
    r"SYSTEM\CurrentControlSet\Control\Class"
    r"\{4d36e968-e325-11ce-bfc1-08002be10318}"
)


def _to_bytes_int(value) -> int:
    """Normalise a registry value (int, or raw little-endian bytes on some
    drivers/Python versions) to an int byte count. 0 on anything unusable."""
    if isinstance(value, int):
        return value
    if isinstance(value, bytes):
        try:
            return int.from_bytes(value, "little")
        except (ValueError, OverflowError):
            return 0
    return 0


def list_display_adapters() -> list[dict]:
    """Enumerate display adapters from the display-class registry key.

    Returns a list of dicts:
        {"name": str, "vram_bytes": int, "vram_gb": float, "source": str}

    ``source`` is "qwMemorySize" (the 64-bit value; trustworthy) or
    "MemorySize" (legacy 32-bit fallback; may itself be capped) or "" when
    no size value was present. Software/virtual adapters usually have no
    size value at all.
    """
    import winreg  # deferred: lets --help run on non-Windows

    adapters: list[dict] = []
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _DISPLAY_CLASS) as root:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            if not sub.isdigit():   # skip "Properties" etc.
                continue
            try:
                with winreg.OpenKey(root, sub) as k:
                    try:
                        name = str(winreg.QueryValueEx(k, "DriverDesc")[0])
                    except OSError:
                        continue
                    vram = 0
                    source = ""
                    for value_name, src in (
                        ("HardwareInformation.qwMemorySize", "qwMemorySize"),
                        ("HardwareInformation.MemorySize", "MemorySize"),
                    ):
                        try:
                            raw = winreg.QueryValueEx(k, value_name)[0]
                        except OSError:
                            continue
                        vram = _to_bytes_int(raw)
                        if vram > 0:
                            source = src
                            break
                    adapters.append({
                        "name": name,
                        "vram_bytes": vram,
                        "vram_gb": round(vram / (1024 ** 3), 1),
                        "source": source,
                    })
            except OSError:
                continue
    return adapters


def get_vram_bytes(gpu_name: str | None = None) -> int:
    """Return the VRAM byte count of the first adapter matching ``gpu_name``
    (case-insensitive substring), or of the largest adapter when None.
    Returns 0 if nothing matched or no size value was found."""
    adapters = list_display_adapters()
    if gpu_name:
        want = gpu_name.lower()
        adapters = [a for a in adapters if want in a["name"].lower()]
    if not adapters:
        return 0
    return max(a["vram_bytes"] for a in adapters)


# ---------------------------------------------------------------------------
# Passive startup update check (best-effort, fail-silent, cached 24h).
#
# On a normal run this makes at most one 2-second GET to the public GitHub
# releases endpoint and prints ONE stderr line if a newer release exists. It
# never auto-updates and never nags; any failure is silent. Pure stdlib.
# ---------------------------------------------------------------------------
_NAME = "amd-vram-detection"
_REPO = "casul185/amd-vram-detection"
_ENV_OPTOUT = "AMD_VRAM_NO_UPDATE_CHECK"
_LATEST_API = "https://api.github.com/repos/%s/releases/latest"
_RELEASES_PAGE = "https://github.com/%s/releases/latest"
_UA_CHECK = "amd-vram-detection-update-check"
_CACHE_TTL = 24 * 60 * 60
_CHECK_TIMEOUT = 2.0


def _optout() -> bool:
    val = os.environ.get(_ENV_OPTOUT, "")
    return bool(val) and val.strip().lower() not in ("0", "false")


def _cache_file() -> str:
    base = (os.environ.get("LOCALAPPDATA")
            or os.environ.get("XDG_CACHE_HOME")
            or os.path.expanduser("~/.cache"))
    d = os.path.join(base, _NAME)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "update_check.json")


def _read_cache() -> dict:
    try:
        with open(_cache_file(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_cache(now: float, latest: str | None) -> None:
    try:
        with open(_cache_file(), "w", encoding="utf-8") as fh:
            json.dump({"last_check_epoch": now, "latest_version": latest}, fh)
    except Exception:
        pass


def _strip_v(s) -> str:
    s = str(s or "").strip()
    return s[1:] if s[:1] in ("v", "V") else s


def _parse_version(s) -> tuple | None:
    """Parse 'MAJOR.MINOR.PATCH' into an int tuple; ignore any pre-release/build
    suffix. Return None on anything malformed (never raises)."""
    try:
        s = _strip_v(s)
        for sep in ("-", "+", " "):
            if sep in s:
                s = s.split(sep, 1)[0]
        if not s:
            return None
        out = []
        for part in s.split("."):
            if not part.isdigit():
                return None
            out.append(int(part))
        return tuple(out) if out else None
    except Exception:
        return None


def _is_newer(remote: str, local: str) -> bool:
    r = _parse_version(remote)
    lo = _parse_version(local)
    if r is None or lo is None:
        return False
    return r > lo


def _fetch_latest_tag(url: str, timeout: float) -> str | None:
    """Best-effort GET of releases/latest; returns the raw tag_name or None."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA_CHECK})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("tag_name")


def notify_if_update_available(current: str = __version__, repo: str = _REPO) -> None:
    """Print ONE stderr line if a newer release exists. Fail-silent on all
    errors; hits the network at most once per 24h; honors AMD_VRAM_NO_UPDATE_CHECK."""
    try:
        if _optout():
            return
        now = time.time()
        cached = _read_cache()
        latest = cached.get("latest_version")
        fresh = (now - float(cached.get("last_check_epoch", 0) or 0)) < _CACHE_TTL
        if not fresh:
            fetched = None
            try:
                raw = _fetch_latest_tag(_LATEST_API % repo, _CHECK_TIMEOUT)
                fetched = _strip_v(raw) if raw else None
            except Exception:
                fetched = None
            if fetched:
                latest = fetched
            _write_cache(now, latest)
        if latest and _is_newer(latest, _strip_v(current)):
            sys.stderr.write(
                f">> A new version of {_NAME} is available: v{_strip_v(latest)} "
                f"(you have {_strip_v(current)}) — {_RELEASES_PAGE % repo}\n"
            )
    except Exception:
        return


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    notify_if_update_available(__version__)
    if sys.platform != "win32":
        print("vram.py reads the Windows registry and only runs on Windows.")
        return 1
    name_filter = argv[0] if argv else None

    adapters = list_display_adapters()
    if name_filter:
        want = name_filter.lower()
        adapters = [a for a in adapters if want in a["name"].lower()]
    if not adapters:
        print("no matching display adapters found")
        return 1

    for a in adapters:
        if a["vram_bytes"] > 0:
            note = "" if a["source"] == "qwMemorySize" else \
                "  (legacy 32-bit value — may be capped)"
            print(f"{a['name']}: {a['vram_gb']} GB "
                  f"({a['vram_bytes']} bytes, {a['source']}){note}")
        else:
            print(f"{a['name']}: no VRAM size value in registry "
                  "(software/virtual adapter?)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
