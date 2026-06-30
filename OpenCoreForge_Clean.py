#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import ctypes
import hashlib
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
import urllib.request
import zipfile
from pathlib import Path

APP_NAME = "OpenCore Forge"
APP_VERSION = "5.0.0-clean"


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


def gui_python_exe():
    if not is_windows():
        return sys.executable
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return str(candidate if candidate.exists() else Path(sys.executable))


def show_native_error(text):
    try:
        if is_windows():
            ctypes.windll.user32.MessageBoxW(None, str(text), APP_NAME, 0x10)
        else:
            print(text)
    except Exception:
        print(text)


def elevate_before_everything():
    if is_admin():
        return
    if "--elevated" in sys.argv or "--no-admin" in sys.argv:
        return
    script = str(Path(sys.argv[0]).resolve())
    args = [script] + [arg for arg in sys.argv[1:] if arg != "--elevated"] + ["--elevated"]
    if is_windows():
        params = " ".join([f'"{arg}"' if " " in arg else arg for arg in args])
        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", gui_python_exe(), params, None, 1)
        if result > 32:
            raise SystemExit(0)
        show_native_error("Administrator rights are required. Elevation was cancelled or failed.")
        raise SystemExit(1)
    if is_linux():
        pkexec = shutil.which("pkexec")
        if pkexec:
            env = [f"DISPLAY={os.environ.get('DISPLAY', '')}", f"XAUTHORITY={os.environ.get('XAUTHORITY', '')}"]
            subprocess.Popen([pkexec, "env"] + env + [sys.executable] + args)
            raise SystemExit(0)
        show_native_error("Root rights are required for USB flashing. Please install/use pkexec or run with sudo.")
        raise SystemExit(1)


elevate_before_everything()

BASE = Path(tempfile.gettempdir()) / "OpenCoreForge_Runtime"
DOWNLOADS = BASE / "downloads"
EXTRACTED = BASE / "extracted"
OUTPUT = BASE / "output"
REPORTS = BASE / "reports"
LOGS = BASE / "logs"
for folder in [BASE, DOWNLOADS, EXTRACTED, OUTPUT, REPORTS, LOGS]:
    folder.mkdir(parents=True, exist_ok=True)

STATE_FILE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "OpenCoreForge_state.json"
CRASH_LOG = LOGS / "crash.log"
GUI_LOG = LOGS / "gui_callback_error.log"
APP_LOG = LOGS / "app.log"

