"""
Genera l'icona dell'app "Split PDF 50" usando Pillow.
Produce: icon.ico (Windows) e icon.png (macOS .app bundle)

Uso: python genera_icona.py
     (viene eseguito automaticamente da start.bat / start.sh se icon.ico non esiste)
"""

import os
import sys


def create_icon():
    """
    Crea un'icona verde con il numero "50" al centro.
    Salva icon.ico (multi-size, per Windows) e icon.png (256x256, per macOS).
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("  [icona] Pillow non disponibile, icona non generata.")
        return None, None

    SIZES = [16, 32, 48, 64, 128, 256]
    BG_COLOR    = (27, 107, 69)       # Verde scuro
    TEXT_COLOR  = (168, 230, 194)     # Verde chiaro

    images = []

    for size in SIZES:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Sfondo arrotondato
        radius = max(2, size // 6)
        draw.rounded_rectangle([0, 0, size - 1, size - 1],
                                radius=radius, fill=BG_COLOR)

        # Numero "50" centrato
        font_size = max(6, int(size * 0.4))
        font = None

        # Prova font di sistema
        font_candidates = [
            'arialbd.ttf', 'Arial Bold.ttf', 'arial.ttf',
            '/System/Library/Fonts/Helvetica.ttc',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        ]
        for fc in font_candidates:
            try:
                font = ImageFont.truetype(fc, font_size)
                break
            except Exception:
                continue

        if font is None:
            try:
                font = ImageFont.load_default()
            except Exception:
                pass

        text = '50'
        if font:
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                x = (size - tw) // 2 - bbox[0]
                y = (size - th) // 2 - bbox[1]
                draw.text((x, y), text, fill=TEXT_COLOR, font=font)
            except Exception:
                pass

        images.append(img)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    ico_path = os.path.join(base_dir, 'icon.ico')
    png_path = os.path.join(base_dir, 'icon.png')

    # Salva .ico (multi-size per Windows)
    try:
        images[0].save(
            ico_path,
            format='ICO',
            sizes=[(s, s) for s in SIZES],
            append_images=images[1:],
        )
        print(f'  Icona ICO salvata: {ico_path}')
    except Exception as e:
        print(f'  [icona] Errore salvataggio ICO: {e}')
        ico_path = None

    # Salva .png (256x256 per macOS)
    try:
        images[-1].save(png_path, format='PNG')
        print(f'  Icona PNG salvata: {png_path}')

        # Copia nella cartella .app Resources (se esiste)
        app_resources = os.path.join(
            base_dir, 'Split PDF 50.app', 'Contents', 'Resources'
        )
        if os.path.isdir(app_resources):
            import shutil
            shutil.copy2(png_path, os.path.join(app_resources, 'AppIcon.png'))
    except Exception as e:
        print(f'  [icona] Errore salvataggio PNG: {e}')
        png_path = None

    return ico_path, png_path


def create_windows_shortcut(ico_path: str):
    """
    Crea un collegamento .lnk sul Desktop Windows con l'icona generata.
    Richiede pywin32 oppure usa PowerShell come alternativa.
    """
    import sys, subprocess, os

    if sys.platform != 'win32':
        return

    vbs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'Avvia Split PDF 50.vbs')
    desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
    lnk_path = os.path.join(desktop, 'Split PDF 50.lnk')

    icon_arg = f', "{ico_path}"' if ico_path else ''

    ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{lnk_path}")
$Shortcut.TargetPath = "{vbs_path}"
$Shortcut.WorkingDirectory = "{os.path.dirname(vbs_path)}"
$Shortcut.Description = "Split PDF 50"
{f'$Shortcut.IconLocation = "{ico_path}"' if ico_path else ''}
$Shortcut.Save()
"""
    try:
        subprocess.run(
            ['powershell', '-NonInteractive', '-WindowStyle', 'Hidden', '-Command', ps_script],
            capture_output=True, timeout=30
        )
        print(f'  Collegamento Desktop creato: {lnk_path}')
    except Exception as e:
        print(f'  [collegamento] Errore: {e}')


