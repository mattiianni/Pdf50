#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo " Split PDF 50 - Avvio server..."
echo " ─────────────────────────────────────────"
echo ""

# Controlla Python 3
if ! command -v python3 &>/dev/null; then
    echo " [ERRORE] Python 3 non trovato."
    echo " Installalo con: brew install python3  (macOS)"
    echo "            oppure: sudo apt install python3  (Linux)"
    exit 1
fi

# Installa dipendenze se necessario
if [ ! -f ".deps_installed" ]; then
    echo " Installazione dipendenze Python..."
    pip3 install -r requirements.txt
    touch .deps_installed
    echo " Dipendenze installate."
    echo ""
fi

# Genera l'icona (solo al primo avvio)
if [ ! -f "icon.png" ]; then
    echo " Generazione icona..."
    python3 genera_icona.py
    # Rendi eseguibile lo script del .app bundle
    chmod +x "Split PDF 50.app/Contents/MacOS/splitpdf50" 2>/dev/null || true
fi

# Avvia il server
python3 app.py
