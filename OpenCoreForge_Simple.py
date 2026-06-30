
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
APP_VERSION = "3.0.0-simple"
WORKSPACE_NAME = "OpenCoreForge"

SOURCES = {
    "OpCore-Simplify": "https://github.com/lzhoang2801/OpCore-Simplify/archive/refs/heads/main.zip",
    "OpCore-Simplify.py": "https://raw.githubusercontent.com/lzhoang2801/OpCore-Simplify/refs/heads/main/OpCore-Simplify.py",
    "OpenCorePkg": "https://github.com/acidanthera/OpenCorePkg/releases/download/1.0.7/OpenCore-1.0.7-RELEASE.zip",
    "gibMacOS": "https://github.com/corpnewt/gibMacOS/archive/refs/heads/master.zip",
    "USBToolBox": "https://github.com/USBToolBox/tool/releases/latest/download/Windows.zip",
    "USBToolBox.kext": "https://github.com/USBToolBox/kext/releases/latest/download/USBToolBox.kext.zip"
}

MACOS_ITEMS = [
    ("High Sierra", "10.13", "Legacy", "Older systems / legacy NVIDIA setups"),
    ("Mojave", "10.14", "Legacy", "Older stable baseline"),
    ("Catalina", "10.15", "Stable", "Good older Intel baseline"),
    ("Big Sur", "11", "Stable", "USB mapping is important"),
    ("Monterey", "12", "Recommended", "Often stable for Intel systems"),
    ("Ventura", "13", "Modern", "Good with many AMD RX GPUs"),
    ("Sonoma", "14", "Modern", "May require additional tuning"),
    ("Sequoia", "15", "Current", "Check hardware compatibility carefully"),
    ("Tahoe", "26", "Experimental", "Only if tools and hardware are compatible")
]

TXT = {
    "en": {
        "title": "OpenCore Forge", "subtitle": "Select macOS, select USB, press Flash.",
        "language": "Language", "mode": "Mode", "test": "Test", "real": "Real",
        "macos": "macOS", "usb": "USB drive", "refresh": "Refresh",
        "flash": "Flash", "advanced": "Advanced", "log": "Log",
        "status_preparing": "Preparing automatically: downloading tools, scanning hardware, finding USB drives...",
        "status_ready": "Ready. Select macOS and USB, then press Flash.",
        "status_flashing": "Flashing...", "status_done": "Done.", "status_failed": "Failed.",
        "admin_needed": "Administrator rights are required for real USB flashing. Windows will ask for permission.",
        "erase_prompt": "The selected USB drive will be erased. Type ERASE to continue:",
        "cancelled": "Cancelled.", "select_macos": "Select a macOS version.", "select_usb": "Select a USB drive.",
        "no_build": "No finished EFI folder was found. Create or select an EFI source first.",
        "choose_efi": "Choose EFI folder", "choose_recovery": "Choose Recovery folder", "auto_find": "Auto-find EFI/Recovery",
        "open_workspace": "Open workspace", "test_output": "Test output folder", "validation": "Validation",
        "passed": "PASSED", "warnings": "PASSED WITH WARNINGS", "failed": "FAILED",
        "admin_restart": "Restart as administrator", "safe_default": "Safe defaults enabled",
        "efi": "EFI", "recovery": "Recovery", "detected": "Detected", "not_found": "Not found",
        "clean_error": "Clean error", "selected": "Selected", "recommended": "Recommended",
        "options": "Options", "secureboot": "SecureBootModel", "scanpolicy": "ScanPolicy", "hideaux": "HideAuxiliary", "verbose": "Verbose boot", "validate": "Auto test after flash"
    },
    "de": {
        "title": "OpenCore Forge", "subtitle": "macOS wählen, USB wählen, Flash drücken.",
        "language": "Sprache", "mode": "Modus", "test": "Test", "real": "Echt",
        "macos": "macOS", "usb": "USB-Laufwerk", "refresh": "Aktualisieren",
        "flash": "Flash", "advanced": "Erweitert", "log": "Log",
        "status_preparing": "Automatische Vorbereitung: Tools laden, Hardware scannen, USB-Laufwerke finden...",
        "status_ready": "Bereit. macOS und USB wählen, dann Flash drücken.",
        "status_flashing": "Flash läuft...", "status_done": "Fertig.", "status_failed": "Fehlgeschlagen.",
        "admin_needed": "Für echtes USB-Flashen sind Administratorrechte nötig. Windows fragt nach Berechtigung.",
        "erase_prompt": "Das gewählte USB-Laufwerk wird gelöscht. Tippe ERASE zum Fortfahren:",
        "cancelled": "Abgebrochen.", "select_macos": "Wähle eine macOS-Version.", "select_usb": "Wähle ein USB-Laufwerk.",
        "no_build": "Kein fertiger EFI-Ordner gefunden. Erstelle oder wähle zuerst eine EFI-Quelle.",
        "choose_efi": "EFI-Ordner wählen", "choose_recovery": "Recovery-Ordner wählen", "auto_find": "EFI/Recovery automatisch suchen",
        "open_workspace": "Workspace öffnen", "test_output": "Test-Ausgabeordner", "validation": "Test",
        "passed": "BESTANDEN", "warnings": "BESTANDEN MIT WARNUNGEN", "failed": "FEHLGESCHLAGEN",
        "admin_restart": "Als Administrator neu starten", "safe_default": "Sichere Defaults aktiv",
        "efi": "EFI", "recovery": "Recovery", "detected": "Erkannt", "not_found": "Nicht gefunden",
        "clean_error": "Saubere Fehlerbeschreibung", "selected": "Ausgewählt", "recommended": "Empfohlen",
        "options": "Optionen", "secureboot": "SecureBootModel", "scanpolicy": "ScanPolicy", "hideaux": "HideAuxiliary", "verbose": "Verbose Boot", "validate": "Nach Flash automatisch testen"
    }
}