SOURCES = {
    "OpenCorePkg": "https://github.com/acidanthera/OpenCorePkg/releases/download/1.0.7/OpenCore-1.0.7-RELEASE.zip",
    "gibMacOS": "https://github.com/corpnewt/gibMacOS/archive/refs/heads/master.zip",
    "OpCore-Simplify": "https://github.com/lzhoang2801/OpCore-Simplify/archive/refs/heads/main.zip",
    "OpCore-Simplify.py": "https://raw.githubusercontent.com/lzhoang2801/OpCore-Simplify/refs/heads/main/OpCore-Simplify.py",
}

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
        "prepare": "Preparing environment...",
        "ready": "Select USB and macOS, then press FLASH.",
        "ready_save": "Select macOS, then press SAVE.",
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
        "efi": "EFI source",
        "recovery": "Recovery source",
        "browse": "Browse",
        "auto_find": "Auto find",
        "secure": "SecureBootModel",
        "scan": "ScanPolicy",
        "hide": "HideAuxiliary",
        "verbose": "Verbose boot",
        "no_macos": "No macOS selected.",
        "no_usb": "No USB device selected.",
        "no_efi": "No usable EFI folder found or selected.",
        "need_confirm": "Please tick the erase confirmation checkbox first.",
        "working": "Working...",
        "done": "Done.",
        "failed": "Failed.",
        "download_warn": "Some downloads failed. You can still select EFI/Recovery manually.",
        "verify_ok": "Verification passed.",
        "verify_warn": "Verification passed with warnings.",
        "verify_fail": "Verification failed.",
        "cleanup_ask": "Remove temporary downloads, extracted tools and output? Reports/logs stay.",
        "cleanup_done": "Temporary files removed.",
    },
    "de": {
        "choose_language": "Sprache waehlen",
        "prepare": "Umgebung wird vorbereitet...",
        "ready": "USB und macOS waehlen, dann FLASH druecken.",
        "ready_save": "macOS waehlen, dann SPEICHERN druecken.",
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
        "efi": "EFI-Quelle",
        "recovery": "Recovery-Quelle",
        "browse": "Durchsuchen",
        "auto_find": "Automatisch suchen",
        "secure": "SecureBootModel",
        "scan": "ScanPolicy",
        "hide": "HideAuxiliary",
        "verbose": "Verbose Boot",
        "no_macos": "Kein macOS gewaehlt.",
        "no_usb": "Kein USB-Laufwerk gewaehlt.",
        "no_efi": "Kein nutzbarer EFI-Ordner gefunden oder gewaehlt.",
        "need_confirm": "Bitte zuerst das Loesch-Bestaetigungskaestchen aktivieren.",
        "working": "Laeuft...",
        "done": "Fertig.",
        "failed": "Fehlgeschlagen.",
        "download_warn": "Einige Downloads sind fehlgeschlagen. EFI/Recovery kann trotzdem manuell gewaehlt werden.",
        "verify_ok": "Pruefung bestanden.",
        "verify_warn": "Pruefung mit Warnungen bestanden.",
        "verify_fail": "Pruefung fehlgeschlagen.",
        "cleanup_ask": "Temporäre Downloads, extrahierte Tools und Output entfernen? Reports/Logs bleiben.",
        "cleanup_done": "Temporäre Dateien entfernt.",
    },
}


