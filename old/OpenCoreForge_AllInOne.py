
#!/usr/bin/env python3
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
APP_VERSION = "2.0.0"

SOURCES = {
    "OpCore-Simplify": "https://github.com/lzhoang2801/OpCore-Simplify/archive/refs/heads/main.zip",
    "OpCore-Simplify.py": "https://raw.githubusercontent.com/lzhoang2801/OpCore-Simplify/refs/heads/main/OpCore-Simplify.py",
    "OpenCorePkg": "https://github.com/acidanthera/OpenCorePkg/releases/download/1.0.7/OpenCore-1.0.7-RELEASE.zip",
    "gibMacOS": "https://github.com/corpnewt/gibMacOS/archive/refs/heads/master.zip",
    "USBToolBox": "https://github.com/USBToolBox/tool/releases/latest/download/Windows.zip",
    "USBToolBox.kext": "https://github.com/USBToolBox/kext/releases/latest/download/USBToolBox.kext.zip"
}

MACOS_ITEMS = [
    ("High Sierra", "10.13", "legacy", "Older systems / legacy NVIDIA setups"),
    ("Mojave", "10.14", "legacy", "Older stable baseline"),
    ("Catalina", "10.15", "stable", "Good older Intel baseline"),
    ("Big Sur", "11", "stable", "USB mapping is important"),
    ("Monterey", "12", "recommended", "Often stable for Intel systems"),
    ("Ventura", "13", "modern", "Good with many AMD RX GPUs"),
    ("Sonoma", "14", "modern", "May require additional tuning"),
    ("Sequoia", "15", "current", "Check hardware compatibility carefully"),
    ("Tahoe", "26", "experimental", "Only if tools and hardware are compatible")
]

TR = {
    "en": {
        "start_title": "One-page guided workflow",
        "start_sub": "Preparation and hardware scan run automatically. Select macOS, adjust options if needed, then press Flash.",
        "language": "Language", "mode": "Mode", "real_mode": "Real", "test_mode": "Test",
        "status": "Status", "hardware": "Hardware", "macos": "macOS version", "usb": "USB drive",
        "options": "Advanced options", "flash": "Flash", "refresh": "Refresh drives", "open_workspace": "Open workspace",
        "prepare_running": "Preparing tools and scanning hardware...", "ready": "Ready. Select macOS and USB, then press Flash.",
        "download_tools": "Download/update tools", "scan_hw": "Scan hardware", "auto": "Automatic",
        "secure_boot_model": "SecureBootModel", "scan_policy": "ScanPolicy", "hide_aux": "HideAuxiliary", "verbose": "Verbose boot args",
        "validate_after": "Validate after flash", "erase_warning": "The selected USB drive will be erased. Type ERASE to continue:",
        "cancelled": "Cancelled.", "no_usb": "No USB drive selected.", "no_macos": "No macOS version selected.",
        "admin_required": "Administrator rights are required for real USB flashing.", "test_target": "Test mode target folder",
        "flash_running": "Flashing and validating...", "flash_done": "Flash completed.", "flash_failed": "Flash failed.",
        "missing_build": "No ready EFI/recovery output was found. Build output is required before flashing.",
        "clean_error": "Clean error description", "log": "Log", "choose_folder": "Choose folder", "detected": "Detected",
        "score_good": "Good", "score_possible": "Possible", "score_problem": "Problematic", "score_unknown": "Unknown",
        "efi_source": "EFI source", "recovery_source": "Recovery source", "auto_detect": "Auto-detect", "manual": "Manual",
        "selected": "Selected", "not_found": "Not found", "validation": "Validation", "passed": "Passed", "warnings": "Warnings", "failed": "Failed"
    },
    "de": {
        "start_title": "Geführter Ein-Seiten-Ablauf",
        "start_sub": "Vorbereitung und Hardware-Scan laufen automatisch. macOS wählen, falls nötig Optionen anpassen, dann Flash drücken.",
        "language": "Sprache", "mode": "Modus", "real_mode": "Echt", "test_mode": "Test",
        "status": "Status", "hardware": "Hardware", "macos": "macOS-Version", "usb": "USB-Laufwerk",
        "options": "Erweiterte Optionen", "flash": "Flash", "refresh": "Laufwerke aktualisieren", "open_workspace": "Workspace öffnen",
        "prepare_running": "Tools werden vorbereitet und Hardware wird gescannt...", "ready": "Bereit. macOS und USB wählen, dann Flash drücken.",
        "download_tools": "Tools laden/aktualisieren", "scan_hw": "Hardware scannen", "auto": "Automatisch",
        "secure_boot_model": "SecureBootModel", "scan_policy": "ScanPolicy", "hide_aux": "HideAuxiliary", "verbose": "Verbose Boot-Args",
        "validate_after": "Nach Flash validieren", "erase_warning": "Das gewählte USB-Laufwerk wird gelöscht. Tippe ERASE zum Fortfahren:",
        "cancelled": "Abgebrochen.", "no_usb": "Kein USB-Laufwerk ausgewählt.", "no_macos": "Keine macOS-Version ausgewählt.",
        "admin_required": "Für echtes USB-Flashen sind Administratorrechte nötig.", "test_target": "Testmodus-Zielordner",
        "flash_running": "Flash und Validierung laufen...", "flash_done": "Flash abgeschlossen.", "flash_failed": "Flash fehlgeschlagen.",
        "missing_build": "Keine fertige EFI/Recovery-Ausgabe gefunden. Vor dem Flashen wird ein Build-Output benötigt.",
        "clean_error": "Saubere Fehlerbeschreibung", "log": "Log", "choose_folder": "Ordner wählen", "detected": "Erkannt",
        "score_good": "Gut", "score_possible": "Möglich", "score_problem": "Problematisch", "score_unknown": "Unbekannt",
        "efi_source": "EFI-Quelle", "recovery_source": "Recovery-Quelle", "auto_detect": "Automatisch suchen", "manual": "Manuell",
        "selected": "Ausgewählt", "not_found": "Nicht gefunden", "validation": "Validierung", "passed": "Bestanden", "warnings": "Warnungen", "failed": "Fehlgeschlagen"
    }
}


