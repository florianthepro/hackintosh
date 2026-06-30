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
APP_VERSION = "1.1.0-stable"


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


def gui_python():
    if not is_windows():
        return sys.executable
    p = Path(sys.executable).with_name("pythonw.exe")
    return str(p if p.exists() else Path(sys.executable))


def native_message(text):
    try:
        if is_windows():
            ctypes.windll.user32.MessageBoxW(None, str(text), APP_NAME, 0x10)
        else:
            print(text)
    except Exception:
        print(text)


def elevate_first():
    if is_admin() or "--no-admin" in sys.argv or "--elevated" in sys.argv:
        return
    script = str(Path(sys.argv[0]).resolve())
    args = [script] + [a for a in sys.argv[1:] if a != "--elevated"] + ["--elevated"]
    if is_windows():
        params = " ".join([f'"{a}"' if " " in a else a for a in args])
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", gui_python(), params, None, 1)
        if rc > 32:
            raise SystemExit(0)
        native_message("Administratorrechte sind erforderlich. / Administrator rights are required.")
        raise SystemExit(1)
    if is_linux():
        pkexec = shutil.which("pkexec")
        if pkexec:
            env = [f"DISPLAY={os.environ.get('DISPLAY','')}", f"XAUTHORITY={os.environ.get('XAUTHORITY','')}"]
            subprocess.Popen([pkexec, "env"] + env + [sys.executable] + args)
            raise SystemExit(0)
        native_message("Root-Rechte sind erforderlich. / Root rights are required.")
        raise SystemExit(1)


elevate_first()

BASE = Path(tempfile.gettempdir()) / "OpenCoreForge_Runtime"
LOGS = BASE / "logs"
REPORTS = BASE / "reports"
for d in (BASE, LOGS, REPORTS):
    d.mkdir(parents=True, exist_ok=True)
APP_LOG = LOGS / "app.log"
CRASH_LOG = LOGS / "crash.log"
CALLBACK_LOG = LOGS / "gui_callback_error.log"
STATE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "OpenCoreForge_state.json"

MACOS = [
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
    "de": {
        "title": "OpenCore Forge",
        "choose": "Sprache waehlen",
        "device": "USB-Stick",
        "macos": "macOS",
        "efi": "EFI-Ordner",
        "recovery": "Recovery-Ordner",
        "browse": "Waehlen",
        "refresh": "Aktualisieren",
        "save_folder": "In Ordner speichern statt USB flashen",
        "verify": "Nachher pruefen",
        "confirm": "Ich verstehe, dass der USB-Stick geloescht wird",
        "flash": "FLASH",
        "save": "SPEICHERN",
        "reports": "Reports",
        "ready": "USB und macOS waehlen. EFI ggf. waehlen. Danach FLASH.",
        "ready_save": "macOS und EFI waehlen. Danach SPEICHERN.",
        "no_usb": "Kein USB-Stick gewaehlt.",
        "no_macos": "Kein macOS gewaehlt.",
        "no_efi": "Kein EFI-Ordner gewaehlt oder gefunden.",
        "need_confirm": "Bitte zuerst das Loesch-Bestaetigungskaestchen aktivieren.",
        "working": "Laeuft...",
        "done": "Fertig.",
        "failed": "Fehlgeschlagen.",
        "check_ok": "Pruefung bestanden.",
        "check_warn": "Pruefung mit Warnungen bestanden.",
        "check_fail": "Pruefung fehlgeschlagen.",
    },
    "en": {
        "title": "OpenCore Forge",
        "choose": "Choose language",
        "device": "USB drive",
        "macos": "macOS",
        "efi": "EFI folder",
        "recovery": "Recovery folder",
        "browse": "Browse",
        "refresh": "Refresh",
        "save_folder": "Save to folder instead of flashing USB",
        "verify": "Verify afterwards",
        "confirm": "I understand the selected USB drive will be erased",
        "flash": "FLASH",
        "save": "SAVE",
        "reports": "Reports",
        "ready": "Select USB and macOS. Select EFI if needed. Then press FLASH.",
        "ready_save": "Select macOS and EFI. Then press SAVE.",
        "no_usb": "No USB drive selected.",
        "no_macos": "No macOS selected.",
        "no_efi": "No EFI folder selected or found.",
        "need_confirm": "Please tick the erase confirmation checkbox first.",
        "working": "Working...",
        "done": "Done.",
        "failed": "Failed.",
        "check_ok": "Verification passed.",
        "check_warn": "Verification passed with warnings.",
        "check_fail": "Verification failed.",
    }
}


