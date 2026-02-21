"""
Conversione di tutti i tipi di file in formato PDF.
Utilizza LibreOffice per documenti Office, img2pdf per immagini,
e p7m_handler per file firmati digitalmente.
"""

import os
import sys
import shutil
import subprocess
import tempfile
import uuid

# Estensioni gestite da LibreOffice
LIBREOFFICE_EXTENSIONS = {
    '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.odt', '.ods', '.odp', '.odg', '.rtf', '.txt',
    '.csv', '.html', '.htm', '.xml',
}

# Estensioni immagini
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp',
    '.tiff', '.tif', '.webp',
}


def find_libreoffice() -> str:
    """
    Trova il percorso dell'eseguibile LibreOffice nel sistema.
    Ritorna il percorso o None se non trovato.
    """
    if sys.platform == 'win32':
        candidates = [
            r'C:\Program Files\LibreOffice\program\soffice.exe',
            r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
            r'C:\Program Files\LibreOffice 7\program\soffice.exe',
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path
        # Cerca nel PATH
        result = shutil.which('soffice')
        if result:
            return result

    elif sys.platform == 'darwin':
        candidates = [
            '/Applications/LibreOffice.app/Contents/MacOS/soffice',
            '/usr/local/bin/soffice',
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path
        result = shutil.which('soffice')
        if result:
            return result

    else:
        result = shutil.which('soffice')
        if result:
            return result

    return None


def _convert_image_to_pdf(image_path: str, output_dir: str) -> str:
    """
    Converte un'immagine in PDF usando img2pdf (lossless) o Pillow come fallback.
    """
    base = os.path.splitext(os.path.basename(image_path))[0]
    output_path = os.path.join(output_dir, f'{base}_{uuid.uuid4().hex[:8]}.pdf')

    # Tentativo 1: img2pdf (preserva qualità originale)
    try:
        import img2pdf
        from PIL import Image

        # img2pdf non supporta RGBA o palette - convertiamo prima se necessario
        with Image.open(image_path) as img:
            if img.mode in ('RGBA', 'LA', 'P'):
                # Converti in RGB per img2pdf
                converted_path = os.path.join(output_dir, f'_conv_{uuid.uuid4().hex[:8]}.jpg')
                img.convert('RGB').save(converted_path, 'JPEG', quality=95)
                with open(output_path, 'wb') as f:
                    f.write(img2pdf.convert(converted_path))
                os.unlink(converted_path)
            else:
                with open(output_path, 'wb') as f:
                    f.write(img2pdf.convert(image_path))

        return output_path

    except Exception:
        pass

    # Tentativo 2: Pillow → PDF diretto
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            rgb_img = img.convert('RGB')
            rgb_img.save(output_path, 'PDF', resolution=150)
        return output_path
    except Exception as e:
        raise RuntimeError(f'Impossibile convertire immagine: {e}')


def _convert_office_to_pdf(file_path: str, output_dir: str, lo_path: str) -> str:
    """
    Converte un documento Office in PDF tramite LibreOffice headless.
    """
    if not lo_path:
        raise RuntimeError('LibreOffice non trovato. Installalo per convertire documenti Office.')

    # LibreOffice scrive il PDF nella stessa cartella del file sorgente
    # Per sicurezza, copiamo il file in una cartella temporanea dedicata
    tmp_dir = tempfile.mkdtemp(prefix='lo_conv_')
    try:
        tmp_input = os.path.join(tmp_dir, os.path.basename(file_path))
        shutil.copy2(file_path, tmp_input)

        result = subprocess.run(
            [lo_path, '--headless', '--norestore',
             '--convert-to', 'pdf',
             '--outdir', tmp_dir,
             tmp_input],
            capture_output=True,
            timeout=120,
            env={**os.environ, 'HOME': tmp_dir}  # evita conflitti di lock
        )

        # Cerca il PDF generato
        base = os.path.splitext(os.path.basename(file_path))[0]
        expected_pdf = os.path.join(tmp_dir, f'{base}.pdf')

        if not os.path.isfile(expected_pdf):
            # LibreOffice a volte usa un nome leggermente diverso
            pdfs = [f for f in os.listdir(tmp_dir) if f.endswith('.pdf')]
            if not pdfs:
                raise RuntimeError(
                    f'LibreOffice non ha prodotto PDF. '
                    f'Exit code: {result.returncode}. '
                    f'Stderr: {result.stderr.decode(errors="ignore")[:200]}'
                )
            expected_pdf = os.path.join(tmp_dir, pdfs[0])

        # Sposta nella output_dir
        final_path = os.path.join(
            output_dir,
            f'{base}_{uuid.uuid4().hex[:8]}.pdf'
        )
        shutil.move(expected_pdf, final_path)
        return final_path

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _convert_txt_to_pdf(file_path: str, output_dir: str, lo_path: str) -> str:
    """
    Converte testo semplice in PDF. Prima prova LibreOffice, poi fpdf2.
    """
    # Prova LibreOffice
    if lo_path:
        try:
            return _convert_office_to_pdf(file_path, output_dir, lo_path)
        except Exception:
            pass

    # Fallback: fpdf2
    try:
        from fpdf import FPDF

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font('Helvetica', size=10)

        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        for line in content.split('\n'):
            pdf.multi_cell(0, 5, line)

        base = os.path.splitext(os.path.basename(file_path))[0]
        output_path = os.path.join(output_dir, f'{base}_{uuid.uuid4().hex[:8]}.pdf')
        pdf.output(output_path)
        return output_path

    except Exception as e:
        raise RuntimeError(f'Conversione testo fallita: {e}')


def convert_to_pdf(file_path: str, output_dir: str, lo_path: str = None) -> str:
    """
    Converte qualsiasi file supportato in PDF.
    Ritorna il percorso del PDF generato, o solleva un'eccezione.

    Pipeline:
    - .p7m       → estrazione contenuto → conversione ricorsiva
    - immagini   → img2pdf / Pillow
    - .pdf       → copia diretta
    - Office/txt → LibreOffice
    """
    ext = os.path.splitext(file_path)[1].lower()

    # File P7M: estrai prima il contenuto
    if ext == '.p7m':
        from core.p7m_handler import extract_p7m
        extracted = extract_p7m(file_path, output_dir)
        if extracted is None:
            raise RuntimeError('Impossibile estrarre il contenuto dal file P7M')
        # Converti ricorsivamente il file estratto
        try:
            result = convert_to_pdf(extracted, output_dir, lo_path)
        finally:
            # Rimuovi il file estratto intermedio
            if os.path.exists(extracted):
                os.unlink(extracted)
        return result

    # PDF: copia direttamente nella output_dir
    if ext == '.pdf':
        base = os.path.splitext(os.path.basename(file_path))[0]
        dest = os.path.join(output_dir, f'{base}_{uuid.uuid4().hex[:8]}.pdf')
        shutil.copy2(file_path, dest)
        return dest

    # Immagini
    if ext in IMAGE_EXTENSIONS:
        return _convert_image_to_pdf(file_path, output_dir)

    # Testo semplice
    if ext == '.txt':
        return _convert_txt_to_pdf(file_path, output_dir, lo_path)

    # Documenti Office e tutto il resto → LibreOffice
    if ext in LIBREOFFICE_EXTENSIONS or lo_path:
        return _convert_office_to_pdf(file_path, output_dir, lo_path)

    raise RuntimeError(f'Formato non supportato: {ext}')
