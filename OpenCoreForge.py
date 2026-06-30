
import os, sys, json, time, queue, shutil, zipfile, ctypes, traceback, threading, subprocess, urllib.request, tempfile
from pathlib import Path

APP_TITLE = "OpenCore Forge"
APP_VERSION = "1.0.0"
MIN_PY = (3, 10)


def safe_base_dir():
    candidates = []
    for env in ("LOCALAPPDATA", "APPDATA", "USERPROFILE", "TEMP", "TMP"):
        v = os.environ.get(env)
        if v:
            candidates.append(Path(v) / "OpenCoreOneClickWorkspace")
    candidates.append(Path.home() / "OpenCoreOneClickWorkspace")
    candidates.append(Path(tempfile.gettempdir()) / "OpenCoreOneClickWorkspace")
    for c in candidates:
        try:
            c.mkdir(parents=True, exist_ok=True)
            test = c / ".write_test"
            test.write_text("ok", encoding="utf-8")
            test.unlink(missing_ok=True)
            return c
        except Exception:
            pass
    raise PermissionError("Kein beschreibbarer Workspace gefunden: " + ", ".join(map(str, candidates)))

BASE = safe_base_dir()
DOWNLOADS = BASE / "downloads"
EXTRACTED = BASE / "extracted"
TOOLS = BASE / "tools"
LOGS = BASE / "logs"
VENV = BASE / "pyenv"
CRASH_LOG = LOGS / "crash.log"
STATE = BASE / "state.json"

SOURCES = {
    "OpCore-Simplify": "https://github.com/lzhoang2801/OpCore-Simplify/archive/refs/heads/main.zip",
    "OpCore-Simplify.py": "https://raw.githubusercontent.com/lzhoang2801/OpCore-Simplify/refs/heads/main/OpCore-Simplify.py",
    "OpenCorePkg": "https://github.com/acidanthera/OpenCorePkg/releases/download/1.0.7/OpenCore-1.0.7-RELEASE.zip",
    "gibMacOS": "https://github.com/corpnewt/gibMacOS/archive/refs/heads/master.zip",
    "USBToolBox": "https://github.com/USBToolBox/tool/releases/latest/download/Windows.zip",
    "USBToolBox.kext": "https://github.com/USBToolBox/kext/releases/latest/download/USBToolBox.kext.zip"
}

MACOS_ITEMS = [
    ("High Sierra", "10.13", "Legacy", "Relevant for older systems / legacy NVIDIA setups"),
    ("Mojave", "10.14", "Legacy", "Older stable baseline"),
    ("Catalina", "10.15", "Stabil", "Good older Intel baseline"),
    ("Big Sur", "11", "Stabil", "USB mapping is important"),
    ("Monterey", "12", "Empfohlen", "Often stable for Intel systems"),
    ("Ventura", "13", "Modern", "Good with many AMD RX GPUs"),
    ("Sonoma", "14", "Modern", "May require additional tuning/patches"),
    ("Sequoia", "15", "Aktuell", "Check compatibility carefully"),
    ("Tahoe", "26", "Experimentell", "Only if tools/hardware are compatible")
]

for p in [DOWNLOADS, EXTRACTED, TOOLS, LOGS]:
    p.mkdir(parents=True, exist_ok=True)