def safe_base_dir():
    candidates = []
    for env in ("LOCALAPPDATA", "APPDATA", "USERPROFILE", "TEMP", "TMP"):
        v = os.environ.get(env)
        if v:
            candidates.append(Path(v) / "OpenCoreForge")
    candidates.append(Path.home() / "OpenCoreForge")
    candidates.append(Path(tempfile.gettempdir()) / "OpenCoreForge")
    for c in candidates:
        try:
            c.mkdir(parents=True, exist_ok=True)
            t = c / ".write_test"
            t.write_text("ok", encoding="utf-8")
            t.unlink(missing_ok=True)
            return c
        except Exception:
            pass
    raise RuntimeError("No writable workspace found")

BASE = safe_base_dir()
DOWNLOADS = BASE / "downloads"
EXTRACTED = BASE / "extracted"
TOOLS = BASE / "tools"
OUTPUT = BASE / "output"
LOGS = BASE / "logs"
STATE_FILE = BASE / "state.json"
for d in (DOWNLOADS, EXTRACTED, TOOLS, OUTPUT, LOGS):
    d.mkdir(parents=True, exist_ok=True)


def is_windows(): return os.name == "nt"

def is_admin():
    if is_windows():
        try: return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception: return False
    try: return os.geteuid() == 0
    except Exception: return False


def run_ps_json(cmd, timeout=60):
    if not is_windows(): return []
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd + " | ConvertTo-Json -Depth 6"], capture_output=True, text=True, timeout=timeout)
        if not r.stdout.strip(): return []
        data = json.loads(r.stdout)
        return data if isinstance(data, list) else [data]
    except Exception:
        return []


