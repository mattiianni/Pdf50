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


if __name__ == '__main__':
    print('\n  Generazione icona Split PDF 50...')
    ico, png = create_icon()

    if sys.platform == 'win32' and ico:
        create_windows_shortcut(ico)

    print('  Fatto.\n')