def create_macos_app(png_path: str):
    """
    Crea (o ricrea) il bundle "Split PDF 50.app" nella cartella del progetto.
    Compila lo script AppleScript con osacompile e imposta l'icona ICNS.
    Solo macOS.
    """
    import sys, os, subprocess, shutil, tempfile

    if sys.platform != 'darwin':
        return

    base_dir = os.path.dirname(os.path.abspath(__file__))
    app_path  = os.path.join(base_dir, 'Split PDF 50.app')

    # ── Scrivi lo script AppleScript ──────────────────────────────
    applescript = '''\
property serverURL : "http://localhost:5000"
property pidFile   : "/tmp/pdf50_server.pid"
property logFile   : "/tmp/pdf50_server.log"

on run
  launchServer()
end run

on launchServer()
  set appBundlePath to POSIX path of (path to me)
  if appBundlePath ends with "/" then
    set appBundlePath to text 1 thru -2 of appBundlePath
  end if
  set appDir to do shell script "dirname " & quoted form of appBundlePath
  set pythonPath to appDir & "/.venv/bin/python"

  set serverRunning to false
  try
    do shell script "curl -sf --connect-timeout 1 " & serverURL & "/api/system-info > /dev/null 2>&1"
    set serverRunning to true
  on error
  end try

  if not serverRunning then
    do shell script "cd " & quoted form of appDir & " && nohup " & quoted form of pythonPath & " app.py >> " & logFile & " 2>&1 & echo $! > " & pidFile
    set attempts to 0
    repeat
      delay 1
      set attempts to attempts + 1
      try
        do shell script "curl -sf --connect-timeout 1 " & serverURL & "/api/system-info > /dev/null 2>&1"
        exit repeat
      on error
        if attempts >= 15 then
          display alert "Split PDF 50" message "Il server non risponde." & return & "Log: " & logFile as critical
          quit
          return
        end if
      end try
    end repeat
    display notification "Split PDF 50 è pronto su localhost:5000" with title "Split PDF 50"
  end if

  open location serverURL
end launchServer

on idle
  set serverRunning to false
  try
    do shell script "curl -sf --connect-timeout 2 " & serverURL & "/api/system-info > /dev/null 2>&1"
    set serverRunning to true
  on error
  end try
  if not serverRunning then
    try
      set appBundlePath to POSIX path of (path to me)
      if appBundlePath ends with "/" then
        set appBundlePath to text 1 thru -2 of appBundlePath
      end if
      set appDir to do shell script "dirname " & quoted form of appBundlePath
      set pythonPath to appDir & "/.venv/bin/python"
      do shell script "cd " & quoted form of appDir & " && nohup " & quoted form of pythonPath & " app.py >> " & logFile & " 2>&1 & echo $! > " & pidFile
      display notification "Server riavviato automaticamente" with title "Split PDF 50"
    on error
    end try
  end if
  return 30
end idle

on quit
  try
    do shell script "if [ -f " & pidFile & " ]; then kill $(cat " & pidFile & ") 2>/dev/null || true; rm -f " & pidFile & "; fi; pkill -f 'python.*app.py' 2>/dev/null || true"
  on error
  end try
  continue quit
end quit
'''

    with tempfile.NamedTemporaryFile(suffix='.applescript', mode='w',
                                     delete=False, encoding='utf-8') as f:
        f.write(applescript)
        tmp_script = f.name

    try:
        # Rimuovi bundle precedente
        if os.path.exists(app_path):
            shutil.rmtree(app_path)

        # Compila
        r = subprocess.run(
            ['osacompile', '-o', app_path, tmp_script],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            print(f'  [app] Errore osacompile: {r.stderr.strip()}')
            return
        print(f'  App compilata: {app_path}')

        # ── Crea icona ICNS ──────────────────────────────────────
        if png_path and os.path.isfile(png_path):
            try:
                iconset_dir = tempfile.mkdtemp(suffix='.iconset')
                sizes = [
                    (16,  'icon_16x16.png'),
                    (32,  'icon_16x16@2x.png'),
                    (32,  'icon_32x32.png'),
                    (64,  'icon_32x32@2x.png'),
                    (128, 'icon_128x128.png'),
                    (256, 'icon_128x128@2x.png'),
                    (256, 'icon_256x256.png'),
                    (512, 'icon_256x256@2x.png'),
                    (512, 'icon_512x512.png'),
                ]
                for sz, name in sizes:
                    subprocess.run(
                        ['sips', '-z', str(sz), str(sz), png_path,
                         '--out', os.path.join(iconset_dir, name)],
                        capture_output=True,
                    )
                icns_path = os.path.join(base_dir, 'icon.icns')
                subprocess.run(
                    ['iconutil', '-c', 'icns', iconset_dir, '-o', icns_path],
                    capture_output=True,
                )
                shutil.rmtree(iconset_dir, ignore_errors=True)

                if os.path.isfile(icns_path):
                    dest = os.path.join(app_path, 'Contents', 'Resources', 'applet.icns')
                    shutil.copy2(icns_path, dest)
                    os.remove(icns_path)
                    # Forza refresh Finder
                    subprocess.run(['touch', app_path], capture_output=True)
                    print(f'  Icona applicata all\'app.')
            except Exception as e:
                print(f'  [app] Icona non applicata: {e}')

    finally:
        os.unlink(tmp_script)


if __name__ == '__main__':
    print('\n  Generazione icona Split PDF 50...')
    ico, png = create_icon()

    if sys.platform == 'win32' and ico:
        create_windows_shortcut(ico)

    if sys.platform == 'darwin':
        create_macos_app(png)

    print('  Fatto.\n')