def log_line(text):
    try:
        with APP_LOG.open("a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + str(text) + "\n")
    except Exception:
        pass


def write_file(path, text):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(text), encoding="utf-8")
    except Exception:
        pass


def human_size(value):
    try:
        n = int(value)
    except Exception:
        return str(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024


def run_ps_json(command):
    if not is_windows():
        return []
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command + " | ConvertTo-Json -Depth 5"],
            capture_output=True, text=True, timeout=60
        )
        if not r.stdout.strip():
            return []
        data = json.loads(r.stdout)
        return data if isinstance(data, list) else [data]
    except Exception:
        return []


def list_usb():
    if is_windows():
        result = []
        for d in run_ps_json("Get-Disk | Select Number,FriendlyName,Model,Size,BusType,IsBoot,IsSystem,OperationalStatus"):
            if str(d.get("IsBoot", False)).lower() == "true" or str(d.get("IsSystem", False)).lower() == "true":
                continue
            if str(d.get("BusType", "")).lower() in ("usb", "sd", "mmc"):
                result.append({"platform": "windows", **d})
        return result
    if is_linux():
        result = []
        try:
            r = subprocess.run(["lsblk", "-J", "-b", "-o", "NAME,MODEL,SIZE,TYPE,TRAN,RM,RO"], capture_output=True, text=True, timeout=30)
            data = json.loads(r.stdout) if r.stdout.strip() else {}
            for d in data.get("blockdevices", []):
                removable = str(d.get("rm", "0")) == "1"
                usb = str(d.get("tran", "")).lower() == "usb"
                readonly = str(d.get("ro", "0")) in ("1", "true", "True")
                if d.get("type") == "disk" and (removable or usb) and not readonly:
                    result.append({"platform": "linux", "path": "/dev/" + d.get("name", ""), "model": d.get("model") or d.get("name"), "size": d.get("size")})
        except Exception:
            pass
        return result
    return []