def is_windows():
    return os.name == "nt"

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

def relaunch_admin():
    if not is_windows() or is_admin():
        return False
    try:
        params = " ".join([f'"{a}"' if " " in a else a for a in sys.argv])
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        return True
    except Exception:
        return False

def safe_base():
    candidates = []
    for env in ["LOCALAPPDATA", "APPDATA", "USERPROFILE", "TEMP", "TMP"]:
        v = os.environ.get(env)
        if v:
            candidates.append(Path(v) / WORKSPACE_NAME)
    candidates += [Path.home() / WORKSPACE_NAME, Path(tempfile.gettempdir()) / WORKSPACE_NAME]
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

BASE = safe_base()
DOWNLOADS = BASE / "downloads"
EXTRACTED = BASE / "extracted"
TOOLS = BASE / "tools"
OUTPUT = BASE / "output"
LOGS = BASE / "logs"
STATE = BASE / "state.json"
for p in [DOWNLOADS, EXTRACTED, TOOLS, OUTPUT, LOGS]:
    p.mkdir(parents=True, exist_ok=True)

def run_ps_json(cmd, timeout=60):
    if not is_windows():
        return []
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd + " | ConvertTo-Json -Depth 6"], capture_output=True, text=True, timeout=timeout)
        if not r.stdout.strip():
            return []
        data = json.loads(r.stdout)
        return data if isinstance(data, list) else [data]
    except Exception:
        return []

def get_hardware():
    if not is_windows():
        return {"cpu": [sys.platform], "gpu": [], "disks": []}
    return {
        "cpu": [x.get("Name", "") for x in run_ps_json("Get-CimInstance Win32_Processor | Select Name,Manufacturer,NumberOfCores,NumberOfLogicalProcessors")],
        "gpu": [x.get("Name", "") for x in run_ps_json("Get-CimInstance Win32_VideoController | Select Name,AdapterRAM,PNPDeviceID")],
        "mainboard": run_ps_json("Get-CimInstance Win32_BaseBoard | Select Manufacturer,Product,Version"),
        "disks": run_ps_json("Get-Disk | Select Number,FriendlyName,Model,Size,BusType,PartitionStyle,IsBoot,IsSystem")
    }

def list_usb():
    out = []
    for d in run_ps_json("Get-Disk | Select Number,FriendlyName,Model,Size,BusType,PartitionStyle,IsBoot,IsSystem"):
        if str(d.get("IsBoot", False)).lower() == "true" or str(d.get("IsSystem", False)).lower() == "true":
            continue
        if str(d.get("BusType", "")).lower() in ["usb", "sd", "mmc"]:
            out.append(d)
    return out

def size(v):
    try:
        v = int(v)
    except Exception:
        return str(v)
    units = ["B", "KB", "MB", "GB", "TB"]
    f = float(v)
    for u in units:
        if f < 1024 or u == units[-1]:
            return f"{f:.1f} {u}"
        f /= 1024

