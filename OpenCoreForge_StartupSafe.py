
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import json
import time
import queue
import shutil
import zipfile
import hashlib
import plistlib
import tempfile
import threading
import traceback
import subprocess
import urllib.request
import ctypes
from pathlib import Path

APP = "OpenCore Forge"
VER = "4.5.0-startup-safe"
BASE = Path(tempfile.gettempdir()) / "OpenCoreForge_Runtime"
DOWNLOADS = BASE / "downloads"
EXTRACTED = BASE / "extracted"
OUTPUT = BASE / "output"
REPORTS = BASE / "reports"
LOGS = BASE / "logs"
for p in [BASE, DOWNLOADS, EXTRACTED, OUTPUT, REPORTS, LOGS]:
    p.mkdir(parents=True, exist_ok=True)
EARLY_LOG = LOGS / "startup.log"

def elog(msg):
    try:
        with EARLY_LOG.open("a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + str(msg) + "\n")
    except Exception:
        pass

def is_win():
    return os.name == "nt"

def is_linux():
    return sys.platform.startswith("linux")

def is_admin():
    if is_win():
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    try:
        return os.geteuid() == 0
    except Exception:
        return False

def gui_python():
    if not is_win():
        return sys.executable
    p = Path(sys.executable).with_name("pythonw.exe")
    return str(p if p.exists() else Path(sys.executable))

def elevate_first():
    if is_admin():
        return False
    if "--elevated" in sys.argv or "--no-admin" in sys.argv:
        return False
    script = str(Path(sys.argv[0]).resolve())
    args = [script] + [a for a in sys.argv[1:] if a != "--elevated"] + ["--elevated"]
    if is_win():
        params = " ".join([f'"{a}"' if " " in a else a for a in args])
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", gui_python(), params, None, 1)
        elog(f"elevate rc={rc} exe={gui_python()} params={params}")
        return rc > 32
    if is_linux():
        pk = shutil.which("pkexec")
        if pk:
            env = [f"DISPLAY={os.environ.get('DISPLAY','')}", f"XAUTHORITY={os.environ.get('XAUTHORITY','')}"]
            subprocess.Popen([pk, "env"] + env + [sys.executable] + args)
            return True
    return False

try:
    if elevate_first():
        sys.exit(0)
except Exception:
    elog(traceback.format_exc())

SOURCES = {
    "OpenCorePkg": "https://github.com/acidanthera/OpenCorePkg/releases/download/1.0.7/OpenCore-1.0.7-RELEASE.zip",
    "gibMacOS": "https://github.com/corpnewt/gibMacOS/archive/refs/heads/master.zip",
    "OpCore-Simplify": "https://github.com/lzhoang2801/OpCore-Simplify/archive/refs/heads/main.zip",
    "OpCore-Simplify.py": "https://raw.githubusercontent.com/lzhoang2801/OpCore-Simplify/refs/heads/main/OpCore-Simplify.py"
}
MACOS = ["macOS High Sierra 10.13", "macOS Mojave 10.14", "macOS Catalina 10.15", "macOS Big Sur 11", "macOS Monterey 12", "macOS Ventura 13", "macOS Sonoma 14", "macOS Sequoia 15", "macOS Tahoe 26"]
TEXT = {
    "en": {
        "choose": "Choose language", "ready": "Select USB and macOS, then press FLASH.", "device": "Device", "macos": "macOS", "advanced": "Advanced options", "savefolder": "Save to folder instead of flashing USB", "verify": "Verify after flash/save", "confirm": "I understand the selected USB drive will be erased", "flash": "FLASH", "save": "SAVE", "cleanup": "Cleanup", "reports": "Reports", "efi": "EFI source", "recovery": "Recovery source", "browse": "Browse", "autofind": "Auto find", "noefi": "No usable EFI folder found or selected.", "nousb": "No USB device selected.", "nomacos": "No macOS selected.", "needconfirm": "Please tick the erase confirmation checkbox first.", "working": "Working...", "done": "Done.", "failed": "Failed.", "warn_dl": "Some downloads failed. You can still select EFI/Recovery manually."
    },
    "de": {
        "choose": "Sprache waehlen", "ready": "USB und macOS waehlen, dann FLASH druecken.", "device": "Laufwerk", "macos": "macOS", "advanced": "Erweiterte Optionen", "savefolder": "In Ordner speichern statt USB flashen", "verify": "Nach Flash/Speichern pruefen", "confirm": "Ich verstehe, dass das ausgewaehlte USB-Laufwerk geloescht wird", "flash": "FLASH", "save": "SPEICHERN", "cleanup": "Cleanup", "reports": "Reports", "efi": "EFI-Quelle", "recovery": "Recovery-Quelle", "browse": "Durchsuchen", "autofind": "Automatisch suchen", "noefi": "Kein nutzbarer EFI-Ordner gefunden oder gewaehlt.", "nousb": "Kein USB-Laufwerk gewaehlt.", "nomacos": "Kein macOS gewaehlt.", "needconfirm": "Bitte zuerst das Loesch-Bestaetigungskaestchen aktivieren.", "working": "Laeuft...", "done": "Fertig.", "failed": "Fehlgeschlagen.", "warn_dl": "Einige Downloads sind fehlgeschlagen. EFI/Recovery kann trotzdem manuell gewaehlt werden."
    }
}
STATE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "OpenCoreForge_state.json"

def hsize(x):
    try:
        x = int(x)
    except Exception:
        return str(x)
    for u in ["B", "KB", "MB", "GB", "TB"]:
        if x < 1024 or u == "TB":
            return f"{x:.1f} {u}"
        x /= 1024

def psjson(cmd):
    if not is_win():
        return []
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd + " | ConvertTo-Json -Depth 5"], capture_output=True, text=True, timeout=60)
        if not r.stdout.strip():
            return []
        j = json.loads(r.stdout)
        return j if isinstance(j, list) else [j]
    except Exception:
        return []