def get_hardware():
    if not is_windows():
        return {"system": [sys.platform], "note": "Hardware scan is optimized for Windows."}
    return {
        "cpu": [x.get("Name", "") for x in run_ps_json("Get-CimInstance Win32_Processor | Select Name,Manufacturer,NumberOfCores,NumberOfLogicalProcessors")],
        "gpu": [x.get("Name", "") for x in run_ps_json("Get-CimInstance Win32_VideoController | Select Name,AdapterRAM,PNPDeviceID")],
        "mainboard": run_ps_json("Get-CimInstance Win32_BaseBoard | Select Manufacturer,Product,Version"),
        "bios": run_ps_json("Get-CimInstance Win32_BIOS | Select Manufacturer,SMBIOSBIOSVersion,ReleaseDate"),
        "disks": run_ps_json("Get-Disk | Select Number,FriendlyName,Model,Size,BusType,PartitionStyle,IsBoot,IsSystem"),
        "network": run_ps_json("Get-CimInstance Win32_NetworkAdapter | ? {$_.PhysicalAdapter -eq $true} | Select Name,Manufacturer,PNPDeviceID"),
        "audio": run_ps_json("Get-CimInstance Win32_SoundDevice | Select Name,Manufacturer,PNPDeviceID")
    }


def list_usb_disks():
    out = []
    for d in run_ps_json("Get-Disk | Select Number,FriendlyName,Model,Size,BusType,PartitionStyle,IsBoot,IsSystem"):
        if str(d.get("IsBoot", False)).lower() == "true" or str(d.get("IsSystem", False)).lower() == "true":
            continue
        if str(d.get("BusType", "")).lower() in ["usb", "sd", "mmc"]:
            out.append(d)
    return out


def human_size(v):
    try: v = int(v)
    except Exception: return str(v)
    units = ["B", "KB", "MB", "GB", "TB"]
    f = float(v)
    for u in units:
        if f < 1024 or u == units[-1]: return f"{f:.1f} {u}"
        f /= 1024


