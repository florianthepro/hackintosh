#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import ctypes
import json
import os
import plistlib
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

APP_NAME = "OpenCore Forge"
APP_VERSION = "1.0.0-zero"

# =============================================================================
# Hard rules for this build
# - Admin/root elevation happens before any GUI/workspace/scan work.
# - No internet downloads during startup.
# - Language selection is inside the main Tk window, no secondary Toplevel.
# - The GUI is compact and resizable.
# - USB erase confirmation is a checkbox, not typed text.
# - Default action is USB flash; advanced option can switch to folder save.
# =============================================================================


def is_windows():
    return os.name == "nt"


def is_linux():
    return sys.platform.startswith("linux")


def is_admin():
    if is_windows():
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    try:
        return os.geteuid() == 0
    except Exception:
        return False


def gui_python_executable():
    if not is_windows():
        return sys.executable
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return str(pythonw if pythonw.exists() else Path(sys.executable))


def native_error(message):
    try:
        if is_windows():
            ctypes.windll.user32.MessageBoxW(None, str(message), APP_NAME, 0x10)
        else:
            print(message)
    except Exception:
        print(message)


def elevate_before_anything():
    if is_admin():
        return
    if "--elevated" in sys.argv or "--no-admin" in sys.argv:
        return
    script = str(Path(sys.argv[0]).resolve())
    args = [script] + [arg for arg in sys.argv[1:] if arg != "--elevated"] + ["--elevated"]
    if is_windows():
        params = " ".join([f'"{arg}"' if " " in arg else arg for arg in args])
        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", gui_python_executable(), params, None, 1)
        if result > 32:
            raise SystemExit(0)
        native_error("Administrator rights are required. Elevation was cancelled or failed.")
        raise SystemExit(1)
    if is_linux():
        pkexec = shutil.which("pkexec")
        if pkexec:
            env = [f"DISPLAY={os.environ.get('DISPLAY', '')}", f"XAUTHORITY={os.environ.get('XAUTHORITY', '')}"]
            subprocess.Popen([pkexec, "env"] + env + [sys.executable] + args)
            raise SystemExit(0)
        native_error("Root rights are required. Install/use pkexec or start with sudo.")
        raise SystemExit(1)


elevate_before_anything()

BASE = Path(tempfile.gettempdir()) / "OpenCoreForge_Runtime"
LOGS = BASE / "logs"
REPORTS = BASE / "reports"
OUTPUT = BASE / "output"
for folder in (BASE, LOGS, REPORTS, OUTPUT):
    folder.mkdir(parents=True, exist_ok=True)

STATE_FILE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "OpenCoreForge_state.json"
APP_LOG = LOGS / "app.log"
CRASH_LOG = LOGS / "crash.log"
CALLBACK_LOG = LOGS / "gui_callback_error.log"

MACOS_CHOICES = [
    "macOS High Sierra 10.13",
    "macOS Mojave 10.14",
    "macOS Catalina 10.15",
    "macOS Big Sur 11",
    "macOS Monterey 12",
    "macOS Ventura 13",
    "macOS Sonoma 14",
    "macOS Sequoia 15",
    "macOS Tahoe 26",
]

