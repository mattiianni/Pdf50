@echo off
title Split PDF 50
cd /d "%~dp0"

echo.
echo  Split PDF 50 - Avvio server...
echo  ─────────────────────────────────────────
echo.

:: Controlla se Python e' installato
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERRORE] Python non trovato.
    echo  Scaricalo da: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:: Installa/aggiorna le dipendenze se necessario
if not exist ".deps_installed" (
    echo  Installazione dipendenze Python...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo  [ERRORE] Installazione dipendenze fallita.
        echo  Prova: pip install -r requirements.txt
        pause
        exit /b 1
    )
    echo installed > .deps_installed
    echo  Dipendenze installate con successo.
    echo.
)

:: Genera l'icona e il collegamento Desktop (solo al primo avvio)
if not exist "icon.ico" (
    echo  Generazione icona...
    python genera_icona.py
)

:: Avvia il server (il browser si apre automaticamente)
python app.py

pause