def elog(text):
    try:
        with CRASH_LOG.open("a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + str(text) + "\n")
    except Exception:
        pass

def fatal(text):
    elog(text)
    try:
        if os.name == "nt":
            ctypes.windll.user32.MessageBoxW(None, str(text), APP_TITLE, 0x10)
    except Exception:
        pass
    print(text)
    try: input("Press Enter...")
    except Exception: pass

def is_windows(): return os.name == "nt"

def is_admin():
    if is_windows():
        try: return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception: return False
    try: return os.geteuid() == 0
    except Exception: return False

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog, simpledialog
except Exception as e:
    fatal("Tkinter fehlt. Installiere Python von python.org neu und aktiviere 'tcl/tk and IDLE'. Error: " + repr(e))
    raise SystemExit(1)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} {APP_VERSION}")
        self.geometry("1280x820")
        self.minsize(1100, 720)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.uiq = queue.Queue(); self.proc = None; self.hardware = {}; self.selected_disk = None
        self.usb_letter = "O"; self.efi_path = None; self.recovery_path = None; self.selected_macos = None
        self.load_state(); self.setup_style(); self.build_ui(); self.after(80, self.drain)
        self.log("Application started.")
        self.log(f"Workspace: {BASE}")
        self.log(f"Python: {sys.version.split()[0]} | Admin={is_admin()} | Windows={is_windows()}")
        self.banner_msg('Ready. Start with "Prepare All".', "ok")
        if is_windows() and not is_admin(): self.banner_msg("Warning: Not running as administrator. USB formatting requires administrator rights.", "warn")

    def report_callback_exception(self, exc, val, tb):
        text = "".join(traceback.format_exception(exc, val, tb)); elog(text); self.log("FEHLER: " + str(val))
        try: messagebox.showerror("Error", "Error abgefangen, Fenster bleibt offen.\n\n" + text[-3000:])
        except Exception: pass

    def setup_style(self):
        self.configure(bg="#0f172a"); style = ttk.Style(self)
        try: style.theme_use("clam")
        except Exception: pass
        style.configure("Side.TFrame", background="#111827")
        style.configure("Content.TFrame", background="#f8fafc")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("SideTitle.TLabel", background="#111827", foreground="#e5e7eb", font=("Segoe UI", 16, "bold"))
        style.configure("Title.TLabel", background="#f8fafc", foreground="#0f172a", font=("Segoe UI", 20, "bold"))
        style.configure("Sub.TLabel", background="#f8fafc", foreground="#475569", font=("Segoe UI", 10))
        style.configure("Nav.TButton", background="#1f2937", foreground="#f9fafb", borderwidth=0, padding=(14,10), font=("Segoe UI",10,"bold"))
        style.map("Nav.TButton", background=[("active", "#374151")])
        style.configure("Accent.TButton", background="#2563eb", foreground="#ffffff", padding=(14,9), font=("Segoe UI",10,"bold"))
        style.configure("Danger.TButton", background="#dc2626", foreground="#ffffff", padding=(14,9), font=("Segoe UI",10,"bold"))
        style.configure("TButton", padding=(12,8), font=("Segoe UI",10))
        style.configure("TLabel", background="#f8fafc", foreground="#111827", font=("Segoe UI",10))
        style.configure("Treeview", rowheight=28, font=("Segoe UI",10))

    def build_ui(self):
        self.grid_columnconfigure(1, weight=1); self.grid_rowconfigure(0, weight=1)
        side = ttk.Frame(self, style="Side.TFrame", padding=18); side.grid(row=0,column=0,sticky="ns")
        ttk.Label(side, text="OC OneClick", style="SideTitle.TLabel").pack(anchor="w", pady=(0,18))
        self.frames = {}
        for key,label in [("home","Start"),("hardware","Hardware"),("macos","macOS"),("tools","Tools"),("usb","USB"),("write","Write"),("help","Boot Help"),("logs","Logs")]:
            ttk.Button(side, text=label, style="Nav.TButton", command=lambda k=key:self.show(k)).pack(fill="x", pady=4)
        ttk.Button(side, text="Open Workspace", style="Nav.TButton", command=self.open_workspace).pack(fill="x", pady=(24,4))
        content=ttk.Frame(self,style="Content.TFrame"); content.grid(row=0,column=1,sticky="nsew"); content.grid_columnconfigure(0,weight=1); content.grid_rowconfigure(2,weight=1)
        head=ttk.Frame(content,style="Content.TFrame",padding=(24,18,24,8)); head.grid(row=0,column=0,sticky="ew")
        self.title_lbl=ttk.Label(head,text="Start",style="Title.TLabel"); self.title_lbl.pack(anchor="w")
        self.sub_lbl=ttk.Label(head,text="",style="Sub.TLabel"); self.sub_lbl.pack(anchor="w",pady=(4,0))
        self.banner=tk.Label(content,text="",bg="#e0f2fe",fg="#075985",anchor="w",padx=18,pady=10,font=("Segoe UI",10,"bold")); self.banner.grid(row=1,column=0,sticky="ew",padx=24,pady=(0,8))
        self.pages=ttk.Frame(content,style="Content.TFrame"); self.pages.grid(row=2,column=0,sticky="nsew",padx=24,pady=(0,12)); self.pages.grid_rowconfigure(0,weight=1); self.pages.grid_columnconfigure(0,weight=1)
        self.make_pages(); self.show("home")

    def page(self,key):
        f=ttk.Frame(self.pages,style="Content.TFrame"); f.grid(row=0,column=0,sticky="nsew"); self.frames[key]=f; return f
    def card(self,parent,pad=16): return ttk.Frame(parent,style="Card.TFrame",padding=pad)
    def show(self,key):
        titles={"home":("Start","Guided workflow."),"hardware":("Hardware","Detect hardware."),"macos":("macOS","Choose a version."),"tools":("Tools","GitHub tools and terminal."),"usb":("USB","Prepare USB safely."),"write":("Write","Copy EFI/Recovery."),"help":("Boot Help","Troubleshooting."),"logs":("Logs","Error und Meldungen.")}
        self.frames[key].tkraise(); self.title_lbl.config(text=titles[key][0]); self.sub_lbl.config(text=titles[key][1])

    def make_pages(self):
        self.make_home(); self.make_hardware(); self.make_macos(); self.make_tools(); self.make_usb(); self.make_write(); self.make_help(); self.make_logs()
    def make_home(self):
        f=self.page("home"); f.grid_columnconfigure(0,weight=1); f.grid_rowconfigure(2,weight=1)
        c=self.card(f); c.grid(row=0,column=0,sticky="ew")
        ttk.Label(c,text="Guided Workflow",font=("Segoe UI",14,"bold"),background="#ffffff").pack(anchor="w")
        ttk.Label(c,text="Prepare first, then scan hardware, choose macOS, prepare the USB drive, and write the files.",background="#ffffff",foreground="#334155").pack(anchor="w",pady=8)
        row=ttk.Frame(c,style="Card.TFrame"); row.pack(fill="x")
        ttk.Button(row,text="1. Prepare All",style="Accent.TButton",command=self.autoprepare).pack(side="left",padx=4)
        ttk.Button(row,text="2. Scan Hardware",command=lambda:[self.show("hardware"),self.scan_hardware()]).pack(side="left",padx=4)
        ttk.Button(row,text="3. Choose macOS",command=lambda:self.show("macos")).pack(side="left",padx=4)
        ttk.Button(row,text="4. Select USB",command=lambda:[self.show("usb"),self.refresh_disks()]).pack(side="left",padx=4)
        ttk.Button(row,text="5. Write",command=lambda:self.show("write")).pack(side="left",padx=4)
        self.progress=ttk.Progressbar(f,mode="indeterminate"); self.progress.grid(row=1,column=0,sticky="ew",pady=14)
        self.home_box=tk.Text(f,bg="#ffffff",fg="#111827",relief="flat",font=("Consolas",10),wrap="word"); self.home_box.grid(row=2,column=0,sticky="nsew")
    def make_hardware(self):
        f=self.page("hardware"); top=self.card(f); top.pack(fill="x"); ttk.Button(top,text="Scan Hardware",style="Accent.TButton",command=self.scan_hardware).pack(side="left"); ttk.Button(top,text="Save JSON",command=self.save_hardware).pack(side="left",padx=8)
        self.hw_box=tk.Text(f,bg="#ffffff",relief="flat",font=("Consolas",10),wrap="word"); self.hw_box.pack(fill="both",expand=True,pady=12)
    def make_macos(self):
        f=self.page("macos"); self.macos_grid=ttk.Frame(f,style="Content.TFrame"); self.macos_grid.pack(fill="both",expand=True); self.render_macos()
    def make_tools(self):
        f=self.page("tools"); top=self.card(f); top.pack(fill="x")
        ttk.Button(top,text="Download Tools",style="Accent.TButton",command=self.download_extract_all).pack(side="left",padx=4)
        ttk.Button(top,text="Dependencies",command=self.install_requirements).pack(side="left",padx=4)
        ttk.Button(top,text="OpCore-Simplify",command=self.run_opcore).pack(side="left",padx=4)
        ttk.Button(top,text="gibMacOS",command=self.run_gibmacos).pack(side="left",padx=4)
        ttk.Button(top,text="USBToolBox",command=self.run_usbtoolbox).pack(side="left",padx=4)
        ttk.Button(top,text="Stop",style="Danger.TButton",command=self.stop_proc).pack(side="right")
        self.console=tk.Text(f,bg="#020617",fg="#e2e8f0",insertbackground="#fff",relief="flat",font=("Consolas",10),wrap="word"); self.console.pack(fill="both",expand=True,pady=12)
        inp=self.card(f,8); inp.pack(fill="x"); self.stdin_var=tk.StringVar(); ent=ttk.Entry(inp,textvariable=self.stdin_var); ent.pack(side="left",fill="x",expand=True,padx=(0,8)); ent.bind("<Return>",lambda e:self.send_stdin()); ttk.Button(inp,text="Send",command=self.send_stdin).pack(side="left")
    def make_usb(self):
        f=self.page("usb"); top=self.card(f); top.pack(fill="x")
        ttk.Button(top,text="Refresh",style="Accent.TButton",command=self.refresh_disks).pack(side="left",padx=4)
        ttk.Button(top,text="Erase USB + GPT/FAT32",style="Danger.TButton",command=self.prepare_usb).pack(side="left",padx=4)
        ttk.Label(top,text="Letter:",background="#fff").pack(side="left",padx=(18,4)); self.letter_var=tk.StringVar(value=self.usb_letter); ttk.Entry(top,width=5,textvariable=self.letter_var).pack(side="left")
        self.disk_tree=ttk.Treeview(f,columns=("num","name","size","bus","part","model"),show="headings")
        for col,title,width in [("num","Disk",70),("name","Name",220),("size","Size",110),("bus","Bus",80),("part","Partition",100),("model","Model",520)]: self.disk_tree.heading(col,text=title); self.disk_tree.column(col,width=width)
        self.disk_tree.pack(fill="both",expand=True,pady=12); self.disk_tree.bind("<<TreeviewSelect>>",self.on_disk_select); self.usb_info=ttk.Label(f,text="No USB drive selected."); self.usb_info.pack(anchor="w")
    def make_write(self):
        f=self.page("write"); c=self.card(f); c.pack(fill="x")
        ttk.Button(c,text="Choose EFI",command=self.pick_efi).grid(row=0,column=0,padx=4,pady=4,sticky="w"); self.efi_lbl=ttk.Label(c,text="no EFI selected",background="#fff"); self.efi_lbl.grid(row=0,column=1,sticky="w")
        ttk.Button(c,text="Choose Recovery",command=self.pick_recovery).grid(row=1,column=0,padx=4,pady=4,sticky="w"); self.rec_lbl=ttk.Label(c,text="no Recovery selected",background="#fff"); self.rec_lbl.grid(row=1,column=1,sticky="w")
        row=ttk.Frame(c,style="Card.TFrame"); row.grid(row=2,column=0,columnspan=2,sticky="w",pady=8)
        ttk.Button(row,text="Auto-detect",command=self.auto_find).pack(side="left",padx=4); ttk.Button(row,text="Copy to USB",style="Accent.TButton",command=self.copy_to_usb).pack(side="left",padx=4); ttk.Button(row,text="Sanity Check",command=self.sanity_dialog).pack(side="left",padx=4); ttk.Button(row,text="Set Verbose Boot",command=self.set_verbose).pack(side="left",padx=4)
        self.write_box=tk.Text(f,bg="#ffffff",relief="flat",font=("Consolas",10),wrap="word"); self.write_box.pack(fill="both",expand=True,pady=12)
    def make_help(self):
        f=self.page("help"); c=self.card(f); c.pack(fill="x"); txt="""If the Apple logo/progress bar gets stuck:\n1. Run Reset NVRAM in the OpenCore menu.\n2. Verbose boot args: -v keepsyms=1 debug=0x100.\n3. Use ScanPolicy=0, HideAuxiliary=False, SecureBootModel=Disabled for installer testing.\n4. Check OpenRuntime.efi + HfsPlus.efi/OpenHfsPlus.efi.\n5. After changes, run OC Snapshot/ocvalidate.\n6. BIOS: disable Secure Boot/Fast Boot/CSM, enable AHCI."""; ttk.Label(c,text=txt,background="#fff",justify="left",wraplength=1000).pack(anchor="w")
    def make_logs(self):
        f=self.page("logs"); top=self.card(f); top.pack(fill="x"); ttk.Button(top,text="Save Log",command=self.save_log).pack(side="left",padx=4); ttk.Button(top,text="Open Crash Log",command=self.open_crash).pack(side="left",padx=4); ttk.Button(top,text="Clear",command=lambda:self.log_box.delete("1.0","end")).pack(side="left",padx=4)
        self.log_box=tk.Text(f,bg="#ffffff",relief="flat",font=("Consolas",10),wrap="word"); self.log_box.pack(fill="both",expand=True,pady=12)

    def banner_msg(self,text,mode="info"):
        colors={"info":("#e0f2fe","#075985"),"ok":("#dcfce7","#166534"),"warn":("#fef3c7","#92400e"),"err":("#fee2e2","#991b1b")}; bg,fg=colors.get(mode,colors["info"]); self.banner.config(text=text,bg=bg,fg=fg)
    def q(self,fn,*args): self.uiq.put((fn,args))
    def drain(self):
        try:
            while True:
                fn,args=self.uiq.get_nowait(); fn(*args)
        except queue.Empty: pass
        self.after(80,self.drain)
    def log(self,msg):
        line=time.strftime("[%H:%M:%S] ")+str(msg)+"\n"; elog(str(msg)); print(line,end="")
        for n in ("log_box","home_box"):
            b=getattr(self,n,None)
            if b:
                try: b.insert("end",line); b.see("end")
                except Exception: pass
    def wlog(self,msg): self.log(msg); self.write_box.insert("end",str(msg)+"\n"); self.write_box.see("end")
    def task(self,name,fn):
        def run():
            self.q(self.progress.start,8); self.q(self.banner_msg,name+" running...","info")
            try: fn(); self.q(self.banner_msg,name+" completed.","ok")
            except Exception:
                text=traceback.format_exc(); elog(text); self.q(self.log,text); self.q(self.banner_msg,name+" failed. See logs.","err")
            finally: self.q(self.progress.stop)
        threading.Thread(target=run,daemon=True).start()

    def load_state(self):
        try:
            if STATE.exists(): self.usb_letter=json.loads(STATE.read_text(encoding="utf-8")).get("usb_letter","O")
        except Exception: pass
    def save_state(self):
        try: STATE.write_text(json.dumps({"usb_letter":self.usb_letter},indent=2),encoding="utf-8")
        except Exception: pass
    def pyexe(self):
        p=VENV/("Scripts/python.exe" if is_windows() else "bin/python"); return str(p) if p.exists() else sys.executable
    def autoprepare(self): self.task("Vorbereitung",lambda:[self.ensure_env(),self.download_extract(),self.install_requirements(sync=True)])
    def ensure_env(self):
        self.q(self.log,"Checking pip/venv..."); subprocess.run([sys.executable,"-m","ensurepip","--upgrade"],capture_output=True,text=True,timeout=180); subprocess.run([sys.executable,"-m","pip","install","--upgrade","pip","setuptools","wheel"],capture_output=True,text=True,timeout=300)
        if not VENV.exists(): subprocess.run([sys.executable,"-m","venv",str(VENV)],capture_output=True,text=True,timeout=300)
    def download_extract_all(self): self.task("Download Tools",self.download_extract)
    def download_extract(self):
        for name,url in SOURCES.items():
            ext=".py" if url.endswith(".py") else ".zip"; target=DOWNLOADS/(clean(name)+ext)
            if target.exists() and target.stat().st_size>0: self.q(self.log,"Already exists: "+target.name); continue
            self.q(self.log,"Downloading "+name+"...")
            with urllib.request.urlopen(url,timeout=90) as r, target.open("wb") as f: shutil.copyfileobj(r,f)
        for z in DOWNLOADS.glob("*.zip"):
            dest=EXTRACTED/z.stem
            if dest.exists() and any(dest.iterdir()): continue
            dest.mkdir(parents=True,exist_ok=True)
            try:
                with zipfile.ZipFile(z,"r") as zipf: zipf.extractall(dest)
                self.q(self.log,"Extracted: "+z.name)
            except Exception as e: self.q(self.log,"Extraction failed "+z.name+": "+str(e))
        raw=DOWNLOADS/"OpCore-Simplify_py.py"
        if raw.exists(): shutil.copy2(raw,TOOLS/"OpCore-Simplify.py")
    def install_requirements(self,sync=False):
        def work():
            py=self.pyexe(); self.q(self.log,"Using Python: "+py); subprocess.run([py,"-m","ensurepip","--upgrade"],capture_output=True,text=True,timeout=180); subprocess.run([py,"-m","pip","install","--upgrade","pip","setuptools","wheel"],capture_output=True,text=True,timeout=300)
            reqs=list(EXTRACTED.rglob("requirements.txt")); self.q(self.log,"requirements found: "+str(len(reqs)))
            for req in reqs:
                r=subprocess.run([py,"-m","pip","install","-r",str(req)],capture_output=True,text=True,timeout=900)
                if r.stdout: self.q(self.log,r.stdout[-1500:])
                if r.stderr: self.q(self.log,r.stderr[-1500:])
        if sync: work()
        else: self.task("Dependencies",work)
    def scan_hardware(self):
        def work(): data=get_hw(); self.hardware=data; self.q(self.hw_box.delete,"1.0","end"); self.q(self.hw_box.insert,"end",json.dumps(data,indent=2,ensure_ascii=False)); self.q(self.render_macos); self.q(self.log,"Hardware-Scan completed.")
        self.task("Hardware-Scan",work)
    def save_hardware(self): p=LOGS/"hardware.json"; p.write_text(json.dumps(self.hardware,indent=2,ensure_ascii=False),encoding="utf-8"); messagebox.showinfo("Saved",str(p))
    def render_macos(self):
        for w in self.macos_grid.winfo_children(): w.destroy()
        cpu=" ".join(self.hardware.get("cpu",[])) if self.hardware else ""; gpu=" ".join(self.hardware.get("gpu",[])) if self.hardware else ""
        for i,item in enumerate(MACOS_ITEMS):
            name,ver,tag,desc=item; score,reason=score_macos(name,cpu,gpu); c=ttk.Frame(self.macos_grid,style="Card.TFrame",padding=16); c.grid(row=i//3,column=i%3,sticky="nsew",padx=8,pady=8); self.macos_grid.columnconfigure(i%3,weight=1)
            ttk.Label(c,text="macOS "+name,font=("Segoe UI",14,"bold"),background="#fff").pack(anchor="w"); ttk.Label(c,text=f"Version {ver} · {tag}",background="#fff",foreground="#475569").pack(anchor="w",pady=(2,8)); ttk.Label(c,text="Bewertung: "+score,background="#fff",font=("Segoe UI",10,"bold")).pack(anchor="w"); ttk.Label(c,text=desc+"\n"+reason,background="#fff",foreground="#334155",wraplength=310).pack(anchor="w",pady=8); ttk.Button(c,text="Auswählen",style="Accent.TButton",command=lambda it=item:self.choose_macos(it)).pack(anchor="w")
    def choose_macos(self,item): self.selected_macos=item; self.log(f"Selected: macOS {item[0]} {item[1]}"); self.show("tools")
    def start_proc(self,cmd,cwd=None):
        if self.proc and self.proc.poll() is None: messagebox.showwarning("Running","Please press Stop first."); return
        self.console.insert("end","\n> "+" ".join(map(str,cmd))+"\n"); self.console.see("end")
        self.proc=subprocess.Popen(cmd,cwd=cwd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,errors="replace"); threading.Thread(target=self.read_proc,daemon=True).start()
    def read_proc(self):
        try:
            for line in self.proc.stdout: self.q(self.console.insert,"end",line); self.q(self.console.see,"end")
        except Exception as e: self.q(self.console.insert,"end",f"\n[FEHLER] {e}\n")
        self.q(self.console.insert,"end","\n[Prozess beendet]\n")
    def send_stdin(self):
        txt=self.stdin_var.get(); self.stdin_var.set("")
        if self.proc and self.proc.poll() is None: self.proc.stdin.write(txt+"\n"); self.proc.stdin.flush(); self.console.insert("end",f"\n[INPUT] {txt}\n")
    def stop_proc(self):
        if self.proc and self.proc.poll() is None: self.proc.terminate(); self.banner_msg("Prozess gestoppt.","warn")
    def run_opcore(self):
        scripts=list(EXTRACTED.rglob("OpCore-Simplify.py"))+list(TOOLS.glob("OpCore-Simplify.py"))
        if not scripts: messagebox.showwarning("Missing","Bitte zuerst Download Tools."); return
        self.start_proc([self.pyexe(),str(scripts[0])],cwd=str(scripts[0].parent))
    def run_gibmacos(self):
        bats=list(EXTRACTED.rglob("gibMacOS.bat")); pys=list(EXTRACTED.rglob("gibMacOS.py"))
        if is_windows() and bats: self.start_proc(["cmd","/c",str(bats[0])],cwd=str(bats[0].parent))
        elif pys: self.start_proc([self.pyexe(),str(pys[0])],cwd=str(pys[0].parent))
        else: messagebox.showwarning("Missing","gibMacOS not found.")
    def run_usbtoolbox(self):
        exes=list(EXTRACTED.rglob("Windows.exe"))
        if is_windows() and exes: self.start_proc([str(exes[0])],cwd=str(exes[0].parent))
        else: messagebox.showwarning("Missing","USBToolBox not found.")
    def refresh_disks(self):
        def work():
            disks=list_usb();
            def fill():
                for r in self.disk_tree.get_children(): self.disk_tree.delete(r)
                for d in disks: self.disk_tree.insert("","end",values=(d.get("Number",""),d.get("FriendlyName",""),gb(d.get("Size",0)),d.get("BusType",""),d.get("PartitionStyle",""),d.get("Model","")))
            self.q(fill); self.q(self.log,f"{len(disks)} USB/SD/MMC drive(s) found.")
        self.task("USB-Liste",work)
    def on_disk_select(self,e=None):
        sel=self.disk_tree.selection();
        if sel: vals=self.disk_tree.item(sel[0],"values"); self.selected_disk=str(vals[0]); self.usb_info.config(text=f"Selected: Disk {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]}")
    def prepare_usb(self):
        if not is_windows(): messagebox.showerror("Windows only","USB formatting is only available on Windows."); return
        if not is_admin(): messagebox.showerror("Administrator rights","Please run as administrator."); return
        if not self.selected_disk: messagebox.showwarning("No USB","Select a USB drive first."); return
        letter=self.letter_var.get().strip().upper().replace(":","") or "O"
        if len(letter)!=1 or not letter.isalpha(): messagebox.showerror("Drive letter","Nur einen Drive lettern, z.B. O."); return
        if simpledialog.askstring("Confirmation",f"Disk {self.selected_disk} will be erased. Type ERASE:")!="ERASE": self.log("Cancelled."); return
        self.usb_letter=letter; self.save_state()
        def work():
            script=f"select disk {self.selected_disk}\ndetail disk\nclean\nconvert gpt\ncreate partition primary\nformat fs=fat32 quick label=OPENCORE\nassign letter={letter}\nexit\n"; sp=BASE/"diskpart_prepare.txt"; sp.write_text(script,encoding="utf-8"); r=subprocess.run(["diskpart","/s",str(sp)],capture_output=True,text=True,errors="replace"); self.q(self.wlog,r.stdout); self.q(self.wlog,f"USB prepared: {letter}:\\")
        self.task("USB vorbereiten",work)
    def pick_efi(self):
        p=filedialog.askdirectory(title="Choose EFI")
        if p: self.efi_path=Path(p); self.efi_lbl.config(text=str(self.efi_path))
    def pick_recovery(self):
        p=filedialog.askdirectory(title="com.apple.recovery.boot wählen")
        if p: self.recovery_path=Path(p); self.rec_lbl.config(text=str(self.recovery_path))
    def auto_find(self):
        def work():
            efis=[]; recs=[]
            for root in [BASE,Path.home(),Path.cwd()]:
                try:
                    for p in root.rglob("EFI"):
                        if (p/"OC"/"config.plist").exists(): efis.append(p)
                    for p in root.rglob("com.apple.recovery.boot"):
                        if (p/"BaseSystem.dmg").exists() or (p/"BaseSystem.chunklist").exists(): recs.append(p)
                except Exception: pass
            def apply():
                if efis: self.efi_path=sorted(efis,key=lambda x:len(str(x)))[0]; self.efi_lbl.config(text=str(self.efi_path)); self.wlog("EFI found: "+str(self.efi_path))
                else: self.wlog("No EFI found.")
                if recs: self.recovery_path=sorted(recs,key=lambda x:len(str(x)))[0]; self.rec_lbl.config(text=str(self.recovery_path)); self.wlog("Recovery found: "+str(self.recovery_path))
                else: self.wlog("No Recovery found.")
            self.q(apply)
        self.task("Suchen",work)
    def copy_to_usb(self):
        letter=self.letter_var.get().strip().upper().replace(":","") or self.usb_letter; target=Path(f"{letter}:/")
        if not target.exists(): messagebox.showerror("Not found",f"{target} does not exist."); return
        if not self.efi_path or not self.efi_path.exists(): messagebox.showwarning("EFI missing","Choose EFI."); return
        def work():
            dst=target/"EFI"; 
            if dst.exists(): shutil.rmtree(dst)
            shutil.copytree(self.efi_path,dst); self.q(self.wlog,"EFI copied.")
            if self.recovery_path and self.recovery_path.exists():
                rdst=target/"com.apple.recovery.boot"; 
                if rdst.exists(): shutil.rmtree(rdst)
                shutil.copytree(self.recovery_path,rdst); self.q(self.wlog,"Recovery copied.")
            self.q(self.sanity,target)
        self.task("Kopieren",work)
    def sanity_dialog(self): self.sanity(Path(f"{(self.letter_var.get().strip().upper().replace(':','') or self.usb_letter)}:/"))
    def sanity(self,target):
        self.wlog("Sanity Check:"); checks=[(target/"EFI"/"BOOT"/"BOOTx64.efi","BOOTx64.efi"),(target/"EFI"/"OC"/"config.plist","config.plist"),(target/"EFI"/"OC"/"Drivers"/"OpenRuntime.efi","OpenRuntime.efi"),(target/"com.apple.recovery.boot","com.apple.recovery.boot")]; drivers=target/"EFI"/"OC"/"Drivers"; hfs=drivers.exists() and any(x.name.lower() in ["hfsplus.efi","openhfsplus.efi"] for x in drivers.iterdir())
        for p,n in checks: self.wlog(("OK    " if p.exists() else "MISSING ")+n)
        self.wlog(("OK    " if hfs else "MISSING ")+"HfsPlus.efi/OpenHfsPlus.efi")
    def set_verbose(self):
        if not self.efi_path: self.pick_efi()
        if not self.efi_path: return
        cfg=self.efi_path/"OC"/"config.plist"
        if not cfg.exists(): messagebox.showwarning("Missing",str(cfg)); return
        shutil.copy2(cfg,cfg.with_suffix(".plist.verbosebak")); s=cfg.read_text(encoding="utf-8",errors="ignore")
        if "-v keepsyms=1 debug=0x100" in s: self.wlog("Verbose boot args already exist."); return
        import re
        if "<key>boot-args</key>" in s: cfg.write_text(re.sub(r"(<key>boot-args</key>\s*<string>)(.*?)(</string>)", lambda m:m.group(1)+"-v keepsyms=1 debug=0x100 "+m.group(2)+m.group(3), s, count=1, flags=re.S),encoding="utf-8"); self.wlog("Verbose boot args set.")
        else: self.wlog("boot-args not found.")
    def save_log(self):
        p=LOGS/(time.strftime("log_%Y%m%d_%H%M%S")+".txt"); p.write_text(self.log_box.get("1.0","end"),encoding="utf-8"); messagebox.showinfo("Saved",str(p))
    def open_workspace(self):
        if is_windows(): os.startfile(str(BASE))
        else: subprocess.Popen(["xdg-open",str(BASE)])
    def open_crash(self):
        CRASH_LOG.touch(exist_ok=True)
        if is_windows(): os.startfile(str(CRASH_LOG))
        else: subprocess.Popen(["xdg-open",str(CRASH_LOG)])
    def close(self):
        self.save_state()
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("Close","A tool is still running. Close anyway?"): return
            try: self.proc.terminate()
            except Exception: pass
        self.destroy()

def clean(s): return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)
def ps_json(cmd):
    if not is_windows(): return []
    try:
        r=subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command",cmd+" | ConvertTo-Json -Depth 6"],capture_output=True,text=True,timeout=60)
        if not r.stdout.strip(): return []
        d=json.loads(r.stdout); return d if isinstance(d,list) else [d]
    except Exception as e: elog("PS Error: "+repr(e)); return []
