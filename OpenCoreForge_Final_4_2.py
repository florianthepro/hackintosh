
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, json, time, queue, shutil, zipfile, hashlib, plistlib, tempfile, threading, traceback, subprocess, urllib.request, ctypes
from pathlib import Path

APP="OpenCore Forge"
VER="4.2.0"


def is_win(): return os.name == "nt"
def is_linux(): return sys.platform.startswith("linux")
def is_admin():
    if is_win():
        try: return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception: return False
    try: return os.geteuid() == 0
    except Exception: return False

def pyw():
    if not is_win(): return sys.executable
    p = Path(sys.executable).with_name("pythonw.exe")
    return str(p if p.exists() else Path(sys.executable))

def elevate_now():
    if is_admin(): return True
    script = str(Path(sys.argv[0]).resolve())
    args = [script] + [a for a in sys.argv[1:] if a != "--elevated"] + ["--elevated"]
    if is_win():
        params = " ".join([f'"{a}"' if " " in a else a for a in args])
        return ctypes.windll.shell32.ShellExecuteW(None, "runas", pyw(), params, None, 1) > 32
    if is_linux():
        pk = shutil.which("pkexec")
        if pk:
            env = [f"DISPLAY={os.environ.get('DISPLAY','')}", f"XAUTHORITY={os.environ.get('XAUTHORITY','')}"]
            subprocess.Popen([pk, "env"] + env + [sys.executable] + args)
            return True
    return False

# Admin before workspace, downloads, scan or GUI.
if not is_admin() and "--elevated" not in sys.argv and "--no-admin" not in sys.argv:
    if elevate_now():
        sys.exit(0)

BASE = Path(tempfile.gettempdir()) / "OpenCoreForge_Runtime"
DOWNLOADS, EXTRACTED, TOOLS, OUTPUT, REPORTS, LOGS = [BASE / x for x in ["downloads","extracted","tools","output","reports","logs"]]
for p in [BASE, DOWNLOADS, EXTRACTED, TOOLS, OUTPUT, REPORTS, LOGS]: p.mkdir(parents=True, exist_ok=True)
STATE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "OpenCoreForge_state.json"

