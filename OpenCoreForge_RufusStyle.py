
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
APP_VERSION = "3.1.0"

SOURCES = {
    "OpCore-Simplify": "https://github.com/lzhoang2801/OpCore-Simplify/archive/refs/heads/main.zip",
    "OpCore-Simplify.py": "https://raw.githubusercontent.com/lzhoang2801/OpCore-Simplify/refs/heads/main/OpCore-Simplify.py",
    "OpenCorePkg": "https://github.com/acidanthera/OpenCorePkg/releases/download/1.0.7/OpenCore-1.0.7-RELEASE.zip",
    "gibMacOS": "https://github.com/corpnewt/gibMacOS/archive/refs/heads/master.zip",
    "USBToolBox": "https://github.com/USBToolBox/tool/releases/latest/download/Windows.zip",
    "USBToolBox.kext": "https://github.com/USBToolBox/kext/releases/latest/download/USBToolBox.kext.zip"
}

MACOS = [
    ("macOS High Sierra", "10.13", "Legacy"),
    ("macOS Mojave", "10.14", "Legacy"),
    ("macOS Catalina", "10.15", "Stable"),
    ("macOS Big Sur", "11", "Stable"),
    ("macOS Monterey", "12", "Recommended"),
    ("macOS Ventura", "13", "Modern"),
    ("macOS Sonoma", "14", "Modern"),
    ("macOS Sequoia", "15", "Current"),
    ("macOS Tahoe", "26", "Experimental")
]

TEXT = {
    "en": {
        "choose_language": "Choose language",
        "prep": "Preparing workspace, tools, device report and scan...",
        "device": "Device",
        "macos": "macOS",
        "select": "SELECT",
        "advanced": "Advanced options",
        "verify": "Verify stick after flashing",
        "flash": "FLASH",
        "status_ready": "Ready. Select a device and macOS, then press FLASH.",
        "status_prep": "Preparing automatically...",
        "status_flash": "Flashing...",
        "status_done": "Done.",
        "status_fail": "Failed.",
        "options": "Options",
        "efi": "EFI source",
        "recovery": "Recovery source",
        "browse": "Browse",
        "auto_find": "Auto find",
        "mode": "Mode",
        "test": "Test folder",
        "real": "Real USB",
        "secure": "SecureBootModel",
        "scan": "ScanPolicy",
        "hide": "HideAuxiliary",
        "verbose": "Verbose boot",
        "admin": "Real USB flashing requires administrator rights. Restart with administrator rights now?",
        "erase": "The selected USB drive will be erased. Type ERASE to continue:",
        "no_device": "No target device selected.",
        "no_os": "No macOS version selected.",
        "no_efi": "No usable EFI folder found or selected.",
        "cancel": "Cancelled.",
        "open_report": "Open report",
        "workspace": "Workspace",
        "report_ok": "Verification passed.",
        "report_warn": "Verification passed with warnings.",
        "report_fail": "Verification failed.",
        "clean_error": "Clean error description",
        "test_target": "Test output folder"
    },
    "de": {
        "choose_language": "Sprache wählen",
        "prep": "Workspace, Tools, Gerätebericht und Scan werden vorbereitet...",
        "device": "Laufwerk",
        "macos": "macOS",
        "select": "AUSWÄHLEN",
        "advanced": "Erweiterte Optionen",
        "verify": "Stick nach dem Flashen überprüfen",
        "flash": "FLASH",
        "status_ready": "Bereit. Laufwerk und macOS wählen, dann FLASH drücken.",
        "status_prep": "Automatische Vorbereitung läuft...",
        "status_flash": "Flash läuft...",
        "status_done": "Fertig.",
        "status_fail": "Fehlgeschlagen.",
        "options": "Optionen",
        "efi": "EFI-Quelle",
        "recovery": "Recovery-Quelle",
        "browse": "Durchsuchen",
        "auto_find": "Automatisch suchen",
        "mode": "Modus",
        "test": "Testordner",
        "real": "Echter USB",
        "secure": "SecureBootModel",
        "scan": "ScanPolicy",
        "hide": "HideAuxiliary",
        "verbose": "Verbose Boot",
        "admin": "Für echtes USB-Flashen sind Administratorrechte nötig. Jetzt mit Administratorrechten neu starten?",
        "erase": "Das gewählte USB-Laufwerk wird gelöscht. Tippe ERASE zum Fortfahren:",
        "no_device": "Kein Ziellaufwerk ausgewählt.",
        "no_os": "Keine macOS-Version ausgewählt.",
        "no_efi": "Kein nutzbarer EFI-Ordner gefunden oder ausgewählt.",
        "cancel": "Abgebrochen.",
        "open_report": "Report öffnen",
        "workspace": "Workspace",
        "report_ok": "Überprüfung bestanden.",
        "report_warn": "Überprüfung mit Warnungen bestanden.",
        "report_fail": "Überprüfung fehlgeschlagen.",
        "clean_error": "Saubere Fehlerbeschreibung",
        "test_target": "Test-Ausgabeordner"
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
        params = " ".join([f'"{x}"' if " " in x else x for x in sys.argv])
        return ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1) > 32
    except Exception:
        return False


def safe_workspace():
    candidates = []
    for e in ("LOCALAPPDATA", "APPDATA", "USERPROFILE", "TEMP", "TMP"):
        v = os.environ.get(e)
        if v:
            candidates.append(Path(v) / "OpenCoreForge")
    candidates += [Path.home() / "OpenCoreForge", Path(tempfile.gettempdir()) / "OpenCoreForge"]
    for p in candidates:
        try:
            p.mkdir(parents=True, exist_ok=True)
            t = p / ".write_test"
            t.write_text("ok", encoding="utf-8")
            t.unlink(missing_ok=True)
            return p
        except Exception:
            pass
    raise RuntimeError("No writable workspace found")

BASE = safe_workspace()
DOWNLOADS = BASE / "downloads"
EXTRACTED = BASE / "extracted"
TOOLS = BASE / "tools"
OUTPUT = BASE / "output"
REPORTS = BASE / "reports"
LOGS = BASE / "logs"
STATE = BASE / "state.json"
for d in (DOWNLOADS, EXTRACTED, TOOLS, OUTPUT, REPORTS, LOGS):
    d.mkdir(parents=True, exist_ok=True)


def cmd_json(cmd):
    if not is_windows():
        return []
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd + " | ConvertTo-Json -Depth 6"], capture_output=True, text=True, timeout=80)
        if not r.stdout.strip():
            return []
        v = json.loads(r.stdout)
        return v if isinstance(v, list) else [v]
    except Exception:
        return []


