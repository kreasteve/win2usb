# win2usb

**Create bootable Windows USB drives from ISO files — on macOS and Linux.**

---

## Why?

Making a Windows USB on macOS or Linux is more painful than it should be:

- **Rufus** is Windows-only.
- **balenaEtcher** doesn't handle Windows ISOs correctly — the result often won't boot.
- Doing it manually means juggling `diskutil`, `hdiutil`, `wimlib-imagex`, and `rsync`, while also working around the FAT32 4 GB file size limit that trips up every Windows 11 ISO.

`win2usb` automates the entire process in a single command.

---

## Features

- Works on **macOS** (Intel + Apple Silicon) and **Linux** (apt, pacman, dnf)
- Auto-detects the OS and uses the right native tools
- Handles the **FAT32 4 GB limit** — splits `install.wim` automatically when needed
- **Installs missing dependencies** (wimlib, rsync) without manual steps
- Safety checks prevent accidentally formatting a system disk
- Includes a simple **GUI** (tkinter — no extra dependencies)

---

## Quick Start

### CLI

```bash
# macOS
./win2usb.sh ~/Downloads/Win11.iso /dev/disk5

# Linux
./win2usb.sh ~/Downloads/Win11.iso /dev/sdb

# Skip confirmation prompt (useful in scripts)
./win2usb.sh --yes ~/Downloads/Win11.iso /dev/disk5
```

### GUI

```bash
python3 win2usb_gui.py
```

Select your ISO, pick the USB drive from the dropdown, and click **Create Bootable USB**.

---

## What It Looks Like

```
$ ./win2usb.sh ~/Downloads/Win11.iso /dev/disk5

win2usb — Windows Bootable USB Creator

[+] Detected OS: macos
==> Checking dependencies
[+] All dependencies OK.
==> Formatting /dev/disk5 as GPT + FAT32
[+] USB mounted at: /Volumes/WINUSB
==> Mounting ISO
==> Copying files to USB (excluding install.wim)
==> install.wim is 6500MB (>4GB) — splitting into chunks
[+] install.wim split complete.
==> Syncing and ejecting USB

Done! Your Windows USB drive is ready.
```

---

## Installation

**Clone and run directly:**

```bash
git clone https://github.com/kreasteve/win2usb.git
cd win2usb
./win2usb.sh ~/Downloads/Win11.iso /dev/diskN
```

**Homebrew:**

```bash
brew install kreasteve/tap/win2usb
```

---

## How It Works

1. **Format** — Wipes the target USB and creates a GPT partition table with a FAT32 partition.
2. **Mount** — Mounts the Windows ISO.
3. **Copy** — Copies all files to the USB, skipping `install.wim` if it exceeds 4 GB.
4. **Split** — If needed, uses `wimlib-imagex` to split `install.wim` into FAT32-compatible chunks.
5. **Eject** — Syncs and safely unmounts the drive.

---

## Requirements

| Requirement | Notes |
|---|---|
| macOS or Linux | macOS requires Homebrew for dependency installation |
| Python 3 | Only needed for the GUI |
| wimlib | Installed automatically if missing |
| rsync | Installed automatically if missing |

---

## Status

This project is in **early release**. It works, but hasn't been tested on every combination yet.

### Tested

| What | Result |
|---|---|
| macOS (Apple Silicon) + Win11 25H2 German ISO | Boots and installs successfully |
| GUI on macOS | Working (dark theme, progress bars, drive detection) |
| CLI on macOS | Working |
| `install.wim` > 4 GB (auto-split) | Working |

### Not yet tested

- **Linux** (CLI and GUI) — the code is there but needs real-world testing
- **Windows 10** ISOs
- **ISOs with `install.esd`** instead of `install.wim`
- **`install.wim` < 4 GB** (no split needed — different code path)
- **Intel Macs**
- **Legacy BIOS boot** — we use GPT (UEFI only), which is fine for Win11 but may not work on older machines
- **Secure Boot**

### Known limitations

- **UEFI only** — the USB is formatted with GPT, so it won't boot on legacy BIOS systems
- **macOS ships rsync 2.6.9** — ancient but works; edge cases possible
- **tkinter on Linux** may need to be installed separately (`sudo apt install python3-tk`)

If you test on a setup not listed above, please open an issue and let us know how it went!

---

## License

MIT — see [LICENSE](LICENSE).