SOURCES = {
    "OpCore-Simplify": "https://github.com/lzhoang2801/OpCore-Simplify/archive/refs/heads/main.zip",
    "OpCore-Simplify.py": "https://raw.githubusercontent.com/lzhoang2801/OpCore-Simplify/refs/heads/main/OpCore-Simplify.py",
    "OpenCorePkg": "https://github.com/acidanthera/OpenCorePkg/releases/download/1.0.7/OpenCore-1.0.7-RELEASE.zip",
    "gibMacOS": "https://github.com/corpnewt/gibMacOS/archive/refs/heads/master.zip",
}
MACOS=[("macOS High Sierra","10.13","Legacy"),("macOS Mojave","10.14","Legacy"),("macOS Catalina","10.15","Stable"),("macOS Big Sur","11","Stable"),("macOS Monterey","12","Recommended"),("macOS Ventura","13","Modern"),("macOS Sonoma","14","Modern"),("macOS Sequoia","15","Current"),("macOS Tahoe","26","Experimental")]
TXT={
"en":{"lang":"Choose language / Sprache wählen","ready":"Ready. Select device and macOS, then press FLASH.","ready_save":"Ready. Select macOS, then press SAVE.","device":"Device","macos":"macOS","advanced":"Advanced options","save_folder":"Save to folder instead of flashing USB","verify":"Verify after flash/save","confirm":"I understand the selected USB drive will be erased","confirm_need":"Please tick the erase confirmation checkbox first.","flash":"FLASH","save":"SAVE","cleanup":"Cleanup","workspace":"Workspace","reports":"Reports","efi":"EFI source","recovery":"Recovery source","browse":"Browse","auto_find":"Auto find","secure":"SecureBootModel","scan":"ScanPolicy","hide":"HideAuxiliary","verbose":"Verbose boot","no_macos":"No macOS version selected.","no_usb":"No USB device selected.","no_efi":"No usable EFI folder was found or selected.","done":"Done.","failed":"Failed.","saving":"Saving EFI and Recovery folder...","flashing":"Flashing...","clean":"Clean error description","download_warn":"Some downloads failed. The tool remains usable; missing components may need manual selection.","ok":"Verification passed.","warn":"Verification passed with warnings.","fail":"Verification failed.","cleanup1":"Remove temporary downloads, extracted tools and output? Reports/logs will be kept.","cleanup2":"Remove the full temporary workspace including reports and logs?","cleanup_done":"Temporary files removed.","prep":"Preparing..."},
"de":{"lang":"Sprache wählen / Choose language","ready":"Bereit. Laufwerk und macOS wählen, dann FLASH drücken.","ready_save":"Bereit. macOS wählen, dann SPEICHERN drücken.","device":"Laufwerk","macos":"macOS","advanced":"Erweiterte Optionen","save_folder":"In Ordner speichern statt USB flashen","verify":"Nach Flash/Speichern überprüfen","confirm":"Ich verstehe, dass das ausgewählte USB-Laufwerk gelöscht wird","confirm_need":"Bitte zuerst das Lösch-Bestätigungskästchen aktivieren.","flash":"FLASH","save":"SPEICHERN","cleanup":"Cleanup","workspace":"Workspace","reports":"Reports","efi":"EFI-Quelle","recovery":"Recovery-Quelle","browse":"Durchsuchen","auto_find":"Automatisch suchen","secure":"SecureBootModel","scan":"ScanPolicy","hide":"HideAuxiliary","verbose":"Verbose Boot","no_macos":"Keine macOS-Version ausgewählt.","no_usb":"Kein USB-Laufwerk ausgewählt.","no_efi":"Kein nutzbarer EFI-Ordner gefunden oder ausgewählt.","done":"Fertig.","failed":"Fehlgeschlagen.","saving":"EFI und Recovery-Ordner werden gespeichert...","flashing":"Flash läuft...","clean":"Saubere Fehlerbeschreibung","download_warn":"Einige Downloads sind fehlgeschlagen. Das Tool bleibt nutzbar; fehlende Bestandteile müssen ggf. manuell gewählt werden.","ok":"Überprüfung bestanden.","warn":"Überprüfung mit Warnungen bestanden.","fail":"Überprüfung fehlgeschlagen.","cleanup1":"Temporäre Downloads, extrahierte Tools und Output entfernen? Reports/Logs bleiben erhalten.","cleanup2":"Kompletten temporären Workspace inklusive Reports und Logs entfernen?","cleanup_done":"Temporäre Dateien entfernt.","prep":"Vorbereitung läuft..."}}

def hsize(n):
    try: n=int(n)
    except Exception: return str(n)
    for u in ["B","KB","MB","GB","TB"]:
        if n < 1024 or u == "TB": return f"{n:.1f} {u}"
        n /= 1024

def psjson(cmd, timeout=80):
    if not is_win(): return []
    try:
        r=subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command",cmd+" | ConvertTo-Json -Depth 6"],capture_output=True,text=True,timeout=timeout)
        if not r.stdout.strip(): return []
        j=json.loads(r.stdout); return j if isinstance(j,list) else [j]
    except Exception: return []

def usb_list():
    if is_win():
        out=[]
        for d in psjson("Get-Disk | Select Number,FriendlyName,Model,Size,BusType,PartitionStyle,IsBoot,IsSystem"):
            if str(d.get("IsBoot",False)).lower()=="true" or str(d.get("IsSystem",False)).lower()=="true": continue
            if str(d.get("BusType","")).lower() in ["usb","sd","mmc"]: out.append({"platform":"windows",**d})
        return out
    if is_linux():
        out=[]
        try:
            r=subprocess.run(["lsblk","-J","-b","-o","NAME,MODEL,SIZE,TYPE,TRAN,RM,RO,MOUNTPOINT"],capture_output=True,text=True,timeout=30)
            for d in json.loads(r.stdout).get("blockdevices",[]):
                if d.get("type")=="disk" and (str(d.get("tran","")).lower()=="usb" or str(d.get("rm","0"))=="1") and str(d.get("ro","0")) not in ["1","True","true"]:
                    out.append({"platform":"linux","Path":"/dev/"+d.get("name",""),"Model":d.get("model") or d.get("name"),"Size":d.get("size")})
        except Exception: pass
        return out
    return []

