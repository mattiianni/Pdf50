# -*- mode: python ; coding: utf-8 -*-
# ─────────────────────────────────────────────────────────────────────────────
# Split PDF 50 — spec PyInstaller per l'app standalone macOS (Apple Silicon)
#
# Non usarlo direttamente: lancia ./build_macos.sh, che prepara il venv,
# l'icona e poi esegue:  pyinstaller --noconfirm --clean SplitPDF50.spec
#
# Risultato: dist/Split PDF 50.app  (binario arm64, Python e dipendenze
# incluse; restano esterni solo Tesseract, Ghostscript, pango e LibreOffice,
# che sono programmi di sistema installati via Homebrew).
# ─────────────────────────────────────────────────────────────────────────────

import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

APP_NAME = 'Split PDF 50'
BUNDLE_ID = 'com.mattiaianniello.splitpdf50'
VERSION = os.environ.get('SPLITPDF50_VERSION', '1.1.0')
TARGET_ARCH = os.environ.get('SPLITPDF50_ARCH', 'arm64')   # arm64 | x86_64 | universal2

datas = [('static', 'static')]
binaries = []
hiddenimports = collect_submodules('core')

# ocrmypdf carica i plugin builtin (tesseract, ghostscript, ...) via pluggy
# con import dinamici: senza collect_all il bundle non li vede.
# docx2pdf porta con sé convert.jxa (script JXA per Word su macOS).
for pkg in ('ocrmypdf', 'pikepdf', 'docx2pdf', 'weasyprint', 'pydyf',
            'tinycss2', 'cssselect2', 'pyphen', 'fpdf', 'mammoth', 'img2pdf'):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:  # pacchetto opzionale non installato
        print(f'[spec] {pkg}: {e}')

icon_file = None
for cand in ('build/AppIcon.icns', 'icon.icns', 'icon.png'):
    if os.path.isfile(cand):
        icon_file = cand
        break

a = Analysis(
    ['app.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'IPython', 'pytest'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='splitpdf50',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch=TARGET_ARCH if sys.platform == 'darwin' else None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='splitpdf50',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name=f'{APP_NAME}.app',
        icon=icon_file,
        bundle_identifier=BUNDLE_ID,
        version=VERSION,
        info_plist={
            'CFBundleName': APP_NAME,
            'CFBundleDisplayName': APP_NAME,
            'CFBundleShortVersionString': VERSION,
            'CFBundleVersion': VERSION,
            'LSMinimumSystemVersion': '12.0',
            'LSArchitecturePriority': ['arm64'],
            'NSHighResolutionCapable': True,
            # Server in background: nessuna finestra/Dock "non risponde".
            # Si chiude dal pulsante "Esci" nella pagina web.
            'LSUIElement': True,
            'NSAppleEventsUsageDescription':
                'Split PDF 50 usa Microsoft Word e la finestra di scelta '
                'cartella del Finder per convertire i documenti.',
        },
    )
