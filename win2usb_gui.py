#!/usr/bin/env python3
"""win2usb GUI — Tkinter-Wrapper fuer win2usb.sh"""

import os
import sys
import subprocess
import threading
import platform
from pathlib import Path
from tkinter import (
    Tk, Frame, Label, StringVar,
    Text, Scrollbar, filedialog, messagebox, END, DISABLED, NORMAL, RIGHT, LEFT,
    BOTH, X, Y, TOP, BOTTOM, W, E, N, S
)
from tkinter import ttk

# --- Skript-Pfad relativ zu dieser Datei ---
SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = SCRIPT_DIR / "win2usb.sh"

IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

# --- Farben fuer dunkles Theme ---
BG = "#2b2b2b"
FG = "#d4d4d4"
BG_INPUT = "#3c3c3c"
BG_BUTTON = "#5a5a5a"
FG_BUTTON = "#ffffff"
BG_ACCENT = "#0078d4"
FG_ACCENT = "#ffffff"
BG_OUTPUT = "#1e1e1e"
FG_OUTPUT = "#cccccc"
FG_STATUS = "#888888"


def get_removable_drives():
    """Erkennt externe/entfernbare Laufwerke mit Details (Name, Groesse, Label)."""
    drives = []
    try:
        if IS_MACOS:
            # Alle externen physischen Disks finden
            result = subprocess.run(
                ["diskutil", "list", "external", "physical"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("/dev/disk"):
                    disk = line.split()[0]
                    # Details der Whole-Disk holen (Media Name, Size)
                    info = subprocess.run(
                        ["diskutil", "info", disk],
                        capture_output=True, text=True, timeout=10
                    )
                    size = ""
                    media_name = ""
                    for info_line in info.stdout.splitlines():
                        info_line = info_line.strip()
                        if info_line.startswith("Disk Size:"):
                            size_part = info_line.split(":", 1)[1].strip()
                            size = size_part.split("(")[0].strip()
                        elif info_line.startswith("Device / Media Name:"):
                            media_name = info_line.split(":", 1)[1].strip()
                    # Volume Names von den Partitionen holen
                    volume_names = []
                    list_result = subprocess.run(
                        ["diskutil", "list", disk],
                        capture_output=True, text=True, timeout=10
                    )
                    for list_line in list_result.stdout.splitlines():
                        list_line = list_line.strip()
                        # Partitionszeilen haben ein Format wie:
                        # "1: EFI EFI 209.7 MB disk5s1"
                        # "2: Microsoft Basic Data WIN11 15.2 GB disk5s2"
                        if list_line and list_line[0].isdigit() and ":" in list_line:
                            part_id = list_line.split()[-1]  # z.B. disk5s2
                            part_info = subprocess.run(
                                ["diskutil", "info", part_id],
                                capture_output=True, text=True, timeout=10
                            )
                            for pi_line in part_info.stdout.splitlines():
                                pi_line = pi_line.strip()
                                if pi_line.startswith("Volume Name:"):
                                    vn = pi_line.split(":", 1)[1].strip()
                                    if vn and "Not applicable" not in vn and vn != "EFI":
                                        volume_names.append(vn)
                    # Label zusammenbauen: "/dev/disk5 — SanDisk 3.2Gen1, 15.4 GB, "WIN11""
                    detail_parts = []
                    if media_name and media_name not in ("Untitled", ""):
                        detail_parts.append(media_name)
                    if size:
                        detail_parts.append(size)
                    for vn in volume_names:
                        detail_parts.append(f'"{vn}"')
                    if detail_parts:
                        label = f"{disk} — {', '.join(detail_parts)}"
                    else:
                        label = disk
                    drives.append((disk, label))
        elif IS_LINUX:
            result = subprocess.run(
                ["lsblk", "-d", "-n", "-o", "NAME,SIZE,RM,TYPE,TRAN,MODEL"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.splitlines():
                parts = line.split(None, 5)
                if len(parts) >= 4:
                    name, size, removable, dtype = parts[0], parts[1], parts[2], parts[3]
                    tran = parts[4] if len(parts) > 4 else ""
                    model = parts[5].strip() if len(parts) > 5 else ""
                    if dtype == "disk" and (removable == "1" or tran == "usb"):
                        disk = f"/dev/{name}"
                        detail_parts = []
                        if model:
                            detail_parts.append(model)
                        detail_parts.append(size)
                        label = f"{disk} — {', '.join(detail_parts)}"
                        drives.append((disk, label))
    except Exception as e:
        print(f"Error detecting drives: {e}", file=sys.stderr)
    return drives


class Win2UsbGui:
    def __init__(self, root):
        self.root = root
        self.root.title("win2usb")
        self.root.geometry("700x560")
        self.root.minsize(600, 450)
        self.root.configure(bg=BG)

        self.iso_path = StringVar(value="")
        self.selected_drive = StringVar(value="")
        self.drives = []
        self.process = None
        self.running = False

        # ttk Styles fuer Buttons (macOS ignoriert bg/fg auf normalen Buttons)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.TButton",
                        background=BG_BUTTON, foreground=FG_BUTTON,
                        font=("Helvetica", 11), padding=(10, 4),
                        borderwidth=0, relief="flat")
        style.map("Dark.TButton",
                  background=[("active", BG_ACCENT)],
                  foreground=[("active", FG_ACCENT)])
        style.configure("Accent.TButton",
                        background=BG_ACCENT, foreground=FG_ACCENT,
                        font=("Helvetica", 13, "bold"), padding=(20, 8),
                        borderwidth=0, relief="flat")
        style.configure("Dark.TCombobox",
                        fieldbackground=BG_INPUT, background=BG_BUTTON,
                        foreground=FG, selectbackground=BG_ACCENT,
                        selectforeground=FG_ACCENT, arrowcolor=FG,
                        font=("Helvetica", 10))
        style.map("Dark.TCombobox",
                  fieldbackground=[("readonly", BG_INPUT)],
                  foreground=[("readonly", FG)])
        # Dropdown-Liste stylen
        self.root.option_add("*TCombobox*Listbox.background", BG_INPUT)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", BG_ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", FG_ACCENT)
        self.root.option_add("*TCombobox*Listbox.font", ("Helvetica", 10))

        style.map("Accent.TButton",
                  background=[("active", "#005a9e"), ("disabled", "#555555")],
                  foreground=[("active", FG_ACCENT), ("disabled", "#888888")])
        style.configure("Dark.Horizontal.TProgressbar",
                        troughcolor=BG_INPUT, background=BG_ACCENT,
                        darkcolor=BG_ACCENT, lightcolor=BG_ACCENT,
                        bordercolor=BG_INPUT)

        self._build_ui()
        self._refresh_drives()

    def _build_ui(self):
        # Titel
        title = Label(self.root, text="win2usb", font=("Helvetica", 18, "bold"),
                       bg=BG, fg=FG_ACCENT)
        title.pack(pady=(15, 2))
        subtitle = Label(self.root, text="Create bootable Windows USB drives",
                          font=("Helvetica", 10), bg=BG, fg=FG_STATUS)
        subtitle.pack(pady=(0, 15))

        # --- ISO Auswahl ---
        iso_frame = Frame(self.root, bg=BG)
        iso_frame.pack(fill=X, padx=20, pady=5)

        Label(iso_frame, text="Windows ISO:", bg=BG, fg=FG,
              font=("Helvetica", 11)).pack(side=LEFT)
        ttk.Button(iso_frame, text="Select ISO", command=self._select_iso,
                   style="Dark.TButton").pack(side=RIGHT)

        iso_path_label = Label(self.root, textvariable=self.iso_path,
                                bg=BG_INPUT, fg=FG, anchor=W, padx=8, pady=4,
                                font=("Helvetica", 10))
        iso_path_label.pack(fill=X, padx=20, pady=(0, 10))

        # --- USB Auswahl ---
        usb_frame = Frame(self.root, bg=BG)
        usb_frame.pack(fill=X, padx=20, pady=5)

        Label(usb_frame, text="USB Drive:", bg=BG, fg=FG,
              font=("Helvetica", 11)).pack(side=LEFT)
        ttk.Button(usb_frame, text="Refresh", command=self._refresh_drives,
                   style="Dark.TButton").pack(side=RIGHT)

        self.drive_menu_frame = Frame(self.root, bg=BG)
        self.drive_menu_frame.pack(fill=X, padx=20, pady=(0, 10))
        self._build_drive_menu()

        # --- Start Button ---
        self.start_btn = ttk.Button(
            self.root, text="Create Bootable USB", command=self._start,
            style="Accent.TButton"
        )
        self.start_btn.pack(pady=10)

        # --- Progress Section ---
        progress_frame = Frame(self.root, bg=BG)
        progress_frame.pack(fill=X, padx=20, pady=(0, 5))

        self.step_label = Label(progress_frame, text="Ready",
                                bg=BG, fg=FG, font=("Helvetica", 10), anchor=W)
        self.step_label.pack(fill=X)

        self.step_progress = ttk.Progressbar(
            progress_frame, mode="determinate", maximum=100,
            style="Dark.Horizontal.TProgressbar")
        self.step_progress.pack(fill=X, pady=(2, 4))

        overall_label = Label(progress_frame, text="Overall:",
                              bg=BG, fg=FG_STATUS, font=("Helvetica", 9), anchor=W)
        overall_label.pack(fill=X)

        self.overall_progress = ttk.Progressbar(
            progress_frame, mode="determinate", maximum=100,
            style="Dark.Horizontal.TProgressbar")
        self.overall_progress.pack(fill=X, pady=(2, 0))

        # Progress state
        self._current_step = 0
        self._total_steps = 7
        self._step_pct = 0

        # --- Output ---
        output_frame = Frame(self.root, bg=BG)
        output_frame.pack(fill=BOTH, expand=True, padx=20, pady=(5, 0))

        scrollbar = Scrollbar(output_frame)
        scrollbar.pack(side=RIGHT, fill=Y)

        self.output = Text(output_frame, bg=BG_OUTPUT, fg=FG_OUTPUT,
                           font=("Menlo" if IS_MACOS else "Monospace", 10),
                           relief="flat", wrap="word", state=DISABLED,
                           yscrollcommand=scrollbar.set)
        self.output.pack(fill=BOTH, expand=True)
        scrollbar.config(command=self.output.yview)

        # --- Status Bar ---
        self.status = Label(self.root, text="Ready", bg=BG, fg=FG_STATUS,
                             anchor=W, padx=10, font=("Helvetica", 9))
        self.status.pack(fill=X, side=BOTTOM, pady=(5, 8))

    def _build_drive_menu(self):
        for widget in self.drive_menu_frame.winfo_children():
            widget.destroy()

        # Mapping: label -> disk path, und die StringVar zeigt das Label an
        self._label_to_disk = {}
        if self.drives:
            for disk, label in self.drives:
                self._label_to_disk[label] = disk
            labels = [d[1] for d in self.drives]
            self.selected_drive.set(labels[0])
        else:
            labels = ["No drives found"]
            self.selected_drive.set("")

        combo = ttk.Combobox(self.drive_menu_frame, textvariable=self.selected_drive,
                             values=labels, state="readonly", style="Dark.TCombobox")
        combo.pack(fill=X)

    def _refresh_drives(self):
        self.drives = get_removable_drives()
        self._build_drive_menu()
        self._set_status(f"Found {len(self.drives)} removable drive(s)")

    def _select_iso(self):
        path = filedialog.askopenfilename(
            title="Select Windows ISO",
            filetypes=[("ISO files", "*.iso *.ISO"), ("All files", "*.*")]
        )
        if path:
            self.iso_path.set(path)

    def _append_output(self, text):
        import re
        lines = text.splitlines(keepends=True)
        for line in lines:
            stripped = line.strip()
            # Parse step markers: ##STEP:num:total:Description##
            step_match = re.match(r'^##STEP:(\d+):(\d+):(.+)##$', stripped)
            if step_match:
                self._current_step = int(step_match.group(1))
                self._total_steps = int(step_match.group(2))
                desc = step_match.group(3)
                self._step_pct = 0
                self.step_label.configure(
                    text=f"Step {self._current_step}/{self._total_steps}: {desc}")
                self.step_progress["value"] = 0
                self._update_overall_progress()
                continue
            # Parse progress markers: ##PROGRESS:percent##
            pct_match = re.match(r'^##PROGRESS:(\d+)##$', stripped)
            if pct_match:
                self._step_pct = int(pct_match.group(1))
                self.step_progress["value"] = self._step_pct
                self._update_overall_progress()
                continue
            # Regular output — only auto-scroll if user is at the bottom
            at_bottom = self.output.yview()[1] >= 0.95
            self.output.configure(state=NORMAL)
            self.output.insert(END, line)
            if at_bottom:
                self.output.see(END)
            self.output.configure(state=DISABLED)

    def _update_overall_progress(self):
        """Calculate overall progress: completed steps + current step fraction."""
        completed = max(0, self._current_step - 1)
        overall = (completed * 100 + self._step_pct) / self._total_steps
        self.overall_progress["value"] = min(100, overall)

    def _on_complete(self, success, rc=None):
        """Update progress display on completion or failure."""
        if success:
            self.step_label.configure(text="Complete! USB drive has been ejected.")
            self.step_progress["value"] = 100
            self.overall_progress["value"] = 100
            self._set_status("Done! USB drive is ready. You can remove it now.")
        else:
            status = f"Failed (exit code {rc})" if rc is not None else "Error"
            self.step_label.configure(text="Failed!")
            self._set_status(status)

    def _set_status(self, text):
        self.status.configure(text=text)

    def _start(self):
        iso = self.iso_path.get()
        drive_label = self.selected_drive.get()
        # Label zurueck zum Device-Pfad aufloesen
        drive = self._label_to_disk.get(drive_label, drive_label)

        if not iso or not os.path.isfile(iso):
            messagebox.showerror("Error", "Please select a valid ISO file.")
            return
        if not drive or drive not in [d[0] for d in self.drives]:
            messagebox.showerror("Error", "Please select a USB drive.")
            return

        confirm = messagebox.askyesno(
            "Confirm",
            f"This will ERASE ALL DATA on {drive}.\n\nContinue?"
        )
        if not confirm:
            return

        # UI aktualisieren
        self.output.configure(state=NORMAL)
        self.output.delete("1.0", END)
        self.output.configure(state=DISABLED)
        self.start_btn.state(["disabled"])
        self.running = True
        self._set_status("Running...")

        # Reset progress
        self._current_step = 0
        self._total_steps = 7
        self._step_pct = 0
        self.step_label.configure(text="Ready")
        self.step_progress["value"] = 0
        self.overall_progress["value"] = 0

        # Skript in Hintergrund-Thread ausfuehren
        thread = threading.Thread(target=self._run_script, args=(iso, drive), daemon=True)
        thread.start()

    def _run_script(self, iso, drive):
        cmd = ["bash", str(SCRIPT_PATH), "--yes", iso, drive]

        # Auf Linux brauchen wir sudo
        if IS_LINUX and os.geteuid() != 0:
            # pkexec fuer grafische Sudo-Abfrage, Fallback auf sudo
            if subprocess.run(["which", "pkexec"], capture_output=True).returncode == 0:
                cmd = ["pkexec"] + cmd
            else:
                cmd = ["sudo"] + cmd

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                universal_newlines=True
            )

            for line in self.process.stdout:
                # ANSI-Farbcodes entfernen fuer die Anzeige
                clean = self._strip_ansi(line)
                self.root.after(0, self._append_output, clean)

            self.process.wait()
            rc = self.process.returncode

            if rc == 0:
                self.root.after(0, self._on_complete, True)
                self.root.after(0, lambda: messagebox.showinfo("Success",
                    "Bootable Windows USB created successfully!"))
            else:
                self.root.after(0, self._on_complete, False, rc)
                self.root.after(0, lambda: messagebox.showerror("Error",
                    f"Script failed with exit code {rc}.\nCheck the output for details."))

        except Exception as e:
            self.root.after(0, self._append_output, f"\nError: {e}\n")
            self.root.after(0, self._on_complete, False)
        finally:
            self.running = False
            self.process = None
            self.root.after(0, lambda: self.start_btn.state(["!disabled"]))

    @staticmethod
    def _strip_ansi(text):
        """Entfernt ANSI-Escape-Sequenzen."""
        import re
        return re.sub(r'\x1b\[[0-9;]*m', '', text)


def main():
    root = Tk()

    # Dunkles Theme global setzen
    root.option_add("*Background", BG)
    root.option_add("*Foreground", FG)

    app = Win2UsbGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
