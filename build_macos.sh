#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Split PDF 50 — build dell'app standalone macOS (Apple Silicon / arm64)
#
#   ./build_macos.sh               build + installa sul Desktop
#   ./build_macos.sh --applications  build + installa in /Applications
#   ./build_macos.sh --no-install  solo build (risultato in dist/)
#   ./build_macos.sh --skip-brew   non controlla/installa i tool Homebrew
#
# Cosa fa:
#   1. verifica di essere su macOS arm64 con un Python 3.10+ nativo arm64
#   2. controlla (e installa via Homebrew, se manca) tesseract + lingua ITA,
#      ghostscript e pango (per WeasyPrint)
#   3. crea/aggiorna il virtualenv .venv-build e installa requirements + PyInstaller
#   4. genera l'icona .icns (1024 px) con Pillow + sips + iconutil
#   5. esegue PyInstaller con SplitPDF50.spec → dist/Split PDF 50.app
#   6. firma ad-hoc, rimuove la quarantena e copia l'app sul Desktop
#      (sostituendo la versione precedente, dopo aver fermato il server attivo)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="Split PDF 50"
APP_BUNDLE="dist/${APP_NAME}.app"
VENV="$SCRIPT_DIR/.venv-build"

INSTALL_DIR="$HOME/Desktop"
DO_INSTALL=1
DO_BREW=1
for arg in "$@"; do
  case "$arg" in
    --applications) INSTALL_DIR="/Applications" ;;
    --no-install)   DO_INSTALL=0 ;;
    --skip-brew)    DO_BREW=0 ;;
    -h|--help)      sed -n 2,20p "$0"; exit 0 ;;
    *) echo "Opzione sconosciuta: $arg"; exit 2 ;;
  esac
done

step() { printf '\n\033[1;32m▶ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m  ✗ %s\033[0m\n' "$*"; exit 1; }

# ── 1. Piattaforma ───────────────────────────────────────────────────────────
step "Verifica piattaforma"
[[ "$(uname -s)" == "Darwin" ]] || die "Questo script va eseguito su macOS."
if [[ "$(uname -m)" != "arm64" ]]; then
  # Terminale aperto sotto Rosetta: rilancia nativo
  if [[ "$(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)" == "1" ]]; then
    warn "Terminale in Rosetta (x86_64): rilancio lo script in modalità arm64"
    exec arch -arm64 /bin/bash "$0" "$@"
  fi
  die "Serve un Mac Apple Silicon (arm64)."
fi

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:$PATH"

PYTHON=""
for cand in /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 \
            /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3 \
            /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
            "$(command -v python3 || true)"; do
  [[ -n "$cand" && -x "$cand" ]] || continue
  if "$cand" -c 'import sys,platform; sys.exit(0 if sys.version_info>=(3,10) and platform.machine()=="arm64" else 1)' 2>/dev/null; then
    PYTHON="$cand"; break
  fi
done
[[ -n "$PYTHON" ]] || die "Python 3.10+ arm64 non trovato. Installa con: brew install python@3.13"
echo "  Python: $PYTHON ($("$PYTHON" -V 2>&1), $("$PYTHON" -c 'import platform;print(platform.machine())'))"