def score_macos(name, hw):
    text = (" ".join(hw.get("cpu", [])) + " " + " ".join(hw.get("gpu", []))).lower()
    if not text.strip():
        return "?", "Unknown"
    if ("rtx" in text or "gtx 10" in text or "gtx 16" in text or "nvidia" in text) and name in ["Ventura", "Sonoma", "Sequoia", "Tahoe"]:
        return "!", "NVIDIA risk"
    if "ryzen" in text or "threadripper" in text:
        return "~", "AMD patches needed"
    if any(x in text for x in ["rx 560", "rx 570", "rx 580", "rx 590", "rx 5500", "rx 5600", "rx 5700", "rx 6600", "rx 6800", "rx 6900", "radeon pro", "navi"]):
        return "+", "AMD GPU detected"
    if "intel" in text:
        return "+", "Intel detected"
    return "?", "Check manually"

def validate_target(root):
    root = Path(root)
    results = []
    def add(level, msg): results.append((level, msg))
    def check(p, label, fail=True):
        add("OK" if Path(p).exists() else ("FAIL" if fail else "WARN"), label if Path(p).exists() else label + " missing")
    check(root / "EFI", "EFI folder")
    check(root / "EFI" / "BOOT" / "BOOTx64.efi", "BOOTx64.efi")
    check(root / "EFI" / "OC" / "config.plist", "config.plist")
    check(root / "EFI" / "OC" / "Drivers" / "OpenRuntime.efi", "OpenRuntime.efi")
    drivers = root / "EFI" / "OC" / "Drivers"
    hfs = drivers.exists() and any(x.name.lower() in ["hfsplus.efi", "openhfsplus.efi"] for x in drivers.iterdir())
    add("OK" if hfs else "WARN", "HFS driver" if hfs else "HFS driver missing")
    rec = root / "com.apple.recovery.boot"
    check(rec, "Recovery folder", fail=False)
    if rec.exists():
        check(rec / "BaseSystem.dmg", "BaseSystem.dmg")
        check(rec / "BaseSystem.chunklist", "BaseSystem.chunklist", fail=False)
        dmg = rec / "BaseSystem.dmg"
        if dmg.exists():
            h = hashlib.sha256()
            with dmg.open("rb") as f:
                for chunk in iter(lambda: f.read(8*1024*1024), b""):
                    h.update(chunk)
            add("OK", "BaseSystem.dmg SHA256 " + h.hexdigest())
    cfg = root / "EFI" / "OC" / "config.plist"
    if cfg.exists():
        try:
            with cfg.open("rb") as f:
                pl = plistlib.load(f)
            add("OK", "config.plist parsed")
            sp = pl.get("Misc", {}).get("Security", {}).get("ScanPolicy")
            add("OK" if sp == 0 else "WARN", f"ScanPolicy={sp}")
            ha = pl.get("Misc", {}).get("Boot", {}).get("HideAuxiliary")
            add("OK" if ha is False else "WARN", f"HideAuxiliary={ha}")
        except Exception as e:
            add("FAIL", "config.plist parse failed: " + str(e))
    status = "passed"
    for lvl, _ in results:
        if lvl == "FAIL":
            status = "failed"
            break
        if lvl == "WARN" and status != "failed":
            status = "warnings"
    return status, results

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, simpledialog, filedialog
except Exception as e:
    print("Tkinter missing", e)
    raise

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.lang = "en"
        self.mode = "test"
        self.hw = {}
        self.usb = []
        self.selected_macos = None
        self.selected_usb = None
        self.efi = None
        self.recovery = None
        self.queue = queue.Queue()
        self.load_state()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1180x760")
        self.minsize(980, 640)
        self.style()
        self.ui()
        self.after(100, self.drain)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.log("Workspace: " + str(BASE))
        self.auto_prepare()

    def tr(self, k): return TXT[self.lang].get(k, k)
    def load_state(self):
        try:
            if STATE.exists():
                s = json.loads(STATE.read_text(encoding="utf-8"))
                self.lang = s.get("lang", self.lang)
                self.mode = s.get("mode", self.mode)
        except Exception: pass
    def save_state(self):
        STATE.write_text(json.dumps({"lang": self.lang, "mode": self.mode}, indent=2), encoding="utf-8")
    def style(self):
        st = ttk.Style(self)
        try: st.theme_use("clam")
        except Exception: pass
        self.configure(bg="#f3f4f6")
        st.configure("TFrame", background="#f3f4f6")
        st.configure("Card.TFrame", background="#ffffff")
        st.configure("TLabel", background="#f3f4f6", foreground="#111827", font=("Segoe UI", 10))
        st.configure("Card.TLabel", background="#ffffff", foreground="#111827", font=("Segoe UI", 10))
        st.configure("Title.TLabel", background="#f3f4f6", foreground="#111827", font=("Segoe UI", 22, "bold"))
        st.configure("Accent.TButton", background="#2563eb", foreground="#ffffff", padding=(16, 10), font=("Segoe UI", 11, "bold"))
        st.configure("Danger.TButton", background="#dc2626", foreground="#ffffff", padding=(16, 10), font=("Segoe UI", 11, "bold"))
        st.configure("TButton", padding=(10, 7), font=("Segoe UI", 10))
    def ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        top = ttk.Frame(self, padding=18)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text=self.tr("title"), style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(top, text=self.tr("subtitle")).grid(row=1, column=0, sticky="w")
        right = ttk.Frame(top)
        right.grid(row=0, column=1, rowspan=2, sticky="e")
        self.lang_var = tk.StringVar(value=self.lang)
        ttk.Label(right, text=self.tr("language")).pack(side="left", padx=4)
        lb = ttk.Combobox(right, width=5, textvariable=self.lang_var, values=["en", "de"], state="readonly")
        lb.pack(side="left", padx=4)
        lb.bind("<<ComboboxSelected>>", lambda e: self.change_language())
        self.mode_var = tk.StringVar(value=self.mode)
        ttk.Label(right, text=self.tr("mode")).pack(side="left", padx=(16, 4))
        mb = ttk.Combobox(right, width=7, textvariable=self.mode_var, values=["test", "real"], state="readonly")
        mb.pack(side="left", padx=4)
        mb.bind("<<ComboboxSelected>>", lambda e: self.change_mode())
        if is_windows() and not is_admin():
            ttk.Button(right, text=self.tr("admin_restart"), command=self.admin_restart).pack(side="left", padx=(16, 0))
        self.banner = tk.Label(self, text="", bg="#dbeafe", fg="#1e40af", anchor="w", padx=16, pady=10, font=("Segoe UI", 10, "bold"))
        self.banner.grid(row=1, column=0, sticky="ew", padx=18)
        main = ttk.Frame(self, padding=18)
        main.grid(row=2, column=0, sticky="nsew")
        main.columnconfigure(0, weight=2)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)
        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text=self.tr("macos"), font=("Segoe UI", 13, "bold")).grid(row=0, column=0, sticky="w")
        self.canvas = tk.Canvas(left, bg="#f3f4f6", highlightthickness=0)
        self.scroll = ttk.Scrollbar(left, orient="vertical", command=self.canvas.yview)
        self.tiles = ttk.Frame(self.canvas)
        self.tiles.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0,0), window=self.tiles, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.scroll.grid(row=1, column=1, sticky="ns")
        self.canvas.bind_all("<MouseWheel>", self.mousewheel)
        rightp = ttk.Frame(main)
        rightp.grid(row=0, column=1, sticky="nsew")
        self.status = tk.Text(rightp, height=9, bg="#ffffff", relief="flat", font=("Consolas", 9), wrap="word")
        self.status.pack(fill="x", pady=(0, 10))
        card = ttk.Frame(rightp, style="Card.TFrame", padding=12)
        card.pack(fill="x", pady=6)
        ttk.Label(card, text=self.tr("usb"), style="Card.TLabel", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.usb_var = tk.StringVar()
        self.usb_combo = ttk.Combobox(card, textvariable=self.usb_var, state="readonly")
        self.usb_combo.pack(fill="x", pady=6)
        self.usb_combo.bind("<<ComboboxSelected>>", lambda e: self.select_usb())
        ttk.Button(card, text=self.tr("refresh"), command=self.refresh_usb).pack(anchor="w")
        adv = ttk.LabelFrame(rightp, text=self.tr("advanced"), padding=10)
        adv.pack(fill="x", pady=6)
        self.secure = tk.StringVar(value="Disabled")
        self.scan = tk.StringVar(value="0")
        self.hide = tk.StringVar(value="False")
        self.verbose = tk.BooleanVar(value=True)
        self.valid = tk.BooleanVar(value=True)
        self.row(adv, self.tr("secureboot"), self.secure, ["Disabled", "Default"])
        self.row(adv, self.tr("scanpolicy"), self.scan, ["0", "Default"])
        self.row(adv, self.tr("hideaux"), self.hide, ["False", "True"])
        ttk.Checkbutton(adv, text=self.tr("verbose"), variable=self.verbose).pack(anchor="w")
        ttk.Checkbutton(adv, text=self.tr("validate"), variable=self.valid).pack(anchor="w")
        ttk.Button(adv, text=self.tr("auto_find"), command=self.autofind).pack(anchor="w", pady=(8, 2))
        ttk.Button(adv, text=self.tr("choose_efi"), command=self.pick_efi).pack(anchor="w", pady=2)
        ttk.Button(adv, text=self.tr("choose_recovery"), command=self.pick_recovery).pack(anchor="w", pady=2)
        ttk.Button(rightp, text=self.tr("flash"), style="Accent.TButton", command=self.flash).pack(fill="x", pady=10)
        ttk.Button(rightp, text=self.tr("open_workspace"), command=self.open_workspace).pack(fill="x")
        bottom = ttk.Frame(self, padding=(18, 0, 18, 18))
        bottom.grid(row=3, column=0, sticky="nsew")
        bottom.columnconfigure(0, weight=1)
        ttk.Label(bottom, text=self.tr("log"), font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")
        self.logbox = tk.Text(bottom, height=9, bg="#111827", fg="#e5e7eb", relief="flat", font=("Consolas", 9), wrap="word")
        self.logbox.grid(row=1, column=0, sticky="nsew")
        self.render_tiles()
        self.set_banner(self.tr("status_preparing"), "info")
    def row(self, parent, label, var, vals):
        f = ttk.Frame(parent)
        f.pack(fill="x", pady=2)
        ttk.Label(f, text=label).pack(side="left")
        ttk.Combobox(f, textvariable=var, values=vals, state="readonly", width=12).pack(side="right")
    def change_language(self):
        self.lang = self.lang_var.get(); self.save_state(); self.rebuild()
    def change_mode(self):
        self.mode = self.mode_var.get(); self.save_state(); self.update_status()
    def rebuild(self):
        for w in self.winfo_children(): w.destroy()
        self.ui(); self.update_status(); self.populate_usb()
    def set_banner(self, text, mode="info"):
        colors = {"info": ("#dbeafe", "#1e40af"), "ok": ("#dcfce7", "#166534"), "warn": ("#fef3c7", "#92400e"), "err": ("#fee2e2", "#991b1b")}
        bg, fg = colors.get(mode, colors["info"])
        self.banner.config(text=text, bg=bg, fg=fg)
    def log(self, msg):
        line = time.strftime("[%H:%M:%S] ") + str(msg) + "\n"
        self.logbox.insert("end", line); self.logbox.see("end")
        try:
            with (LOGS / "app.log").open("a", encoding="utf-8") as f: f.write(line)
        except Exception: pass
    def q(self, fn, *args): self.queue.put((fn,args))
    def drain(self):
        try:
            while True:
                fn,args = self.queue.get_nowait(); fn(*args)
        except queue.Empty: pass
        self.after(100, self.drain)
    def task(self, name, fn):
        def run():
            self.q(self.set_banner, name, "info")
            try: fn()
            except Exception:
                err = traceback.format_exc()
                self.q(self.log, err)
                self.q(self.set_banner, self.tr("status_failed") + " " + self.tr("clean_error") + ": " + err.splitlines()[-1], "err")
        threading.Thread(target=run, daemon=True).start()
    def admin_restart(self):
        if relaunch_admin(): self.destroy()
    def auto_prepare(self): self.task(self.tr("status_preparing"), self.prepare)
    def prepare(self):
        self.download()
        self.hw = get_hardware()
        self.usb = list_usb()
        self.q(self.populate_usb)
        self.q(self.autofind)
        self.q(self.render_tiles)
        self.q(self.update_status)
        self.q(self.set_banner, self.tr("status_ready"), "ok")
    def download(self):
        for name, url in SOURCES.items():
            ext = ".py" if url.endswith(".py") else ".zip"
            target = DOWNLOADS / ("".join(c if c.isalnum() or c in "-_" else "_" for c in name) + ext)
            if not target.exists() or target.stat().st_size == 0:
                self.q(self.log, "Downloading " + name)
                with urllib.request.urlopen(url, timeout=90) as r, target.open("wb") as f: shutil.copyfileobj(r,f)
        for z in DOWNLOADS.glob("*.zip"):
            dest = EXTRACTED / z.stem
            if dest.exists() and any(dest.iterdir()): continue
            dest.mkdir(parents=True, exist_ok=True)
            try:
                with zipfile.ZipFile(z,"r") as zipf: zipf.extractall(dest)
            except Exception as e: self.q(self.log, f"Extract failed {z.name}: {e}")
    def populate_usb(self):
        vals = [f"Disk {d.get('Number')} | {d.get('FriendlyName')} | {size(d.get('Size',0))} | {d.get('BusType')}" for d in self.usb]
        self.usb_combo["values"] = vals
        if vals and not self.usb_var.get(): self.usb_var.set(vals[0]); self.select_usb()
    def refresh_usb(self):
        def work(): self.usb = list_usb(); self.q(self.populate_usb); self.q(self.update_status)
        self.task(self.tr("refresh"), work)
    def select_usb(self):
        i = self.usb_combo.current()
        if 0 <= i < len(self.usb): self.selected_usb = self.usb[i]; self.update_status()
    def render_tiles(self):
        for w in self.tiles.winfo_children(): w.destroy()
        for i,item in enumerate(MACOS_ITEMS):
            name, ver, tag, desc = item
            mark, reason = score_macos(name, self.hw)
            card = ttk.Frame(self.tiles, style="Card.TFrame", padding=14)
            card.grid(row=i//2, column=i%2, sticky="nsew", padx=8, pady=8)
            self.tiles.columnconfigure(i%2, weight=1)
            ttk.Label(card, text=f"macOS {name}", style="Card.TLabel", font=("Segoe UI", 14, "bold")).pack(anchor="w")
            ttk.Label(card, text=f"{ver} · {tag} · {mark} {reason}", style="Card.TLabel").pack(anchor="w")
            ttk.Label(card, text=desc, style="Card.TLabel", wraplength=360).pack(anchor="w", pady=6)
            ttk.Button(card, text=self.tr("selected") if self.selected_macos == item else self.tr("macos"), style="Accent.TButton", command=lambda x=item:self.select_macos(x)).pack(anchor="w")
    def select_macos(self,item): self.selected_macos=item; self.render_tiles(); self.update_status()
    def mousewheel(self,e):
        try: self.canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        except Exception: pass
    def update_status(self):
        self.status.delete("1.0","end")
        self.status.insert("end", f"{self.tr('mode')}: {self.mode}\nAdmin: {is_admin()}\n")
        self.status.insert("end", "CPU: " + (", ".join(self.hw.get("cpu",[])) if self.hw else "-") + "\n")
        self.status.insert("end", "GPU: " + (", ".join(self.hw.get("gpu",[])) if self.hw else "-") + "\n")
        if self.selected_macos: self.status.insert("end", f"macOS: {self.selected_macos[0]} {self.selected_macos[1]}\n")
        if self.selected_usb: self.status.insert("end", f"USB: Disk {self.selected_usb.get('Number')} {self.selected_usb.get('FriendlyName')}\n")
        self.status.insert("end", f"{self.tr('efi')}: {self.efi if self.efi else self.tr('not_found')}\n")
        self.status.insert("end", f"{self.tr('recovery')}: {self.recovery if self.recovery else self.tr('not_found')}\n")
    def autofind(self):
        efis=[]; recs=[]
        for root in [BASE, Path.home(), Path.cwd()]:
            try:
                for p in root.rglob("EFI"):
                    if (p/"OC"/"config.plist").exists(): efis.append(p)
                for p in root.rglob("com.apple.recovery.boot"):
                    if (p/"BaseSystem.dmg").exists() or (p/"BaseSystem.chunklist").exists(): recs.append(p)
            except Exception: pass
        if efis: self.efi = sorted(efis, key=lambda x: len(str(x)))[0]
        if recs: self.recovery = sorted(recs, key=lambda x: len(str(x)))[0]
        self.update_status()
    def pick_efi(self):
        p = filedialog.askdirectory(title=self.tr("choose_efi"))
        if p: self.efi=Path(p); self.update_status()
    def pick_recovery(self):
        p = filedialog.askdirectory(title=self.tr("choose_recovery"))
        if p: self.recovery=Path(p); self.update_status()
    def flash(self):
        if not self.selected_macos: messagebox.showwarning(APP_NAME, self.tr("select_macos")); return
        if not self.efi or not Path(self.efi).exists(): messagebox.showerror(APP_NAME, self.tr("no_build")); return
        if self.mode == "real":
            if not self.selected_usb: messagebox.showwarning(APP_NAME, self.tr("select_usb")); return
            if is_windows() and not is_admin():
                if messagebox.askyesno(APP_NAME, self.tr("admin_needed")):
                    self.admin_restart()
                return
            if simpledialog.askstring(APP_NAME, self.tr("erase_prompt")) != "ERASE": self.log(self.tr("cancelled")); return
        self.task(self.tr("status_flashing"), self.flash_worker)
    def flash_worker(self):
        if self.mode == "test":
            target = OUTPUT / "test_stick"
            if target.exists(): shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)
            self.q(self.log, self.tr("test_output") + ": " + str(target))
        else:
            target = self.format_usb()
        dst = target / "EFI"
        if dst.exists(): shutil.rmtree(dst)
        shutil.copytree(self.efi, dst)
        if self.recovery and Path(self.recovery).exists():
            rdst = target / "com.apple.recovery.boot"
            if rdst.exists(): shutil.rmtree(rdst)
            shutil.copytree(self.recovery, rdst)
        self.patch_config(target)
        if self.valid.get():
            status, items = validate_target(target)
            lines = [f"[{a}] {b}" for a,b in items]
            (target/"validation_report.txt").write_text("\n".join(lines), encoding="utf-8")
            self.q(self.log, "\n".join(lines))
            word = self.tr("passed") if status=="passed" else self.tr("warnings") if status=="warnings" else self.tr("failed")
            self.q(self.set_banner, self.tr("status_done") + " " + self.tr("validation") + ": " + word, "ok" if status=="passed" else "warn" if status=="warnings" else "err")
        else:
            self.q(self.set_banner, self.tr("status_done"), "ok")
    def format_usb(self):
        letter="O"
        n=self.selected_usb.get("Number")
        script=f"select disk {n}\ndetail disk\nclean\nconvert gpt\ncreate partition primary\nformat fs=fat32 quick label=OPENCORE\nassign letter={letter}\nexit\n"
        sp=BASE/"diskpart_flash.txt"; sp.write_text(script,encoding="utf-8")
        r=subprocess.run(["diskpart","/s",str(sp)], capture_output=True, text=True, errors="replace")
        self.q(self.log, r.stdout + "\n" + r.stderr)
        if r.returncode != 0: raise RuntimeError("diskpart failed")
        target=Path(f"{letter}:/")
        if not target.exists(): raise RuntimeError("drive letter not available after format")
        return target
    def patch_config(self,target):
        cfg=target/"EFI"/"OC"/"config.plist"
        if not cfg.exists(): return
        try:
            shutil.copy2(cfg, cfg.with_suffix(".plist.before_forge"))
            with cfg.open("rb") as f: pl=plistlib.load(f)
            pl.setdefault("Misc",{}).setdefault("Security",{})["SecureBootModel"]=self.secure.get()
            if self.scan.get()=="0": pl.setdefault("Misc",{}).setdefault("Security",{})["ScanPolicy"]=0
            pl.setdefault("Misc",{}).setdefault("Boot",{})["HideAuxiliary"]=(self.hide.get()=="True")
            if self.verbose.get():
                nv=pl.setdefault("NVRAM",{}).setdefault("Add",{}).setdefault("7C436110-AB2A-4BBB-A880-FE41995C9F82",{})
                args=str(nv.get("boot-args",""))
                for x in ["-v","keepsyms=1","debug=0x100"]:
                    if x not in args.split(): args=(x+" "+args).strip()
                nv["boot-args"]=args
            with cfg.open("wb") as f: plistlib.dump(pl,f)
        except Exception as e: self.q(self.log, "config patch skipped: "+str(e))
    def open_workspace(self):
        if is_windows(): os.startfile(str(BASE))
        else: subprocess.Popen(["xdg-open", str(BASE)])
    def close(self): self.save_state(); self.destroy()

if __name__ == "__main__":
    try:
        App().mainloop()
    except Exception:
        err=traceback.format_exc()
        (LOGS/"crash.log").write_text(err, encoding="utf-8")
        try:
            if is_windows(): ctypes.windll.user32.MessageBoxW(None, err[-3000:], APP_NAME, 0x10)
        except Exception: pass
        print(err)
