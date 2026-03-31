# win2usb

Create bootable Windows USB drives from ISO files on macOS and Linux. Handles the FAT32 4GB file size limit by automatically splitting `install.wim` when needed.

## Requirements

- **wimlib** and **rsync** — installed automatically if missing
- macOS: requires Homebrew
- Linux: requires sudo for disk operations

## Usage

### CLI

```bash
# macOS
./win2usb.sh ~/Downloads/Win11.iso /dev/disk5

# Linux
./win2usb.sh ~/Downloads/Win11.iso /dev/sdb

# Skip confirmation prompt (for scripting)
./win2usb.sh --yes ~/Downloads/Win11.iso /dev/disk5
```

### GUI

```bash
python3 win2usb_gui.py
```

Select your ISO, pick the USB drive from the dropdown, and click "Create Bootable USB".

## Supported Platforms

- macOS (Intel + Apple Silicon)
- Linux (apt, pacman, dnf)