def report_env():
    data={"app":APP,"version":VER,"python":sys.version,"executable":sys.executable,"admin":is_admin(),"platform":sys.platform,"workspace":str(BASE)}
    if is_win(): data["disks"]=psjson("Get-Disk | Select Number,FriendlyName,Model,Size,BusType,PartitionStyle,IsBoot,IsSystem")
    (REPORTS/"environment_report.json").write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")

def download(url,target):
    last=""
    for i in range(3):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":f"Mozilla/5.0 {APP}/{VER}"})
            with urllib.request.urlopen(req,timeout=120) as r, target.open("wb") as f: shutil.copyfileobj(r,f)
            if target.exists() and target.stat().st_size>0: return True,""
        except Exception as e: last=str(e); time.sleep(i+1)
    try: target.unlink(missing_ok=True)
    except Exception: pass
    return False,last

def validate(root):
    root=Path(root); rows=[]
    def add(a,b): rows.append((a,b))
    def chk(p,n,fail=True): add("OK" if Path(p).exists() else ("FAIL" if fail else "WARN"), n if Path(p).exists() else n+" missing")
    chk(root/"EFI","EFI folder"); chk(root/"EFI"/"BOOT"/"BOOTx64.efi","BOOTx64.efi"); chk(root/"EFI"/"OC"/"config.plist","config.plist"); chk(root/"EFI"/"OC"/"Drivers"/"OpenRuntime.efi","OpenRuntime.efi")
    drivers=root/"EFI"/"OC"/"Drivers"; hfs=drivers.exists() and any(x.name.lower() in ["hfsplus.efi","openhfsplus.efi"] for x in drivers.iterdir())
    add("OK" if hfs else "WARN","HFS driver" if hfs else "HFS driver missing")
    rec=root/"com.apple.recovery.boot"; chk(rec,"Recovery folder",False)
    if rec.exists():
        chk(rec/"BaseSystem.dmg","BaseSystem.dmg"); chk(rec/"BaseSystem.chunklist","BaseSystem.chunklist",False)
        dmg=rec/"BaseSystem.dmg"
        if dmg.exists():
            hs=hashlib.sha256()
            with dmg.open("rb") as f:
                for c in iter(lambda:f.read(8*1024*1024),b""): hs.update(c)
            add("OK","BaseSystem.dmg SHA256 "+hs.hexdigest())
    cfg=root/"EFI"/"OC"/"config.plist"
    if cfg.exists():
        try:
            with cfg.open("rb") as f: pl=plistlib.load(f)
            add("OK","config.plist parsed")
            sp=pl.get("Misc",{}).get("Security",{}).get("ScanPolicy"); ha=pl.get("Misc",{}).get("Boot",{}).get("HideAuxiliary"); sb=pl.get("Misc",{}).get("Security",{}).get("SecureBootModel")
            add("OK" if sp==0 else "WARN",f"ScanPolicy={sp}"); add("OK" if ha is False else "WARN",f"HideAuxiliary={ha}"); add("OK" if str(sb).lower()=="disabled" else "WARN",f"SecureBootModel={sb}")
        except Exception as e: add("FAIL","config.plist parse failed: "+str(e))
    status="passed"
    for a,_ in rows:
        if a=="FAIL": status="failed"; break
        if a=="WARN": status="warnings"
    return status,rows

try:
    import tkinter as tk
    from tkinter import ttk,messagebox,filedialog
except Exception as e:
    print("Tkinter required",e); raise