def sha256_file(p, chunk=8*1024*1024):
    h = hashlib.sha256()
    total = 0
    with open(p, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b: break
            total += len(b)
            h.update(b)
    return h.hexdigest(), total


def compatibility(name, hardware):
    t = (" ".join(hardware.get("cpu", [])) + " " + " ".join(hardware.get("gpu", []))).lower()
    if not t.strip(): return "unknown", "Scan pending"
    if ("rtx" in t or "gtx 10" in t or "gtx 16" in t or "nvidia" in t) and name in ["Ventura", "Sonoma", "Sequoia", "Tahoe"]:
        return "problem", "Many newer NVIDIA GPUs are unsuitable"
    if "ryzen" in t or "threadripper" in t:
        return "possible", "AMD requires kernel patches"
    if any(x in t for x in ["rx 560", "rx 570", "rx 580", "rx 590", "rx 5500", "rx 5600", "rx 5700", "rx 6600", "rx 6800", "rx 6900", "radeon pro", "navi"]):
        return "good", "AMD RX/Radeon detected"
    if "intel" in t:
        return "possible", "Intel detected; check iGPU/SMBIOS"
    return "unknown", "No rule matched"


def validate_stick(root):
    root = Path(root)
    items = []
    def add(level, msg): items.append((level, msg))
    def exists(path, label, fail=True):
        if Path(path).exists(): add("OK", label)
        else: add("FAIL" if fail else "WARN", label + " missing")
    exists(root / "EFI", "EFI folder")
    exists(root / "EFI" / "BOOT" / "BOOTx64.efi", "BOOTx64.efi")
    exists(root / "EFI" / "OC" / "config.plist", "config.plist")
    exists(root / "EFI" / "OC" / "Drivers" / "OpenRuntime.efi", "OpenRuntime.efi")
    drivers = root / "EFI" / "OC" / "Drivers"
    hfs = drivers.exists() and any(x.name.lower() in ["hfsplus.efi", "openhfsplus.efi"] for x in drivers.iterdir())
    add("OK" if hfs else "WARN", "HFS driver" + ("" if hfs else " missing"))
    rec = root / "com.apple.recovery.boot"
    exists(rec, "Recovery folder", fail=False)
    if rec.exists():
        exists(rec / "BaseSystem.dmg", "BaseSystem.dmg")
        exists(rec / "BaseSystem.chunklist", "BaseSystem.chunklist", fail=False)
    cfg = root / "EFI" / "OC" / "config.plist"
    if cfg.exists():
        try:
            with cfg.open("rb") as f: pl = plistlib.load(f)
            add("OK", "config.plist parsed")
            sp = pl.get("Misc", {}).get("Security", {}).get("ScanPolicy")
            add("OK" if sp == 0 else "WARN", f"ScanPolicy={sp}")
            ha = pl.get("Misc", {}).get("Boot", {}).get("HideAuxiliary")
            add("OK" if ha is False else "WARN", f"HideAuxiliary={ha}")
        except Exception as e:
            add("FAIL", "config.plist parse failed: " + str(e))
    return items

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog, simpledialog
except Exception as e:
    print("Tkinter is missing:", e)
    raise

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1220x820")
        self.minsize(1060, 700)
        self.queue = queue.Queue()
        self.lang = "en"
        self.mode = "test"
        self.hardware = {}
        self.usb_disks = []
        self.selected_macos = None
        self.selected_disk = None
        self.efi_source = None
        self.recovery_source = None
        self.default_opts = {
            "SecureBootModel": "Disabled",
            "ScanPolicy": "0",
            "HideAuxiliary": "False",
            "Verbose": True,
            "Validate": True
        }
        self.load_state()
        self.setup_style()
        self.build_ui()
        self.after(100, self.drain)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.log(f"Workspace: {BASE}")
        self.autostart()

    def t(self, key): return TR.get(self.lang, TR["en"]).get(key, key)

    def load_state(self):
        try:
            if STATE_FILE.exists():
                s = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                self.lang = s.get("lang", self.lang)
                self.mode = s.get("mode", self.mode)
        except Exception:
            pass

    def save_state(self):
        STATE_FILE.write_text(json.dumps({"lang": self.lang, "mode": self.mode}, indent=2), encoding="utf-8")

    def setup_style(self):
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except Exception: pass
        self.configure(bg="#f3f4f6")
        style.configure("TFrame", background="#f3f4f6")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("TLabel", background="#f3f4f6", foreground="#111827", font=("Segoe UI", 10))
        style.configure("Card.TLabel", background="#ffffff", foreground="#111827", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background="#f3f4f6", foreground="#111827", font=("Segoe UI", 20, "bold"))
        style.configure("Accent.TButton", background="#2563eb", foreground="#ffffff", padding=(14, 9), font=("Segoe UI", 10, "bold"))
        style.configure("Danger.TButton", background="#dc2626", foreground="#ffffff", padding=(14, 9), font=("Segoe UI", 10, "bold"))
        style.configure("TButton", padding=(10, 7), font=("Segoe UI", 10))

    def build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        header = ttk.Frame(self, padding=18)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        self.title_lbl = ttk.Label(header, text=APP_NAME, style="Title.TLabel")
        self.title_lbl.grid(row=0, column=0, sticky="w")
        right = ttk.Frame(header)
        right.grid(row=0, column=1, sticky="e")
        ttk.Label(right, text=self.t("language")).pack(side="left", padx=(0, 6))
        self.lang_var = tk.StringVar(value=self.lang)
        lang_box = ttk.Combobox(right, width=7, textvariable=self.lang_var, values=["en", "de"], state="readonly")
        lang_box.pack(side="left", padx=4)
        lang_box.bind("<<ComboboxSelected>>", lambda e: self.change_lang())
        ttk.Label(right, text=self.t("mode")).pack(side="left", padx=(18, 6))
        self.mode_var = tk.StringVar(value=self.mode)
        mode_box = ttk.Combobox(right, width=8, textvariable=self.mode_var, values=["test", "real"], state="readonly")
        mode_box.pack(side="left", padx=4)
        mode_box.bind("<<ComboboxSelected>>", lambda e: self.change_mode())

        self.banner = tk.Label(self, text="", bg="#dbeafe", fg="#1e40af", padx=16, pady=10, anchor="w", font=("Segoe UI", 10, "bold"))
        self.banner.grid(row=1, column=0, sticky="ew", padx=18)

        main = ttk.Frame(self, padding=18)
        main.grid(row=2, column=0, sticky="nsew")
        main.columnconfigure(0, weight=2)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(1, weight=1)

        left = ttk.Frame(main)
        left.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 12))
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text=self.t("macos"), font=("Segoe UI", 13, "bold")).grid(row=0, column=0, sticky="w")
        self.tile_canvas = tk.Canvas(left, bg="#f3f4f6", highlightthickness=0)
        self.tile_scroll = ttk.Scrollbar(left, orient="vertical", command=self.tile_canvas.yview)
        self.tile_frame = ttk.Frame(self.tile_canvas)
        self.tile_frame.bind("<Configure>", lambda e: self.tile_canvas.configure(scrollregion=self.tile_canvas.bbox("all")))
        self.tile_canvas.create_window((0, 0), window=self.tile_frame, anchor="nw")
        self.tile_canvas.configure(yscrollcommand=self.tile_scroll.set)
        self.tile_canvas.grid(row=1, column=0, sticky="nsew")
        self.tile_scroll.grid(row=1, column=1, sticky="ns")
        left.columnconfigure(0, weight=1)
        self.tile_canvas.bind_all("<MouseWheel>", self.on_mousewheel)

        right_panel = ttk.Frame(main)
        right_panel.grid(row=0, column=1, sticky="nsew")
        self.status_box = tk.Text(right_panel, height=9, bg="#ffffff", relief="flat", font=("Consolas", 9), wrap="word")
        ttk.Label(right_panel, text=self.t("status"), font=("Segoe UI", 13, "bold")).pack(anchor="w")
        self.status_box.pack(fill="x", pady=(4, 12))

        usb_card = ttk.Frame(right_panel, style="Card.TFrame", padding=12)
        usb_card.pack(fill="x", pady=6)
        ttk.Label(usb_card, text=self.t("usb"), style="Card.TLabel", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.usb_var = tk.StringVar()
        self.usb_combo = ttk.Combobox(usb_card, textvariable=self.usb_var, state="readonly")
        self.usb_combo.pack(fill="x", pady=6)
        self.usb_combo.bind("<<ComboboxSelected>>", lambda e: self.select_usb())
        ttk.Button(usb_card, text=self.t("refresh"), command=self.refresh_usb).pack(anchor="w")

        opt_card = ttk.Frame(right_panel, style="Card.TFrame", padding=12)
        opt_card.pack(fill="x", pady=6)
        ttk.Label(opt_card, text=self.t("options"), style="Card.TLabel", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.secure_var = tk.StringVar(value=self.default_opts["SecureBootModel"])
        self.scan_var = tk.StringVar(value=self.default_opts["ScanPolicy"])
        self.hide_var = tk.StringVar(value=self.default_opts["HideAuxiliary"])
        self.verbose_var = tk.BooleanVar(value=self.default_opts["Verbose"])
        self.validate_var = tk.BooleanVar(value=self.default_opts["Validate"])
        self.form_row(opt_card, self.t("secure_boot_model"), self.secure_var, ["Disabled", "Default"])
        self.form_row(opt_card, self.t("scan_policy"), self.scan_var, ["0", "Default"])
        self.form_row(opt_card, self.t("hide_aux"), self.hide_var, ["False", "True"])
        ttk.Checkbutton(opt_card, text=self.t("verbose"), variable=self.verbose_var).pack(anchor="w", pady=2)
        ttk.Checkbutton(opt_card, text=self.t("validate_after"), variable=self.validate_var).pack(anchor="w", pady=2)
        ttk.Button(opt_card, text=self.t("auto_detect"), command=self.autodetect_outputs).pack(anchor="w", pady=(8, 0))
        ttk.Button(opt_card, text=self.t("efi_source"), command=self.pick_efi).pack(anchor="w", pady=2)
        ttk.Button(opt_card, text=self.t("recovery_source"), command=self.pick_recovery).pack(anchor="w", pady=2)

        self.flash_btn = ttk.Button(right_panel, text=self.t("flash"), style="Accent.TButton", command=self.flash)
        self.flash_btn.pack(fill="x", pady=12)
        ttk.Button(right_panel, text=self.t("open_workspace"), command=self.open_workspace).pack(fill="x")

        log_frame = ttk.Frame(self, padding=(18, 0, 18, 18))
        log_frame.grid(row=3, column=0, sticky="nsew")
        log_frame.rowconfigure(1, weight=1)
        log_frame.columnconfigure(0, weight=1)
        ttk.Label(log_frame, text=self.t("log"), font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")
        self.log_box = tk.Text(log_frame, height=10, bg="#111827", fg="#e5e7eb", insertbackground="#ffffff", relief="flat", font=("Consolas", 9), wrap="word")
        self.log_box.grid(row=1, column=0, sticky="nsew")
        self.render_tiles()
        self.set_banner(self.t("prepare_running"), "info")

    def form_row(self, parent, label, var, values):
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label, style="Card.TLabel").pack(side="left")
        ttk.Combobox(row, textvariable=var, values=values, width=12, state="readonly").pack(side="right")

    def change_lang(self):
        self.lang = self.lang_var.get()
        self.save_state()
        self.rebuild()

    def change_mode(self):
        self.mode = self.mode_var.get()
        self.save_state()
        self.log(f"Mode: {self.mode}")

    def rebuild(self):
        for w in self.winfo_children(): w.destroy()
        self.build_ui()
        self.log("Language changed")
        self.update_status()

    def set_banner(self, text, mode="info"):
        colors = {"info": ("#dbeafe", "#1e40af"), "ok": ("#dcfce7", "#166534"), "warn": ("#fef3c7", "#92400e"), "err": ("#fee2e2", "#991b1b")}
        bg, fg = colors.get(mode, colors["info"])
        self.banner.config(text=text, bg=bg, fg=fg)

    def q(self, fn, *args): self.queue.put((fn, args))

    def drain(self):
        try:
            while True:
                fn, args = self.queue.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.after(100, self.drain)

    def run_task(self, title, fn):
        def worker():
            self.q(self.set_banner, title, "info")
            try:
                fn()
            except Exception:
                err = traceback.format_exc()
                self.q(self.log, err)
                self.q(self.set_banner, self.t("flash_failed") + " " + self.t("clean_error") + ": " + err.splitlines()[-1], "err")
        threading.Thread(target=worker, daemon=True).start()

    def log(self, msg):
        line = time.strftime("[%H:%M:%S] ") + str(msg) + "\n"
        self.log_box.insert("end", line)
        self.log_box.see("end")
        try:
            (LOGS / "app.log").open("a", encoding="utf-8").write(line)
        except Exception:
            pass

    def status(self, msg):
        self.status_box.insert("end", str(msg) + "\n")
        self.status_box.see("end")

    def update_status(self):
        self.status_box.delete("1.0", "end")
        self.status(f"{self.t('mode')}: {self.mode}")
        self.status(f"Admin: {is_admin()}")
        cpu = ", ".join(self.hardware.get("cpu", [])) if self.hardware else "-"
        gpu = ", ".join(self.hardware.get("gpu", [])) if self.hardware else "-"
        self.status(f"CPU: {cpu}")
        self.status(f"GPU: {gpu}")
        if self.selected_macos:
            self.status(f"{self.t('selected')}: macOS {self.selected_macos[0]} {self.selected_macos[1]}")
        if self.efi_source:
            self.status(f"EFI: {self.efi_source}")
        if self.recovery_source:
            self.status(f"Recovery: {self.recovery_source}")

    def autostart(self):
        self.run_task(self.t("prepare_running"), self.prepare_and_scan)

    def prepare_and_scan(self):
        self.download_tools()
        self.hardware = get_hardware()
        self.usb_disks = list_usb_disks()
        self.q(self.populate_usb)
        self.q(self.render_tiles)
        self.q(self.update_status)
        self.q(self.autodetect_outputs)
        self.q(self.set_banner, self.t("ready"), "ok")
        self.q(self.log, "Automatic preparation completed")

    def download_tools(self):
        for name, url in SOURCES.items():
            ext = ".py" if url.endswith(".py") else ".zip"
            target = DOWNLOADS / (self.clean_name(name) + ext)
            if target.exists() and target.stat().st_size > 0:
                self.q(self.log, f"Already exists: {target.name}")
                continue
            self.q(self.log, f"Downloading {name}")
            with urllib.request.urlopen(url, timeout=90) as r, target.open("wb") as f:
                shutil.copyfileobj(r, f)
        for z in DOWNLOADS.glob("*.zip"):
            dest = EXTRACTED / z.stem
            if dest.exists() and any(dest.iterdir()): continue
            dest.mkdir(parents=True, exist_ok=True)
            try:
                with zipfile.ZipFile(z, "r") as zipf: zipf.extractall(dest)
                self.q(self.log, f"Extracted {z.name}")
            except Exception as e:
                self.q(self.log, f"Extraction failed {z.name}: {e}")
        raw = DOWNLOADS / "OpCore-Simplify_py.py"
        if raw.exists(): shutil.copy2(raw, TOOLS / "OpCore-Simplify.py")

    def clean_name(self, s): return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)

    def populate_usb(self):
        values = []
        for d in self.usb_disks:
            values.append(f"Disk {d.get('Number')} | {d.get('FriendlyName')} | {human_size(d.get('Size', 0))} | {d.get('BusType')}")
        self.usb_combo["values"] = values
        if values and not self.usb_var.get():
            self.usb_var.set(values[0])
            self.select_usb()

    def refresh_usb(self):
        def work():
            self.usb_disks = list_usb_disks()
            self.q(self.populate_usb)
            self.q(self.log, f"USB drives: {len(self.usb_disks)}")
        self.run_task(self.t("refresh"), work)

    def select_usb(self):
        idx = self.usb_combo.current()
        if idx >= 0 and idx < len(self.usb_disks):
            self.selected_disk = self.usb_disks[idx]
            self.update_status()

    def on_mousewheel(self, event):
        try:
            self.tile_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def render_tiles(self):
        for w in self.tile_frame.winfo_children(): w.destroy()
        for i, item in enumerate(MACOS_ITEMS):
            name, ver, tag, desc = item
            score, reason = compatibility(name, self.hardware)
            score_key = {"good": "score_good", "possible": "score_possible", "problem": "score_problem", "unknown": "score_unknown"}.get(score, "score_unknown")
            card = ttk.Frame(self.tile_frame, style="Card.TFrame", padding=14)
            card.grid(row=i//2, column=i%2, sticky="nsew", padx=8, pady=8)
            self.tile_frame.columnconfigure(i%2, weight=1)
            ttk.Label(card, text=f"macOS {name}", style="Card.TLabel", font=("Segoe UI", 14, "bold")).pack(anchor="w")
            ttk.Label(card, text=f"{ver} · {tag}", style="Card.TLabel", foreground="#475569").pack(anchor="w")
            ttk.Label(card, text=f"{self.t(score_key)} — {reason}", style="Card.TLabel", wraplength=360).pack(anchor="w", pady=6)
            ttk.Label(card, text=desc, style="Card.TLabel", wraplength=360).pack(anchor="w")
            ttk.Button(card, text=self.t("selected") if self.selected_macos == item else self.t("macos"), style="Accent.TButton", command=lambda it=item: self.select_macos(it)).pack(anchor="w", pady=(10,0))

    def select_macos(self, item):
        self.selected_macos = item
        self.log(f"Selected macOS {item[0]} {item[1]}")
        self.render_tiles()
        self.update_status()

    def autodetect_outputs(self):
        efis, recs = [], []
        roots = [BASE, Path.home(), Path.cwd()]
        for root in roots:
            try:
                for p in root.rglob("EFI"):
                    if (p / "OC" / "config.plist").exists(): efis.append(p)
                for p in root.rglob("com.apple.recovery.boot"):
                    if (p / "BaseSystem.dmg").exists() or (p / "BaseSystem.chunklist").exists(): recs.append(p)
            except Exception:
                pass
        if efis:
            self.efi_source = sorted(efis, key=lambda x: len(str(x)))[0]
        if recs:
            self.recovery_source = sorted(recs, key=lambda x: len(str(x)))[0]
        self.update_status()

    def pick_efi(self):
        p = filedialog.askdirectory(title=self.t("efi_source"))
        if p: self.efi_source = Path(p); self.update_status()

    def pick_recovery(self):
        p = filedialog.askdirectory(title=self.t("recovery_source"))
        if p: self.recovery_source = Path(p); self.update_status()

    def flash(self):
        if not self.selected_macos:
            messagebox.showwarning(APP_NAME, self.t("no_macos")); return
        if self.mode == "real" and not self.selected_disk:
            messagebox.showwarning(APP_NAME, self.t("no_usb")); return
        if self.mode == "real" and is_windows() and not is_admin():
            messagebox.showerror(APP_NAME, self.t("admin_required")); return
        confirm = "ERASE"
        if self.mode == "real":
            val = simpledialog.askstring(APP_NAME, self.t("erase_warning"))
            if val != confirm:
                self.log(self.t("cancelled")); return
        self.run_task(self.t("flash_running"), self.flash_worker)

    def flash_worker(self):
        if not self.efi_source or not self.efi_source.exists():
            self.q(self.set_banner, self.t("missing_build"), "err")
            self.q(self.log, self.t("missing_build"))
            return
        if self.mode == "test":
            target = OUTPUT / "test_stick"
            if target.exists(): shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)
            self.q(self.log, f"{self.t('test_target')}: {target}")
        else:
            target = self.prepare_real_usb()
        dst_efi = target / "EFI"
        if dst_efi.exists(): shutil.rmtree(dst_efi)
        shutil.copytree(self.efi_source, dst_efi)
        if self.recovery_source and self.recovery_source.exists():
            dst_rec = target / "com.apple.recovery.boot"
            if dst_rec.exists(): shutil.rmtree(dst_rec)
            shutil.copytree(self.recovery_source, dst_rec)
        self.apply_default_config(target)
        if self.validate_var.get():
            items = validate_stick(target)
            report = []
            status = "passed"
            for level, msg in items:
                report.append(f"[{level}] {msg}")
                if level == "FAIL": status = "failed"
                elif level == "WARN" and status != "failed": status = "warnings"
            (target / "validation_report.txt").write_text("\n".join(report), encoding="utf-8")
            self.q(self.log, "\n".join(report))
            self.q(self.set_banner, f"{self.t('flash_done')} {self.t('validation')}: {self.t(status)}", "ok" if status == "passed" else "warn" if status == "warnings" else "err")
        else:
            self.q(self.set_banner, self.t("flash_done"), "ok")

    def prepare_real_usb(self):
        letter = "O"
        disk_num = self.selected_disk.get("Number")
        script = f"select disk {disk_num}\ndetail disk\nclean\nconvert gpt\ncreate partition primary\nformat fs=fat32 quick label=OPENCORE\nassign letter={letter}\nexit\n"
        sp = BASE / "diskpart_flash.txt"
        sp.write_text(script, encoding="utf-8")
        r = subprocess.run(["diskpart", "/s", str(sp)], capture_output=True, text=True, errors="replace")
        self.q(self.log, r.stdout + "\n" + r.stderr)
        if r.returncode != 0:
            raise RuntimeError("diskpart failed")
        target = Path(f"{letter}:/")
        if not target.exists():
            raise RuntimeError(f"Drive {letter}: not found after formatting")
        return target

    def apply_default_config(self, target):
        cfg = target / "EFI" / "OC" / "config.plist"
        if not cfg.exists(): return
        backup = cfg.with_suffix(".plist.before_forge")
        shutil.copy2(cfg, backup)
        try:
            with cfg.open("rb") as f: pl = plistlib.load(f)
            pl.setdefault("Misc", {}).setdefault("Security", {})["SecureBootModel"] = self.secure_var.get()
            if self.scan_var.get() == "0": pl.setdefault("Misc", {}).setdefault("Security", {})["ScanPolicy"] = 0
            pl.setdefault("Misc", {}).setdefault("Boot", {})["HideAuxiliary"] = (self.hide_var.get() == "True")
            if self.verbose_var.get():
                nv = pl.setdefault("NVRAM", {}).setdefault("Add", {}).setdefault("7C436110-AB2A-4BBB-A880-FE41995C9F82", {})
                args = str(nv.get("boot-args", ""))
                for x in ["-v", "keepsyms=1", "debug=0x100"]:
                    if x not in args.split(): args = (x + " " + args).strip()
                nv["boot-args"] = args
            with cfg.open("wb") as f: plistlib.dump(pl, f)
        except Exception as e:
            self.q(self.log, f"config patch skipped: {e}")

    def open_workspace(self):
        if is_windows(): os.startfile(str(BASE))
        else: subprocess.Popen(["xdg-open", str(BASE)])

    def on_close(self):
        self.save_state()
        self.destroy()

if __name__ == "__main__":
    try:
        App().mainloop()
    except Exception:
        err = traceback.format_exc()
        (LOGS / "crash.log").write_text(err, encoding="utf-8")
        try:
            if is_windows(): ctypes.windll.user32.MessageBoxW(None, err[-3000:], APP_NAME, 0x10)
        except Exception:
            pass
        print(err)
