#!/usr/bin/env python3
"""win2usb GUI — Tkinter-Wrapper fuer win2usb.sh"""

import os
import sys
import subprocess
import threading
import platform
from pathlib import Path
from tkinter import (
    Tk, Frame, Label, Button, StringVar, OptionMenu,
    Text, Scrollbar, filedialog, messagebox, END, DISABLED, NORMAL, RIGHT, LEFT,
    BOTH, X, Y, TOP, BOTTOM, W, E, N, S
)

# --- Skript-Pfad relativ zu dieser Datei ---
SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = SCRIPT_DIR / "win2usb.sh"

IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

# --- Farben fuer dunkles Theme ---
BG = "#2b2b2b"
FG = "#d4d4d4"
BG_INPUT = "#3c3c3c"
BG_BUTTON = "#404040"
FG_BUTTON = "#e0e0e0"
BG_ACCENT = "#0078d4"
FG_ACCENT = "#ffffff"
BG_OUTPUT = "#1e1e1e"
FG_OUTPUT = "#cccccc"
FG_STATUS = "#888888"


def get_removable_drives():
    """Erkennt externe/entfernbare Laufwerke."""
    drives = []
    try:
        if IS_MACOS:
            result = subprocess.run(
                ["diskutil", "list", "external", "physical"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("/dev/disk"):
                    disk = line.split()[0]
                    # Groesse extrahieren
                    size = ""
                    if "*" in line:
                        parts = line.split("*")
                        if len(parts) > 1:
                            size = parts[1].strip().split()[0:2]
                            size = " ".join(size)
                    label = f"{disk} ({size})" if size else disk
                    drives.append((disk, label))
        elif IS_LINUX:
            result = subprocess.run(
                ["lsblk", "-d", "-n", "-o", "NAME,SIZE,RM,TYPE,TRAN"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 4:
                    name, size, removable, dtype = parts[0], parts[1], parts[2], parts[3]
                    tran = parts[4] if len(parts) > 4 else ""
                    if dtype == "disk" and (removable == "1" or tran == "usb"):
                        disk = f"/dev/{name}"
                        drives.append((disk, f"{disk} ({size})"))
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
        Button(iso_frame, text="Select ISO", command=self._select_iso,
               bg=BG_BUTTON, fg=FG_BUTTON, relief="flat", padx=10,
               activebackground=BG_ACCENT, activeforeground=FG_ACCENT
        ).pack(side=RIGHT)

        iso_path_label = Label(self.root, textvariable=self.iso_path,
                                bg=BG_INPUT, fg=FG, anchor=W, padx=8, pady=4,
                                font=("Helvetica", 10))
        iso_path_label.pack(fill=X, padx=20, pady=(0, 10))

        # --- USB Auswahl ---
        usb_frame = Frame(self.root, bg=BG)
        usb_frame.pack(fill=X, padx=20, pady=5)

        Label(usb_frame, text="USB Drive:", bg=BG, fg=FG,
              font=("Helvetica", 11)).pack(side=LEFT)
        Button(usb_frame, text="Refresh", command=self._refresh_drives,
               bg=BG_BUTTON, fg=FG_BUTTON, relief="flat", padx=8,
               activebackground=BG_ACCENT, activeforeground=FG_ACCENT
        ).pack(side=RIGHT)

        self.drive_menu_frame = Frame(self.root, bg=BG)
        self.drive_menu_frame.pack(fill=X, padx=20, pady=(0, 10))
        self._build_drive_menu()

        # --- Start Button ---
        self.start_btn = Button(
            self.root, text="Create Bootable USB", command=self._start,
            bg=BG_ACCENT, fg=FG_ACCENT, font=("Helvetica", 12, "bold"),
            relief="flat", padx=20, pady=8,
            activebackground="#005a9e", activeforeground=FG_ACCENT
        )
        self.start_btn.pack(pady=10)

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

        labels = [d[1] for d in self.drives] if self.drives else ["No drives found"]
        if self.drives:
            self.selected_drive.set(self.drives[0][0])
        else:
            self.selected_drive.set("")

        menu = OptionMenu(self.drive_menu_frame, self.selected_drive, *
                          ([d[0] for d in self.drives] if self.drives else [""]))
        menu.configure(bg=BG_INPUT, fg=FG, relief="flat", highlightthickness=0,
                       activebackground=BG_ACCENT, activeforeground=FG_ACCENT,
                       font=("Helvetica", 10))
        menu["menu"].configure(bg=BG_INPUT, fg=FG, activebackground=BG_ACCENT,
                                activeforeground=FG_ACCENT)

        # Anzeige-Labels statt roher Device-Pfade
        menu["menu"].delete(0, END)
        for disk, label in self.drives:
            menu["menu"].add_command(label=label,
                                      command=lambda d=disk: self.selected_drive.set(d))
        if not self.drives:
            menu["menu"].add_command(label="No drives found", command=lambda: None)

        menu.pack(fill=X)

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
        self.output.configure(state=NORMAL)
        self.output.insert(END, text)
        self.output.see(END)
        self.output.configure(state=DISABLED)

    def _set_status(self, text):
        self.status.configure(text=text)

    def _start(self):
        iso = self.iso_path.get()
        drive = self.selected_drive.get()

        if not iso or not os.path.isfile(iso):
            messagebox.showerror("Error", "Please select a valid ISO file.")
            return
        if not drive:
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
        self.start_btn.configure(state=DISABLED)
        self.running = True
        self._set_status("Running...")

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
                self.root.after(0, self._set_status, "Done! USB drive is ready.")
                self.root.after(0, lambda: messagebox.showinfo("Success",
                    "Bootable Windows USB created successfully!"))
            else:
                self.root.after(0, self._set_status, f"Failed (exit code {rc})")
                self.root.after(0, lambda: messagebox.showerror("Error",
                    f"Script failed with exit code {rc}.\nCheck the output for details."))

        except Exception as e:
            self.root.after(0, self._append_output, f"\nError: {e}\n")
            self.root.after(0, self._set_status, "Error")
        finally:
            self.running = False
            self.process = None
            self.root.after(0, lambda: self.start_btn.configure(state=NORMAL))

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