class Splash(tk.Toplevel):
    def __init__(self,master):
        super().__init__(master); self.title(APP); self.geometry("440x145"); self.resizable(False,False); self.configure(bg="#f3f4f6")
        self.label=tk.Label(self,text="Preparing...",bg="#f3f4f6",font=("Segoe UI",12,"bold")); self.label.pack(pady=(22,12))
        pb=ttk.Progressbar(self,mode="indeterminate",length=340); pb.pack(); pb.start(8)
        tk.Label(self,text=str(BASE),bg="#f3f4f6",fg="#4b5563",wraplength=400,font=("Segoe UI",8)).pack(pady=8)
class Lang(tk.Toplevel):
    def __init__(self,master,cb):
        super().__init__(master); self.cb=cb; self.title(APP); self.geometry("330x180"); self.resizable(False,False); self.configure(bg="#f3f4f6")
        tk.Label(self,text="Choose language / Sprache wählen",bg="#f3f4f6",font=("Segoe UI",12,"bold")).pack(pady=(20,14))
        r=tk.Frame(self,bg="#f3f4f6"); r.pack()
        tk.Button(r,text="🇬🇧 English",width=12,height=2,command=lambda:self.pick("en"),font=("Segoe UI",10)).pack(side="left",padx=8)
        tk.Button(r,text="🇩🇪 Deutsch",width=12,height=2,command=lambda:self.pick("de"),font=("Segoe UI",10)).pack(side="left",padx=8)
    def pick(self,l): self.cb(l); self.destroy()

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.withdraw(); self.lang="en"; self.usb=[]; self.efi=None; self.recovery=None; self.selected_usb=None; self.selected_macos=None; self.errors=[]; self.q=queue.Queue(); self.load(); self.splash=Splash(self); self.after(80,self.drain); threading.Thread(target=self.boot,daemon=True).start()
    def t(self,k): return TXT[self.lang].get(k,k)
    def load(self):
        try:
            if STATE.exists(): self.lang=json.loads(STATE.read_text(encoding="utf-8")).get("lang",self.lang)
        except Exception: pass
    def save_state(self):
        try: STATE.write_text(json.dumps({"lang":self.lang},indent=2),encoding="utf-8")
        except Exception: pass
    def put(self,fn,*args): self.q.put((fn,args))
    def drain(self):
        try:
            while True:
                f,a=self.q.get_nowait(); f(*a)
        except queue.Empty: pass
        self.after(80,self.drain)
    def boot(self):
        try:
            self.put(self.splash.label.config,{"text":"Creating reports..."}); report_env()
            self.put(self.splash.label.config,{"text":"Downloading tools..."}); self.downloads()
            self.put(self.splash.label.config,{"text":"Scanning USB devices..."}); self.usb=usb_list(); self.find()
        except Exception:
            err=traceback.format_exc(); (LOGS/"crash.log").write_text(err,encoding="utf-8"); self.put(messagebox.showerror,APP,err[-3000:])
        self.put(self.ready)
    def downloads(self):
        for n,u in SOURCES.items():
            ext=".py" if u.endswith(".py") else ".zip"; target=DOWNLOADS/("".join(c if c.isalnum() or c in "-_" else "_" for c in n)+ext)
            if target.exists() and target.stat().st_size>0: continue
            ok,e=download(u,target)
            if not ok: self.errors.append(f"{n}: {e}")
        for z in DOWNLOADS.glob("*.zip"):
            d=EXTRACTED/z.stem
            if d.exists() and any(d.iterdir()): continue
            d.mkdir(parents=True,exist_ok=True)
            try:
                with zipfile.ZipFile(z,"r") as f: f.extractall(d)
            except Exception as e: self.errors.append(f"extract {z.name}: {e}")
        if self.errors: (LOGS/"download_errors.log").write_text("\n".join(self.errors),encoding="utf-8")
    def find(self):
        efis=[]; recs=[]
        for root in [BASE,Path.home(),Path.cwd()]:
            try:
                for p in root.rglob("EFI"):
                    if (p/"OC"/"config.plist").exists(): efis.append(p)
                for p in root.rglob("com.apple.recovery.boot"):
                    if (p/"BaseSystem.dmg").exists() or (p/"BaseSystem.chunklist").exists(): recs.append(p)
            except Exception: pass
        self.efi=sorted(efis,key=lambda x:len(str(x)))[0] if efis else None; self.recovery=sorted(recs,key=lambda x:len(str(x)))[0] if recs else None
    def ready(self): self.splash.destroy(); Lang(self,self.set_lang)
    def set_lang(self,l): self.lang=l; self.save_state(); self.build(); self.deiconify(); [self.log(x) for x in ([self.t("download_warn")]+self.errors if self.errors else [])]
    def style(self):
        s=ttk.Style(self)
        try: s.theme_use("clam")
        except Exception: pass
        self.configure(bg="#f3f4f6"); s.configure("TFrame",background="#f3f4f6"); s.configure("TLabel",background="#f3f4f6",font=("Segoe UI",9)); s.configure("Title.TLabel",background="#f3f4f6",font=("Segoe UI",14,"bold")); s.configure("Small.TLabel",background="#f3f4f6",foreground="#4b5563",font=("Segoe UI",8)); s.configure("TButton",padding=(8,5),font=("Segoe UI",9)); s.configure("Flash.TButton",padding=(14,7),font=("Segoe UI",10,"bold"))
    def build(self):
        self.style(); self.title(f"{APP} {VER}"); self.geometry("520x420"); self.minsize(500,390); self.resizable(True,True); self.protocol("WM_DELETE_WINDOW",self.close)
        m=ttk.Frame(self,padding=10); m.pack(fill="both",expand=True)
        ttk.Label(m,text=APP,style="Title.TLabel").grid(row=0,column=0,sticky="w"); self.sub=ttk.Label(m,text=self.t("ready"),style="Small.TLabel"); self.sub.grid(row=1,column=0,sticky="w",pady=(0,6))
        form=ttk.Frame(m); form.grid(row=2,column=0,sticky="ew"); form.columnconfigure(1,weight=1)
        ttk.Label(form,text=self.t("device")).grid(row=0,column=0,sticky="w",padx=(0,8),pady=4); self.devvar=tk.StringVar(); self.devbox=ttk.Combobox(form,textvariable=self.devvar,state="readonly",width=41); self.devbox.grid(row=0,column=1,sticky="ew",pady=4); self.devbox.bind("<<ComboboxSelected>>",lambda e:self.seldev())
        ttk.Label(form,text=self.t("macos")).grid(row=1,column=0,sticky="w",padx=(0,8),pady=4); self.osvar=tk.StringVar(); self.osbox=ttk.Combobox(form,textvariable=self.osvar,state="readonly",width=41); self.osbox.grid(row=1,column=1,sticky="ew",pady=4); self.osbox.bind("<<ComboboxSelected>>",lambda e:self.selos())
        self.advopen=tk.BooleanVar(False); self.advbtn=ttk.Checkbutton(m,text="▼ "+self.t("advanced"),variable=self.advopen,command=self.toggle); self.advbtn.grid(row=3,column=0,sticky="w",pady=(5,0)); self.adv=ttk.Frame(m)
        self.savefolder=tk.BooleanVar(False); self.secure=tk.StringVar(value="Disabled"); self.scan=tk.StringVar(value="0"); self.hide=tk.StringVar(value="False"); self.verbose=tk.BooleanVar(value=True)
        ttk.Checkbutton(self.adv,text=self.t("save_folder"),variable=self.savefolder,command=self.updatebtn).grid(row=0,column=0,columnspan=3,sticky="w")
        self.opt(1,self.t("secure"),self.secure,["Disabled","Default"]); self.opt(2,self.t("scan"),self.scan,["0","Default"]); self.opt(3,self.t("hide"),self.hide,["False","True"]); ttk.Checkbutton(self.adv,text=self.t("verbose"),variable=self.verbose).grid(row=4,column=1,sticky="w")
        ttk.Label(self.adv,text=self.t("efi")).grid(row=5,column=0,sticky="w"); self.efil=ttk.Label(self.adv,text=str(self.efi) if self.efi else "-",width=32); self.efil.grid(row=5,column=1,sticky="ew"); ttk.Button(self.adv,text=self.t("browse"),command=self.pickefi).grid(row=5,column=2,padx=3)
        ttk.Label(self.adv,text=self.t("recovery")).grid(row=6,column=0,sticky="w"); self.recl=ttk.Label(self.adv,text=str(self.recovery) if self.recovery else "-",width=32); self.recl.grid(row=6,column=1,sticky="ew"); ttk.Button(self.adv,text=self.t("browse"),command=self.pickrec).grid(row=6,column=2,padx=3); ttk.Button(self.adv,text=self.t("auto_find"),command=self.refreshfind).grid(row=7,column=1,sticky="w")
        self.status=tk.Text(m,height=6,width=58,bg="#111827",fg="#e5e7eb",relief="flat",font=("Consolas",8),wrap="word"); self.status.grid(row=5,column=0,sticky="nsew",pady=(7,6)); m.rowconfigure(5,weight=1)
        b=ttk.Frame(m); b.grid(row=6,column=0,sticky="ew"); b.columnconfigure(1,weight=1); self.verify=tk.BooleanVar(True); self.confirm=tk.BooleanVar(False); ch=ttk.Frame(b); ch.grid(row=0,column=0,sticky="w"); ttk.Checkbutton(ch,text=self.t("verify"),variable=self.verify).pack(anchor="w"); ttk.Checkbutton(ch,text=self.t("confirm_erase"),variable=self.confirm).pack(anchor="w")
        ttk.Button(b,text=self.t("cleanup"),command=self.cleanup).grid(row=0,column=1,sticky="e",padx=2); ttk.Button(b,text=self.t("reports"),command=lambda:self.open(REPORTS)).grid(row=0,column=2,sticky="e",padx=2); ttk.Button(b,text=self.t("workspace"),command=lambda:self.open(BASE)).grid(row=0,column=3,sticky="e",padx=2); self.flashbtn=ttk.Button(b,text=self.t("flash"),style="Flash.TButton",command=self.flash); self.flashbtn.grid(row=0,column=4,sticky="e")
        self.populate(); self.log(self.t("ready"))
    def opt(self,r,l,var,vals): ttk.Label(self.adv,text=l).grid(row=r,column=0,sticky="w"); ttk.Combobox(self.adv,textvariable=var,values=vals,state="readonly",width=14).grid(row=r,column=1,sticky="w")
    def toggle(self): self.adv.grid(row=4,column=0,sticky="ew",pady=2) if self.advopen.get() else self.adv.grid_remove(); self.advbtn.config(text=("▲ " if self.advopen.get() else "▼ ")+self.t("advanced"))
    def updatebtn(self): self.flashbtn.config(text=self.t("save") if self.savefolder.get() else self.t("flash")); self.sub.config(text=self.t("ready_save") if self.savefolder.get() else self.t("ready"))
    def populate(self):
        vals=[]
        for d in self.usb: vals.append(f"Disk {d.get('Number')} | {d.get('FriendlyName')} | {human(d.get('Size',0))}" if d.get("platform")=="windows" else f"{d.get('Path')} | {d.get('Model')} | {human(d.get('Size',0))}")
        self.devbox["values"]=vals
        if vals: self.devvar.set(vals[0]); self.seldev()
        self.osbox["values"]=[f"{a} ({b}) - {c}" for a,b,c in MACOS]
    def seldev(self): i=self.devbox.current(); self.selected_usb=self.usb[i] if 0<=i<len(self.usb) else None
    def selos(self): i=self.osbox.current(); self.selected_macos=MACOS[i] if 0<=i<len(MACOS) else None
    def refreshfind(self): self.find(); self.efil.config(text=str(self.efi) if self.efi else "-"); self.recl.config(text=str(self.recovery) if self.recovery else "-")
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
        if not self.selected_macos: messagebox.showwarning(APP,self.t("no_macos")); return
        if not self.efi or not Path(self.efi).exists(): messagebox.showerror(APP,self.t("no_efi")); return
        if self.savefolder.get():
            p=filedialog.askdirectory(title=self.t("save_folder"))
            if p: threading.Thread(target=lambda:self.save_to(Path(p)),daemon=True).start()
            return
        if not self.selected_usb: messagebox.showwarning(APP,self.t("no_usb")); return
        if not admin():
            if elevate(): self.close()
            else: messagebox.showerror(APP,self.t("admin_fail"))
            return
        if not self.confirm.get(): messagebox.showwarning(APP,self.t("confirm_need")); return
        threading.Thread(target=self.flash_worker,daemon=True).start()
    def save_to(self,target):
        try: self.put(self.log,self.t("saving")); self.copy(target); self.patch(target); self.report(target) if self.verify.get() else None; self.put(self.log,self.t("done"))
        except Exception: self.err()
    def flash_worker(self):
        try: self.put(self.log,self.t("flashing")); target=self.format_usb(); self.copy(target); self.patch(target); self.report(target) if self.verify.get() else None; self.put(self.log,self.t("done"))
        except Exception: self.err()
    def copy(self,target):
        dst=target/"EFI"; shutil.rmtree(dst,ignore_errors=True); shutil.copytree(self.efi,dst)
        if self.recovery and Path(self.recovery).exists(): rec=target/"com.apple.recovery.boot"; shutil.rmtree(rec,ignore_errors=True); shutil.copytree(self.recovery,rec)
    def report(self,target):
        status,rows=validate(target); rp=REPORTS/("validation_"+time.strftime("%Y%m%d_%H%M%S")+".txt"); lines=[f"{APP} {VER}",f"Target: {target}",f"macOS: {self.selected_macos}",""]+[f"[{a}] {b}" for a,b in rows]; rp.write_text("\n".join(lines),encoding="utf-8"); self.put(self.log,"\n".join(lines[-len(rows):])); msg=self.t("ok") if status=="passed" else self.t("warn") if status=="warnings" else self.t("fail"); self.put(messagebox.showinfo if status!="failed" else messagebox.showerror,APP,msg+"\n\n"+str(rp))
    def format_usb(self):
        if win():
            num=self.selected_usb.get("Number"); ps=BASE/"flash_usb.ps1"; ps.write_text(f"""$ErrorActionPreference='Stop'\n$diskNumber={num}\n$d=Get-Disk -Number $diskNumber\nif($d.IsBoot -or $d.IsSystem){{throw 'Refusing boot/system disk'}}\nSet-Disk -Number $diskNumber -IsReadOnly $false -ErrorAction SilentlyContinue\nSet-Disk -Number $diskNumber -IsOffline $false -ErrorAction SilentlyContinue\nClear-Disk -Number $diskNumber -RemoveData -RemoveOEM -Confirm:$false\nInitialize-Disk -Number $diskNumber -PartitionStyle GPT\n$p=New-Partition -DiskNumber $diskNumber -Size 4GB -AssignDriveLetter\nFormat-Volume -Partition $p -FileSystem FAT32 -NewFileSystemLabel OPENCORE -Confirm:$false -Force\n(Get-Volume -Partition $p).DriveLetter\n""",encoding="utf-8"); r=subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-File",str(ps)],capture_output=True,text=True,timeout=180); (LOGS/"powershell_flash_stdout.log").write_text(r.stdout or "",encoding="utf-8"); (LOGS/"powershell_flash_stderr.log").write_text(r.stderr or "",encoding="utf-8"); self.put(self.log,(r.stdout or "")+"\n"+(r.stderr or ""));
            if r.returncode!=0: raise RuntimeError("PowerShell format failed: "+((r.stderr or r.stdout).strip()[-600:]))
            letters=[x.strip().replace(":","") for x in r.stdout.splitlines() if x.strip()]
            if not letters: raise RuntimeError("No drive letter returned after formatting")
            target=Path(f"{letters[-1]}:/")
            for _ in range(30):
                if target.exists(): return target
                time.sleep(.25)
            raise RuntimeError(f"Drive {letters[-1]}: not available")
        if linux():
            dev=self.selected_usb.get("Path"); m=BASE/"mnt_usb"; subprocess.run(["umount",str(m)],capture_output=True,text=True); shutil.rmtree(m,ignore_errors=True); m.mkdir(parents=True,exist_ok=True)
            for c in [["parted","-s",dev,"mklabel","gpt"],["parted","-s",dev,"mkpart","primary","fat32","1MiB","4097MiB"],["partprobe",dev]]:
                r=subprocess.run(c,capture_output=True,text=True)
                if r.returncode!=0: raise RuntimeError("command failed: "+" ".join(c)+" :: "+(r.stderr or r.stdout))
            part=dev+"1"; time.sleep(1); r=subprocess.run(["mkfs.vfat","-F","32","-n","OPENCORE",part],capture_output=True,text=True)
            if r.returncode!=0: raise RuntimeError("mkfs.vfat failed: "+(r.stderr or r.stdout))
            r=subprocess.run(["mount",part,str(m)],capture_output=True,text=True)
            if r.returncode!=0: raise RuntimeError("mount failed: "+(r.stderr or r.stdout))
            return m
        raise RuntimeError("Unsupported platform")
    def patch(self,target):
        cfg=target/"EFI"/"OC"/"config.plist"
        if not cfg.exists(): return
        try:
            shutil.copy2(cfg,cfg.with_suffix(".plist.before_forge")); pl=plistlib.load(cfg.open("rb")); pl.setdefault("Misc",{}).setdefault("Security",{})["SecureBootModel"]=self.secure.get()
            if self.scan.get()=="0": pl.setdefault("Misc",{}).setdefault("Security",{})["ScanPolicy"]=0
            pl.setdefault("Misc",{}).setdefault("Boot",{})["HideAuxiliary"]=(self.hide.get()=="True")
            if self.verbose.get():
                nv=pl.setdefault("NVRAM",{}).setdefault("Add",{}).setdefault("7C436110-AB2A-4BBB-A880-FE41995C9F82",{}); args=str(nv.get("boot-args",""))
                for x in ["-v","keepsyms=1","debug=0x100"]:
                    if x not in args.split(): args=(x+" "+args).strip()
                nv["boot-args"]=args
            plistlib.dump(pl,cfg.open("wb"))
        except Exception as e: self.put(self.log,"config patch skipped: "+str(e))
    def err(self):
        err=traceback.format_exc(); (LOGS/"operation_error.log").write_text(err,encoding="utf-8"); clean=err.splitlines()[-1]; self.put(self.log,self.t("failed")+" "+self.t("clean")+": "+clean); self.put(messagebox.showerror,APP,self.t("failed")+"\n\n"+clean)
    def open(self,p):
        if win(): os.startfile(str(p))
        elif linux(): subprocess.Popen(["xdg-open",str(p)])
        else: subprocess.Popen(["open",str(p)])
    def cleanup(self):
        if messagebox.askyesno(APP,self.t("cleanup1")):
            for p in [DOWNLOADS,EXTRACTED,TOOLS,OUTPUT]: shutil.rmtree(p,ignore_errors=True); p.mkdir(parents=True,exist_ok=True)
            self.log(self.t("cleanup_done"))
        if messagebox.askyesno(APP,self.t("cleanup2")):
            shutil.rmtree(BASE,ignore_errors=True); messagebox.showinfo(APP,self.t("cleanup_all"))
    def close(self): self.save_state(); self.destroy()

if __name__=="__main__":
    try: App().mainloop()
    except Exception:
        err=traceback.format_exc(); LOGS.mkdir(parents=True,exist_ok=True); (LOGS/"crash.log").write_text(err,encoding="utf-8")
        try:
            if win(): ctypes.windll.user32.MessageBoxW(None,err[-3500:],APP,0x10)
        except Exception: pass
        print(err)
