#!/usr/bin/env bash
# win2usb.sh — Erstellt bootfaehige Windows-USB-Sticks aus ISO-Dateien
# Funktioniert auf macOS und Linux.

set -euo pipefail

# --- Farben ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# --- Globale Variablen fuer Cleanup ---
ISO_MOUNT=""
USB_MOUNT=""
SKIP_CONFIRM=0
OS_TYPE=""

# --- Hilfsfunktionen ---

msg()     { echo -e "${GREEN}[+]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
err()     { echo -e "${RED}[ERROR]${NC} $*" >&2; }
step()    { echo -e "\n${BLUE}${BOLD}==> $*${NC}"; }

usage() {
    cat <<EOF
${BOLD}win2usb${NC} — Create bootable Windows USB drives from ISO files

${BOLD}Usage:${NC}
    $(basename "$0") [options] <path-to-iso> <disk>

${BOLD}Examples:${NC}
    $(basename "$0") ~/Downloads/Win11.iso /dev/disk5          # macOS
    $(basename "$0") ~/Downloads/Win11.iso /dev/sdb            # Linux

${BOLD}Options:${NC}
    --help, -h      Show this help message
    --yes, -y       Skip confirmation prompt (for GUI/scripted use)
    --no-confirm    Same as --yes

${BOLD}Notes:${NC}
    - On Linux, sudo is required for disk operations.
    - Dependencies (wimlib, rsync) are installed automatically if missing.
    - The target disk will be completely erased and reformatted.
EOF
    exit 0
}

cleanup() {
    if [[ -z "$ISO_MOUNT" && -z "$USB_MOUNT" ]]; then return; fi
    echo ""
    warn "Cleaning up..."
    if [[ -n "$ISO_MOUNT" ]]; then
        if [[ "$OS_TYPE" == "macos" ]]; then
            hdiutil detach "$ISO_MOUNT" 2>/dev/null || true
        else
            sudo umount "$ISO_MOUNT" 2>/dev/null || true
            rmdir "$ISO_MOUNT" 2>/dev/null || true
        fi
    fi
    if [[ -n "$USB_MOUNT" ]]; then
        if [[ "$OS_TYPE" == "macos" ]]; then
            diskutil unmount "$USB_MOUNT" 2>/dev/null || true
        else
            sudo umount "$USB_MOUNT" 2>/dev/null || true
            rmdir "$USB_MOUNT" 2>/dev/null || true
        fi
    fi
}

trap cleanup EXIT INT TERM

detect_os() {
    case "$(uname -s)" in
        Darwin) OS_TYPE="macos" ;;
        Linux)  OS_TYPE="linux" ;;
        *)      err "Unsupported operating system: $(uname -s)"; exit 1 ;;
    esac
    msg "Detected OS: $OS_TYPE"
}

# --- Abhaengigkeiten pruefen/installieren ---

check_command() {
    command -v "$1" &>/dev/null
}

install_deps_macos() {
    if ! check_command brew; then
        err "Homebrew is not installed. Please install it from https://brew.sh"
        exit 1
    fi
    local missing=()
    if ! check_command wimlib-imagex; then missing+=(wimlib); fi
    if ! check_command rsync; then missing+=(rsync); fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        warn "Missing dependencies: ${missing[*]}"
        echo -n "Install them via Homebrew? [Y/n] "
        if [[ $SKIP_CONFIRM -eq 1 ]]; then
            echo "y (auto)"
        else
            read -r answer
            if [[ "$answer" =~ ^[Nn] ]]; then
                err "Cannot proceed without dependencies."; exit 1
            fi
        fi
        brew install "${missing[@]}"
    fi
}