def human(n):
    try:
        n = int(n)
    except Exception:
        return str(n)
    units = ["B", "KB", "MB", "GB", "TB"]
    f = float(n)
    for u in units:
        if f < 1024 or u == units[-1]:
            return f"{f:.1f} {u}"
        f /= 1024


def hardware_report():
    if not is_windows():
        data = {"system": sys.platform, "admin": is_admin()}
    else:
        data = {
            "admin": is_admin(),
            "cpu": cmd_json("Get-CimInstance Win32_Processor | Select Name,Manufacturer,NumberOfCores,NumberOfLogicalProcessors"),
            "gpu": cmd_json("Get-CimInstance Win32_VideoController | Select Name,AdapterRAM,PNPDeviceID"),
            "board": cmd_json("Get-CimInstance Win32_BaseBoard | Select Manufacturer,Product,Version"),
            "bios": cmd_json("Get-CimInstance Win32_BIOS | Select Manufacturer,SMBIOSBIOSVersion,ReleaseDate"),
            "disks": cmd_json("Get-Disk | Select Number,FriendlyName,Model,Size,BusType,PartitionStyle,IsBoot,IsSystem"),
            "network": cmd_json("Get-CimInstance Win32_NetworkAdapter | ? {$_.PhysicalAdapter -eq $true} | Select Name,Manufacturer,PNPDeviceID"),
            "audio": cmd_json("Get-CimInstance Win32_SoundDevice | Select Name,Manufacturer,PNPDeviceID")
        }
    (REPORTS / "device_report.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def usb_disks():
    out = []
    for d in cmd_json("Get-Disk | Select Number,FriendlyName,Model,Size,BusType,PartitionStyle,IsBoot,IsSystem"):
        if str(d.get("IsBoot", False)).lower() == "true" or str(d.get("IsSystem", False)).lower() == "true":
            continue
        if str(d.get("BusType", "")).lower() in ["usb", "sd", "mmc"]:
            out.append(d)
    return out


def validate_stick(root):
    root = Path(root)
    rows = []
    def add(level, msg): rows.append((level, msg))
    def check(path, label, fail=True):
        add("OK" if Path(path).exists() else ("FAIL" if fail else "WARN"), label if Path(path).exists() else label + " missing")
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
                for c in iter(lambda: f.read(8 * 1024 * 1024), b""):
                    h.update(c)
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
        except Exception as e:
            add("FAIL", "config.plist parse failed: " + str(e))
    status = "passed"
    for lvl, _ in rows:
        if lvl == "FAIL":
            status = "failed"
            break
        if lvl == "WARN" and status != "failed":
            status = "warnings"
    return status, rows

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, simpledialog, filedialog
except Exception as e:
    print("Tkinter missing", e)
    raise

class Splash(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title(APP_NAME)
        self.geometry("480x170")
        self.resizable(False, False)
        self.configure(bg="#f3f4f6")
        self.label = tk.Label(self, text="Preparing...", bg="#f3f4f6", fg="#111827", font=("Segoe UI", 13, "bold"))
        self.label.pack(pady=(28, 16))
        self.pb = ttk.Progressbar(self, mode="indeterminate", length=380)
        self.pb.pack(pady=8)
        self.pb.start(8)
        self.status = tk.Label(self, text=str(BASE), bg="#f3f4f6", fg="#4b5563", wraplength=430, font=("Segoe UI", 9))
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
        self.mode = "test"
        self.hw = {}
        self.usb = []
        self.selected_usb = None
        self.selected_macos = None
        self.efi = None
        self.recovery = None
        self.last_report = None
        self.q = queue.Queue()
        self.load_state()
        self.splash = Splash(self)
        self.after(100, self.drain)
        threading.Thread(target=self.bootstrap, daemon=True).start()

    def text(self, key):
        return TEXT[self.lang].get(key, key)

    def load_state(self):
        try:
            if STATE.exists():
                data = json.loads(STATE.read_text(encoding="utf-8"))
                self.lang = data.get("lang", self.lang)
                self.mode = data.get("mode", self.mode)
        except Exception:
            pass

    def save_state(self):
        STATE.write_text(json.dumps({"lang": self.lang, "mode": self.mode}, indent=2), encoding="utf-8")

    def put(self, fn, *args):
        self.q.put((fn, args))

    def drain(self):
        try:
            while True:
                fn, args = self.q.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.after(80, self.drain)

    def bootstrap(self):
        try:
            self.put(self.splash.label.config, {"text": "Creating environment..."})
            self.create_environment_report()
            self.put(self.splash.label.config, {"text": "Downloading tools..."})
            self.download_tools()
            self.put(self.splash.label.config, {"text": "Scanning device..."})
            self.hw = hardware_report()
            self.usb = usb_disks()
            self.find_outputs()
            self.put(self.bootstrap_done)
        except Exception:
            err = traceback.format_exc()
            (LOGS / "crash.log").write_text(err, encoding="utf-8")
            self.put(messagebox.showerror, APP_NAME, err[-3000:])
            self.put(self.bootstrap_done)

    def create_environment_report(self):
        report = {
            "app": APP_NAME,
            "version": APP_VERSION,
            "python": sys.version,
            "executable": sys.executable,
            "workspace": str(BASE),
            "admin": is_admin(),
            "platform": sys.platform,
            "time": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        (REPORTS / "environment_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    def download_tools(self):
        for name, url in SOURCES.items():
            ext = ".py" if url.endswith(".py") else ".zip"
            filename = "".join(c if c.isalnum() or c in "-_" else "_" for c in name) + ext
            target = DOWNLOADS / filename
            if not target.exists() or target.stat().st_size == 0:
                with urllib.request.urlopen(url, timeout=90) as r, target.open("wb") as f:
                    shutil.copyfileobj(r, f)
        for z in DOWNLOADS.glob("*.zip"):
            dest = EXTRACTED / z.stem
            if dest.exists() and any(dest.iterdir()):
                continue
            dest.mkdir(parents=True, exist_ok=True)
            try:
                with zipfile.ZipFile(z, "r") as zipf:
                    zipf.extractall(dest)
            except Exception as e:
                (LOGS / "extract_errors.log").open("a", encoding="utf-8").write(f"{z}: {e}\n")
        raw = DOWNLOADS / "OpCore-Simplify_py.py"
        if raw.exists():
            shutil.copy2(raw, TOOLS / "OpCore-Simplify.py")

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
        self.splash.destroy()
        LanguageDialog(self, self.set_language_and_show)

    def set_language_and_show(self, lang):
        self.lang = lang
        self.save_state()
        self.build_main()
        self.deiconify()

    def style(self):
        st = ttk.Style(self)
        try: st.theme_use("clam")
        except Exception: pass
        self.configure(bg="#f3f4f6")
        st.configure("TFrame", background="#f3f4f6")
        st.configure("Card.TFrame", background="#ffffff")
        st.configure("TLabel", background="#f3f4f6", foreground="#111827", font=("Segoe UI", 10))
        st.configure("Small.TLabel", background="#f3f4f6", foreground="#4b5563", font=("Segoe UI", 9))
        st.configure("Title.TLabel", background="#f3f4f6", foreground="#111827", font=("Segoe UI", 15, "bold"))
        st.configure("TButton", padding=(10, 6), font=("Segoe UI", 10))
        st.configure("Flash.TButton", padding=(18, 8), font=("Segoe UI", 10, "bold"))

    def build_main(self):
        self.style()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("620x520")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.main = ttk.Frame(self, padding=16)
        self.main.pack(fill="both", expand=True)
        ttk.Label(self.main, text=APP_NAME, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(self.main, text=self.text("status_ready"), style="Small.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 10))

        form = ttk.Frame(self.main)
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text=self.text("device")).grid(row=0, column=0, sticky="w", padx=(0, 12), pady=6)
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(form, textvariable=self.device_var, state="readonly", width=54)
        self.device_combo.grid(row=0, column=1, sticky="ew", pady=6)
        self.device_combo.bind("<<ComboboxSelected>>", lambda e: self.select_device())
        ttk.Label(form, text=self.text("macos")).grid(row=1, column=0, sticky="w", padx=(0, 12), pady=6)
        self.macos_var = tk.StringVar()
        self.macos_combo = ttk.Combobox(form, textvariable=self.macos_var, state="readonly", width=54)
        self.macos_combo.grid(row=1, column=1, sticky="ew", pady=6)
        self.macos_combo.bind("<<ComboboxSelected>>", lambda e: self.select_macos())
        ttk.Label(form, text=self.text("mode")).grid(row=2, column=0, sticky="w", padx=(0, 12), pady=6)
        self.mode_var = tk.StringVar(value=self.mode)
        self.mode_combo = ttk.Combobox(form, textvariable=self.mode_var, state="readonly", width=54, values=["test", "real"])
        self.mode_combo.grid(row=2, column=1, sticky="ew", pady=6)
        self.mode_combo.bind("<<ComboboxSelected>>", lambda e: self.change_mode())

        self.adv_open = tk.BooleanVar(value=False)
        self.adv_btn = ttk.Checkbutton(self.main, text="▼ " + self.text("advanced"), variable=self.adv_open, command=self.toggle_advanced)
        self.adv_btn.grid(row=3, column=0, sticky="w", pady=(8, 2))
        self.adv = ttk.Frame(self.main)
        self.secure_var = tk.StringVar(value="Disabled")
        self.scan_var = tk.StringVar(value="0")
        self.hide_var = tk.StringVar(value="False")
        self.verbose_var = tk.BooleanVar(value=True)
        self.add_option(self.adv, 0, self.text("secure"), self.secure_var, ["Disabled", "Default"])
        self.add_option(self.adv, 1, self.text("scan"), self.scan_var, ["0", "Default"])
        self.add_option(self.adv, 2, self.text("hide"), self.hide_var, ["False", "True"])
        ttk.Checkbutton(self.adv, text=self.text("verbose"), variable=self.verbose_var).grid(row=3, column=1, sticky="w", pady=3)
        ttk.Label(self.adv, text=self.text("efi")).grid(row=4, column=0, sticky="w", pady=3)
        self.efi_label = ttk.Label(self.adv, text=str(self.efi) if self.efi else "-", width=42)
        self.efi_label.grid(row=4, column=1, sticky="ew", pady=3)
        ttk.Button(self.adv, text=self.text("browse"), command=self.pick_efi).grid(row=4, column=2, padx=4)
        ttk.Label(self.adv, text=self.text("recovery")).grid(row=5, column=0, sticky="w", pady=3)
        self.rec_label = ttk.Label(self.adv, text=str(self.recovery) if self.recovery else "-", width=42)
        self.rec_label.grid(row=5, column=1, sticky="ew", pady=3)
        ttk.Button(self.adv, text=self.text("browse"), command=self.pick_recovery).grid(row=5, column=2, padx=4)
        ttk.Button(self.adv, text=self.text("auto_find"), command=self.refresh_find).grid(row=6, column=1, sticky="w", pady=4)

        self.status = tk.Text(self.main, height=8, width=70, bg="#111827", fg="#e5e7eb", relief="flat", font=("Consolas", 9), wrap="word")
        self.status.grid(row=5, column=0, sticky="ew", pady=(10, 8))

        bottom = ttk.Frame(self.main)
        bottom.grid(row=6, column=0, sticky="ew")
        bottom.columnconfigure(1, weight=1)
        self.verify_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bottom, text=self.text("verify"), variable=self.verify_var).grid(row=0, column=0, sticky="w")
        ttk.Button(bottom, text=self.text("workspace"), command=self.open_workspace).grid(row=0, column=1, sticky="e", padx=8)
        ttk.Button(bottom, text=self.text("flash"), style="Flash.TButton", command=self.flash).grid(row=0, column=2, sticky="e")

        self.populate()
        self.write_status(self.text("status_ready"))

    def add_option(self, parent, row, label, var, values):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Combobox(parent, textvariable=var, values=values, state="readonly", width=18).grid(row=row, column=1, sticky="w", pady=3)

    def toggle_advanced(self):
        if self.adv_open.get():
            self.adv_btn.config(text="▲ " + self.text("advanced"))
            self.adv.grid(row=4, column=0, sticky="ew", pady=4)
        else:
            self.adv_btn.config(text="▼ " + self.text("advanced"))
            self.adv.grid_remove()

    def populate(self):
        devs = [f"Disk {d.get('Number')} | {d.get('FriendlyName')} | {human(d.get('Size', 0))} | {d.get('BusType')}" for d in self.usb]
        if self.mode == "test":
            devs = [self.text("test_target") + f" | {OUTPUT / 'test_stick'}"] + devs
        self.device_combo["values"] = devs
        if devs:
            self.device_var.set(devs[0])
            self.select_device()
        self.macos_combo["values"] = [f"{a} ({b}) - {c}" for a, b, c in MACOS]

    def select_device(self):
        i = self.device_combo.current()
        if self.mode == "test" and i == 0:
            self.selected_usb = None
        else:
            idx = i - 1 if self.mode == "test" else i
            self.selected_usb = self.usb[idx] if 0 <= idx < len(self.usb) else None

    def select_macos(self):
        i = self.macos_combo.current()
        self.selected_macos = MACOS[i] if 0 <= i < len(MACOS) else None

    def change_mode(self):
        self.mode = self.mode_var.get()
        self.save_state()
        self.populate()

    def refresh_find(self):
        self.find_outputs()
        self.efi_label.config(text=str(self.efi) if self.efi else "-")
        self.rec_label.config(text=str(self.recovery) if self.recovery else "-")

    def pick_efi(self):
        p = filedialog.askdirectory(title=self.text("efi"))
        if p:
            self.efi = Path(p)
            self.efi_label.config(text=str(self.efi))

    def pick_recovery(self):
        p = filedialog.askdirectory(title=self.text("recovery"))
        if p:
            self.recovery = Path(p)
            self.rec_label.config(text=str(self.recovery))

    def write_status(self, msg):
        line = time.strftime("[%H:%M:%S] ") + str(msg) + "\n"
        self.status.insert("end", line)
        self.status.see("end")
        try:
            with (LOGS / "app.log").open("a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    def flash(self):
        if not self.selected_macos:
            messagebox.showwarning(APP_NAME, self.text("no_os")); return
        if not self.efi or not Path(self.efi).exists():
            messagebox.showerror(APP_NAME, self.text("no_efi")); return
        if self.mode == "real":
            if not self.selected_usb:
                messagebox.showwarning(APP_NAME, self.text("no_device")); return
            if is_windows() and not is_admin():
                if messagebox.askyesno(APP_NAME, self.text("admin")):
                    if relaunch_admin(): self.destroy()
                return
            if simpledialog.askstring(APP_NAME, self.text("erase")) != "ERASE":
                self.write_status(self.text("cancel")); return
        threading.Thread(target=self.flash_worker, daemon=True).start()

    def flash_worker(self):
        try:
            self.put(self.write_status, self.text("status_flash"))
            if self.mode == "test":
                target = OUTPUT / "test_stick"
                if target.exists(): shutil.rmtree(target)
                target.mkdir(parents=True, exist_ok=True)
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
            if self.verify_var.get():
                status, rows = validate_stick(target)
                report_path = REPORTS / ("validation_" + time.strftime("%Y%m%d_%H%M%S") + ".txt")
                report = [f"{APP_NAME} {APP_VERSION}", f"Target: {target}", f"macOS: {self.selected_macos}", ""] + [f"[{a}] {b}" for a,b in rows]
                report_path.write_text("\n".join(report), encoding="utf-8")
                self.last_report = report_path
                self.put(self.write_status, "\n".join(report[-len(rows):]))
                if status == "passed": msg = self.text("report_ok")
                elif status == "warnings": msg = self.text("report_warn")
                else: msg = self.text("report_fail")
                self.put(self.write_status, msg + " Report: " + str(report_path))
                self.put(messagebox.showinfo if status != "failed" else messagebox.showerror, APP_NAME, msg + "\n\n" + str(report_path))
            self.put(self.write_status, self.text("status_done"))
        except Exception:
            err = traceback.format_exc()
            (LOGS / "flash_error.log").write_text(err, encoding="utf-8")
            clean = err.splitlines()[-1]
            self.put(self.write_status, self.text("status_fail") + " " + self.text("clean_error") + ": " + clean)
            self.put(messagebox.showerror, APP_NAME, self.text("status_fail") + "\n\n" + clean)

    def format_usb(self):
        letter = "O"
        num = self.selected_usb.get("Number")
        script = f"select disk {num}\ndetail disk\nclean\nconvert gpt\ncreate partition primary\nformat fs=fat32 quick label=OPENCORE\nassign letter={letter}\nexit\n"
        sp = BASE / "diskpart_flash.txt"
        sp.write_text(script, encoding="utf-8")
        r = subprocess.run(["diskpart", "/s", str(sp)], capture_output=True, text=True, errors="replace")
        self.put(self.write_status, r.stdout + "\n" + r.stderr)
        if r.returncode != 0:
            raise RuntimeError("diskpart failed")
        target = Path(f"{letter}:/")
        if not target.exists():
            raise RuntimeError("drive O: not available after formatting")
        return target

    def patch_config(self, target):
        cfg = target / "EFI" / "OC" / "config.plist"
        if not cfg.exists(): return
        try:
            shutil.copy2(cfg, cfg.with_suffix(".plist.before_forge"))
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
            self.put(self.write_status, "config patch skipped: " + str(e))

    def open_workspace(self):
        if is_windows(): os.startfile(str(BASE))
        else: subprocess.Popen(["xdg-open", str(BASE)])

    def close(self):
        self.save_state()
        self.destroy()

if __name__ == "__main__":
    try:
        App().mainloop()
    except Exception:
        err = traceback.format_exc()
        (LOGS / "crash.log").write_text(err, encoding="utf-8")
        try:
            if is_windows(): ctypes.windll.user32.MessageBoxW(None, err[-3500:], APP_NAME, 0x10)
        except Exception:
            pass
        print(err)
