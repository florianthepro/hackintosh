#!/usr/bin/env bash
#
# macOS USB Setup (Linux) - erstellt einen bootfaehigen macOS-Installations-Stick.
# Gleicher Ablauf wie setup.exe: Hardware-Scan -> lauffaehige Versionen -> Auswahl
# -> USB waehlen -> schreiben. Eigene Implementierung; extern sind nur die Daten
# selbst (macOS-Recovery von Apple, OpenCore/Kext-Binaries von ihren Projekten).
#
set -euo pipefail
export LC_ALL=C

OC_VERSION="1.0.7"
LILU_VERSION="1.7.1"
VSMC_VERSION="1.3.7"
WEG_VERSION="1.7.0"

readonly OSRECOVERY="http://osrecovery.apple.com"
readonly UA="InternetRecovery/1.0"
readonly MLB_ZERO="00000000000000000"

# name : marketing : recoveryVersion : darwin : board-id : os-type : smbiosDesktop : smbiosLaptop
readonly RELEASES=(
  "Tahoe:26:latest:25:Mac-27AD2F918AE68F61:latest:MacPro7,1:MacBookPro16,1"
  "Sequoia:15:15.7.4:24:Mac-0CFF9C7C2B63DF8D:default:MacPro7,1:MacBookPro16,1"
  "Sonoma:14:14.8.4:23:Mac-827FAC58A8FDFA22:default:MacPro7,1:MacBookPro16,1"
  "Ventura:13:13.7.8:22:Mac-EE2EBD4B90B839A8:default:iMacPro1,1:MacBookPro16,1"
  "Monterey:12:12.7.6:21:Mac-9AE82516C7C6B903:default:iMacPro1,1:MacBookPro15,1"
  "Big-Sur:11:11.7.11:20:Mac-BE0E8AC46FE800CC:default:iMacPro1,1:MacBookPro15,1"
  "Catalina:10.15:10.15.8:19:Mac-66F35F19FE2A0D05:default:iMacPro1,1:MacBookPro14,1"
  "High-Sierra:10.13:10.13.6:17:Mac-942452F5819B1C1B:default:iMac14,2:MacBookPro11,1"
)

if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; RST=$'\033[0m'
else
  BOLD=""; DIM=""; RED=""; GRN=""; YEL=""; RST=""
fi

LOG="${TMPDIR:-/tmp}/macos-usb-setup-$(date +%Y%m%d-%H%M%S).log"
WORK=""; MNT=""

log()  { printf '%s\n' "$*" >>"$LOG"; }
step() { printf '%s==>%s %s\n' "$BOLD" "$RST" "$*"; log "STEP $*"; }
info() { printf '    %s\n' "$*"; log "INFO $*"; }
warn() { printf '%s[!]%s %s\n' "$YEL" "$RST" "$*"; log "WARN $*"; }

# die <stufe> <meldung> [empfehlung]
die() {
  printf '\n%s[Fehler: %s]%s %s\n' "$RED" "$1" "$RST" "$2" >&2
  [[ -n "${3:-}" ]] && printf '    Empfehlung: %s\n' "$3" >&2
  printf '    Protokoll: %s\n' "$LOG" >&2
  log "FEHLER [$1] $2"
  exit 1
}

cleanup() {
  [[ -n "$MNT" && -d "$MNT" ]] && { sync || true; umount "$MNT" 2>/dev/null || true; rmdir "$MNT" 2>/dev/null || true; }
  [[ -n "$WORK" && -d "$WORK" ]] && rm -rf "$WORK" 2>/dev/null || true
}
trap cleanup EXIT
trap 'die Unerwartet "Abbruch in Zeile $LINENO." "Protokoll pruefen."' ERR

require_root() {
  if [[ $EUID -ne 0 ]]; then
    info "Root-Rechte erforderlich (Partitionieren/Formatieren) - starte via sudo neu."
    exec sudo -E bash "$0" "$@"
  fi
}

