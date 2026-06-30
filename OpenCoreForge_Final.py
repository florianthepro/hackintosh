
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenCore Forge
Cross-platform GUI assistant for preparing an OpenCore/macOS recovery USB layout.

Supported host platforms:
- Windows 10/11: USB flashing via diskpart, automatic UAC elevation, GUI-only elevated relaunch when pythonw.exe is available.
- Linux: USB flashing via lsblk/parted/mkfs.vfat/mount, automatic pkexec/sudo elevation when available.

Important:
- The tool uses a temporary workspace under the OS temp directory.
- Downloads are best-effort and retryable. A failed download does not crash the UI.
- If "Save to folder" is enabled, only EFI and com.apple.recovery.boot are copied to the selected folder.
"""

from __future__ import annotations

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
APP_VERSION = "4.0.0"
APP_ID = "opencore-forge"

SOURCES = {
    "OpCore-Simplify": "https://github.com/lzhoang2801/OpCore-Simplify/archive/refs/heads/main.zip",
    "OpCore-Simplify.py": "https://raw.githubusercontent.com/lzhoang2801/OpCore-Simplify/refs/heads/main/OpCore-Simplify.py",
    "OpenCorePkg": "https://github.com/acidanthera/OpenCorePkg/releases/download/1.0.7/OpenCore-1.0.7-RELEASE.zip",
    "gibMacOS": "https://github.com/corpnewt/gibMacOS/archive/refs/heads/master.zip",
    "USBToolBox": "https://github.com/USBToolBox/tool/releases/latest/download/Windows.zip",
    "USBToolBox.kext": "https://github.com/USBToolBox/kext/releases/latest/download/USBToolBox.kext.zip",
}

MACOS_CHOICES = [
    ("macOS High Sierra", "10.13", "Legacy"),
    ("macOS Mojave", "10.14", "Legacy"),
    ("macOS Catalina", "10.15", "Stable"),
    ("macOS Big Sur", "11", "Stable"),
    ("macOS Monterey", "12", "Recommended"),
    ("macOS Ventura", "13", "Modern"),
    ("macOS Sonoma", "14", "Modern"),
    ("macOS Sequoia", "15", "Current"),
    ("macOS Tahoe", "26", "Experimental"),
]

TEXT = {
    "en": {
        "choose_language": "Choose language / Sprache wählen",
        "preparing": "Preparing temporary environment, reports, downloads and device scan...",
        "ready": "Ready. Select a device and macOS, then press FLASH.",
        "ready_save": "Ready. Select macOS, then press SAVE.",
        "device": "Device",
        "macos": "macOS",
        "advanced": "Advanced options",
        "save_folder": "Save to folder instead of flashing USB",
        "verify": "Verify after flash/save",
        "flash": "FLASH",
        "save": "SAVE",
        "cleanup": "Cleanup",
        "workspace": "Workspace",
        "reports": "Reports",
        "efi": "EFI source",
        "recovery": "Recovery source",
        "browse": "Browse",
        "auto_find": "Auto find",
        "secure": "SecureBootModel",
        "scan": "ScanPolicy",
        "hide": "HideAuxiliary",
        "verbose": "Verbose boot",
        "no_macos": "No macOS version selected.",
        "no_device": "No USB device selected.",
        "no_efi": "No usable EFI folder was found or selected.",
        "erase": "The selected USB drive will be erased. Type ERASE to continue:",
        "cancelled": "Cancelled.",
        "flashing": "Flashing...",
        "saving": "Saving EFI and Recovery folder...",
        "done": "Done.",
        "failed": "Failed.",
        "clean_error": "Clean error description",
        "download_warn": "Some downloads failed. The tool remains usable; missing components may need manual selection.",
        "admin_failed": "Administrator elevation failed or was cancelled.",
        "verify_ok": "Verification passed.",
        "verify_warn": "Verification passed with warnings.",
        "verify_fail": "Verification failed.",
        "saved_to": "Saved to folder",
        "cleanup_temp_confirm": "Remove temporary downloads, extracted tools and output? Reports/logs will be kept.",
        "cleanup_all_confirm": "Remove the full temporary workspace including reports and logs?",
        "cleanup_done": "Temporary files removed. Reports and logs kept.",
        "cleanup_all_done": "Workspace removed. Close the application now.",
        "admin_needed": "Administrator rights are required for USB flashing. The tool will relaunch elevated.",
    },
    "de": {
        "choose_language": "Sprache wählen / Choose language",
        "preparing": "Temporäre Umgebung, Reports, Downloads und Geräte-Scan werden vorbereitet...",
        "ready": "Bereit. Laufwerk und macOS wählen, dann FLASH drücken.",
        "ready_save": "Bereit. macOS wählen, dann SPEICHERN drücken.",
        "device": "Laufwerk",
        "macos": "macOS",
        "advanced": "Erweiterte Optionen",
        "save_folder": "In Ordner speichern statt USB flashen",
        "verify": "Nach Flash/Speichern überprüfen",
        "flash": "FLASH",
        "save": "SPEICHERN",
        "cleanup": "Cleanup",
        "workspace": "Workspace",
        "reports": "Reports",
        "efi": "EFI-Quelle",
        "recovery": "Recovery-Quelle",
        "browse": "Durchsuchen",
        "auto_find": "Automatisch suchen",
        "secure": "SecureBootModel",
        "scan": "ScanPolicy",
        "hide": "HideAuxiliary",
        "verbose": "Verbose Boot",
        "no_macos": "Keine macOS-Version ausgewählt.",
        "no_device": "Kein USB-Laufwerk ausgewählt.",
        "no_efi": "Kein nutzbarer EFI-Ordner gefunden oder ausgewählt.",
        "erase": "Das gewählte USB-Laufwerk wird gelöscht. Tippe ERASE zum Fortfahren:",
        "cancelled": "Abgebrochen.",
        "flashing": "Flash läuft...",
        "saving": "EFI und Recovery-Ordner werden gespeichert...",
        "done": "Fertig.",
        "failed": "Fehlgeschlagen.",
        "clean_error": "Saubere Fehlerbeschreibung",
        "download_warn": "Einige Downloads sind fehlgeschlagen. Das Tool bleibt nutzbar; fehlende Bestandteile müssen ggf. manuell gewählt werden.",
        "admin_failed": "Administrator-Erhöhung fehlgeschlagen oder abgebrochen.",
        "verify_ok": "Überprüfung bestanden.",
        "verify_warn": "Überprüfung mit Warnungen bestanden.",
        "verify_fail": "Überprüfung fehlgeschlagen.",
        "saved_to": "Gespeichert in Ordner",
        "cleanup_temp_confirm": "Temporäre Downloads, extrahierte Tools und Output entfernen? Reports/Logs bleiben erhalten.",
        "cleanup_all_confirm": "Kompletten temporären Workspace inklusive Reports und Logs entfernen?",
        "cleanup_done": "Temporäre Dateien entfernt. Reports und Logs bleiben erhalten.",
        "cleanup_all_done": "Workspace entfernt. Anwendung jetzt schließen.",
        "admin_needed": "Für USB-Flashen sind Administratorrechte nötig. Das Tool startet erhöht neu.",
    },
}

# -----------------------------------------------------------------------------
# Platform, paths and elevation
# -----------------------------------------------------------------------------

def is_windows() -> bool:
    return os.name == "nt"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_admin() -> bool:
    if is_windows():
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    try:
        return os.geteuid() == 0
    except Exception:
        return False


def pythonw_path() -> str:
    if not is_windows():
        return sys.executable
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    return str(pyw) if pyw.exists() else str(exe)


def relaunch_admin_gui() -> bool:
    """Relaunch elevated. On Windows, prefer pythonw.exe to avoid a second console window."""
    if is_admin():
        return True
    script = Path(sys.argv[0]).resolve()
    args = [str(script)] + [x for x in sys.argv[1:] if x != "--elevated-child"] + ["--elevated-child"]
    if is_windows():
        params = " ".join([f'"{a}"' if " " in a else a for a in args])
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", pythonw_path(), params, None, 1)
        if rc > 32:
            return True
        return False
    if is_linux():
        env = os.environ.copy()
        env.setdefault("DISPLAY", os.environ.get("DISPLAY", ""))
        env.setdefault("XAUTHORITY", os.environ.get("XAUTHORITY", ""))
        pkexec = shutil.which("pkexec")
        if pkexec:
            cmd = [pkexec, "env", f"DISPLAY={env.get('DISPLAY','')}", f"XAUTHORITY={env.get('XAUTHORITY','')}", sys.executable] + args
            subprocess.Popen(cmd)
            return True
        sudo = shutil.which("sudo")
        xterm = shutil.which("xterm") or shutil.which("konsole") or shutil.which("gnome-terminal")
        if sudo and xterm:
            subprocess.Popen([xterm, "-e", sudo, sys.executable] + args)
            return True
    return False


def runtime_base() -> Path:
    base = Path(tempfile.gettempdir()) / "OpenCoreForge_Runtime"
    base.mkdir(parents=True, exist_ok=True)
    return base


BASE = runtime_base()
DOWNLOADS = BASE / "downloads"
EXTRACTED = BASE / "extracted"
TOOLS = BASE / "tools"
OUTPUT = BASE / "output"
REPORTS = BASE / "reports"
LOGS = BASE / "logs"
for _p in (DOWNLOADS, EXTRACTED, TOOLS, OUTPUT, REPORTS, LOGS):
    _p.mkdir(parents=True, exist_ok=True)

STATE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "OpenCoreForge_state.json"

# -----------------------------------------------------------------------------
# System helpers
# -----------------------------------------------------------------------------

def run_json_windows(ps_command: str, timeout: int = 80):
    if not is_windows():
        return []
    try:
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_command + " | ConvertTo-Json -Depth 6"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if not r.stdout.strip():
            return []
        data = json.loads(r.stdout)
        return data if isinstance(data, list) else [data]
    except Exception:
        return []


def human_size(value) -> str:
    try:
        n = int(value)
    except Exception:
        return str(value)
    units = ["B", "KB", "MB", "GB", "TB"]
    f = float(n)
    for u in units:
        if f < 1024 or u == units[-1]:
            return f"{f:.1f} {u}"
        f /= 1024


def hardware_report() -> dict:
    if is_windows():
        data = {
            "admin": is_admin(),
            "platform": sys.platform,
            "cpu": run_json_windows("Get-CimInstance Win32_Processor | Select Name,Manufacturer,NumberOfCores,NumberOfLogicalProcessors"),
            "gpu": run_json_windows("Get-CimInstance Win32_VideoController | Select Name,AdapterRAM,PNPDeviceID"),
            "board": run_json_windows("Get-CimInstance Win32_BaseBoard | Select Manufacturer,Product,Version"),
            "bios": run_json_windows("Get-CimInstance Win32_BIOS | Select Manufacturer,SMBIOSBIOSVersion,ReleaseDate"),
            "disks": run_json_windows("Get-Disk | Select Number,FriendlyName,Model,Size,BusType,PartitionStyle,IsBoot,IsSystem"),
        }
    elif is_linux():
        data = {"admin": is_admin(), "platform": sys.platform, "lsblk": []}
        try:
            r = subprocess.run(["lsblk", "-J", "-o", "NAME,MODEL,SIZE,TYPE,TRAN,RM,RO,MOUNTPOINT"], capture_output=True, text=True, timeout=30)
            data["lsblk"] = json.loads(r.stdout).get("blockdevices", []) if r.stdout.strip() else []
        except Exception:
            pass
    else:
        data = {"admin": is_admin(), "platform": sys.platform}
    (REPORTS / "device_report.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def list_usb_disks():
    if is_windows():
        rows = []
        for d in run_json_windows("Get-Disk | Select Number,FriendlyName,Model,Size,BusType,PartitionStyle,IsBoot,IsSystem"):
            if str(d.get("IsBoot", False)).lower() == "true" or str(d.get("IsSystem", False)).lower() == "true":
                continue
            if str(d.get("BusType", "")).lower() in ("usb", "sd", "mmc"):
                rows.append({"platform": "windows", **d})
        return rows
    if is_linux():
        rows = []
        try:
            r = subprocess.run(["lsblk", "-J", "-b", "-o", "NAME,MODEL,SIZE,TYPE,TRAN,RM,RO,MOUNTPOINT"], capture_output=True, text=True, timeout=30)
            devices = json.loads(r.stdout).get("blockdevices", []) if r.stdout.strip() else []
            for d in devices:
                if d.get("type") == "disk" and (str(d.get("tran", "")).lower() == "usb" or str(d.get("rm", "0")) == "1"):
                    if d.get("ro") in (True, "1", 1):
                        continue
                    rows.append({"platform": "linux", "Name": d.get("name"), "Model": d.get("model") or d.get("name"), "Size": d.get("size"), "Path": "/dev/" + d.get("name", "")})
        except Exception:
            pass
        return rows
    return []


def free_drive_letter(preferred="O") -> str:
    if not is_windows():
        return preferred
    used = set()
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    for i in range(26):
        if mask & (1 << i):
            used.add(chr(ord("A") + i))
    preferred = preferred.upper().replace(":", "")[:1] or "O"
    if preferred not in used:
        return preferred
    for letter in "QRSTUVWXYZONMLKJIHGFEDP":
        if letter not in used:
            return letter
    raise RuntimeError("No free drive letter available")

# -----------------------------------------------------------------------------
# Download and validation
# -----------------------------------------------------------------------------

def robust_download(url: str, target: Path, tries: int = 3):
    headers = {"User-Agent": f"Mozilla/5.0 {APP_NAME}/{APP_VERSION}"}
    last = ""
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as r, target.open("wb") as f:
                shutil.copyfileobj(r, f)
            if target.exists() and target.stat().st_size > 0:
                return True, ""
        except Exception as exc:
            last = str(exc)
            time.sleep(1.5 * (attempt + 1))
    try:
        target.unlink(missing_ok=True)
    except Exception:
        pass
    return False, last


def validate_layout(root: Path):
    root = Path(root)
    rows = []
    def add(level, message): rows.append((level, message))
    def check(path, label, fail=True):
        add("OK" if Path(path).exists() else ("FAIL" if fail else "WARN"), label if Path(path).exists() else f"{label} missing")

    check(root / "EFI", "EFI folder")
    check(root / "EFI" / "BOOT" / "BOOTx64.efi", "BOOTx64.efi")
    check(root / "EFI" / "OC" / "config.plist", "config.plist")
    check(root / "EFI" / "OC" / "Drivers" / "OpenRuntime.efi", "OpenRuntime.efi")
    drivers = root / "EFI" / "OC" / "Drivers"
    hfs = drivers.exists() and any(x.name.lower() in ("hfsplus.efi", "openhfsplus.efi") for x in drivers.iterdir())
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
                for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
                    h.update(chunk)
            add("OK", "BaseSystem.dmg SHA256 " + h.hexdigest())

    cfg = root / "EFI" / "OC" / "config.plist"
    if cfg.exists():
        try:
            with cfg.open("rb") as f:
                pl = plistlib.load(f)
            add("OK", "config.plist parsed")
            sp = pl.get("Misc", {}).get("Security", {}).get("ScanPolicy")
            ha = pl.get("Misc", {}).get("Boot", {}).get("HideAuxiliary")
            sbm = pl.get("Misc", {}).get("Security", {}).get("SecureBootModel")
            add("OK" if sp == 0 else "WARN", f"ScanPolicy={sp}")
            add("OK" if ha is False else "WARN", f"HideAuxiliary={ha}")
            add("OK" if str(sbm).lower() == "disabled" else "WARN", f"SecureBootModel={sbm}")
        except Exception as exc:
            add("FAIL", "config.plist parse failed: " + str(exc))

    status = "passed"
    for level, _ in rows:
        if level == "FAIL":
            status = "failed"
            break
        if level == "WARN":
            status = "warnings"
    return status, rows

# -----------------------------------------------------------------------------
# GUI
# -----------------------------------------------------------------------------
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, simpledialog, filedialog
except Exception as exc:
    print("Tkinter is required:", exc)
    raise


class Splash(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title(APP_NAME)
        self.geometry("510x175")
        self.resizable(False, False)
        self.configure(bg="#f3f4f6")
        self.label = tk.Label(self, text="Preparing...", bg="#f3f4f6", fg="#111827", font=("Segoe UI", 13, "bold"))
        self.label.pack(pady=(28, 16))
        self.pb = ttk.Progressbar(self, mode="indeterminate", length=400)
        self.pb.pack(pady=8)
        self.pb.start(8)
        self.status = tk.Label(self, text=str(BASE), bg="#f3f4f6", fg="#4b5563", wraplength=460, font=("Segoe UI", 9))
        self.status.pack(pady=8)


class LanguageDialog(tk.Toplevel):
    def __init__(self, master, callback):
        super().__init__(master)
        self.callback = callback
        self.title(APP_NAME)
        self.geometry("360x210")
        self.resizable(False, False)
        self.configure(bg="#f3f4f6")
        tk.Label(self, text="Choose language / Sprache wählen", bg="#f3f4f6", fg="#111827", font=("Segoe UI", 13, "bold")).pack(pady=(24, 16))
        row = tk.Frame(self, bg="#f3f4f6")
        row.pack(pady=12)
        tk.Button(row, text="🇬🇧  English", width=14, height=2, command=lambda: self.pick("en"), font=("Segoe UI", 11)).pack(side="left", padx=10)
        tk.Button(row, text="🇩🇪  Deutsch", width=14, height=2, command=lambda: self.pick("de"), font=("Segoe UI", 11)).pack(side="left", padx=10)

    def pick(self, lang):
        self.callback(lang)
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self.lang = "en"
        self.usb = []
        self.selected_usb = None
        self.selected_macos = None
        self.efi = None
        self.recovery = None
        self.download_errors = []
        self.last_report = None
        self.queue = queue.Queue()
        self.load_state()
        self.splash = Splash(self)
        self.after(80, self.drain)
        threading.Thread(target=self.bootstrap, daemon=True).start()

    def t(self, key):
        return TEXT[self.lang].get(key, key)

    def load_state(self):
        try:
            if STATE.exists():
                self.lang = json.loads(STATE.read_text(encoding="utf-8")).get("lang", self.lang)
        except Exception:
            pass

    def save_state(self):
        try:
            STATE.write_text(json.dumps({"lang": self.lang}, indent=2), encoding="utf-8")
        except Exception:
            pass

    def put(self, fn, *args):
        self.queue.put((fn, args))

    def drain(self):
        try:
            while True:
                fn, args = self.queue.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.after(80, self.drain)

    def bootstrap(self):
        try:
            self.put(self.splash.label.config, {"text": "Creating reports..."})
            env = {"app": APP_NAME, "version": APP_VERSION, "python": sys.version, "executable": sys.executable, "admin": is_admin(), "platform": sys.platform, "workspace": str(BASE)}
            (REPORTS / "environment_report.json").write_text(json.dumps(env, indent=2, ensure_ascii=False), encoding="utf-8")
            self.put(self.splash.label.config, {"text": "Downloading tools..."})
            self.download_tools()
            self.put(self.splash.label.config, {"text": "Scanning device..."})
            hardware_report()
            self.usb = list_usb_disks()
            self.find_outputs()
        except Exception:
            err = traceback.format_exc()
            (LOGS / "crash.log").write_text(err, encoding="utf-8")
            self.put(messagebox.showerror, APP_NAME, err[-3000:])
        finally:
            self.put(self.bootstrap_done)

    def download_tools(self):
        for name, url in SOURCES.items():
            ext = ".py" if url.endswith(".py") else ".zip"
            target = DOWNLOADS / ("".join(c if c.isalnum() or c in "-_" else "_" for c in name) + ext)
            if target.exists() and target.stat().st_size > 0:
                continue
            ok, err = robust_download(url, target)
            if not ok:
                self.download_errors.append(f"{name}: {err}")
        for z in DOWNLOADS.glob("*.zip"):
            dest = EXTRACTED / z.stem
            if dest.exists() and any(dest.iterdir()):
                continue
            dest.mkdir(parents=True, exist_ok=True)
            try:
                with zipfile.ZipFile(z, "r") as zipf:
                    zipf.extractall(dest)
            except Exception as exc:
                self.download_errors.append(f"extract {z.name}: {exc}")
        raw = DOWNLOADS / "OpCore-Simplify_py.py"
        if raw.exists():
            shutil.copy2(raw, TOOLS / "OpCore-Simplify.py")
        if self.download_errors:
            (LOGS / "download_errors.log").write_text("\n".join(self.download_errors), encoding="utf-8")

    def find_outputs(self):
        efis, recs = [], []
        for root in [BASE, Path.home(), Path.cwd()]:
            try:
                for p in root.rglob("EFI"):
                    if (p / "OC" / "config.plist").exists():
                        efis.append(p)
                for p in root.rglob("com.apple.recovery.boot"):
                    if (p / "BaseSystem.dmg").exists() or (p / "BaseSystem.chunklist").exists():
                        recs.append(p)
            except Exception:
                pass
        self.efi = sorted(efis, key=lambda p: len(str(p)))[0] if efis else None
        self.recovery = sorted(recs, key=lambda p: len(str(p)))[0] if recs else None

    def bootstrap_done(self):
        try:
            self.splash.destroy()
        except Exception:
            pass
        LanguageDialog(self, self.set_language)

    def set_language(self, lang):
        self.lang = lang
        self.save_state()
        self.build_main()
        self.deiconify()
        if self.download_errors:
            self.write_status(self.t("download_warn"))
            self.write_status("\n".join(self.download_errors))

    def style_gui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        self.configure(bg="#f3f4f6")
        style.configure("TFrame", background="#f3f4f6")
        style.configure("TLabel", background="#f3f4f6", foreground="#111827", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background="#f3f4f6", foreground="#111827", font=("Segoe UI", 15, "bold"))
        style.configure("Small.TLabel", background="#f3f4f6", foreground="#4b5563", font=("Segoe UI", 9))
        style.configure("TButton", padding=(10, 6), font=("Segoe UI", 10))
        style.configure("Flash.TButton", padding=(18, 8), font=("Segoe UI", 10, "bold"))

    def build_main(self):
        self.style_gui()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("640x535")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.close)
        main = ttk.Frame(self, padding=16)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text=APP_NAME, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.sub = ttk.Label(main, text=self.t("ready"), style="Small.TLabel")
        self.sub.grid(row=1, column=0, sticky="w", pady=(0, 10))
        form = ttk.Frame(main)
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text=self.t("device")).grid(row=0, column=0, sticky="w", padx=(0, 12), pady=6)
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(form, textvariable=self.device_var, state="readonly", width=56)
        self.device_combo.grid(row=0, column=1, sticky="ew", pady=6)
        self.device_combo.bind("<<ComboboxSelected>>", lambda _e: self.select_device())

        ttk.Label(form, text=self.t("macos")).grid(row=1, column=0, sticky="w", padx=(0, 12), pady=6)
        self.macos_var = tk.StringVar()
        self.macos_combo = ttk.Combobox(form, textvariable=self.macos_var, state="readonly", width=56)
        self.macos_combo.grid(row=1, column=1, sticky="ew", pady=6)
        self.macos_combo.bind("<<ComboboxSelected>>", lambda _e: self.select_macos())

        self.advanced_open = tk.BooleanVar(value=False)
        self.advanced_button = ttk.Checkbutton(main, text="▼ " + self.t("advanced"), variable=self.advanced_open, command=self.toggle_advanced)
        self.advanced_button.grid(row=3, column=0, sticky="w", pady=(8, 2))
        self.advanced = ttk.Frame(main)

        self.save_folder_var = tk.BooleanVar(value=False)
        self.secure_var = tk.StringVar(value="Disabled")
        self.scan_var = tk.StringVar(value="0")
        self.hide_var = tk.StringVar(value="False")
        self.verbose_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.advanced, text=self.t("save_folder"), variable=self.save_folder_var, command=self.update_flash_text).grid(row=0, column=0, columnspan=3, sticky="w", pady=3)
        self.add_option(self.advanced, 1, self.t("secure"), self.secure_var, ["Disabled", "Default"])
        self.add_option(self.advanced, 2, self.t("scan"), self.scan_var, ["0", "Default"])
        self.add_option(self.advanced, 3, self.t("hide"), self.hide_var, ["False", "True"])
        ttk.Checkbutton(self.advanced, text=self.t("verbose"), variable=self.verbose_var).grid(row=4, column=1, sticky="w", pady=3)
        ttk.Label(self.advanced, text=self.t("efi")).grid(row=5, column=0, sticky="w", pady=3)
        self.efi_label = ttk.Label(self.advanced, text=str(self.efi) if self.efi else "-", width=43)
        self.efi_label.grid(row=5, column=1, sticky="ew", pady=3)
        ttk.Button(self.advanced, text=self.t("browse"), command=self.pick_efi).grid(row=5, column=2, padx=4)
        ttk.Label(self.advanced, text=self.t("recovery")).grid(row=6, column=0, sticky="w", pady=3)
        self.recovery_label = ttk.Label(self.advanced, text=str(self.recovery) if self.recovery else "-", width=43)
        self.recovery_label.grid(row=6, column=1, sticky="ew", pady=3)
        ttk.Button(self.advanced, text=self.t("browse"), command=self.pick_recovery).grid(row=6, column=2, padx=4)
        ttk.Button(self.advanced, text=self.t("auto_find"), command=self.refresh_find).grid(row=7, column=1, sticky="w", pady=4)

        self.status = tk.Text(main, height=8, width=72, bg="#111827", fg="#e5e7eb", relief="flat", font=("Consolas", 9), wrap="word")
        self.status.grid(row=5, column=0, sticky="ew", pady=(10, 8))
        bottom = ttk.Frame(main)
        bottom.grid(row=6, column=0, sticky="ew")
        bottom.columnconfigure(1, weight=1)
        self.verify_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bottom, text=self.t("verify"), variable=self.verify_var).grid(row=0, column=0, sticky="w")
        ttk.Button(bottom, text=self.t("cleanup"), command=self.cleanup).grid(row=0, column=1, sticky="e", padx=8)
        ttk.Button(bottom, text=self.t("reports"), command=lambda: self.open_path(REPORTS)).grid(row=0, column=2, sticky="e", padx=8)
        ttk.Button(bottom, text=self.t("workspace"), command=lambda: self.open_path(BASE)).grid(row=0, column=3, sticky="e", padx=8)
        self.flash_button = ttk.Button(bottom, text=self.t("flash"), style="Flash.TButton", command=self.flash)
        self.flash_button.grid(row=0, column=4, sticky="e")
        self.populate()
        self.write_status(self.t("ready"))

    def add_option(self, parent, row, label, var, values):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Combobox(parent, textvariable=var, values=values, state="readonly", width=18).grid(row=row, column=1, sticky="w", pady=3)

    def toggle_advanced(self):
        if self.advanced_open.get():
            self.advanced_button.config(text="▲ " + self.t("advanced"))
            self.advanced.grid(row=4, column=0, sticky="ew", pady=4)
        else:
            self.advanced_button.config(text="▼ " + self.t("advanced"))
            self.advanced.grid_remove()

    def update_flash_text(self):
        save_mode = self.save_folder_var.get()
        self.flash_button.config(text=self.t("save") if save_mode else self.t("flash"))
        self.sub.config(text=self.t("ready_save") if save_mode else self.t("ready"))

    def populate(self):
        devs = []
        for d in self.usb:
            if d.get("platform") == "windows":
                devs.append(f"Disk {d.get('Number')} | {d.get('FriendlyName')} | {human_size(d.get('Size', 0))} | {d.get('BusType')}")
            else:
                devs.append(f"{d.get('Path')} | {d.get('Model')} | {human_size(d.get('Size', 0))}")
        self.device_combo["values"] = devs
        if devs:
            self.device_var.set(devs[0])
            self.select_device()
        self.macos_combo["values"] = [f"{name} ({ver}) - {tag}" for name, ver, tag in MACOS_CHOICES]

    def select_device(self):
        idx = self.device_combo.current()
        self.selected_usb = self.usb[idx] if 0 <= idx < len(self.usb) else None

    def select_macos(self):
        idx = self.macos_combo.current()
        self.selected_macos = MACOS_CHOICES[idx] if 0 <= idx < len(MACOS_CHOICES) else None

    def refresh_find(self):
        self.find_outputs()
        self.efi_label.config(text=str(self.efi) if self.efi else "-")
        self.recovery_label.config(text=str(self.recovery) if self.recovery else "-")

    def pick_efi(self):
        path = filedialog.askdirectory(title=self.t("efi"))
        if path:
            self.efi = Path(path)
            self.efi_label.config(text=str(self.efi))

    def pick_recovery(self):
        path = filedialog.askdirectory(title=self.t("recovery"))
        if path:
            self.recovery = Path(path)
            self.recovery_label.config(text=str(self.recovery))

    def write_status(self, message):
        line = time.strftime("[%H:%M:%S] ") + str(message) + "\n"
        self.status.insert("end", line)
        self.status.see("end")
        try:
            with (LOGS / "app.log").open("a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    def flash(self):
        if not self.selected_macos:
            messagebox.showwarning(APP_NAME, self.t("no_macos")); return
        if not self.efi or not Path(self.efi).exists():
            messagebox.showerror(APP_NAME, self.t("no_efi")); return
        if self.save_folder_var.get():
            target = filedialog.askdirectory(title=self.t("save_folder"))
            if target:
                threading.Thread(target=lambda: self.save_to_folder(Path(target)), daemon=True).start()
            return
        if not self.selected_usb:
            messagebox.showwarning(APP_NAME, self.t("no_device")); return
        if not is_admin():
            messagebox.showinfo(APP_NAME, self.t("admin_needed"))
            if relaunch_admin_gui():
                self.close()
            else:
                messagebox.showerror(APP_NAME, self.t("admin_failed"))
            return
        if simpledialog.askstring(APP_NAME, self.t("erase")) != "ERASE":
            self.write_status(self.t("cancelled")); return
        threading.Thread(target=self.flash_worker, daemon=True).start()

    def save_to_folder(self, target: Path):
        try:
            self.put_status(self.t("saving"))
            efi_out = target / "EFI"
            if efi_out.exists(): shutil.rmtree(efi_out)
            shutil.copytree(self.efi, efi_out)
            if self.recovery and Path(self.recovery).exists():
                rec_out = target / "com.apple.recovery.boot"
                if rec_out.exists(): shutil.rmtree(rec_out)
                shutil.copytree(self.recovery, rec_out)
            self.patch_config(target)
            if self.verify_var.get():
                self.write_report(target)
            self.put_status(self.t("done"))
        except Exception:
            self.handle_error()

    def flash_worker(self):
        try:
            self.put_status(self.t("flashing"))
            target = self.format_usb()
            dst = target / "EFI"
            if dst.exists(): shutil.rmtree(dst)
            shutil.copytree(self.efi, dst)
            if self.recovery and Path(self.recovery).exists():
                rec = target / "com.apple.recovery.boot"
                if rec.exists(): shutil.rmtree(rec)
                shutil.copytree(self.recovery, rec)
            self.patch_config(target)
            if self.verify_var.get():
                self.write_report(target)
            self.put_status(self.t("done"))
        except Exception:
            self.handle_error()

    def put_status(self, text):
        self.put(self.write_status, text)

    def write_report(self, target: Path):
        status, rows = validate_layout(target)
        report_path = REPORTS / ("validation_" + time.strftime("%Y%m%d_%H%M%S") + ".txt")
        lines = [f"{APP_NAME} {APP_VERSION}", f"Target: {target}", f"macOS: {self.selected_macos}", ""] + [f"[{a}] {b}" for a, b in rows]
        report_path.write_text("\n".join(lines), encoding="utf-8")
        self.last_report = report_path
        self.put_status("\n".join(lines[-len(rows):]))
        msg = self.t("verify_ok") if status == "passed" else self.t("verify_warn") if status == "warnings" else self.t("verify_fail")
        self.put(messagebox.showinfo if status != "failed" else messagebox.showerror, APP_NAME, msg + "\n\n" + str(report_path))

    def format_usb(self) -> Path:
        if is_windows():
            letter = free_drive_letter("O")
            num = self.selected_usb.get("Number")
            if num is None:
                raise RuntimeError("No Windows disk number selected")
            script = (
                f"select disk {num}\n"
                "detail disk\n"
                "clean\n"
                "convert gpt\n"
                "create partition primary size=4096\n"
                "format fs=fat32 quick label=OPENCORE\n"
                f"assign letter={letter}\n"
                "exit\n"
            )
            sp = BASE / "diskpart_flash.txt"
            sp.write_text(script, encoding="utf-8")
            r = subprocess.run(["diskpart", "/s", str(sp)], capture_output=True, text=True, errors="replace")
            (LOGS / "diskpart_last_stdout.log").write_text(r.stdout or "", encoding="utf-8")
            (LOGS / "diskpart_last_stderr.log").write_text(r.stderr or "", encoding="utf-8")
            self.put_status((r.stdout or "") + "\n" + (r.stderr or ""))
            if r.returncode != 0:
                raise RuntimeError(f"diskpart failed with code {r.returncode}")
            target = Path(f"{letter}:/")
            for _ in range(30):
                if target.exists():
                    return target
                time.sleep(0.25)
            raise RuntimeError(f"Drive {letter}: not available after formatting")
        if is_linux():
            dev = self.selected_usb.get("Path")
            if not dev:
                raise RuntimeError("No Linux block device selected")
            mount_dir = BASE / "mnt_usb"
            if mount_dir.exists():
                subprocess.run(["umount", str(mount_dir)], capture_output=True, text=True)
                shutil.rmtree(mount_dir, ignore_errors=True)
            mount_dir.mkdir(parents=True, exist_ok=True)
            cmds = [
                ["parted", "-s", dev, "mklabel", "gpt"],
                ["parted", "-s", dev, "mkpart", "primary", "fat32", "1MiB", "4097MiB"],
                ["partprobe", dev],
            ]
            for c in cmds:
                r = subprocess.run(c, capture_output=True, text=True)
                if r.returncode != 0:
                    raise RuntimeError("command failed: " + " ".join(c) + " :: " + (r.stderr or r.stdout))
            part = dev + "1"
            time.sleep(1)
            r = subprocess.run(["mkfs.vfat", "-F", "32", "-n", "OPENCORE", part], capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError("mkfs.vfat failed: " + (r.stderr or r.stdout))
            r = subprocess.run(["mount", part, str(mount_dir)], capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError("mount failed: " + (r.stderr or r.stdout))
            return mount_dir
        raise RuntimeError("Unsupported platform for USB flashing")

    def patch_config(self, target: Path):
        cfg = target / "EFI" / "OC" / "config.plist"
        if not cfg.exists(): return
        try:
            shutil.copy2(cfg, cfg.with_suffix(".plist.before_forge"))
            with cfg.open("rb") as f:
                pl = plistlib.load(f)
            pl.setdefault("Misc", {}).setdefault("Security", {})["SecureBootModel"] = self.secure_var.get()
            if self.scan_var.get() == "0":
                pl.setdefault("Misc", {}).setdefault("Security", {})["ScanPolicy"] = 0
            pl.setdefault("Misc", {}).setdefault("Boot", {})["HideAuxiliary"] = (self.hide_var.get() == "True")
            if self.verbose_var.get():
                nv = pl.setdefault("NVRAM", {}).setdefault("Add", {}).setdefault("7C436110-AB2A-4BBB-A880-FE41995C9F82", {})
                args = str(nv.get("boot-args", ""))
                for x in ["-v", "keepsyms=1", "debug=0x100"]:
                    if x not in args.split(): args = (x + " " + args).strip()
                nv["boot-args"] = args
            with cfg.open("wb") as f:
                plistlib.dump(pl, f)
        except Exception as exc:
            self.put_status("config patch skipped: " + str(exc))

    def handle_error(self):
        err = traceback.format_exc()
        (LOGS / "operation_error.log").write_text(err, encoding="utf-8")
        clean = err.splitlines()[-1]
        self.put_status(self.t("failed") + " " + self.t("clean_error") + ": " + clean)
        self.put(messagebox.showerror, APP_NAME, self.t("failed") + "\n\n" + clean)

    def open_path(self, path: Path):
        if is_windows():
            os.startfile(str(path))
        elif is_linux():
            subprocess.Popen(["xdg-open", str(path)])
        else:
            subprocess.Popen(["open", str(path)])

    def cleanup(self):
        if messagebox.askyesno(APP_NAME, self.t("cleanup_temp_confirm")):
            for p in [DOWNLOADS, EXTRACTED, TOOLS, OUTPUT]:
                shutil.rmtree(p, ignore_errors=True)
                p.mkdir(parents=True, exist_ok=True)
            self.write_status(self.t("cleanup_done"))
        if messagebox.askyesno(APP_NAME, self.t("cleanup_all_confirm")):
            shutil.rmtree(BASE, ignore_errors=True)
            messagebox.showinfo(APP_NAME, self.t("cleanup_all_done"))

    def close(self):
        self.save_state()
        self.destroy()


if __name__ == "__main__":
    try:
        App().mainloop()
    except Exception:
        err = traceback.format_exc()
        try:
            LOGS.mkdir(parents=True, exist_ok=True)
            (LOGS / "crash.log").write_text(err, encoding="utf-8")
        except Exception:
            pass
        try:
            if is_windows():
                ctypes.windll.user32.MessageBoxW(None, err[-3500:], APP_NAME, 0x10)
        except Exception:
            pass
        print(err)