install_deps_linux() {
    local missing=()
    if ! check_command wimlib-imagex; then missing+=(wimlib); fi
    if ! check_command rsync; then missing+=(rsync); fi
    if ! check_command mkfs.vfat; then missing+=(dosfstools); fi

    if [[ ${#missing[@]} -eq 0 ]]; then return; fi

    warn "Missing dependencies: ${missing[*]}"

    # Paketnamen abhaengig vom Paketmanager
    local pkgs=()
    local pm=""
    if check_command apt-get; then
        pm="apt-get"
        for m in "${missing[@]}"; do
            case "$m" in
                wimlib)     pkgs+=(wimtools) ;;
                rsync)      pkgs+=(rsync) ;;
                dosfstools) pkgs+=(dosfstools) ;;
            esac
        done
    elif check_command pacman; then
        pm="pacman"
        for m in "${missing[@]}"; do
            case "$m" in
                wimlib)     pkgs+=(wimlib) ;;
                rsync)      pkgs+=(rsync) ;;
                dosfstools) pkgs+=(dosfstools) ;;
            esac
        done
    elif check_command dnf; then
        pm="dnf"
        for m in "${missing[@]}"; do
            case "$m" in
                wimlib)     pkgs+=(wimlib-utils) ;;
                rsync)      pkgs+=(rsync) ;;
                dosfstools) pkgs+=(dosfstools) ;;
            esac
        done
    else
        err "No supported package manager found (apt/pacman/dnf)."
        err "Please install manually: wimlib-imagex, rsync, mkfs.vfat"
        exit 1
    fi

    echo -n "Install them via $pm? [Y/n] "
    if [[ $SKIP_CONFIRM -eq 1 ]]; then
        echo "y (auto)"
    else
        read -r answer
        if [[ "$answer" =~ ^[Nn] ]]; then
            err "Cannot proceed without dependencies."; exit 1
        fi
    fi

    case "$pm" in
        apt-get) sudo apt-get update -qq && sudo apt-get install -y "${pkgs[@]}" ;;
        pacman)  sudo pacman -Sy --noconfirm "${pkgs[@]}" ;;
        dnf)     sudo dnf install -y "${pkgs[@]}" ;;
    esac
}

# --- Validierung ---

validate_inputs() {
    local iso="$1"
    local disk="$2"

    # ISO pruefen
    if [[ ! -f "$iso" ]]; then
        err "ISO file not found: $iso"; exit 1
    fi
    if [[ "${iso##*.}" != "iso" && "${iso##*.}" != "ISO" ]]; then
        warn "File does not have .iso extension — continuing anyway."
    fi

    # Disk pruefen
    if [[ ! -e "$disk" ]]; then
        err "Disk not found: $disk"; exit 1
    fi

    # Systemdisk-Schutz
    if [[ "$OS_TYPE" == "macos" ]]; then
        if [[ "$disk" == "/dev/disk0" || "$disk" == "/dev/disk0"* && "$disk" =~ ^/dev/disk0s ]]; then
            err "Refusing to operate on the system disk (/dev/disk0)."; exit 1
        fi
        # Auch disk1 ist oft der Systemcontainer
        if diskutil info "$disk" 2>/dev/null | grep -q "APFS Container"; then
            err "This looks like a system APFS container. Refusing."; exit 1
        fi
    else
        # Linux: /dev/sda oder /dev/nvme0n1 ist typischerweise die Systemdisk
        local rootdisk
        rootdisk=$(lsblk -no PKNAME "$(findmnt -n -o SOURCE /)" 2>/dev/null || echo "")
        if [[ -n "$rootdisk" && "$disk" == "/dev/$rootdisk" ]]; then
            err "Refusing to operate on the system disk (/dev/$rootdisk)."; exit 1
        fi
    fi
}

show_disk_info() {
    local disk="$1"
    step "Disk information for $disk"
    if [[ "$OS_TYPE" == "macos" ]]; then
        diskutil list "$disk"
    else
        sudo lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT "$disk"
    fi
}