def usb_list():
    if is_win():
        out = []
        for d in psjson("Get-Disk | Select Number,FriendlyName,Model,Size,BusType,PartitionStyle,IsBoot,IsSystem"):
            if str(d.get("IsBoot", False)).lower() == "true" or str(d.get("IsSystem", False)).lower() == "true":
                continue
            if str(d.get("BusType", "")).lower() in ["usb", "sd", "mmc"]:
                out.append({"platform": "windows", **d})
        return out
    if is_linux():
        out = []
        try:
            r = subprocess.run(["lsblk", "-J", "-b", "-o", "NAME,MODEL,SIZE,TYPE,TRAN,RM,RO"], capture_output=True, text=True, timeout=30)
            for d in json.loads(r.stdout).get("blockdevices", []):
                if d.get("type") == "disk" and (str(d.get("tran", "")).lower() == "usb" or str(d.get("rm", "0")) == "1"):
                    out.append({"platform": "linux", "Path": "/dev/" + d.get("name", ""), "Model": d.get("model") or d.get("name"), "Size": d.get("size")})
        except Exception:
            pass
        return out
    return []

def validate(root):
    root = Path(root)
    rows = []
    def add(a,b): rows.append((a,b))
    def chk(p,n,fail=True): add("OK" if Path(p).exists() else ("FAIL" if fail else "WARN"), n if Path(p).exists() else n + " missing")
    chk(root / "EFI", "EFI folder")
    chk(root / "EFI" / "BOOT" / "BOOTx64.efi", "BOOTx64.efi")
    chk(root / "EFI" / "OC" / "config.plist", "config.plist")
    chk(root / "EFI" / "OC" / "Drivers" / "OpenRuntime.efi", "OpenRuntime.efi")
    rec = root / "com.apple.recovery.boot"
    chk(rec, "Recovery folder", False)
    if rec.exists():
        chk(rec / "BaseSystem.dmg", "BaseSystem.dmg")
        chk(rec / "BaseSystem.chunklist", "BaseSystem.chunklist", False)
    status = "passed"
    for a,_ in rows:
        if a == "FAIL": status = "failed"; break
        if a == "WARN": status = "warnings"
    return status, rows

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
except Exception:
    elog(traceback.format_exc())
    raise

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.lang = "en"
        self.selected_usb = None
        self.selected_macos = None
        self.usb = []
        self.efi = None
        self.recovery = None
        self.errors = []
        self.q = queue.Queue()
        self.load_state()
        self.setup_style()
        self.title(f"{APP} {VER}")
        self.geometry("520x400")
        self.minsize(500, 360)
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.show_language()
        self.after(80, self.drain)

    def report_callback_exception(self, exc, val, tb):
        err = "".join(traceback.format_exception(exc, val, tb))
        (LOGS / "gui_callback_error.log").write_text(err, encoding="utf-8")
        messagebox.showerror(APP, err[-3500:])

    def t(self, k): return TEXT.get(self.lang, TEXT["en"]).get(k, k)
    def load_state(self):
        try:
            if STATE.exists(): self.lang = json.loads(STATE.read_text(encoding="utf-8")).get("lang", self.lang)
        except Exception: pass
    def save_state(self):
        try: STATE.write_text(json.dumps({"lang": self.lang}, indent=2), encoding="utf-8")
        except Exception: pass
    def setup_style(self):
        st = ttk.Style(self)
        try: st.theme_use("clam")
        except Exception: pass
        self.configure(bg="#f3f4f6")
        st.configure("TFrame", background="#f3f4f6")
        st.configure("TLabel", background="#f3f4f6", font=("Segoe UI", 9))
        st.configure("Title.TLabel", background="#f3f4f6", font=("Segoe UI", 14, "bold"))
        st.configure("Small.TLabel", background="#f3f4f6", foreground="#4b5563", font=("Segoe UI", 8))
        st.configure("TButton", padding=(8,5), font=("Segoe UI", 9))
        st.configure("Flash.TButton", padding=(14,7), font=("Segoe UI", 10, "bold"))
    def clear(self):
        for w in self.winfo_children(): w.destroy()
    def show_language(self):
        self.clear()
        m = ttk.Frame(self, padding=18); m.pack(fill="both", expand=True)
        ttk.Label(m, text=APP, style="Title.TLabel").pack(anchor="w")
        ttk.Label(m, text="Choose language / Sprache waehlen", style="Small.TLabel").pack(anchor="w", pady=(0,22))
        r = ttk.Frame(m); r.pack(expand=True)
        ttk.Button(r, text="English", command=lambda: self.start("en")).pack(side="left", padx=10, ipadx=10, ipady=8)
        ttk.Button(r, text="Deutsch", command=lambda: self.start("de")).pack(side="left", padx=10, ipadx=10, ipady=8)
    def start(self, lang):
        self.lang = lang
        self.save_state()
        self.show_prepare()
        threading.Thread(target=self.bootstrap, daemon=True).start()
    def show_prepare(self):
        self.clear()
        m = ttk.Frame(self, padding=18); m.pack(fill="both", expand=True)
        ttk.Label(m, text=APP, style="Title.TLabel").pack(anchor="w")
        ttk.Label(m, text=self.t("working")).pack(anchor="w", pady=20)
        pb = ttk.Progressbar(m, mode="indeterminate"); pb.pack(fill="x"); pb.start(8)
        ttk.Label(m, text=str(BASE), style="Small.TLabel", wraplength=460).pack(anchor="w", pady=10)
    def put(self, fn, *args): self.q.put((fn,args))
    def drain(self):
        try:
            while True:
                fn,args = self.q.get_nowait(); fn(*args)
        except queue.Empty: pass
        self.after(80, self.drain)
    def bootstrap(self):
        try:
            report = {"app": APP, "version": VER, "admin": is_admin(), "platform": sys.platform, "workspace": str(BASE)}
            (REPORTS / "environment_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            self.downloads()
            self.usb = usb_list()
            self.find_outputs()
        except Exception:
            err = traceback.format_exc(); (LOGS / "startup_after_language.log").write_text(err, encoding="utf-8"); self.put(messagebox.showerror, APP, err[-3500:])
        self.put(self.build_main)
    def downloads(self):
        for name,url in SOURCES.items():
            ext = ".py" if url.endswith(".py") else ".zip"
            target = DOWNLOADS / ("".join(c if c.isalnum() or c in "-_" else "_" for c in name) + ext)
            if target.exists() and target.stat().st_size > 0: continue
            ok, err = self.download(url, target)
            if not ok: self.errors.append(f"{name}: {err}")
        for z in DOWNLOADS.glob("*.zip"):
            dest = EXTRACTED / z.stem
            if dest.exists() and any(dest.iterdir()): continue
            dest.mkdir(parents=True, exist_ok=True)
            try:
                with zipfile.ZipFile(z, "r") as f: f.extractall(dest)
            except Exception as e: self.errors.append(f"extract {z.name}: {e}")
        if self.errors: (LOGS / "download_errors.log").write_text("\n".join(self.errors), encoding="utf-8")
    def download(self, url, target):
        last = ""
        for i in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": f"Mozilla/5.0 {APP}/{VER}"})
                with urllib.request.urlopen(req, timeout=120) as r, target.open("wb") as f: shutil.copyfileobj(r,f)
                if target.exists() and target.stat().st_size > 0: return True, ""
            except Exception as e: last=str(e); time.sleep(i+1)
        return False, last
    def find_outputs(self):
        efis=[]; recs=[]
        for root in [BASE, Path.home(), Path.cwd()]:
            try:
                for p in root.rglob("EFI"):
                    if (p / "OC" / "config.plist").exists(): efis.append(p)
                for p in root.rglob("com.apple.recovery.boot"):
                    if (p / "BaseSystem.dmg").exists() or (p / "BaseSystem.chunklist").exists(): recs.append(p)
            except Exception: pass
        self.efi = sorted(efis, key=lambda x: len(str(x)))[0] if efis else None
        self.recovery = sorted(recs, key=lambda x: len(str(x)))[0] if recs else None
    def build_main(self):
        self.clear(); self.geometry("520x420")
        m=ttk.Frame(self,padding=10); m.pack(fill="both",expand=True)
        ttk.Label(m,text=APP,style="Title.TLabel").grid(row=0,column=0,sticky="w")
        self.sub=ttk.Label(m,text=self.t("ready"),style="Small.TLabel"); self.sub.grid(row=1,column=0,sticky="w",pady=(0,6))
        form=ttk.Frame(m); form.grid(row=2,column=0,sticky="ew"); form.columnconfigure(1,weight=1)
        ttk.Label(form,text=self.t("device")).grid(row=0,column=0,sticky="w",padx=(0,8),pady=4)
        self.devvar=tk.StringVar(); self.devbox=ttk.Combobox(form,textvariable=self.devvar,state="readonly",width=38); self.devbox.grid(row=0,column=1,sticky="ew",pady=4); self.devbox.bind("<<ComboboxSelected>>",lambda e:self.seldev())
        ttk.Label(form,text=self.t("macos")).grid(row=1,column=0,sticky="w",padx=(0,8),pady=4)
        self.osvar=tk.StringVar(); self.osbox=ttk.Combobox(form,textvariable=self.osvar,state="readonly",width=38); self.osbox.grid(row=1,column=1,sticky="ew",pady=4); self.osbox.bind("<<ComboboxSelected>>",lambda e:self.selos())
        self.advopen=tk.BooleanVar(False); self.advbtn=ttk.Checkbutton(m,text="▼ "+self.t("advanced"),variable=self.advopen,command=self.toggle); self.advbtn.grid(row=3,column=0,sticky="w",pady=(5,0)); self.adv=ttk.Frame(m)
        self.savefolder=tk.BooleanVar(False); self.secure=tk.StringVar(value="Disabled"); self.scan=tk.StringVar(value="0"); self.hide=tk.StringVar(value="False"); self.verbose=tk.BooleanVar(value=True)
        ttk.Checkbutton(self.adv,text=self.t("savefolder"),variable=self.savefolder,command=self.updatebtn).grid(row=0,column=0,columnspan=3,sticky="w")
        self.opt(1,self.t("secure"),self.secure,["Disabled","Default"]); self.opt(2,self.t("scan"),self.scan,["0","Default"]); self.opt(3,self.t("hide"),self.hide,["False","True"]); ttk.Checkbutton(self.adv,text=self.t("verbose"),variable=self.verbose).grid(row=4,column=1,sticky="w")
        ttk.Label(self.adv,text=self.t("efi")).grid(row=5,column=0,sticky="w"); self.efil=ttk.Label(self.adv,text=str(self.efi) if self.efi else "-",width=28); self.efil.grid(row=5,column=1,sticky="ew"); ttk.Button(self.adv,text=self.t("browse"),command=self.pickefi).grid(row=5,column=2,padx=3)
        ttk.Label(self.adv,text=self.t("recovery")).grid(row=6,column=0,sticky="w"); self.recl=ttk.Label(self.adv,text=str(self.recovery) if self.recovery else "-",width=28); self.recl.grid(row=6,column=1,sticky="ew"); ttk.Button(self.adv,text=self.t("browse"),command=self.pickrec).grid(row=6,column=2,padx=3)
        self.status=tk.Text(m,height=6,width=55,bg="#111827",fg="#e5e7eb",relief="flat",font=("Consolas",8),wrap="word"); self.status.grid(row=5,column=0,sticky="nsew",pady=(7,6)); m.rowconfigure(5,weight=1)
        b=ttk.Frame(m); b.grid(row=6,column=0,sticky="ew"); b.columnconfigure(1,weight=1)
        self.verify=tk.BooleanVar(True); self.confirm=tk.BooleanVar(False); ch=ttk.Frame(b); ch.grid(row=0,column=0,sticky="w")
        ttk.Checkbutton(ch,text=self.t("verify"),variable=self.verify).pack(anchor="w"); ttk.Checkbutton(ch,text=self.t("confirm"),variable=self.confirm).pack(anchor="w")
        ttk.Button(b,text=self.t("cleanup"),command=self.cleanup).grid(row=0,column=1,sticky="e",padx=2); ttk.Button(b,text=self.t("reports"),command=lambda:self.open_path(REPORTS)).grid(row=0,column=2,sticky="e",padx=2)
        self.flashbtn=ttk.Button(b,text=self.t("flash"),style="Flash.TButton",command=self.flash); self.flashbtn.grid(row=0,column=3,sticky="e")
        self.populate(); self.log(self.t("ready"));
        if self.errors: self.log(self.t("warn_dl") + "\n" + "\n".join(self.errors))
    def opt(self,r,l,var,vals): ttk.Label(self.adv,text=l).grid(row=r,column=0,sticky="w"); ttk.Combobox(self.adv,textvariable=var,values=vals,state="readonly",width=14).grid(row=r,column=1,sticky="w")
    def toggle(self): self.adv.grid(row=4,column=0,sticky="ew",pady=2) if self.advopen.get() else self.adv.grid_remove(); self.advbtn.config(text=("▲ " if self.advopen.get() else "▼ ")+self.t("advanced"))
    def updatebtn(self): self.flashbtn.config(text=self.t("save") if self.savefolder.get() else self.t("flash")); self.sub.config(text=self.t("ready_save") if self.savefolder.get() else self.t("ready"))
    def populate(self):
        vals=[]
        for d in self.usb: vals.append(f"Disk {d.get('Number')} | {d.get('FriendlyName')} | {hsize(d.get('Size',0))}" if d.get("platform")=="windows" else f"{d.get('Path')} | {d.get('Model')} | {hsize(d.get('Size',0))}")
        self.devbox["values"]=vals
        if vals: self.devvar.set(vals[0]); self.seldev()
        self.osbox["values"] = MACOS
    def seldev(self): i=self.devbox.current(); self.selected_usb=self.usb[i] if 0<=i<len(self.usb) else None
    def selos(self): i=self.osbox.current(); self.selected_macos=MACOS[i] if 0<=i<len(MACOS) else None
    def pickefi(self):
        p=filedialog.askdirectory(title=self.t("efi"))
        if p: self.efi=Path(p); self.efil.config(text=str(self.efi))
    def pickrec(self):
        p=filedialog.askdirectory(title=self.t("recovery"))
        if p: self.recovery=Path(p); self.recl.config(text=str(self.recovery))
    def log(self,msg):
        line=time.strftime("[%H:%M:%S] ")+str(msg)+"\n"; self.status.insert("end",line); self.status.see("end")
        try: (LOGS/"app.log").open("a",encoding="utf-8").write(line)
        except Exception: pass
    def flash(self):
        if not self.selected_macos: messagebox.showwarning(APP,self.t("nomacos")); return
        if not self.efi or not Path(self.efi).exists(): messagebox.showerror(APP,self.t("noefi")); return
        if self.savefolder.get():
            p=filedialog.askdirectory(title=self.t("savefolder"))
            if p: threading.Thread(target=lambda:self.save_to(Path(p)),daemon=True).start()
            return
        if not self.selected_usb: messagebox.showwarning(APP,self.t("nousb")); return
        if not self.confirm.get(): messagebox.showwarning(APP,self.t("needconfirm")); return
        threading.Thread(target=self.flash_worker,daemon=True).start()
    def save_to(self,target):
        try: self.put(self.log,self.t("working")); self.copy_payload(target); self.patch(target); self.report(target) if self.verify.get() else None; self.put(self.log,self.t("done"))
        except Exception: self.err()
    def flash_worker(self):
        try: self.put(self.log,self.t("working")); target=self.format_usb(); self.copy_payload(target); self.patch(target); self.report(target) if self.verify.get() else None; self.put(self.log,self.t("done"))
        except Exception: self.err()
    def copy_payload(self,target):
        dst=target/"EFI"; shutil.rmtree(dst,ignore_errors=True); shutil.copytree(self.efi,dst)
        if self.recovery and Path(self.recovery).exists(): rec=target/"com.apple.recovery.boot"; shutil.rmtree(rec,ignore_errors=True); shutil.copytree(self.recovery,rec)
    def report(self,target):
        status,rows=validate(target); rp=REPORTS/("validation_"+time.strftime("%Y%m%d_%H%M%S")+".txt"); lines=[f"{APP} {VER}",f"Target: {target}",f"macOS: {self.selected_macos}",""]+[f"[{a}] {b}" for a,b in rows]; rp.write_text("\n".join(lines),encoding="utf-8"); self.put(self.log,"\n".join(lines[-len(rows):])); msg=self.t("ok") if status=="passed" else self.t("warn") if status=="warnings" else self.t("fail"); self.put(messagebox.showinfo if status!="failed" else messagebox.showerror,APP,msg+"\n\n"+str(rp))
    def format_usb(self):
        if is_win():
            num=self.selected_usb.get("Number"); ps=BASE/"flash_usb.ps1"; ps.write_text(f"""$ErrorActionPreference='Stop'\n$diskNumber={num}\n$d=Get-Disk -Number $diskNumber\nif($d.IsBoot -or $d.IsSystem){{throw 'Refusing boot/system disk'}}\nSet-Disk -Number $diskNumber -IsReadOnly $false -ErrorAction SilentlyContinue\nSet-Disk -Number $diskNumber -IsOffline $false -ErrorAction SilentlyContinue\nClear-Disk -Number $diskNumber -RemoveData -RemoveOEM -Confirm:$false\nInitialize-Disk -Number $diskNumber -PartitionStyle GPT\n$p=New-Partition -DiskNumber $diskNumber -Size 4GB -AssignDriveLetter\nFormat-Volume -Partition $p -FileSystem FAT32 -NewFileSystemLabel OPENCORE -Confirm:$false -Force\n(Get-Volume -Partition $p).DriveLetter\n""",encoding="utf-8"); r=subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-File",str(ps)],capture_output=True,text=True,timeout=180); (LOGS/"powershell_flash_stdout.log").write_text(r.stdout or "",encoding="utf-8"); (LOGS/"powershell_flash_stderr.log").write_text(r.stderr or "",encoding="utf-8"); self.put(self.log,(r.stdout or "")+"\n"+(r.stderr or ""));
            if r.returncode!=0: raise RuntimeError("PowerShell format failed: "+((r.stderr or r.stdout).strip()[-600:]))
            letters=[x.strip().replace(":","") for x in r.stdout.splitlines() if x.strip()]
            if not letters: raise RuntimeError("No drive letter returned after formatting")
            target=Path(f"{letters[-1]}:/")
            for _ in range(30):
                if target.exists(): return target
                time.sleep(.25)
            raise RuntimeError(f"Drive {letters[-1]}: not available")
        raise RuntimeError("Unsupported platform")
    def patch(self,target):
        cfg=target/"EFI"/"OC"/"config.plist"
        if not cfg.exists(): return
        try:
            shutil.copy2(cfg,cfg.with_suffix(".plist.before_forge")); pl=plistlib.load(cfg.open("rb")); pl.setdefault("Misc",{}).setdefault("Security",{})["SecureBootModel"]="Disabled"; pl.setdefault("Misc",{}).setdefault("Security",{})["ScanPolicy"]=0; pl.setdefault("Misc",{}).setdefault("Boot",{})["HideAuxiliary"]=False; plistlib.dump(pl,cfg.open("wb"))
        except Exception as e: self.put(self.log,"config patch skipped: "+str(e))
    def err(self):
        err=traceback.format_exc(); (LOGS/"operation_error.log").write_text(err,encoding="utf-8"); clean=err.splitlines()[-1]; self.put(self.log,self.t("failed")+": "+clean); self.put(messagebox.showerror,APP,self.t("failed")+"\n\n"+clean)
    def open_path(self,p):
        if is_win(): os.startfile(str(p))
        elif is_linux(): subprocess.Popen(["xdg-open",str(p)])
        else: subprocess.Popen(["open",str(p)])
    def cleanup(self):
        if messagebox.askyesno(APP,self.t("cleanup1")):
            for p in [DOWNLOADS,EXTRACTED,OUTPUT]: shutil.rmtree(p,ignore_errors=True); p.mkdir(parents=True,exist_ok=True)
            self.log(self.t("done"))
    def close(self): self.save_state(); self.destroy()

if __name__ == "__main__":
    try:
        App().mainloop()
    except Exception:
        err=traceback.format_exc(); LOGS.mkdir(parents=True,exist_ok=True); (LOGS/"crash.log").write_text(err,encoding="utf-8")
        try:
            if is_win(): ctypes.windll.user32.MessageBoxW(None,err[-3500:],APP,0x10)
        except Exception: pass
        print(err)