# ── 2. Dipendenze di sistema (Homebrew) ──────────────────────────────────────
if [[ $DO_BREW -eq 1 ]]; then
  step "Verifica strumenti di sistema (Homebrew)"
  if command -v brew >/dev/null 2>&1; then
    missing=()
    command -v tesseract >/dev/null 2>&1 || missing+=(tesseract)
    if ! tesseract --list-langs 2>/dev/null | grep -qx ita; then missing+=(tesseract-lang); fi
    command -v gs >/dev/null 2>&1 || missing+=(ghostscript)
    [[ -e /opt/homebrew/lib/libpango-1.0.dylib ]] || missing+=(pango)
    if [[ ${#missing[@]} -gt 0 ]]; then
      echo "  Installo: ${missing[*]}"
      brew install "${missing[@]}"
    else
      echo "  tesseract (+ita), ghostscript, pango: OK"
    fi
    if [[ ! -d "/Applications/LibreOffice.app" && ! -d "/Applications/Microsoft Word.app" ]]; then
      warn "Né LibreOffice né Microsoft Word trovati: i file Office useranno solo i convertitori interni."
      warn "Consigliato: brew install --cask libreoffice"
    fi
  else
    warn "Homebrew non trovato (https://brew.sh): installa a mano tesseract, tesseract-lang, ghostscript, pango."
  fi
fi

# ── 3. Virtualenv di build ───────────────────────────────────────────────────
step "Preparazione virtualenv di build (.venv-build)"
if [[ -x "$VENV/bin/python" ]] && ! "$VENV/bin/python" -c 'import platform,sys; sys.exit(platform.machine()!="arm64")'; then
  warn "venv esistente non arm64: lo ricreo"; rm -rf "$VENV"
fi
[[ -x "$VENV/bin/python" ]] || "$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip wheel >/dev/null
"$VENV/bin/python" -m pip install -r requirements.txt "pyinstaller>=6.10"

# ── 4. Icona ─────────────────────────────────────────────────────────────────
step "Generazione icona"
mkdir -p build
ICONSET="build/AppIcon.iconset"
rm -rf "$ICONSET"; mkdir -p "$ICONSET"
"$VENV/bin/python" -c 'import genera_icona as g; g.create_hires_png("build/icon_1024.png", 1024)'
for spec in "16 16x16" "32 16x16@2x" "32 32x32" "64 32x32@2x" "128 128x128" \
            "256 128x128@2x" "256 256x256" "512 256x256@2x" "512 512x512" "1024 512x512@2x"; do
  read -r px name <<<"$spec"
  sips -z "$px" "$px" build/icon_1024.png --out "$ICONSET/icon_${name}.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o build/AppIcon.icns
echo "  build/AppIcon.icns"

# ── 5. PyInstaller ───────────────────────────────────────────────────────────
step "Build PyInstaller (arm64)"
VERSION="$(git describe --tags --always 2>/dev/null | sed 's/^v//' || true)"
[[ "$VERSION" =~ ^[0-9]+(\.[0-9]+)*$ ]] || VERSION="1.1.$(git rev-list --count HEAD 2>/dev/null || echo 0)"
export SPLITPDF50_VERSION="$VERSION"
export SPLITPDF50_ARCH="arm64"
rm -rf "dist/${APP_NAME}.app" dist/splitpdf50
"$VENV/bin/pyinstaller" --noconfirm --clean SplitPDF50.spec

[[ -d "$APP_BUNDLE" ]] || die "Build fallita: $APP_BUNDLE non creato."
echo "  Architettura: $(lipo -archs "$APP_BUNDLE/Contents/MacOS/splitpdf50")"

# ── 6. Firma ad-hoc + installazione ──────────────────────────────────────────
step "Firma ad-hoc"
codesign --force --deep --sign - "$APP_BUNDLE"
xattr -cr "$APP_BUNDLE" || true
codesign --verify --deep --strict "$APP_BUNDLE" && echo "  firma OK"

if [[ $DO_INSTALL -eq 1 ]]; then
  step "Installazione in $INSTALL_DIR"
  # Ferma un eventuale server in esecuzione (vecchia app o start.sh)
  curl -sf -X POST -H 'Content-Type: application/json' -d '{"force":true}' \
       http://127.0.0.1:5055/api/shutdown >/dev/null 2>&1 || true
  pkill -f "${APP_NAME}.app/Contents/MacOS/splitpdf50" 2>/dev/null || true
  sleep 1
  DEST="$INSTALL_DIR/${APP_NAME}.app"
  rm -rf "$DEST"
  ditto "$APP_BUNDLE" "$DEST"
  # Aggiorna l'icona in Finder / Launch Services
  /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$DEST" >/dev/null 2>&1 || true
  touch "$DEST"
  echo "  Installata: $DEST"
  echo
  echo "  Doppio click su \"${APP_NAME}\" per avviarla."
  echo "  Log: ~/Library/Logs/SplitPDF50.log"
else
  echo "  App pronta: $SCRIPT_DIR/$APP_BUNDLE"
fi