confirm_erase() {
    local disk="$1"
    if [[ $SKIP_CONFIRM -eq 1 ]]; then
        warn "Skipping confirmation (--yes flag)."
        return
    fi
    echo ""
    echo -e "${RED}${BOLD}WARNING: This will ERASE ALL DATA on $disk.${NC}"
    echo -n "Continue? [y/N] "
    read -r answer
    if [[ ! "$answer" =~ ^[Yy] ]]; then
        msg "Aborted."; exit 0
    fi
}

# --- Hauptschritte ---

format_usb() {
    local disk="$1"
    step "Formatting $disk as GPT + FAT32"

    if [[ "$OS_TYPE" == "macos" ]]; then
        diskutil eraseDisk FAT32 WINUSB GPTFormat "$disk"
        # Mountpoint finden
        USB_MOUNT=$(diskutil info "${disk}s1" 2>/dev/null | grep "Mount Point" | awk -F: '{print $2}' | xargs)
        if [[ -z "$USB_MOUNT" ]]; then
            # Manchmal heisst die Partition anders
            USB_MOUNT="/Volumes/WINUSB"
        fi
        if [[ ! -d "$USB_MOUNT" ]]; then
            err "Could not find USB mount point after formatting."; exit 1
        fi
    else
        # Linux: partitionieren und formatieren
        sudo parted -s "$disk" mklabel gpt
        sudo parted -s "$disk" mkpart primary fat32 1MiB 100%
        sudo parted -s "$disk" set 1 msftdata on
        sync

        # Partition bestimmen (sdb1, nvme0n1p1, etc.)
        local part=""
        if [[ "$disk" =~ nvme ]]; then
            part="${disk}p1"
        else
            part="${disk}1"
        fi

        # Kurz warten bis der Kernel die Partition erkennt
        sleep 2
        sudo mkfs.vfat -F 32 -n WINUSB "$part"

        USB_MOUNT=$(mktemp -d /tmp/win2usb_usb.XXXXXX)
        sudo mount "$part" "$USB_MOUNT"
    fi
    msg "USB mounted at: $USB_MOUNT"
}

mount_iso() {
    local iso="$1"
    step "Mounting ISO"

    if [[ "$OS_TYPE" == "macos" ]]; then
        local mount_output
        mount_output=$(hdiutil attach -readonly -nobrowse "$iso" 2>&1)
        ISO_MOUNT=$(echo "$mount_output" | grep -o '/Volumes/.*' | head -1)
        if [[ -z "$ISO_MOUNT" || ! -d "$ISO_MOUNT" ]]; then
            err "Failed to mount ISO."
            echo "$mount_output"
            exit 1
        fi
    else
        ISO_MOUNT=$(mktemp -d /tmp/win2usb_iso.XXXXXX)
        sudo mount -o loop,ro "$iso" "$ISO_MOUNT"
    fi
    msg "ISO mounted at: $ISO_MOUNT"
}

copy_files() {
    step "Copying files to USB (excluding install.wim)"

    # rsync mit Ausschluss von install.wim
    if [[ "$OS_TYPE" == "macos" ]]; then
        rsync -ah --progress --exclude='sources/install.wim' "$ISO_MOUNT/" "$USB_MOUNT/"
    else
        sudo rsync -ah --progress --exclude='sources/install.wim' "$ISO_MOUNT/" "$USB_MOUNT/"
    fi
    msg "File copy complete."
}