def write_text_file(path, text):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
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
        size = int(value)
    except Exception:
        return str(value)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024


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
        for disk in powershell_json("Get-Disk | Select Number,FriendlyName,Model,Size,BusType,PartitionStyle,IsBoot,IsSystem"):
            if str(disk.get("IsBoot", False)).lower() == "true" or str(disk.get("IsSystem", False)).lower() == "true":
                continue
            if str(disk.get("BusType", "")).lower() in ["usb", "sd", "mmc"]:
                devices.append({"platform": "windows", **disk})
        return devices
    if is_linux():
        devices = []
        try:
            result = subprocess.run(["lsblk", "-J", "-b", "-o", "NAME,MODEL,SIZE,TYPE,TRAN,RM,RO"], capture_output=True, text=True, timeout=30)
            for disk in json.loads(result.stdout).get("blockdevices", []):
                removable = str(disk.get("rm", "0")) == "1"
                usb = str(disk.get("tran", "")).lower() == "usb"
                readonly = str(disk.get("ro", "0")) in ["1", "true", "True"]
                if disk.get("type") == "disk" and (removable or usb) and not readonly:
                    devices.append({"platform": "linux", "Path": "/dev/" + disk.get("name", ""), "Model": disk.get("model") or disk.get("name"), "Size": disk.get("size")})
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
    for level, _message in rows:
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
    write_text_file(CRASH_LOG, traceback.format_exc())
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
        self.download_errors = []
        self.queue = queue.Queue()
        self.load_state()
        self.configure_style()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("520x400")
        self.minsize(500, 360)
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.show_language_page()
        self.after(80, self.drain_queue)

    def report_callback_exception(self, exc, value, tb):
        error_text = "".join(traceback.format_exception(exc, value, tb))
        write_text_file(GUI_LOG, error_text)
        messagebox.showerror(APP_NAME, error_text[-3500:])

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

    def configure_style(self):
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
        self.show_prepare_page()
        threading.Thread(target=self.bootstrap, daemon=True).start()

    def show_prepare_page(self):
        self.clear()
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text=self.text("working")).pack(anchor="w", pady=20)
        progress = ttk.Progressbar(frame, mode="indeterminate")
        progress.pack(fill="x")
        progress.start(8)
        ttk.Label(frame, text=str(BASE), style="Small.TLabel", wraplength=460).pack(anchor="w", pady=10)

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

    def bootstrap(self):
        try:
            report = {"app": APP_NAME, "version": APP_VERSION, "admin": is_admin(), "platform": sys.platform, "workspace": str(BASE)}
            write_text_file(REPORTS / "environment_report.json", json.dumps(report, indent=2))
            self.download_tools()
            self.usb_devices = list_usb_devices()
            self.find_outputs()
        except Exception:
            error_text = traceback.format_exc()
            write_text_file(LOGS / "startup_after_language.log", error_text)
            self.put(messagebox.showerror, APP_NAME, error_text[-3500:])
        self.put(self.show_main_page)

    def download_tools(self):
        for name, url in SOURCES.items():
            ext = ".py" if url.endswith(".py") else ".zip"
            target = DOWNLOADS / ("".join(char if char.isalnum() or char in "-_" else "_" for char in name) + ext)
            if target.exists() and target.stat().st_size > 0:
                continue
            ok, error = self.download(url, target)
            if not ok:
                self.download_errors.append(f"{name}: {error}")
        for archive in DOWNLOADS.glob("*.zip"):
            destination = EXTRACTED / archive.stem
            if destination.exists() and any(destination.iterdir()):
                continue
            destination.mkdir(parents=True, exist_ok=True)
            try:
                with zipfile.ZipFile(archive, "r") as handle:
                    handle.extractall(destination)
            except Exception as error:
                self.download_errors.append(f"extract {archive.name}: {error}")
        if self.download_errors:
            write_text_file(LOGS / "download_errors.log", "\n".join(self.download_errors))

    def download(self, url, target):
        last_error = ""
        for attempt in range(3):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": f"Mozilla/5.0 {APP_NAME}/{APP_VERSION}"})
                with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as output:
                    shutil.copyfileobj(response, output)
                if target.exists() and target.stat().st_size > 0:
                    return True, ""
            except Exception as error:
                last_error = str(error)
                time.sleep(attempt + 1)
        return False, last_error

    def find_outputs(self):
        efis = []
        recoveries = []
        for root in [BASE, Path.home(), Path.cwd()]:
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
        if self.download_errors:
            self.log(self.text("download_warn") + "\n" + "\n".join(self.download_errors))

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
                devices.append(f"{device.get('Path')} | {device.get('Model')} | {human_size(device.get('Size', 0))}")
        self.device_box["values"] = devices
        if devices:
            self.device_var.set(devices[0])
            self.select_device()
        self.macos_box["values"] = MACOS

    def select_device(self):
        index = self.device_box.current()
        self.selected_usb = self.usb_devices[index] if 0 <= index < len(self.usb_devices) else None

    def select_macos(self):
        index = self.macos_box.current()
        self.selected_macos = MACOS[index] if 0 <= index < len(MACOS) else None

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
            if self.verify_var.get():
                self.write_report(target)
            self.put(self.log, self.text("done"))
        except Exception:
            self.handle_error()

    def flash_worker(self):
        try:
            self.put(self.log, self.text("working"))
            target = self.format_usb()
            self.copy_payload(target)
            self.patch_config(target)
            if self.verify_var.get():
                self.write_report(target)
            self.put(self.log, self.text("done"))
        except Exception:
            self.handle_error()

    def copy_payload(self, target):
        target = Path(target)
        efi_out = target / "EFI"
        shutil.rmtree(efi_out, ignore_errors=True)
        shutil.copytree(self.efi_path, efi_out)
        if self.recovery_path and Path(self.recovery_path).exists():
            recovery_out = target / "com.apple.recovery.boot"
            shutil.rmtree(recovery_out, ignore_errors=True)
            shutil.copytree(self.recovery_path, recovery_out)

    def write_report(self, target):
        status, rows = validate_layout(target)
        report = REPORTS / ("validation_" + time.strftime("%Y%m%d_%H%M%S") + ".txt")
        lines = [f"{APP_NAME} {APP_VERSION}", f"Target: {target}", f"macOS: {self.selected_macos}", ""] + [f"[{level}] {msg}" for level, msg in rows]
        write_text_file(report, "\n".join(lines))
        self.put(self.log, "\n".join(lines[-len(rows):]))
        if status == "passed":
            message = self.text("verify_ok")
        elif status == "warnings":
            message = self.text("verify_warn")
        else:
            message = self.text("verify_fail")
        self.put(messagebox.showinfo if status != "failed" else messagebox.showerror, APP_NAME, message + "\n\n" + str(report))

    def format_usb(self):
        if is_windows():
            disk_number = self.selected_usb.get("Number")
            script = BASE / "flash_usb.ps1"
            script.write_text(f"""
$ErrorActionPreference='Stop'
$diskNumber={disk_number}
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
            write_text_file(LOGS / "powershell_flash_stdout.log", result.stdout or "")
            write_text_file(LOGS / "powershell_flash_stderr.log", result.stderr or "")
            self.put(self.log, (result.stdout or "") + "\n" + (result.stderr or ""))
            if result.returncode != 0:
                raise RuntimeError("PowerShell format failed: " + ((result.stderr or result.stdout).strip()[-600:]))
            letters = [item.strip().replace(":", "") for item in result.stdout.splitlines() if item.strip()]
            if not letters:
                raise RuntimeError("No drive letter returned after formatting")
            target = Path(f"{letters[-1]}:/")
            for _ in range(30):
                if target.exists():
                    return target
                time.sleep(0.25)
            raise RuntimeError(f"Drive {letters[-1]}: not available")
        raise RuntimeError("USB flashing is currently implemented for Windows in this startup-safe build")

    def patch_config(self, target):
        config = Path(target) / "EFI" / "OC" / "config.plist"
        if not config.exists():
            return
        try:
            shutil.copy2(config, config.with_suffix(".plist.before_forge"))
            with config.open("rb") as handle:
                data = plistlib.load(handle)
            data.setdefault("Misc", {}).setdefault("Security", {})["SecureBootModel"] = "Disabled"
            data.setdefault("Misc", {}).setdefault("Security", {})["ScanPolicy"] = 0
            data.setdefault("Misc", {}).setdefault("Boot", {})["HideAuxiliary"] = False
            with config.open("wb") as handle:
                plistlib.dump(data, handle)
        except Exception as error:
            self.put(self.log, "config patch skipped: " + str(error))

    def handle_error(self):
        error_text = traceback.format_exc()
        write_text_file(LOGS / "operation_error.log", error_text)
        clean = error_text.splitlines()[-1]
        self.put(self.log, self.text("failed") + ": " + clean)
        self.put(messagebox.showerror, APP_NAME, self.text("failed") + "\n\n" + clean)

    def open_path(self, path):
        if is_windows():
            os.startfile(str(path))
        elif is_linux():
            subprocess.Popen(["xdg-open", str(path)])
        else:
            subprocess.Popen(["open", str(path)])

    def cleanup(self):
        if messagebox.askyesno(APP_NAME, self.text("cleanup_ask")):
            for folder in [DOWNLOADS, EXTRACTED, OUTPUT]:
                shutil.rmtree(folder, ignore_errors=True)
                folder.mkdir(parents=True, exist_ok=True)
            self.log(self.text("done"))

    def close(self):
        self.save_state()
        self.destroy()


if __name__ == "__main__":
    try:
        OpenCoreForge().mainloop()
    except Exception:
        error = traceback.format_exc()
        write_text_file(CRASH_LOG, error)
        show_native_error(error[-3500:])
        print(error)