require_tools() {
  local missing=()
  for c in curl lsblk lscpu lspci sgdisk mkfs.vfat wipefs partprobe unzip python3 findmnt; do
    command -v "$c" >/dev/null 2>&1 || missing+=("$c")
  done
  if (( ${#missing[@]} )); then
    die Voraussetzungen "Fehlende Programme: ${missing[*]}." \
      "Installieren, z. B.: Debian/Ubuntu 'apt install curl util-linux pciutils gdisk dosfstools python3', Fedora 'dnf install ...', Arch 'pacman -S ...'."
  fi
}

# ---------------------------------------------------------------- Hardware-Scan

CPU_VENDOR=""; CPU_FAMILY=0; CPU_MODEL=0; CPU_CORES=1; CPU_BRAND=""
GPU_VEN=(); GPU_DEV=(); HAS_INTEL_IGPU=0; HAS_MODERN_NVIDIA=0
FIRMWARE="unknown"; MEM_BYTES=0

scan_hardware() {
  step "Hardware wird analysiert"

  local vendor family model cps sockets
  vendor=$(lscpu | awk -F: '/^Vendor ID/{gsub(/^[ \t]+/,"",$2);print $2;exit}')
  family=$(lscpu | awk -F: '/^CPU family/{gsub(/[ \t]/,"",$2);print $2;exit}')
  model=$(lscpu  | awk -F: '/^Model:/{gsub(/[ \t]/,"",$2);print $2;exit}')
  cps=$(lscpu    | awk -F: '/^Core\(s\) per socket/{gsub(/[ \t]/,"",$2);print $2;exit}')
  sockets=$(lscpu| awk -F: '/^Socket\(s\)/{gsub(/[ \t]/,"",$2);print $2;exit}')
  CPU_BRAND=$(lscpu | awk -F: '/^Model name/{gsub(/^[ \t]+/,"",$2);print $2;exit}')

  case "$vendor" in
    GenuineIntel) CPU_VENDOR="intel" ;;
    AuthenticAMD) CPU_VENDOR="amd" ;;
    *)            CPU_VENDOR="unknown" ;;
  esac
  CPU_FAMILY=${family:-0}; CPU_MODEL=${model:-0}
  CPU_CORES=$(( ${cps:-1} * ${sockets:-1} )); (( CPU_CORES > 0 )) || CPU_CORES=$(nproc)
  [[ -n "$CPU_BRAND" ]] || CPU_BRAND="$vendor CPU"
  info "CPU: ${CPU_BRAND} (Family ${CPU_FAMILY}, Model ${CPU_MODEL}, ${CPU_CORES} Kerne)"

  local line ids ven dev
  while IFS= read -r line; do
    ids=$(grep -oE '[0-9a-fA-F]{4}:[0-9a-fA-F]{4}' <<<"$line" | tail -n1)
    [[ -n "$ids" ]] || continue
    ven=${ids%%:*}; dev=${ids##*:}
    ven=${ven,,}; dev=${dev,,}
    GPU_VEN+=("$ven"); GPU_DEV+=("$dev")
    info "GPU: [$ven:$dev] ${line#*: }"
    [[ "$ven" == "8086" ]] && HAS_INTEL_IGPU=1
    if [[ "$ven" == "10de" && $((16#$dev)) -ge $((16#1340)) ]]; then HAS_MODERN_NVIDIA=1; fi
  done < <(lspci -nn | grep -iE 'VGA compatible controller|3D controller|Display controller')

  [[ -d /sys/firmware/efi ]] && FIRMWARE="uefi" || FIRMWARE="legacy"
  info "Firmware: ${FIRMWARE}"

  local memkb; memkb=$(awk '/^MemTotal/{print $2;exit}' /proc/meminfo)
  MEM_BYTES=$(( ${memkb:-0} * 1024 ))
  info "RAM: $(( MEM_BYTES / 1073741824 )) GB"
}

# --------------------------------------------------------------- Kompatibilitaet

# level_from <darwin> <min> <sup> <exp> -> supported|experimental|unsupported
level_from() {
  local d=$1 min=$2 sup=$3 exp=$4
  if   (( d < min ));               then echo unsupported
  elif (( sup >= 0 && d <= sup ));  then echo supported
  elif (( exp >= 0 && d <= exp ));  then echo experimental
  else echo unsupported; fi
}
rank() { case "$1" in supported) echo 0;; experimental) echo 1;; *) echo 2;; esac; }
worst() { (( $(rank "$1") >= $(rank "$2") )) && echo "$1" || echo "$2"; }

C_SUP=0; C_EXP=0; C_NOTE=""; C_ALWAYS=0
cpu_window() {
  C_NOTE=""; C_ALWAYS=0
  if [[ "$CPU_VENDOR" == "amd" ]]; then
    if (( CPU_FAMILY >= 23 )); then
      C_SUP=-1; C_EXP=25; C_ALWAYS=1
      C_NOTE="AMD-Ryzen: benoetigt AMD-Vanilla-Kernel-Patches (im EFI enthalten)"
    else
      C_SUP=-1; C_EXP=-1; C_ALWAYS=1; C_NOTE="AMD ohne Ryzen wird nicht unterstuetzt"
    fi
    return
  fi
  if [[ "$CPU_VENDOR" != "intel" || "$CPU_FAMILY" -ne 6 ]]; then
    C_SUP=-1; C_EXP=25; C_ALWAYS=1; C_NOTE="CPU nicht klassifiziert"; return
  fi
  case "$CPU_MODEL" in
    42|58)            C_SUP=21; C_EXP=21; C_NOTE="Sandy/Ivy Bridge: maximal Monterey" ;;
    60|61|69|70|71)   C_SUP=24; C_EXP=25; C_NOTE="Haswell/Broadwell: Tahoe nur experimentell" ;;
    78|94|85|165|166) C_SUP=25; C_EXP=25; C_NOTE="" ;;
    142|158)          C_SUP=25; C_EXP=25; C_NOTE="" ;;
    140|141)          C_SUP=25; C_EXP=25; C_ALWAYS=1; C_NOTE="Ice/Tiger Lake: auf Desktop ggf. CPUFriend" ;;
    151|154|183)      C_SUP=-1; C_EXP=25; C_ALWAYS=1; C_NOTE="Hybrid-CPU: E-Cores ggf. deaktivieren" ;;
    *)                if (( CPU_MODEL <= 47 )); then C_SUP=18; C_EXP=18; C_NOTE="alte Intel-CPU (maximal Mojave)";
                      else C_SUP=-1; C_EXP=25; C_ALWAYS=1; C_NOTE="Intel-CPU nicht klassifiziert"; fi ;;
  esac
}