def validate(target):
    target = Path(target)
    rows = []
    def add(level, msg): rows.append((level, msg))
    def chk(path, label, fail=True):
        add("OK" if Path(path).exists() else ("FAIL" if fail else "WARN"), label if Path(path).exists() else label + " missing")
    chk(target / "EFI", "EFI")
    chk(target / "EFI" / "BOOT" / "BOOTx64.efi", "BOOTx64.efi")
    chk(target / "EFI" / "OC" / "config.plist", "config.plist")
    chk(target / "EFI" / "OC" / "Drivers" / "OpenRuntime.efi", "OpenRuntime.efi")
    rec = target / "com.apple.recovery.boot"
    chk(rec, "Recovery", False)
    if rec.exists():
        chk(rec / "BaseSystem.dmg", "BaseSystem.dmg")
        chk(rec / "BaseSystem.chunklist", "BaseSystem.chunklist", False)
    cfg = target / "EFI" / "OC" / "config.plist"
    if cfg.exists():
        try:
            with cfg.open("rb") as f:
                plistlib.load(f)
            add("OK", "config.plist parsed")
        except Exception as e:
            add("FAIL", "config.plist parse failed: " + str(e))
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
    write_file(CRASH_LOG, traceback.format_exc())
    raise


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.lang = "de"
        self.usb = []
        self.selected_usb = None
        self.selected_macos = None
        self.efi = None
        self.recovery = None
        self.queue = queue.Queue()
        self.load_state()
        self.setup_style()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("500x390")
        self.minsize(480, 360)
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.show_language()
        self.after(100, self.drain)

    def report_callback_exception(self, exc, val, tb):
        err = "".join(traceback.format_exception(exc, val, tb))
        write_file(CALLBACK_LOG, err)
        messagebox.showerror(APP_NAME, err[-3500:])

    def load_state(self):
        try:
            state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
            self.lang = state.get("lang", self.lang)
        except Exception:
            pass

    def save_state(self):
        try:
            STATE.write_text(json.dumps({"lang": self.lang}, indent=2), encoding="utf-8")
        except Exception:
            pass

    def t(self, key):
        return TEXT.get(self.lang, TEXT["de"]).get(key, key)

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
        for w in self.winfo_children():
            w.destroy()

    def show_language(self):
        self.clear()
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text="Choose language / Sprache waehlen", style="Small.TLabel").pack(anchor="w", pady=(0, 22))
        row = ttk.Frame(frame)
        row.pack(expand=True)
        ttk.Button(row, text="Deutsch", command=lambda: self.start("de")).pack(side="left", padx=10, ipadx=10, ipady=8)
        ttk.Button(row, text="English", command=lambda: self.start("en")).pack(side="left", padx=10, ipadx=10, ipady=8)

    def start(self, lang):
        self.lang = lang
        self.save_state()
        self.usb = list_usb()
        self.find_outputs()
        self.show_main()

    def put(self, func, *args):
        self.queue.put((func, args))

    def drain(self):
        try:
            while True:
                func, args = self.queue.get_nowait()
                func(*args)
        except queue.Empty:
            pass
        self.after(100, self.drain)

    def find_outputs(self):
        efis = []
        recs = []
        for root in (BASE, Path.home(), Path.cwd()):
            try:
                for p in root.rglob("EFI"):
                    if (p / "OC" / "config.plist").exists():
                        efis.append(p)
                for p in root.rglob("com.apple.recovery.boot"):
                    if (p / "BaseSystem.dmg").exists() or (p / "BaseSystem.chunklist").exists():
                        recs.append(p)
            except Exception:
                pass
        self.efi = sorted(efis, key=lambda x: len(str(x)))[0] if efis else None
        self.recovery = sorted(recs, key=lambda x: len(str(x)))[0] if recs else None

    def show_main(self):
        self.clear()
        main = ttk.Frame(self, padding=10)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text=APP_NAME, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.subtitle = ttk.Label(main, text=self.t("ready"), style="Small.TLabel")
        self.subtitle.grid(row=1, column=0, sticky="w", pady=(0, 6))

        form = ttk.Frame(main)
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text=self.t("device")).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.device_var = tk.StringVar()
        self.device_box = ttk.Combobox(form, textvariable=self.device_var, state="readonly", width=36)
        self.device_box.grid(row=0, column=1, sticky="ew", pady=4)
        self.device_box.bind("<<ComboboxSelected>>", lambda _e: self.select_device())
        ttk.Button(form, text=self.t("refresh"), command=self.refresh_usb).grid(row=0, column=2, padx=3)

        ttk.Label(form, text=self.t("macos")).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.macos_var = tk.StringVar()
        self.macos_box = ttk.Combobox(form, textvariable=self.macos_var, state="readonly", width=36)
        self.macos_box.grid(row=1, column=1, sticky="ew", pady=4)
        self.macos_box.bind("<<ComboboxSelected>>", lambda _e: self.select_macos())

        self.adv_open = tk.BooleanVar(False)
        self.adv_btn = ttk.Checkbutton(main, text="▼ " + self.t("advanced"), variable=self.adv_open, command=self.toggle_adv)
        self.adv_btn.grid(row=3, column=0, sticky="w", pady=(5, 0))
        self.adv = ttk.Frame(main)
        self.save_folder = tk.BooleanVar(False)
        self.secure = tk.StringVar(value="Disabled")
        self.scan = tk.StringVar(value="0")
        self.hide = tk.StringVar(value="False")
        self.verbose = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.adv, text=self.t("save_to_folder"), variable=self.save_folder, command=self.update_button).grid(row=0, column=0, columnspan=3, sticky="w")
        self.option(1, self.t("secure"), self.secure, ["Disabled", "Default"])
        self.option(2, self.t("scan"), self.scan, ["0", "Default"])
        self.option(3, self.t("hide"), self.hide, ["False", "True"])
        ttk.Checkbutton(self.adv, text=self.t("verbose"), variable=self.verbose).grid(row=4, column=1, sticky="w")
        ttk.Label(self.adv, text=self.t("efi")).grid(row=5, column=0, sticky="w")
        self.efi_label = ttk.Label(self.adv, text=str(self.efi) if self.efi else "-", width=26)
        self.efi_label.grid(row=5, column=1, sticky="ew")
        ttk.Button(self.adv, text=self.t("browse"), command=self.pick_efi).grid(row=5, column=2, padx=3)
        ttk.Label(self.adv, text=self.t("recovery")).grid(row=6, column=0, sticky="w")
        self.rec_label = ttk.Label(self.adv, text=str(self.recovery) if self.recovery else "-", width=26)
        self.rec_label.grid(row=6, column=1, sticky="ew")
        ttk.Button(self.adv, text=self.t("browse"), command=self.pick_recovery).grid(row=6, column=2, padx=3)

        self.status = tk.Text(main, height=6, width=54, bg="#111827", fg="#e5e7eb", relief="flat", font=("Consolas", 8), wrap="word")
        self.status.grid(row=5, column=0, sticky="nsew", pady=(7, 6))
        main.rowconfigure(5, weight=1)

        bottom = ttk.Frame(main)
        bottom.grid(row=6, column=0, sticky="ew")
        bottom.columnconfigure(1, weight=1)
        self.verify = tk.BooleanVar(True)
        self.confirm = tk.BooleanVar(False)
        checks = ttk.Frame(bottom)
        checks.grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(checks, text=self.t("verify"), variable=self.verify).pack(anchor="w")
        ttk.Checkbutton(checks, text=self.t("confirm"), variable=self.confirm).pack(anchor="w")
        ttk.Button(bottom, text=self.t("reports"), command=lambda: self.open_path(REPORTS)).grid(row=0, column=1, sticky="e", padx=2)
        self.flash_button = ttk.Button(bottom, text=self.t("flash"), style="Flash.TButton", command=self.flash)
        self.flash_button.grid(row=0, column=2, sticky="e")

        self.populate()
        self.log(self.t("ready"))

    def option(self, row, label, var, values):
        ttk.Label(self.adv, text=label).grid(row=row, column=0, sticky="w")
        ttk.Combobox(self.adv, textvariable=var, values=values, state="readonly", width=14).grid(row=row, column=1, sticky="w")

    def toggle_adv(self):
        if self.adv_open.get():
            self.adv.grid(row=4, column=0, sticky="ew", pady=2)
            self.adv_btn.config(text="▲ " + self.t("advanced"))
        else:
            self.adv.grid_remove()
            self.adv_btn.config(text="▼ " + self.t("advanced"))

    def update_button(self):
        if self.save_folder.get():
            self.flash_button.config(text=self.t("save"))
            self.subtitle.config(text=self.t("ready_save"))
        else:
            self.flash_button.config(text=self.t("flash"))
            self.subtitle.config(text=self.t("ready"))

    def refresh_usb(self):
        self.usb = list_usb()
        self.populate()
        self.log("USB refreshed")

    def populate(self):
        values = []
        for d in self.usb:
            if d.get("platform") == "windows":
                values.append(f"Disk {d.get('Number')} | {d.get('FriendlyName')} | {human_size(d.get('Size', 0))}")
            else:
                values.append(f"{d.get('path')} | {d.get('model')} | {human_size(d.get('size', 0))}")
        self.device_box["values"] = values
        if values:
            self.device_var.set(values[0])
            self.select_device()
        self.macos_box["values"] = MACOS_CHOICES

    def select_device(self):
        idx = self.device_box.current()
        self.selected_usb = self.usb[idx] if 0 <= idx < len(self.usb) else None

    def select_macos(self):
        idx = self.macos_box.current()
        self.selected_macos = MACOS_CHOICES[idx] if 0 <= idx < len(MACOS_CHOICES) else None

    def pick_efi(self):
        path = filedialog.askdirectory(title=self.t("efi"))
        if path:
            self.efi = Path(path)
            self.efi_label.config(text=str(self.efi))

    def pick_recovery(self):
        path = filedialog.askdirectory(title=self.t("recovery"))
        if path:
            self.recovery = Path(path)
            self.rec_label.config(text=str(self.recovery))

    def log(self, msg):
        line = time.strftime("[%H:%M:%S] ") + str(msg) + "\n"
        self.status.insert("end", line)
        self.status.see("end")
        log_line(msg)

    def flash(self):
        if not self.selected_macos:
            messagebox.showwarning(APP_NAME, self.t("no_macos")); return
        if not self.efi or not Path(self.efi).exists():
            messagebox.showerror(APP_NAME, self.t("no_efi")); return
        if self.save_folder.get():
            folder = filedialog.askdirectory(title=self.t("save_to_folder"))
            if folder:
                threading.Thread(target=lambda: self.save_to_folder(Path(folder)), daemon=True).start()
            return
        if not self.selected_usb:
            messagebox.showwarning(APP_NAME, self.t("no_usb")); return
        if not self.confirm.get():
            messagebox.showwarning(APP_NAME, self.t("need_confirm")); return
        threading.Thread(target=self.flash_worker, daemon=True).start()

    def save_to_folder(self, target):
        try:
            self.put(self.log, self.t("working"))
            self.copy_payload(target)
            self.patch_config(target)
            if self.verify.get(): self.write_report(target)
            self.put(self.log, self.t("done"))
        except Exception:
            self.handle_error()

    def flash_worker(self):
        try:
            self.put(self.log, self.t("working"))
            target = self.format_usb()
            self.copy_payload(target)
            self.patch_config(target)
            if self.verify.get(): self.write_report(target)
            self.put(self.log, self.t("done"))
        except Exception:
            self.handle_error()

    def copy_payload(self, target):
        target = Path(target)
        out = target / "EFI"
        shutil.rmtree(out, ignore_errors=True)
        shutil.copytree(self.efi, out)
        if self.recovery and Path(self.recovery).exists():
            rec = target / "com.apple.recovery.boot"
            shutil.rmtree(rec, ignore_errors=True)
            shutil.copytree(self.recovery, rec)

    def write_report(self, target):
        status, rows = validate(target)
        report = REPORTS / ("validation_" + time.strftime("%Y%m%d_%H%M%S") + ".txt")
        lines = [f"{APP_NAME} {APP_VERSION}", f"Target: {target}", f"macOS: {self.selected_macos}", ""] + [f"[{a}] {b}" for a,b in rows]
        write_file(report, "\n".join(lines))
        self.put(self.log, "\n".join(lines[-len(rows):]))
        msg = self.t("verify_ok") if status == "passed" else self.t("verify_warn") if status == "warnings" else self.t("verify_fail")
        self.put(messagebox.showinfo if status != "failed" else messagebox.showerror, APP_NAME, msg + "\n\n" + str(report))

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
            write_file(LOGS / "powershell_flash_stdout.log", result.stdout or "")
            write_file(LOGS / "powershell_flash_stderr.log", result.stderr or "")
            self.put(self.log, (result.stdout or "") + "\n" + (result.stderr or ""))
            if result.returncode != 0:
                raise RuntimeError("PowerShell format failed: " + ((result.stderr or result.stdout).strip()[-600:]))
            letters = [x.strip().replace(":", "") for x in result.stdout.splitlines() if x.strip()]
            if not letters:
                raise RuntimeError("No drive letter returned after formatting")
            drive = Path(f"{letters[-1]}:/")
            for _ in range(30):
                if drive.exists(): return drive
                time.sleep(0.25)
            raise RuntimeError(f"Drive {letters[-1]}: not available")
        raise RuntimeError("USB flashing is implemented for Windows only in this build")

    def patch_config(self, target):
        cfg = Path(target) / "EFI" / "OC" / "config.plist"
        if not cfg.exists(): return
        try:
            shutil.copy2(cfg, cfg.with_suffix(".plist.before_forge"))
            with cfg.open("rb") as f: data = plistlib.load(f)
            data.setdefault("Misc", {}).setdefault("Security", {})["SecureBootModel"] = self.secure.get()
            if self.scan.get() == "0": data.setdefault("Misc", {}).setdefault("Security", {})["ScanPolicy"] = 0
            data.setdefault("Misc", {}).setdefault("Boot", {})["HideAuxiliary"] = self.hide.get() == "True"
            with cfg.open("wb") as f: plistlib.dump(data, f)
        except Exception as e:
            self.put(self.log, "config patch skipped: " + str(e))

    def handle_error(self):
        err = traceback.format_exc()
        write_file(LOGS / "operation_error.log", err)
        clean = err.splitlines()[-1]
        self.put(self.log, self.t("failed") + ": " + clean)
        self.put(messagebox.showerror, APP_NAME, self.t("failed") + "\n\n" + clean)

    def open_path(self, path):
        if is_windows(): os.startfile(str(path))
        elif is_linux(): subprocess.Popen(["xdg-open", str(path)])
        else: subprocess.Popen(["open", str(path)])

    def close(self):
        self.save_state()
        self.destroy()


if __name__ == "__main__":
    try:
        App().mainloop()
    except Exception:
        error = traceback.format_exc()
        write_file(CRASH_LOG, error)
        native_error(error[-3500:])
        print(error)