TEXT = {
    "en": {
        "choose_language": "Choose language",
        "device": "Device",
        "macos": "macOS",
        "advanced": "Advanced options",
        "save_to_folder": "Save to folder instead of flashing USB",
        "verify": "Verify after flash/save",
        "confirm": "I understand the selected USB drive will be erased",
        "flash": "FLASH",
        "save": "SAVE",
        "cleanup": "Cleanup",
        "reports": "Reports",
        "workspace": "Workspace",
        "refresh": "Refresh",
        "efi": "EFI source",
        "recovery": "Recovery source",
        "browse": "Browse",
        "auto_find": "Auto find",
        "secure": "SecureBootModel",
        "scan": "ScanPolicy",
        "hide": "HideAuxiliary",
        "verbose": "Verbose boot",
        "ready": "Select USB and macOS, then press FLASH.",
        "ready_save": "Select macOS, then press SAVE.",
        "no_usb": "No USB device selected.",
        "no_macos": "No macOS selected.",
        "no_efi": "No usable EFI folder found or selected.",
        "need_confirm": "Please tick the erase confirmation checkbox first.",
        "working": "Working...",
        "done": "Done.",
        "failed": "Failed.",
        "verify_ok": "Verification passed.",
        "verify_warn": "Verification passed with warnings.",
        "verify_fail": "Verification failed.",
        "cleanup_ask": "Remove temporary output and logs?",
        "cleanup_done": "Temporary data removed.",
    },
    "de": {
        "choose_language": "Sprache waehlen",
        "device": "Laufwerk",
        "macos": "macOS",
        "advanced": "Erweiterte Optionen",
        "save_to_folder": "In Ordner speichern statt USB flashen",
        "verify": "Nach Flash/Speichern pruefen",
        "confirm": "Ich verstehe, dass das ausgewaehlte USB-Laufwerk geloescht wird",
        "flash": "FLASH",
        "save": "SPEICHERN",
        "cleanup": "Cleanup",
        "reports": "Reports",
        "workspace": "Workspace",
        "refresh": "Aktualisieren",
        "efi": "EFI-Quelle",
        "recovery": "Recovery-Quelle",
        "browse": "Durchsuchen",
        "auto_find": "Automatisch suchen",
        "secure": "SecureBootModel",
        "scan": "ScanPolicy",
        "hide": "HideAuxiliary",
        "verbose": "Verbose Boot",
        "ready": "USB und macOS waehlen, dann FLASH druecken.",
        "ready_save": "macOS waehlen, dann SPEICHERN druecken.",
        "no_usb": "Kein USB-Laufwerk gewaehlt.",
        "no_macos": "Kein macOS gewaehlt.",
        "no_efi": "Kein nutzbarer EFI-Ordner gefunden oder gewaehlt.",
        "need_confirm": "Bitte zuerst das Loesch-Bestaetigungskaestchen aktivieren.",
        "working": "Laeuft...",
        "done": "Fertig.",
        "failed": "Fehlgeschlagen.",
        "verify_ok": "Pruefung bestanden.",
        "verify_warn": "Pruefung mit Warnungen bestanden.",
        "verify_fail": "Pruefung fehlgeschlagen.",
        "cleanup_ask": "Temporaere Ausgabe und Logs entfernen?",
        "cleanup_done": "Temporaere Daten entfernt.",
    },
}


def safe_write(path, text):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(text), encoding="utf-8")
    except Exception:
        pass


def append_log(text):
    try:
        with APP_LOG.open("a", encoding="utf-8") as handle:
            handle.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + str(text) + "\n")
    except Exception:
        pass


