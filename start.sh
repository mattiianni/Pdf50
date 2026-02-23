#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo " Split PDF 50 - Avvio server..."
echo " ─────────────────────────────────────────"
echo ""

# Usa il virtualenv se presente, altrimenti cerca python3
if [ -f "$SCRIPT_DIR/.venv/bin/python3" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python3"
    PIP="$SCRIPT_DIR/.venv/bin/pip"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
    PIP="pip3"
else
    echo " [ERRORE] Python 3 non trovato."
    echo " Installalo con: brew install python3  (macOS)"
    exit 1
fi

# Installa dipendenze se necessario (solo senza venv)
if [ ! -f "$SCRIPT_DIR/.venv/bin/python3" ] && [ ! -f ".deps_installed" ]; then
    echo " Installazione dipendenze Python..."
    "$PIP" install -r requirements.txt
    touch .deps_installed
    echo " Dipendenze installate."
    echo ""
fi

# Genera l'icona (solo al primo avvio)
if [ ! -f "icon.png" ]; then
    echo " Generazione icona..."
    "$PYTHON" genera_icona.py
    chmod +x "Split PDF 50.app/Contents/MacOS/splitpdf50" 2>/dev/null || true
fi

# Avvia il server
"$PYTHON" app.py