G_MIN=0; G_SUP=0; G_EXP=0; G_NOTE=""; G_ALWAYS=0
gpu_adapter_window() {
  local ven=$1 dec=$((16#$2))
  G_MIN=0; G_SUP=-1; G_EXP=25; G_NOTE=""; G_ALWAYS=0
  case "$ven" in
    10de)
      if (( dec >= 16#1340 )); then G_SUP=17; G_EXP=17; G_ALWAYS=1; G_NOTE="Nvidia: keine Treiber ab Mojave";
      else G_SUP=20; G_EXP=21; G_NOTE="Nvidia Kepler: maximal Big Sur"; fi ;;
    1002|1022)
      if   (( dec >= 16#7440 && dec <= 16#745F )); then G_SUP=-1; G_EXP=-1; G_ALWAYS=1; G_NOTE="AMD Navi3x (RX 7000): keine Treiber"
      elif (( dec >= 16#73A0 && dec <= 16#743F )); then G_MIN=21; G_SUP=25; G_EXP=25; G_NOTE="AMD Navi2x (RX 6000): ab Monterey"
      elif (( dec >= 16#7310 && dec <= 16#739F )); then G_MIN=19; G_SUP=25; G_EXP=25; G_NOTE="AMD Navi1x (RX 5000): ab Catalina"
      elif (( (dec>=16#67C0 && dec<=16#67FF) || (dec>=16#6980 && dec<=16#699F) || (dec>=16#6860 && dec<=16#687F) || (dec>=16#69A0 && dec<=16#69AF) || (dec>=16#66A0 && dec<=16#66BF) )); then G_SUP=25; G_EXP=25
      else G_SUP=21; G_EXP=21; G_NOTE="Alte AMD-GCN: maximal Monterey"; fi ;;
    8086)
      if   (( dec >= 16#0150 && dec <= 16#016F )); then G_SUP=20; G_EXP=20; G_NOTE="Intel HD 4000: maximal Big Sur"
      elif (( (dec>=16#0400 && dec<=16#0D3F) || (dec>=16#1600 && dec<=16#163F) )); then G_SUP=21; G_EXP=21; G_NOTE="Intel HD 5000/Iris: maximal Monterey"
      elif (( dec >= 16#1900 && dec <= 16#193F )); then G_SUP=21; G_EXP=22; G_NOTE="Intel Skylake-iGPU: ab Ventura eingeschraenkt"
      elif (( (dec>=16#5900 && dec<=16#593F) || (dec>=16#3E00 && dec<=16#3EFF) || (dec>=16#9B00 && dec<=16#9BFF) )); then G_SUP=23; G_EXP=25; G_NOTE="Intel UHD 600-Serie: ab Sequoia experimentell"
      elif (( (dec>=16#8A50 && dec<=16#8A5F) || (dec>=16#9A40 && dec<=16#9A7F) )); then G_SUP=-1; G_EXP=25; G_ALWAYS=1; G_NOTE="Intel Ice/Tiger Lake-iGPU: eingeschraenkt"
      else G_SUP=-1; G_EXP=25; G_ALWAYS=1; G_NOTE="Intel-iGPU nicht klassifiziert"; fi ;;
    *) G_SUP=-1; G_EXP=25; G_ALWAYS=1; G_NOTE="Grafik-Hersteller unbekannt" ;;
  esac
}

# evaluate_release <darwin> -> sets R_LEVEL and R_NOTES (newline separated)
R_LEVEL=""; R_NOTES=""
evaluate_release() {
  local d=$1; local notes="" cpu_level gpu_level level="unsupported"

  cpu_window
  cpu_level=$(level_from "$d" 0 "$C_SUP" "$C_EXP")
  if [[ -n "$C_NOTE" && ( "$C_ALWAYS" -eq 1 || "$cpu_level" != "supported" ) ]]; then notes+="$C_NOTE"$'\n'; fi

  if (( ${#GPU_VEN[@]} == 0 )); then
    gpu_level="unsupported"; notes+="Keine Grafikeinheit erkannt"$'\n'
  else
    gpu_level="unsupported"; local best_note="" i l
    for i in "${!GPU_VEN[@]}"; do
      gpu_adapter_window "${GPU_VEN[$i]}" "${GPU_DEV[$i]}"
      l=$(level_from "$d" "$G_MIN" "$G_SUP" "$G_EXP")
      if (( $(rank "$l") < $(rank "$gpu_level") )); then
        gpu_level="$l"
        if [[ -n "$G_NOTE" && ( "$G_ALWAYS" -eq 1 || "$l" != "supported" ) ]]; then best_note="$G_NOTE"; else best_note=""; fi
      fi
    done
    [[ -n "$best_note" ]] && notes+="$best_note"$'\n'
    if (( HAS_MODERN_NVIDIA == 1 && d >= 18 )); then
      notes+="Nvidia: keine Treiber ab Mojave"$'\n'
      [[ "$gpu_level" != "unsupported" && "$HAS_INTEL_IGPU" -eq 1 ]] && notes+="nur iGPU headless nutzbar"$'\n'
    fi
  fi

  level=$(worst "$cpu_level" "$gpu_level")

  if [[ "$FIRMWARE" == "legacy" ]]; then
    notes+="Legacy-BIOS erkannt: im UEFI-Modus booten (CSM deaktivieren)"$'\n'
    [[ "$level" == "supported" ]] && level="experimental"
  fi
  if (( MEM_BYTES > 0 && MEM_BYTES < 2147483648 )); then
    notes+="Weniger als 2 GB RAM: fuer die Installation nicht ausreichend"$'\n'; level="unsupported"
  elif (( MEM_BYTES > 0 && MEM_BYTES < 4294967296 )); then
    notes+="Weniger als 4 GB RAM: Installation kann langsam sein"$'\n'
  fi

  R_LEVEL="$level"; R_NOTES="${notes%$'\n'}"
}

# ----------------------------------------------------------------- Auswahl (TUI)

SEL_IDX=-1
choose_version() {
  step "Lauffaehige macOS-Versionen"
  local -a options=()
  local rec name marketing darwin badge
  for rec in "${RELEASES[@]}"; do
    IFS=: read -r name marketing _ darwin _ _ _ _ <<<"$rec"
    evaluate_release "$darwin"
    [[ "$R_LEVEL" == "unsupported" ]] && continue
    [[ "$R_LEVEL" == "supported" ]] && badge="${GRN}empfohlen${RST}" || badge="${YEL}experimentell${RST}"
    options+=("$rec")
    printf '  %s%2d%s  macOS %-12s %-6s [%s]\n' "$BOLD" "${#options[@]}" "$RST" "$name" "$marketing" "$badge"
    [[ -n "$R_NOTES" ]] && while IFS= read -r n; do printf '        %s- %s%s\n' "$DIM" "$n" "$RST"; done <<<"$R_NOTES"
  done
  (( ${#options[@]} )) || die Kompatibilitaet "Fuer diese Hardware wurde keine lauffaehige macOS-Version gefunden." \
    "Grafik/CPU pruefen; ggf. andere Hardware verwenden."

  local pick
  while :; do
    read -r -p "Version waehlen [1-${#options[@]}]: " pick </dev/tty
    [[ "$pick" =~ ^[0-9]+$ ]] && (( pick >= 1 && pick <= ${#options[@]} )) && break
    warn "Ungueltige Eingabe."
  done
  SELECTED_RELEASE="${options[$((pick-1))]}"
}

SEL_DEV=""; SEL_SIZE=""
choose_usb() {
  step "USB-Datentraeger waehlen"
  local root_disk; root_disk=$(lsblk -no pkname "$(findmnt -no SOURCE / 2>/dev/null)" 2>/dev/null | head -n1)

  local -a devs=() sizes=() models=()
  local name size model tran
  while IFS=$'\t' read -r name size model tran; do
    [[ "$tran" == "usb" ]] || continue
    [[ "$name" == "$root_disk" ]] && continue
    devs+=("/dev/$name"); sizes+=("$size"); models+=("${model:-USB-Datentraeger}")
  done < <(lsblk -dn -o NAME,SIZE,MODEL,TRAN --raw 2>/dev/null | tr -s ' ' '\t')

  if (( ${#devs[@]} == 0 )); then
    die USB "Kein USB-Datentraeger gefunden." "Stick einstecken und Setup erneut starten."
  fi

  printf '  %sAchtung: Der gewaehlte Datentraeger wird vollstaendig geloescht.%s\n' "$YEL" "$RST"
  local i
  for i in "${!devs[@]}"; do
    printf '  %s%2d%s  %-10s %-8s %s\n' "$BOLD" "$((i+1))" "$RST" "${devs[$i]}" "${sizes[$i]}" "${models[$i]}"
  done

  local pick
  while :; do
    read -r -p "USB waehlen [1-${#devs[@]}]: " pick </dev/tty
    [[ "$pick" =~ ^[0-9]+$ ]] && (( pick >= 1 && pick <= ${#devs[@]} )) && break
    warn "Ungueltige Eingabe."
  done
  SEL_DEV="${devs[$((pick-1))]}"; SEL_SIZE="${sizes[$((pick-1))]}"

  local confirm
  printf '\n  %sAlle Daten auf %s (%s) werden geloescht.%s\n' "$RED" "$SEL_DEV" "$SEL_SIZE" "$RST"
  read -r -p "  Zum Bestaetigen 'LOESCHEN' eingeben: " confirm </dev/tty
  [[ "$confirm" == "LOESCHEN" ]] || die Abbruch "Nicht bestaetigt." "Setup erneut starten."
}

# ------------------------------------------------------------------ USB schreiben

fetch() { curl -fL --retry 5 --retry-delay 2 -C - -A "$UA" -o "$2" "$1" || die Download "Download fehlgeschlagen: $1" "Internetverbindung pruefen."; }

prepare_usb() {
  step "USB wird vorbereitet: $SEL_DEV"
  local part
  [[ "$SEL_DEV" =~ [0-9]$ ]] && part="${SEL_DEV}p1" || part="${SEL_DEV}1"

  umount "${SEL_DEV}"* 2>/dev/null || true
  wipefs -a "$SEL_DEV"        >>"$LOG" 2>&1 || die USB "Datentraeger konnte nicht bereinigt werden." "USB neu einstecken, als root ausfuehren."
  sgdisk --zap-all "$SEL_DEV" >>"$LOG" 2>&1 || true
  sgdisk -o -n 1:0:0 -t 1:0700 -c 1:"MACOS-USB" "$SEL_DEV" >>"$LOG" 2>&1 \
    || die USB "GPT-Partition konnte nicht angelegt werden." "USB neu einstecken."
  partprobe "$SEL_DEV" >>"$LOG" 2>&1 || true
  command -v udevadm >/dev/null && udevadm settle || true
  sleep 1
  [[ -b "$part" ]] || die USB "Partition $part nicht gefunden." "USB neu verbinden."

  mkfs.vfat -F 32 -n MACOSUSB "$part" >>"$LOG" 2>&1 \
    || die USB "FAT32-Formatierung fehlgeschlagen." "USB neu einstecken."

  MNT=$(mktemp -d)
  mount "$part" "$MNT" || die USB "Volume konnte nicht eingehaengt werden." "USB neu verbinden."
  info "Volume bereit: $MNT"
}

assemble_efi() {
  step "EFI und OpenCore werden geschrieben"
  WORK=$(mktemp -d)
  local efi="$WORK/EFI"

  info "OpenCore ${OC_VERSION} wird geladen"
  fetch "https://github.com/acidanthera/OpenCorePkg/releases/download/${OC_VERSION}/OpenCore-${OC_VERSION}-RELEASE.zip" "$WORK/oc.zip"
  unzip -q "$WORK/oc.zip" -d "$WORK/oc"
  mkdir -p "$efi"
  cp -r "$WORK/oc/X64/EFI/BOOT" "$efi/BOOT"
  cp -r "$WORK/oc/X64/EFI/OC"   "$efi/OC"

  local drivers="$efi/OC/Drivers" kexts="$efi/OC/Kexts"
  find "$drivers" -maxdepth 1 -type f ! -name 'OpenRuntime.efi' -delete
  fetch "https://raw.githubusercontent.com/acidanthera/OcBinaryData/master/Drivers/HfsPlus.efi" "$drivers/HfsPlus.efi"
  rm -f "$efi/OC"/*.plist
  mkdir -p "$kexts"

  local k
  for k in "Lilu:${LILU_VERSION}" "VirtualSMC:${VSMC_VERSION}" "WhateverGreen:${WEG_VERSION}"; do
    local nm=${k%%:*} ver=${k##*:}
    info "${nm} ${ver} wird geladen"
    fetch "https://github.com/acidanthera/${nm}/releases/download/${ver}/${nm}-${ver}-RELEASE.zip" "$WORK/${nm}.zip"
    unzip -q "$WORK/${nm}.zip" -d "$WORK/${nm}"
    local src; src=$(find "$WORK/${nm}" -maxdepth 3 -type d -name "${nm}.kext" | head -n1)
    [[ -n "$src" ]] || die EFI "Kext ${nm}.kext nicht gefunden." "Erneut versuchen."
    cp -r "$src" "$kexts/${nm}.kext"
  done

  local amd="$WORK/amd-patches.plist"
  if [[ "$CPU_VENDOR" == "amd" ]]; then
    info "AMD-Vanilla-Kernel-Patches werden geladen"
    fetch "https://raw.githubusercontent.com/AMD-OSX/AMD_Vanilla/master/patches.plist" "$amd"
  else
    amd=""
  fi

  info "config.plist wird fuer die erkannte Hardware erzeugt"
  generate_config "$efi/OC/config.plist" "$amd"

  cp -r "$efi" "$MNT/EFI"
  info "EFI geschrieben"
}

generate_config() {
  local out=$1 amd=$2
  local rec smbios_desktop smbios_laptop smbios
  IFS=: read -r _ _ _ _ _ _ smbios_desktop smbios_laptop <<<"$SELECTED_RELEASE"
  local chassis="" ; [[ -r /sys/class/dmi/id/chassis_type ]] && chassis=$(cat /sys/class/dmi/id/chassis_type)
  if [[ "$CPU_VENDOR" == "amd" ]]; then smbios="$smbios_desktop"
  elif [[ "$chassis" =~ ^(8|9|10|11|14|30|31|32)$ ]]; then smbios="$smbios_laptop"
  else smbios="$smbios_desktop"; fi

  local is_amd=0; [[ "$CPU_VENDOR" == "amd" ]] && is_amd=1

  if ! python3 - "$out" "$smbios" "$is_amd" "$CPU_CORES" "${amd:-}" <<'PY'
import sys, secrets, plistlib

out, smbios, is_amd, cores, amd = sys.argv[1], sys.argv[2], sys.argv[3] == "1", int(sys.argv[4]), sys.argv[5]

def kext(bundle, exe):
    return {"Arch": "x86_64", "BundlePath": bundle, "Comment": "", "Enabled": True,
            "ExecutablePath": exe, "MaxKernel": "", "MinKernel": "", "PlistPath": "Contents/Info.plist"}

def driver(path):
    return {"Arguments": "", "Comment": "", "Enabled": True, "LoadEarly": False, "Path": path}

kernel = {
    "Add": [kext("Lilu.kext", "Contents/MacOS/Lilu"),
            kext("VirtualSMC.kext", "Contents/MacOS/VirtualSMC"),
            kext("WhateverGreen.kext", "Contents/MacOS/WhateverGreen")],
    "Block": [], "Force": [], "Patch": [],
    "Emulate": {"Cpuid1Data": b"", "Cpuid1Mask": b"", "DummyPowerManagement": False,
                "MaxKernel": "", "MinKernel": ""},
    "Quirks": {"AppleCpuPmCfgLock": False, "AppleXcpmCfgLock": False, "AppleXcpmExtraMsrs": False,
               "AppleXcpmForceBoost": False, "CustomPciSerialDevice": False, "CustomSMBIOSGuid": False,
               "DisableIoMapper": True, "DisableIoMapperMapping": False, "DisableLinkeditJettison": True,
               "DisableRtcChecksum": False, "ExtendBTFeatureFlags": False, "ExternalDiskIcons": False,
               "ForceAquantiaEthernet": False, "ForceSecureBootScheme": False, "IncreasePciBarSize": False,
               "LapicKernelPanic": False, "LegacyCommpage": False, "PanicNoKextDump": True,
               "PowerTimeoutKernelPanic": True, "ProvideCurrentCpuInfo": is_amd,
               "SetApfsTrimTimeout": -1, "ThirdPartyDrives": False, "XhciPortLimit": False},
    "Scheme": {"CustomKernel": False, "FuzzyMatch": True, "KernelArch": "Auto", "KernelCache": "Auto"},
}

if is_amd and amd:
    with open(amd, "rb") as f:
        patches = plistlib.load(f)
    ak = patches.get("Kernel", {})
    plist_patches = ak.get("Patch", [])
    for p in plist_patches:
        c = p.get("Comment", "")
        r = p.get("Replace")
        if "cpuid_cores_per_package" in c and isinstance(r, (bytes, bytearray)) and len(r) >= 2:
            r = bytearray(r); r[1] = cores & 0xFF; p["Replace"] = bytes(r)
    kernel["Patch"] = plist_patches
    if isinstance(ak.get("Emulate"), dict):
        kernel["Emulate"] = ak["Emulate"]

config = {
    "ACPI": {"Add": [], "Delete": [], "Patch": [],
             "Quirks": {"FadtEnableReset": False, "NormalizeHeaders": False, "RebaseRegions": False,
                        "ResetHwSig": False, "ResetLogoStatus": True, "SyncTableIds": False}},
    "Booter": {"MmioWhitelist": [], "Patch": [],
               "Quirks": {"AllowRelocationBlock": False, "AvoidRuntimeDefrag": True, "DevirtualiseMmio": False,
                          "DisableSingleUser": False, "DisableVariableWrite": False, "DiscardHibernateMap": False,
                          "EnableSafeModeSlide": True, "EnableWriteUnprotector": False, "ForceBooterSignature": False,
                          "ForceExitBootServices": False, "ProtectMemoryRegions": False, "ProtectSecureBoot": False,
                          "ProtectUefiServices": False, "ProvideCustomSlide": True, "ProvideMaxSlide": 0,
                          "RebuildAppleMemoryMap": True, "ResizeAppleGpuBars": -1, "SetupVirtualMap": True,
                          "SignalAppleOS": False, "SyncRuntimePermissions": True}},
    "DeviceProperties": {"Add": {}, "Delete": {}},
    "Kernel": kernel,
    "Misc": {"BlessOverride": [],
             "Boot": {"ConsoleAttributes": 0, "HibernateMode": "None", "HibernateSkipsPicker": False,
                      "HideAuxiliary": False, "InstanceIdentifier": "", "LauncherOption": "Disabled",
                      "LauncherPath": "Default", "PickerAttributes": 17, "PickerAudioAssist": False,
                      "PickerMode": "Builtin", "PickerVariant": "Auto", "PollAppleHotKeys": True,
                      "ShowPicker": True, "TakeoffDelay": 0, "Timeout": 10},
             "Debug": {"AppleDebug": True, "ApplePanic": True, "DisableWatchDog": True, "DisplayDelay": 0,
                       "DisplayLevel": 2147483650, "LogModules": "*", "SysReport": False, "Target": 3},
             "Entries": [],
             "Security": {"AllowSetDefault": True, "ApECID": 0, "AuthRestart": False, "BlacklistAppleUpdate": True,
                          "DmgLoading": "Signed", "EnablePassword": False, "ExposeSensitiveData": 6,
                          "HaltLevel": 2147483648, "PasswordHash": b"", "PasswordSalt": b"",
                          "ScanPolicy": 0, "SecureBootModel": "Disabled", "Vault": "Optional"},
             "Tools": []},
    "NVRAM": {"Add": {"7C436110-AB2A-4BBB-A880-FE41995C9F82":
                          {"boot-args": "-v keepsyms=1 debug=0x100",
                           "csr-active-config": b"\x00\x00\x00\x00",
                           "prev-lang:kbd": b"en-US:0", "run-efi-updater": "No"},
                      "4D1EDE05-38C7-4A6A-9CC6-4BCCA8B38C14":
                          {"DefaultBackgroundColor": b"\x00\x00\x00\x00", "UIScale": b"\x01"}},
              "Delete": {"7C436110-AB2A-4BBB-A880-FE41995C9F82": ["boot-args", "csr-active-config"],
                         "4D1EDE05-38C7-4A6A-9CC6-4BCCA8B38C14": ["DefaultBackgroundColor", "UIScale"]},
              "LegacyEnable": False, "LegacySchema": {}, "WriteFlash": True},
    "PlatformInfo": {"Automatic": True, "CustomMemory": False,
                     "Generic": {"AdviseFeatures": False, "MLB": secrets.token_hex(8).upper()[:17].ljust(17, "0"),
                                 "MaxBIOSVersion": False, "ProcessorType": 0, "ROM": secrets.token_bytes(6),
                                 "SpoofVendor": True, "SystemMemoryStatus": "Auto", "SystemProductName": smbios,
                                 "SystemSerialNumber": secrets.token_hex(6).upper(),
                                 "SystemUUID": str(__import__("uuid").uuid4()).upper()},
                     "UpdateDataHub": True, "UpdateNVRAM": True, "UpdateSMBIOS": True,
                     "UpdateSMBIOSMode": "Create", "UseRawUuidEncoding": False},
    "UEFI": {"APFS": {"EnableJumpstart": True, "GlobalConnect": False, "HideVerbose": False,
                      "JumpstartHotPlug": False, "MinDate": -1, "MinVersion": -1},
             "AppleInput": {"AppleEvent": "Builtin", "CustomDelays": False, "GraphicsInputMirroring": True,
                            "KeyInitialDelay": 50, "KeySubsequentDelay": 5, "PointerPollMask": -1,
                            "PointerPollMax": 0, "PointerPollMin": 0, "PointerSpeedDiv": 1, "PointerSpeedMul": 1},
             "Audio": {"AudioSupport": False},
             "ConnectDrivers": True,
             "Drivers": [driver("OpenRuntime.efi"), driver("HfsPlus.efi")],
             "Input": {"KeyFiltering": False, "KeyForgetThreshold": 5, "KeySupport": True,
                       "KeySupportMode": "Auto", "PointerSupport": False, "PointerSupportMode": "ASUS",
                       "TimerResolution": 50000},
             "Output": {"ClearScreenOnModeSwitch": False, "ConsoleMode": "", "DirectGopRendering": False,
                        "ForceResolution": False, "GopPassThrough": "Disabled", "IgnoreTextInGraphics": False,
                        "InitialMode": "Auto", "ProvideConsoleGop": True, "ReconnectGraphicsOnConnect": False,
                        "ReconnectOnResChange": False, "ReplaceTabWithSpace": False, "Resolution": "Max",
                        "SanitiseClearScreen": False, "TextRenderer": "BuiltinGraphics", "UIScale": 0,
                        "UgaPassThrough": False},
             "ProtocolOverrides": {k: False for k in
                 ["AppleAudio", "AppleBootPolicy", "AppleDebugLog", "AppleEg2Info", "AppleFramebufferInfo",
                  "AppleImageConversion", "AppleImg4Verification", "AppleKeyMap", "AppleRtcRam", "AppleSecureBoot",
                  "AppleSmcIo", "AppleUserInterfaceTheme", "DataHub", "DeviceProperties", "FirmwareVolume",
                  "HashServices", "OSInfo", "UnicodeCollation"]},
             "Quirks": {"ActivateHpetSupport": False, "DisableSecurityPolicy": False, "EnableVectorAcceleration": True,
                        "EnableVmx": False, "ExitBootServicesDelay": 0, "ForceOcWriteFlash": False,
                        "ForgeUefiSupport": False, "IgnoreInvalidFlexRatio": False, "ReleaseUsbOwnership": True,
                        "ReloadOptionRoms": False, "RequestBootVarRouting": True, "ResizeGpuBars": -1,
                        "ResizeUsePciRbIo": False, "ShimRetainProtocol": False, "TscSyncTimeout": 0,
                        "UnblockFsConnect": False},
             "ReservedMemory": []},
}

with open(out, "wb") as f:
    plistlib.dump(config, f)
PY
  then :; else
    die EFI "config.plist konnte nicht erzeugt werden." "python3 pruefen."
  fi
}

# --------------------------------------------------------------- Recovery-Download

rand_hex() { openssl rand -hex "$1" | tr 'a-f' 'A-F'; }

download_recovery() {
  local board ostype name
  IFS=: read -r name _ _ _ board ostype _ _ <<<"$SELECTED_RELEASE"
  step "macOS ${name} wird von Apple geladen"

  local hdr; hdr=$(mktemp)
  curl -s -D "$hdr" -o /dev/null -H "Host: osrecovery.apple.com" -H "Connection: close" -A "$UA" "$OSRECOVERY/" \
    || die Recovery "Verbindung zum Apple-Wiederherstellungsdienst fehlgeschlagen." "Internetverbindung pruefen."
  local session; session=$(grep -oiE 'session=[^;[:space:]]+' "$hdr" | head -n1); rm -f "$hdr"
  [[ -n "$session" ]] || die Recovery "Kein Sitzungscookie erhalten." "Internetverbindung pruefen und erneut versuchen."

  local body resp
  body=$(printf 'cid=%s\nsn=%s\nbid=%s\nk=%s\nfg=%s\nos=%s' \
    "$(rand_hex 8)" "$MLB_ZERO" "$board" "$(rand_hex 32)" "$(rand_hex 32)" "$ostype")
  resp=$(curl -s -X POST --data-binary "$body" \
    -H "Host: osrecovery.apple.com" -H "Connection: close" -A "$UA" \
    -H "Cookie: $session" -H "Content-Type: text/plain" \
    "$OSRECOVERY/InstallationPayload/RecoveryImage") \
    || die Recovery "Recovery-Anfrage fehlgeschlagen." "Internetverbindung pruefen."

  local AU AT CU CT
  AU=$(awk -F': ' '/^AU: /{print $2}' <<<"$resp")
  AT=$(awk -F': ' '/^AT: /{print $2}' <<<"$resp")
  CU=$(awk -F': ' '/^CU: /{print $2}' <<<"$resp")
  CT=$(awk -F': ' '/^CT: /{print $2}' <<<"$resp")
  [[ -n "$AU" && -n "$AT" && -n "$CU" && -n "$CT" ]] \
    || die Recovery "Antwort des Apple-Dienstes unvollstaendig." "macOS-Auswahl und Verbindung pruefen."

  local dir="$MNT/com.apple.recovery.boot"; mkdir -p "$dir"
  info "BaseSystem.dmg wird geladen (mehrere GB)"
  curl -L --retry 5 --retry-delay 2 -C - -A "$UA" -H "Cookie: AssetToken=$AT" -o "$dir/BaseSystem.dmg" "$AU" \
    || die Recovery "Download von BaseSystem.dmg fehlgeschlagen." "Internetverbindung pruefen, Setup erneut ausfuehren."
  info "BaseSystem.chunklist wird geladen"
  curl -L --retry 5 --retry-delay 2 -A "$UA" -H "Cookie: AssetToken=$CT" -o "$dir/BaseSystem.chunklist" "$CU" \
    || die Recovery "Download der Chunklist fehlgeschlagen." "Internetverbindung pruefen."

  step "Recovery-Abbildung wird geprueft"
  if ! python3 - "$dir/BaseSystem.dmg" "$dir/BaseSystem.chunklist" <<'PY'
import sys, struct, hashlib
img, ck = sys.argv[1], sys.argv[2]
d = open(ck, "rb").read()
if len(d) < 36: sys.exit("chunklist zu kurz")
magic, hsize, fv, cm, sm, cnt, coff, soff = struct.unpack_from("<4sIBBBxQQQ", d, 0)
if magic != b"CNKL": sys.exit("ungueltige chunklist")
with open(img, "rb") as f:
    off = coff
    for i in range(cnt):
        size, h = struct.unpack_from("<I32s", d, off); off += 36
        sha = hashlib.sha256(); rem = size
        while rem:
            b = f.read(min(rem, 1 << 20))
            if not b: sys.exit("image zu kurz")
            sha.update(b); rem -= len(b)
        if sha.digest() != h: sys.exit("chunk %d ungueltig" % i)
PY
  then :; else
    die Pruefung "Pruefsumme der Recovery-Abbildung stimmt nicht." "Download beschaedigt - Setup erneut ausfuehren."
  fi
  info "Recovery verifiziert"
}

# ------------------------------------------------------------------------ Abschluss

finish() {
  local name; IFS=: read -r name _ <<<"$SELECTED_RELEASE"
  sync
  step "Fertig - der USB-Stick ist bootfaehig."
  cat <<EOF

  ${GRN}macOS ${name} wurde auf ${SEL_DEV} geschrieben.${RST}

  1.  Rechner neu starten.
  2.  Boot-Menue oeffnen (je nach Board F12, F11, F8 oder Esc).
  3.  Den USB-Datentraeger im UEFI-Modus auswaehlen.
  4.  Im OpenCore-Menue "macOS Base System" starten.
  5.  Festplattendienstprogramm oeffnen und das Ziellaufwerk als APFS loeschen.
  6.  "macOS installieren" waehlen und dem Assistenten folgen.
  7.  macOS wird dabei von Apple geladen - Internetverbindung erforderlich.

  Protokoll: ${LOG}
EOF
}

main() {
  require_root "$@"
  require_tools
  scan_hardware
  choose_version
  choose_usb
  prepare_usb
  assemble_efi
  download_recovery
  finish
}

main "$@"
