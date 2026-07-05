# amd-vram-detection

Read the **true** VRAM size of a GPU on Windows from Python — working around the WMI value that silently caps at 4 GB. Single file, stdlib only.

```
> python vram.py
AMD Radeon RX 6600 XT: 8.0 GB (8589934592 bytes, qwMemorySize)
```

## The problem

The standard way to read VRAM without third-party packages is WMI/CIM:

```powershell
Get-CimInstance Win32_VideoController | Select Name, AdapterRAM
```

`Win32_VideoController.AdapterRAM` is a **uint32** — it physically cannot represent more than ~4 GB. Every modern GPU with more VRAM reports 4,293,918,720 bytes (or overflow garbage). This is a [long-documented](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-videocontroller) WMI limitation, not a driver bug.

NVIDIA users can shell out to `nvidia-smi`. **AMD ships no equivalent that is reliably present**, so on AMD machines a Python program asking "how much VRAM does this box have?" gets a wrong answer from every obvious API.

## The workaround

The display driver writes the real 64-bit value into the GPU's *display class* key in the registry:

```
HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\<0000...>
    DriverDesc                          = "AMD Radeon RX 6600 XT"
    HardwareInformation.qwMemorySize    = REG_QWORD, VRAM in bytes
```

Each numbered subkey is one display adapter. `vram.py` enumerates them with `winreg`, matches `DriverDesc`, and reads the QWORD — correct for >4 GB cards. A legacy 32-bit `HardwareInformation.MemorySize` fallback is read (and labelled as possibly capped) when the QWORD is absent, e.g. under very old drivers.

## Installation

There is nothing to install — it's one file, stdlib only (Python ≥ 3.7, Windows). **Copy `vram.py` into your project** and import it, or run it directly. No `pip`, no dependencies.

## Usage

```
python vram.py               # list every display adapter + true VRAM
python vram.py "RX 6600"     # filter by name substring
```

As a library:

```python
from vram import list_display_adapters, get_vram_bytes

get_vram_bytes("RX 6600")     # -> 8589934592
list_display_adapters()       # -> [{"name": ..., "vram_bytes": ..., "vram_gb": ..., "source": ...}]
```

## Limitations

* Windows only (registry). `--help` runs anywhere; everything else needs `winreg`.
* Reads what the *driver* reported at install time; a software/virtual adapter has no size value (reported as such, not guessed).
* Verified on AMD (Adrenalin) hardware. NVIDIA/Intel drivers also write this key, but if you have `nvidia-smi`/NVML available, prefer those on NVIDIA.

Requires Python ≥ 3.7. No dependencies.

## Support

If this project is useful to you, you can support it at [ko-fi.com/casul185](https://ko-fi.com/casul185).

## License

MIT — see [LICENSE](LICENSE).