handle_install_wim() {
    local wim_path="$ISO_MOUNT/sources/install.wim"

    if [[ ! -f "$wim_path" ]]; then
        warn "No install.wim found — this might be an install.esd image. Checking..."
        local esd_path="$ISO_MOUNT/sources/install.esd"
        if [[ -f "$esd_path" ]]; then
            step "Copying install.esd"
            if [[ "$OS_TYPE" == "macos" ]]; then
                rsync -ah --progress "$esd_path" "$USB_MOUNT/sources/"
            else
                sudo rsync -ah --progress "$esd_path" "$USB_MOUNT/sources/"
            fi
            msg "install.esd copied."
        else
            warn "No install.wim or install.esd found. The ISO might use a different format."
        fi
        return
    fi

    local wim_size
    wim_size=$(stat -f%z "$wim_path" 2>/dev/null || stat -c%s "$wim_path" 2>/dev/null)
    local four_gb=$((4 * 1024 * 1024 * 1024))

    if [[ "$wim_size" -gt "$four_gb" ]]; then
        step "install.wim is $(( wim_size / 1024 / 1024 ))MB (>4GB) — splitting into chunks"
        local dest="$USB_MOUNT/sources/install.swm"
        if [[ "$OS_TYPE" == "macos" ]]; then
            wimlib-imagex split "$wim_path" "$dest" 3800
        else
            sudo wimlib-imagex split "$wim_path" "$dest" 3800
        fi
        msg "install.wim split complete."
    else
        step "install.wim is $(( wim_size / 1024 / 1024 ))MB (<4GB) — copying directly"
        if [[ "$OS_TYPE" == "macos" ]]; then
            rsync -ah --progress "$wim_path" "$USB_MOUNT/sources/"
        else
            sudo rsync -ah --progress "$wim_path" "$USB_MOUNT/sources/"
        fi
        msg "install.wim copied."
    fi
}

eject_usb() {
    local disk="$1"
    step "Syncing and ejecting USB"
    sync

    if [[ "$OS_TYPE" == "macos" ]]; then
        diskutil eject "$disk"
    else
        sudo umount "$USB_MOUNT"
        USB_MOUNT=""  # Cleanup-Trap soll nicht nochmal unmounten
        sudo eject "$disk" 2>/dev/null || true
    fi
    msg "USB safely ejected."
}

unmount_iso() {
    step "Unmounting ISO"
    if [[ "$OS_TYPE" == "macos" ]]; then
        hdiutil detach "$ISO_MOUNT"
    else
        sudo umount "$ISO_MOUNT"
        rmdir "$ISO_MOUNT" 2>/dev/null || true
    fi
    ISO_MOUNT=""
    msg "ISO unmounted."
}

# --- Sudo-Check fuer Linux ---

check_sudo_linux() {
    if [[ "$OS_TYPE" != "linux" ]]; then return; fi
    if [[ $EUID -eq 0 ]]; then return; fi

    warn "This script needs sudo for disk operations on Linux."
    # Sudo-Credentials cachen
    if ! sudo -v; then
        err "Failed to obtain sudo privileges."; exit 1
    fi
}

# --- Argument-Parsing ---

POSITIONAL=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            usage
            ;;
        --yes|-y|--no-confirm)
            SKIP_CONFIRM=1
            shift
            ;;
        *)
            POSITIONAL+=("$1")
            shift
            ;;
    esac
done

if [[ ${#POSITIONAL[@]} -ne 2 ]]; then
    err "Expected 2 arguments: <iso-path> <disk>"
    echo "Run '$(basename "$0") --help' for usage."
    exit 1
fi

ISO_PATH="${POSITIONAL[0]}"
DISK="${POSITIONAL[1]}"

# --- Main ---

echo -e "${BOLD}win2usb${NC} — Windows Bootable USB Creator"
echo ""

detect_os
check_sudo_linux
validate_inputs "$ISO_PATH" "$DISK"

step "Checking dependencies"
if [[ "$OS_TYPE" == "macos" ]]; then
    install_deps_macos
else
    install_deps_linux
fi
msg "All dependencies OK."

show_disk_info "$DISK"
confirm_erase "$DISK"

format_usb "$DISK"
mount_iso "$ISO_PATH"
copy_files
handle_install_wim
unmount_iso
eject_usb "$DISK"

echo ""
echo -e "${GREEN}${BOLD}Done! Your Windows USB drive is ready.${NC}"
echo "You can now boot from it to install Windows."