def get_hw():
    if not is_windows(): return {"system":[sys.platform],"note":"Hardware scan is optimized for Windows."}
    return {"cpu":[x.get("Name","") for x in ps_json("Get-CimInstance Win32_Processor | Select Name,Manufacturer,NumberOfCores,NumberOfLogicalProcessors")],"gpu":[x.get("Name","") for x in ps_json("Get-CimInstance Win32_VideoController | Select Name,AdapterRAM,PNPDeviceID")],"mainboard":ps_json("Get-CimInstance Win32_BaseBoard | Select Manufacturer,Product,Version"),"bios":ps_json("Get-CimInstance Win32_BIOS | Select Manufacturer,SMBIOSBIOSVersion,ReleaseDate"),"disks":ps_json("Get-Disk | Select Number,FriendlyName,Model,Size,BusType,PartitionStyle,IsBoot,IsSystem"),"network":ps_json("Get-CimInstance Win32_NetworkAdapter | ? {$_.PhysicalAdapter -eq $true} | Select Name,Manufacturer,PNPDeviceID"),"audio":ps_json("Get-CimInstance Win32_SoundDevice | Select Name,Manufacturer,PNPDeviceID")}
def list_usb():
    out=[]
    for d in ps_json("Get-Disk | Select Number,FriendlyName,Model,Size,BusType,PartitionStyle,IsBoot,IsSystem"):
        if str(d.get("IsBoot",False)).lower()=="true" or str(d.get("IsSystem",False)).lower()=="true": continue
        if str(d.get("BusType","")).lower() in ["usb","sd","mmc"]: out.append(d)
    return out
def gb(v):
    try: return f"{int(v)/1024**3:.1f} GB"
    except Exception: return str(v)
def score_macos(name,cpu,gpu):
    t=(cpu+" "+gpu).lower()
    if not t.strip(): return "Unknown","Erst Scan Hardware."
    if ("rtx" in t or "gtx 10" in t or "gtx 16" in t or "nvidia" in t) and name in ["Ventura","Sonoma","Sequoia","Tahoe"]: return "Problematic","Many newer NVIDIA GPUs are unsuitable."
    if "ryzen" in t or "threadripper" in t: return "Possible","AMD requires kernel patches."
    if any(x in t for x in ["rx 560","rx 570","rx 580","rx 590","rx 5500","rx 5600","rx 5700","rx 6600","rx 6800","rx 6900","radeon pro","navi"]): return "Good","AMD RX/Radeon detected."
    if "intel" in t: return "Possible/Good","Intel detected; check iGPU/SMBIOS."
    return "Unknown","No clear rule matched."

if __name__ == "__main__":
    try: App().mainloop()
    except Exception:
        text=traceback.format_exc(); elog(text); fatal("Unexpected startup error:\n\n"+text+"\nLog: "+str(CRASH_LOG))