def human_size(value):
    try:
        number = int(value)
    except Exception:
        return str(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if number < 1024 or unit == "TB":
            return f"{number:.1f} {unit}"
        number /= 1024


def powershell_json(command):
    if not is_windows():
        return []
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command + " | ConvertTo-Json -Depth 5"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if not result.stdout.strip():
            return []
        data = json.loads(result.stdout)
        return data if isinstance(data, list) else [data]
    except Exception:
        return []


def list_usb_devices():
    if is_windows():
        devices = []
        disks = powershell_json("Get-Disk | Select Number,FriendlyName,Model,Size,BusType,PartitionStyle,IsBoot,IsSystem")
        for disk in disks:
            if str(disk.get("IsBoot", False)).lower() == "true" or str(disk.get("IsSystem", False)).lower() == "true":
                continue
            if str(disk.get("BusType", "")).lower() in ("usb", "sd", "mmc"):
                devices.append({"platform": "windows", **disk})
        return devices
    if is_linux():
        devices = []
        try:
            result = subprocess.run(["lsblk", "-J", "-b", "-o", "NAME,MODEL,SIZE,TYPE,TRAN,RM,RO"], capture_output=True, text=True, timeout=30)
            data = json.loads(result.stdout) if result.stdout.strip() else {}
            for disk in data.get("blockdevices", []):
                removable = str(disk.get("rm", "0")) == "1"
                usb = str(disk.get("tran", "")).lower() == "usb"
                readonly = str(disk.get("ro", "0")) in ("1", "true", "True")
                if disk.get("type") == "disk" and (removable or usb) and not readonly:
                    devices.append({"platform": "linux", "path": "/dev/" + disk.get("name", ""), "model": disk.get("model") or disk.get("name"), "size": disk.get("size")})
        except Exception:
            pass
        return devices
    return []


def validate_layout(root):
    root = Path(root)
    rows = []

    def add(level, message):
        rows.append((level, message))

    def check(path, label, fail=True):
        if Path(path).exists():
            add("OK", label)
        else:
            add("FAIL" if fail else "WARN", label + " missing")

    check(root / "EFI", "EFI folder")
    check(root / "EFI" / "BOOT" / "BOOTx64.efi", "BOOTx64.efi")
    check(root / "EFI" / "OC" / "config.plist", "config.plist")
    check(root / "EFI" / "OC" / "Drivers" / "OpenRuntime.efi", "OpenRuntime.efi")
    recovery = root / "com.apple.recovery.boot"
    check(recovery, "Recovery folder", False)
    if recovery.exists():
        check(recovery / "BaseSystem.dmg", "BaseSystem.dmg")
        check(recovery / "BaseSystem.chunklist", "BaseSystem.chunklist", False)
    config = root / "EFI" / "OC" / "config.plist"
    if config.exists():
        try:
            with config.open("rb") as handle:
                plistlib.load(handle)
            add("OK", "config.plist parsed")
        except Exception as error:
            add("FAIL", "config.plist parse failed: " + str(error))
    status = "passed"
    for level, _ in rows:
        if level == "FAIL":
            status = "failed"
            break
        if level == "WARN":
            status = "warnings"
    return status, rows


try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
except Exception:
    safe_write(CRASH_LOG, traceback.format_exc())
    raise


class OpenCoreForge(tk.Tk):
    def __init__(self):
        super().__init__()
        self.lang = "en"
        self.usb_devices = []
        self.selected_usb = None
        self.selected_macos = None
        self.efi_path = None
        self.recovery_path = None
        self.queue = queue.Queue()
        self.load_state()
        self.setup_style()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("520x400")
        self.minsize(500, 360)
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.show_language_page()
        self.after(80, self.drain_queue)

    def report_callback_exception(self, exc, value, tb):
        error = "".join(traceback.format_exception(exc, value, tb))
        safe_write(CALLBACK_LOG, error)
        messagebox.showerror(APP_NAME, error[-3500:])

    def text(self, key):
        return TEXT.get(self.lang, TEXT["en"]).get(key, key)

    def load_state(self):
        try:
            if STATE_FILE.exists():
                self.lang = json.loads(STATE_FILE.read_text(encoding="utf-8")).get("lang", self.lang)
        except Exception:
            pass

    def save_state(self):
        try:
            STATE_FILE.write_text(json.dumps({"lang": self.lang}, indent=2), encoding="utf-8")
        except Exception:
            pass

    def setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        self.configure(bg="#f3f4f6")
        style.configure("TFrame", background="#f3f4f6")
        style.configure("TLabel", background="#f3f4f6", font=("Segoe UI", 9))
        style.configure("Title.TLabel", background="#f3f4f6", font=("Segoe UI", 14, "bold"))
        style.configure("Small.TLabel", background="#f3f4f6", foreground="#4b5563", font=("Segoe UI", 8))
        style.configure("TButton", padding=(8, 5), font=("Segoe UI", 9))
        style.configure("Flash.TButton", padding=(14, 7), font=("Segoe UI", 10, "bold"))

    def clear(self):
        for widget in self.winfo_children():
            widget.destroy()

    def show_language_page(self):
        self.clear()
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text="Choose language / Sprache waehlen", style="Small.TLabel").pack(anchor="w", pady=(0, 22))
        row = ttk.Frame(frame)
        row.pack(expand=True)
        ttk.Button(row, text="English", command=lambda: self.start_with_language("en")).pack(side="left", padx=10, ipadx=10, ipady=8)
        ttk.Button(row, text="Deutsch", command=lambda: self.start_with_language("de")).pack(side="left", padx=10, ipadx=10, ipady=8)

    def start_with_language(self, language):
        self.lang = language
        self.save_state()
        self.usb_devices = list_usb_devices()
        self.find_outputs()
        self.show_main_page()

    def put(self, function, *args):
        self.queue.put((function, args))

    def drain_queue(self):
        try:
            while True:
                function, args = self.queue.get_nowait()
                function(*args)
        except queue.Empty:
            pass
        self.after(80, self.drain_queue)

    def find_outputs(self):
        efis = []
        recoveries = []
        for root in (BASE, Path.home(), Path.cwd()):
            try:
                for candidate in root.rglob("EFI"):
                    if (candidate / "OC" / "config.plist").exists():
                        efis.append(candidate)
                for candidate in root.rglob("com.apple.recovery.boot"):
                    if (candidate / "BaseSystem.dmg").exists() or (candidate / "BaseSystem.chunklist").exists():
                        recoveries.append(candidate)
            except Exception:
                pass
        self.efi_path = sorted(efis, key=lambda item: len(str(item)))[0] if efis else None
        self.recovery_path = sorted(recoveries, key=lambda item: len(str(item)))[0] if recoveries else None

    def show_main_page(self):
        self.clear()
        self.geometry("520x420")
        main = ttk.Frame(self, padding=10)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text=APP_NAME, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.subtitle = ttk.Label(main, text=self.text("ready"), style="Small.TLabel")
        self.subtitle.grid(row=1, column=0, sticky="w", pady=(0, 6))

        form = ttk.Frame(main)
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text=self.text("device")).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.device_var = tk.StringVar()
        self.device_box = ttk.Combobox(form, textvariable=self.device_var, state="readonly", width=38)
        self.device_box.grid(row=0, column=1, sticky="ew", pady=4)
        self.device_box.bind("<<ComboboxSelected>>", lambda event: self.select_device())

        ttk.Label(form, text=self.text("macos")).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.macos_var = tk.StringVar()
        self.macos_box = ttk.Combobox(form, textvariable=self.macos_var, state="readonly", width=38)
        self.macos_box.grid(row=1, column=1, sticky="ew", pady=4)
        self.macos_box.bind("<<ComboboxSelected>>", lambda event: self.select_macos())

        self.advanced_open = tk.BooleanVar(value=False)
        self.advanced_button = ttk.Checkbutton(main, text="▼ " + self.text("advanced"), variable=self.advanced_open, command=self.toggle_advanced)
        self.advanced_button.grid(row=3, column=0, sticky="w", pady=(5, 0))
        self.advanced = ttk.Frame(main)

        self.save_folder_var = tk.BooleanVar(value=False)
        self.secure_var = tk.StringVar(value="Disabled")
        self.scan_var = tk.StringVar(value="0")
        self.hide_var = tk.StringVar(value="False")
        self.verbose_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.advanced, text=self.text("save_to_folder"), variable=self.save_folder_var, command=self.update_flash_text).grid(row=0, column=0, columnspan=3, sticky="w")
        self.add_option(1, self.text("secure"), self.secure_var, ["Disabled", "Default"])
        self.add_option(2, self.text("scan"), self.scan_var, ["0", "Default"])
        self.add_option(3, self.text("hide"), self.hide_var, ["False", "True"])
        ttk.Checkbutton(self.advanced, text=self.text("verbose"), variable=self.verbose_var).grid(row=4, column=1, sticky="w")
        ttk.Label(self.advanced, text=self.text("efi")).grid(row=5, column=0, sticky="w")
        self.efi_label = ttk.Label(self.advanced, text=str(self.efi_path) if self.efi_path else "-", width=28)
        self.efi_label.grid(row=5, column=1, sticky="ew")
        ttk.Button(self.advanced, text=self.text("browse"), command=self.pick_efi).grid(row=5, column=2, padx=3)
        ttk.Label(self.advanced, text=self.text("recovery")).grid(row=6, column=0, sticky="w")
        self.recovery_label = ttk.Label(self.advanced, text=str(self.recovery_path) if self.recovery_path else "-", width=28)
        self.recovery_label.grid(row=6, column=1, sticky="ew")
        ttk.Button(self.advanced, text=self.text("browse"), command=self.pick_recovery).grid(row=6, column=2, padx=3)

        self.status = tk.Text(main, height=6, width=55, bg="#111827", fg="#e5e7eb", relief="flat", font=("Consolas", 8), wrap="word")
        self.status.grid(row=5, column=0, sticky="nsew", pady=(7, 6))
        main.rowconfigure(5, weight=1)

        bottom = ttk.Frame(main)
        bottom.grid(row=6, column=0, sticky="ew")
        bottom.columnconfigure(1, weight=1)
        self.verify_var = tk.BooleanVar(value=True)
        self.confirm_var = tk.BooleanVar(value=False)
        checks = ttk.Frame(bottom)
        checks.grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(checks, text=self.text("verify"), variable=self.verify_var).pack(anchor="w")
        ttk.Checkbutton(checks, text=self.text("confirm"), variable=self.confirm_var).pack(anchor="w")
        ttk.Button(bottom, text=self.text("cleanup"), command=self.cleanup).grid(row=0, column=1, sticky="e", padx=2)
        ttk.Button(bottom, text=self.text("reports"), command=lambda: self.open_path(REPORTS)).grid(row=0, column=2, sticky="e", padx=2)
        self.flash_button = ttk.Button(bottom, text=self.text("flash"), style="Flash.TButton", command=self.flash)
        self.flash_button.grid(row=0, column=3, sticky="e")

        self.populate_lists()
        self.log(self.text("ready"))

    def add_option(self, row, label, variable, values):
        ttk.Label(self.advanced, text=label).grid(row=row, column=0, sticky="w")
        ttk.Combobox(self.advanced, textvariable=variable, values=values, state="readonly", width=14).grid(row=row, column=1, sticky="w")

    def toggle_advanced(self):
        if self.advanced_open.get():
            self.advanced.grid(row=4, column=0, sticky="ew", pady=2)
            self.advanced_button.config(text="▲ " + self.text("advanced"))
        else:
            self.advanced.grid_remove()
            self.advanced_button.config(text="▼ " + self.text("advanced"))

    def update_flash_text(self):
        if self.save_folder_var.get():
            self.flash_button.config(text=self.text("save"))
            self.subtitle.config(text=self.text("ready_save"))
        else:
            self.flash_button.config(text=self.text("flash"))
            self.subtitle.config(text=self.text("ready"))

    def populate_lists(self):
        devices = []
        for device in self.usb_devices:
            if device.get("platform") == "windows":
                devices.append(f"Disk {device.get('Number')} | {device.get('FriendlyName')} | {human_size(device.get('Size', 0))}")
            else:
                devices.append(f"{device.get('path')} | {device.get('model')} | {human_size(device.get('size', 0))}")
        self.device_box["values"] = devices
        if devices:
            self.device_var.set(devices[0])
            self.select_device()
        self.macos_box["values"] = MACOS_CHOICES

    def select_device(self):
        index = self.device_box.current()
        self.selected_usb = self.usb_devices[index] if 0 <= index < len(self.usb_devices) else None

    def select_macos(self):
        index = self.macos_box.current()
        self.selected_macos = MACOS_CHOICES[index] if 0 <= index < len(MACOS_CHOICES) else None

    def pick_efi(self):
        path = filedialog.askdirectory(title=self.text("efi"))
        if path:
            self.efi_path = Path(path)
            self.efi_label.config(text=str(self.efi_path))

    def pick_recovery(self):
        path = filedialog.askdirectory(title=self.text("recovery"))
        if path:
            self.recovery_path = Path(path)
            self.recovery_label.config(text=str(self.recovery_path))

    def log(self, message):
        line = time.strftime("[%H:%M:%S] ") + str(message) + "\n"
        self.status.insert("end", line)
        self.status.see("end")
        append_log(message)

    def flash(self):
        if not self.selected_macos:
            messagebox.showwarning(APP_NAME, self.text("no_macos")); return
        if not self.efi_path or not Path(self.efi_path).exists():
            messagebox.showerror(APP_NAME, self.text("no_efi")); return
        if self.save_folder_var.get():
            path = filedialog.askdirectory(title=self.text("save_to_folder"))
            if path:
                threading.Thread(target=lambda: self.save_to_folder(Path(path)), daemon=True).start()
            return
        if not self.selected_usb:
            messagebox.showwarning(APP_NAME, self.text("no_usb")); return
        if not self.confirm_var.get():
            messagebox.showwarning(APP_NAME, self.text("need_confirm")); return
        threading.Thread(target=self.flash_worker, daemon=True).start()

    def save_to_folder(self, target):
        try:
            self.put(self.log, self.text("working"))
            self.copy_payload(target)
            self.patch_config(target)
            if self.verify_var.get(): self.write_report(target)
            self.put(self.log, self.text("done"))
        except Exception:
            self.handle_error()

    def flash_worker(self):
        try:
            self.put(self.log, self.text("working"))
            target = self.format_usb()
            self.copy_payload(target)
            self.patch_config(target)
            if self.verify_var.get(): self.write_report(target)
            self.put(self.log, self.text("done"))
        except Exception:
            self.handle_error()

    def copy_payload(self, target):
        target = Path(target)
        out = target / "EFI"
        shutil.rmtree(out, ignore_errors=True)
        shutil.copytree(self.efi_path, out)
        if self.recovery_path and Path(self.recovery_path).exists():
            recovery = target / "com.apple.recovery.boot"
            shutil.rmtree(recovery, ignore_errors=True)
            shutil.copytree(self.recovery_path, recovery)

    def write_report(self, target):
        status, rows = validate_layout(target)
        report = REPORTS / ("validation_" + time.strftime("%Y%m%d_%H%M%S") + ".txt")
        lines = [f"{APP_NAME} {APP_VERSION}", f"Target: {target}", f"macOS: {self.selected_macos}", ""] + [f"[{level}] {message}" for level, message in rows]
        safe_write(report, "\n".join(lines))
        self.put(self.log, "\n".join(lines[-len(rows):]))
        message = self.text("verify_ok") if status == "passed" else self.text("verify_warn") if status == "warnings" else self.text("verify_fail")
        self.put(messagebox.showinfo if status != "failed" else messagebox.showerror, APP_NAME, message + "\n\n" + str(report))

    def format_usb(self):
        if is_windows():
            number = self.selected_usb.get("Number")
            script = BASE / "flash_usb.ps1"
            script.write_text(f"""
$ErrorActionPreference='Stop'
$diskNumber={number}
$disk=Get-Disk -Number $diskNumber
if($disk.IsBoot -or $disk.IsSystem){{throw 'Refusing boot/system disk'}}
Set-Disk -Number $diskNumber -IsReadOnly $false -ErrorAction SilentlyContinue
Set-Disk -Number $diskNumber -IsOffline $false -ErrorAction SilentlyContinue
Clear-Disk -Number $diskNumber -RemoveData -RemoveOEM -Confirm:$false
Initialize-Disk -Number $diskNumber -PartitionStyle GPT
$part=New-Partition -DiskNumber $diskNumber -Size 4GB -AssignDriveLetter
Format-Volume -Partition $part -FileSystem FAT32 -NewFileSystemLabel OPENCORE -Confirm:$false -Force
(Get-Volume -Partition $part).DriveLetter
""", encoding="utf-8")
            result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], capture_output=True, text=True, timeout=180)
            safe_write(LOGS / "powershell_flash_stdout.log", result.stdout or "")
            safe_write(LOGS / "powershell_flash_stderr.log", result.stderr or "")
            self.put(self.log, (result.stdout or "") + "\n" + (result.stderr or ""))
            if result.returncode != 0:
                raise RuntimeError("PowerShell format failed: " + ((result.stderr or result.stdout).strip()[-600:]))
            letters = [item.strip().replace(":", "") for item in result.stdout.splitlines() if item.strip()]
            if not letters: raise RuntimeError("No drive letter returned after formatting")
            drive = Path(f"{letters[-1]}:/")
            for _ in range(30):
                if drive.exists(): return drive
                time.sleep(0.25)
            raise RuntimeError(f"Drive {letters[-1]}: not available")
        raise RuntimeError("USB flashing is currently implemented for Windows in this clean build")

    def patch_config(self, target):
        config = Path(target) / "EFI" / "OC" / "config.plist"
        if not config.exists(): return
        try:
            shutil.copy2(config, config.with_suffix(".plist.before_forge"))
            with config.open("rb") as handle: data = plistlib.load(handle)
            data.setdefault("Misc", {}).setdefault("Security", {})["SecureBootModel"] = self.secure_var.get()
            if self.scan_var.get() == "0": data.setdefault("Misc", {}).setdefault("Security", {})["ScanPolicy"] = 0
            data.setdefault("Misc", {}).setdefault("Boot", {})["HideAuxiliary"] = self.hide_var.get() == "True"
            with config.open("wb") as handle: plistlib.dump(data, handle)
        except Exception as error:
            self.put(self.log, "config patch skipped: " + str(error))

    def handle_error(self):
        error = traceback.format_exc()
        safe_write(LOGS / "operation_error.log", error)
        clean = error.splitlines()[-1]
        self.put(self.log, self.text("failed") + ": " + clean)
        self.put(messagebox.showerror, APP_NAME, self.text("failed") + "\n\n" + clean)

    def open_path(self, path):
        if is_windows(): os.startfile(str(path))
        elif is_linux(): subprocess.Popen(["xdg-open", str(path)])
        else: subprocess.Popen(["open", str(path)])

    def cleanup(self):
        if messagebox.askyesno(APP_NAME, self.text("cleanup_ask")):
            shutil.rmtree(OUTPUT, ignore_errors=True)
            OUTPUT.mkdir(parents=True, exist_ok=True)
            self.log(self.text("cleanup_done"))

    def close(self):
        self.save_state()
        self.destroy()


if __name__ == "__main__":
    try:
        OpenCoreForge().mainloop()
    except Exception:
        error = traceback.format_exc()
        safe_write(CRASH_LOG, error)
        show_native_error(error[-3500:])
        print(error)
