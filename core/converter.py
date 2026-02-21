"""
Conversione di tutti i tipi di file in formato PDF.

Pipeline a cascata (dal più qualitativo al fallback):
  DOCX/DOC  → 1) docx2pdf (Office COM)  2) mammoth+weasyprint  3) LibreOffice
  XLSX/XLS  → 1) docx2pdf (Office COM)  2) openpyxl+fpdf2       3) LibreOffice
  PPTX/PPT  → 1) docx2pdf (Office COM)  2) python-pptx+fpdf2    3) LibreOffice
  ODT/ODS   → 1) LibreOffice             2) mammoth (ODT)
  RTF/HTML  → 1) mammoth+weasyprint      2) LibreOffice
  TXT/CSV   → 1) fpdf2 (testo diretto)
  Immagini  → 1) img2pdf                 2) Pillow
  PDF       → copia diretta
  P7M       → estrazione + ricorsione

LibreOffice e' OPZIONALE: migliora la qualita' ma non e' indispensabile.
Se Microsoft Office e' installato, docx2pdf lo usa come prima scelta
(massima qualita', zero dipendenze extra).
"""

import os
import sys
import shutil
import subprocess
import tempfile
import uuid

# ── Estensioni per categoria ──────────────────────────────────────────────────

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp'}

DOCX_EXTENSIONS  = {'.doc', '.docx', '.rtf'}
XLSX_EXTENSIONS  = {'.xls', '.xlsx', '.csv', '.ods'}
PPTX_EXTENSIONS  = {'.ppt', '.pptx', '.odp'}
ODT_EXTENSIONS   = {'.odt', '.odg'}
HTML_EXTENSIONS  = {'.html', '.htm'}
TEXT_EXTENSIONS  = {'.txt'}
XML_EXTENSIONS   = {'.xml'}

# ── Ricerca eseguibili di sistema ─────────────────────────────────────────────

def find_libreoffice() -> str:
    """Trova LibreOffice nel sistema. Ritorna il percorso o None."""
    import glob as _glob

    found = shutil.which('soffice')
    if found:
        return found

    if sys.platform == 'win32':
        patterns = [
            r'C:\Program Files\LibreOffice*\program\soffice.exe',
            r'C:\Program Files (x86)\LibreOffice*\program\soffice.exe',
        ]
        for p in patterns:
            matches = _glob.glob(p)
            if matches:
                return matches[-1]

    elif sys.platform == 'darwin':
        for p in [
            '/Applications/LibreOffice.app/Contents/MacOS/soffice',
            '/usr/local/bin/soffice',
            '/opt/homebrew/bin/soffice',
        ]:
            if os.path.isfile(p):
                return p

    return None


def has_microsoft_office() -> bool:
    """
    Verifica se Microsoft Office e' installato e utilizzabile da docx2pdf.
    """
    try:
        import docx2pdf  # noqa
    except ImportError:
        return False

    if sys.platform == 'win32':
        # Controlla se Word e' registrato come applicazione COM
        import winreg
        try:
            winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                           r'SOFTWARE\Microsoft\Office', 0, winreg.KEY_READ)
            return True
        except Exception:
            pass
        # Fallback: controlla percorsi comuni
        import glob as _glob
        patterns = [
            r'C:\Program Files\Microsoft Office\root\Office*\WINWORD.EXE',
            r'C:\Program Files (x86)\Microsoft Office\root\Office*\WINWORD.EXE',
            r'C:\Program Files\Microsoft Office\Office*\WINWORD.EXE',
        ]
        return any(_glob.glob(p) for p in patterns)

    elif sys.platform == 'darwin':
        return os.path.isdir('/Applications/Microsoft Word.app')

    return False


# ── Helper: LibreOffice headless ─────────────────────────────────────────────

def _convert_office_to_pdf(file_path: str, output_dir: str, lo_path: str) -> str:
    """Converti un file tramite LibreOffice headless."""
    tmp_dir = tempfile.mkdtemp(prefix='lo_conv_')
    try:
        tmp_input = os.path.join(tmp_dir, os.path.basename(file_path))
        shutil.copy2(file_path, tmp_input)

        subprocess.run(
            [lo_path, '--headless', '--norestore',
             '--convert-to', 'pdf', '--outdir', tmp_dir, tmp_input],
            capture_output=True, timeout=120,
            env={**os.environ, 'HOME': tmp_dir},
        )

        base = os.path.splitext(os.path.basename(file_path))[0]
        expected = os.path.join(tmp_dir, f'{base}.pdf')
        if not os.path.isfile(expected):
            pdfs = [f for f in os.listdir(tmp_dir) if f.endswith('.pdf')]
            if not pdfs:
                raise RuntimeError('LibreOffice non ha prodotto PDF')
            expected = os.path.join(tmp_dir, pdfs[0])

        dest = os.path.join(output_dir, f'{base}_{uuid.uuid4().hex[:8]}.pdf')
        shutil.move(expected, dest)
        return dest
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Helper: docx2pdf (Office COM / AppleScript) ───────────────────────────────

def _try_docx2pdf(file_path: str, output_dir: str) -> tuple:
    """
    Prova a convertire tramite Microsoft Office (COM).
    Ritorna (percorso_pdf, None) oppure (None, str_errore).
    Copia il file in una posizione trusted prima di convertire per
    evitare la Protected View di Word sui file da cartelle temp.
    """
    import glob as _glob

    # Copia in una cartella non-temp per evitare la Protected View di Word
    tmp_trusted = tempfile.mkdtemp(prefix='docx2pdf_')
    try:
        trusted_copy = os.path.join(tmp_trusted, os.path.basename(file_path))
        shutil.copy2(file_path, trusted_copy)

        # Su Windows rimuovi il flag "file scaricato da internet" (Zone.Identifier)
        if sys.platform == 'win32':
            zone_id = trusted_copy + ':Zone.Identifier'
            try:
                if os.path.exists(zone_id):
                    os.remove(zone_id)
            except Exception:
                pass

        from docx2pdf import convert as _convert
        base = os.path.splitext(os.path.basename(file_path))[0]
        dest = os.path.join(output_dir, f'{base}_{uuid.uuid4().hex[:8]}.pdf')
        _convert(trusted_copy, dest)
        if os.path.isfile(dest) and os.path.getsize(dest) > 0:
            return dest, None
        return None, 'output PDF vuoto o assente dopo la conversione'
    except Exception as e:
        return None, str(e)
    finally:
        shutil.rmtree(tmp_trusted, ignore_errors=True)


# ── DOCX / DOC / RTF ─────────────────────────────────────────────────────────

def _convert_docx_to_pdf(file_path: str, output_dir: str, lo_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    step_errors = []

    # 1) Office COM (Word/Mac Word)
    result, err = _try_docx2pdf(file_path, output_dir)
    if result:
        return result
    step_errors.append(f'Office COM: {err or "?"}')

    # 2) mammoth -> HTML -> weasyprint
    if ext in ('.docx', '.doc', '.rtf'):
        try:
            import mammoth
            import weasyprint

            with open(file_path, 'rb') as f:
                doc = mammoth.convert_to_html(f)

            html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<style>
  @page {{ margin: 2cm; }}
  body {{ font-family: Arial, Helvetica, sans-serif; font-size: 11pt; line-height: 1.5; }}
  table {{ border-collapse: collapse; width: 100%; margin: 8px 0; }}
  td, th {{ border: 1px solid #aaa; padding: 3px 6px; font-size: 9pt; }}
  img {{ max-width: 100%; }}
  h1,h2,h3 {{ color: #1B6B45; }}
</style>
</head><body>{doc.value}</body></html>"""

            base = os.path.splitext(os.path.basename(file_path))[0]
            dest = os.path.join(output_dir, f'{base}_{uuid.uuid4().hex[:8]}.pdf')
            weasyprint.HTML(string=html).write_pdf(dest)

            if os.path.isfile(dest) and os.path.getsize(dest) > 0:
                return dest
            step_errors.append('mammoth+weasyprint: output vuoto')
        except Exception as e:
            step_errors.append(f'mammoth+weasyprint: {e}')

    # 3) LibreOffice
    if lo_path:
        return _convert_office_to_pdf(file_path, output_dir, lo_path)

    raise RuntimeError(
        f'Impossibile convertire {os.path.basename(file_path)}: '
        + ' | '.join(step_errors)
    )


# ── XLSX / XLS / CSV / ODS ───────────────────────────────────────────────────

def _convert_xlsx_to_pdf(file_path: str, output_dir: str, lo_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    step_errors = []

    # 1) Office COM (Excel, solo Windows/macOS con Office)
    result, err = _try_docx2pdf(file_path, output_dir)
    if result:
        return result
    step_errors.append(f'Office COM: {err or "?"}')

    # 2) openpyxl + fpdf2 (tabelle formattate, Python puro)
    if ext in ('.xlsx', '.xls', '.csv', '.ods'):
        try:
            from fpdf import FPDF

            # -- Lettura dati --
            if ext == '.csv':
                import csv
                with open(file_path, newline='', encoding='utf-8-sig', errors='replace') as f:
                    reader = csv.reader(f)
                    raw_rows = [r for r in reader if any(c.strip() for c in r)]
                sheets_data = {
                    os.path.splitext(os.path.basename(file_path))[0]: raw_rows
                }
            else:
                import openpyxl
                wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
                sheets_data = {}
                for name in wb.sheetnames:
                    ws = wb[name]
                    sheet_rows = []
                    for row in ws.iter_rows(values_only=True):
                        cells = [str(c) if c is not None else '' for c in row]
                        if any(c.strip() for c in cells):
                            sheet_rows.append(cells)
                    if sheet_rows:
                        sheets_data[name] = sheet_rows
                wb.close()

            if not sheets_data:
                raise ValueError('Nessun dato trovato nel foglio')

            base = os.path.splitext(os.path.basename(file_path))[0]
            dest = os.path.join(output_dir, f'{base}_{uuid.uuid4().hex[:8]}.pdf')

            pdf = FPDF(orientation='L', unit='mm', format='A4')
            pdf.set_margins(10, 10, 10)
            pdf.set_auto_page_break(auto=True, margin=10)

            for sheet_name, sheet_rows in sheets_data.items():
                pdf.add_page()

                # Titolo foglio
                pdf.set_font('Helvetica', 'B', 12)
                pdf.set_fill_color(27, 107, 69)
                pdf.set_text_color(255, 255, 255)
                pdf.cell(0, 8, sheet_name, fill=True, ln=True)
                pdf.set_text_color(0, 0, 0)
                pdf.ln(2)

                col_count = max(len(r) for r in sheet_rows)
                if col_count == 0:
                    continue

                page_w = pdf.w - 20
                col_w = max(10, min(50, page_w / col_count))
                row_h = 5

                for i, row in enumerate(sheet_rows):
                    row = list(row) + [''] * (col_count - len(row))

                    if i == 0:
                        pdf.set_font('Helvetica', 'B', 7)
                        pdf.set_fill_color(220, 237, 228)
                    elif i % 2 == 0:
                        pdf.set_font('Helvetica', '', 7)
                        pdf.set_fill_color(255, 255, 255)
                    else:
                        pdf.set_font('Helvetica', '', 7)
                        pdf.set_fill_color(245, 247, 246)

                    for cell in row:
                        text = str(cell)
                        if len(text) > 35:
                            text = text[:33] + '\u2026'
                        pdf.cell(col_w, row_h, text, border=1, fill=True)
                    pdf.ln(row_h)

            pdf.output(dest)
            if os.path.isfile(dest) and os.path.getsize(dest) > 0:
                return dest
        except Exception:
            pass

    # 3) LibreOffice
    if lo_path:
        return _convert_office_to_pdf(file_path, output_dir, lo_path)

    raise RuntimeError(
        f'Impossibile convertire {os.path.basename(file_path)}: '
        + ' | '.join(step_errors)
    )


# ── PPTX / PPT / ODP ─────────────────────────────────────────────────────────

def _convert_pptx_to_pdf(file_path: str, output_dir: str, lo_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    step_errors = []

    # 1) Office COM
    result, err = _try_docx2pdf(file_path, output_dir)
    if result:
        return result
    step_errors.append(f'Office COM: {err or "?"}')

    # 2) python-pptx -> testo per slide -> fpdf2
    if ext in ('.pptx', '.ppt'):
        try:
            from pptx import Presentation
            from fpdf import FPDF

            prs = Presentation(file_path)
            base = os.path.splitext(os.path.basename(file_path))[0]
            dest = os.path.join(output_dir, f'{base}_{uuid.uuid4().hex[:8]}.pdf')

            pdf = FPDF(orientation='L', unit='mm', format='A4')
            pdf.set_auto_page_break(auto=True, margin=15)

            for slide_num, slide in enumerate(prs.slides, 1):
                pdf.add_page()
                pdf.set_font('Helvetica', '', 8)
                pdf.set_text_color(150, 150, 150)
                pdf.cell(0, 5, f'Slide {slide_num}', ln=True, align='R')
                pdf.set_text_color(0, 0, 0)

                for shape in slide.shapes:
                    if not shape.has_text_frame:
                        continue
                    for para in shape.text_frame.paragraphs:
                        text = para.text.strip()
                        if not text:
                            continue
                        ph = getattr(shape, 'placeholder_format', None)
                        is_title = ph is not None and getattr(ph, 'idx', -1) == 0
                        if is_title:
                            pdf.set_font('Helvetica', 'B', 16)
                            pdf.set_text_color(27, 107, 69)
                        else:
                            pdf.set_font('Helvetica', '', 11)
                            pdf.set_text_color(0, 0, 0)
                        pdf.multi_cell(0, 7, text)
                        pdf.ln(1)

            pdf.output(dest)
            if os.path.isfile(dest) and os.path.getsize(dest) > 0:
                return dest
        except Exception:
            pass

    # 3) LibreOffice
    if lo_path:
        return _convert_office_to_pdf(file_path, output_dir, lo_path)

    raise RuntimeError(
        f'Impossibile convertire {os.path.basename(file_path)}: '
        + ' | '.join(step_errors)
    )


# ── HTML ─────────────────────────────────────────────────────────────────────

def _convert_html_to_pdf(file_path: str, output_dir: str, lo_path: str) -> str:
    try:
        import weasyprint
        base = os.path.splitext(os.path.basename(file_path))[0]
        dest = os.path.join(output_dir, f'{base}_{uuid.uuid4().hex[:8]}.pdf')
        weasyprint.HTML(filename=file_path).write_pdf(dest)
        if os.path.isfile(dest) and os.path.getsize(dest) > 0:
            return dest
    except Exception:
        pass

    if lo_path:
        return _convert_office_to_pdf(file_path, output_dir, lo_path)

    raise RuntimeError(f'Impossibile convertire HTML: {os.path.basename(file_path)}')


# ── TXT / XML ─────────────────────────────────────────────────────────────────

def _convert_txt_to_pdf(file_path: str, output_dir: str, lo_path: str) -> str:
    try:
        from fpdf import FPDF
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font('Helvetica', size=9)

        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        for line in content.split('\n'):
            pdf.multi_cell(0, 5, line if line else ' ')

        base = os.path.splitext(os.path.basename(file_path))[0]
        dest = os.path.join(output_dir, f'{base}_{uuid.uuid4().hex[:8]}.pdf')
        pdf.output(dest)
        return dest
    except Exception:
        pass

    if lo_path:
        return _convert_office_to_pdf(file_path, output_dir, lo_path)

    raise RuntimeError(f'Impossibile convertire testo: {os.path.basename(file_path)}')


# ── Immagini ──────────────────────────────────────────────────────────────────

def _convert_image_to_pdf(file_path: str, output_dir: str) -> str:
    base = os.path.splitext(os.path.basename(file_path))[0]
    dest = os.path.join(output_dir, f'{base}_{uuid.uuid4().hex[:8]}.pdf')

    try:
        import img2pdf
        from PIL import Image

        with Image.open(file_path) as img:
            if img.mode in ('RGBA', 'LA', 'P'):
                conv = os.path.join(output_dir, f'_img_{uuid.uuid4().hex[:6]}.jpg')
                img.convert('RGB').save(conv, 'JPEG', quality=95)
                with open(dest, 'wb') as f:
                    f.write(img2pdf.convert(conv))
                os.unlink(conv)
            else:
                with open(dest, 'wb') as f:
                    f.write(img2pdf.convert(file_path))
        return dest
    except Exception:
        pass

    try:
        from PIL import Image
        with Image.open(file_path) as img:
            img.convert('RGB').save(dest, 'PDF', resolution=150)
        return dest
    except Exception as e:
        raise RuntimeError(f'Impossibile convertire immagine: {e}')


# ── Entry point pubblico ──────────────────────────────────────────────────────

def convert_to_pdf(file_path: str, output_dir: str, lo_path: str = None) -> str:
    """
    Converte qualsiasi file supportato in PDF.
    lo_path e' opzionale: se None, usa solo le librerie Python.
    """
    ext = os.path.splitext(file_path)[1].lower()

    # P7M: estrai il contenuto e converti ricorsivamente
    if ext == '.p7m':
        from core.p7m_handler import extract_p7m
        extracted = extract_p7m(file_path, output_dir)
        if extracted is None:
            raise RuntimeError('Impossibile estrarre il contenuto dal file P7M')
        try:
            return convert_to_pdf(extracted, output_dir, lo_path)
        finally:
            if os.path.exists(extracted):
                os.unlink(extracted)

    # PDF: copia diretta
    if ext == '.pdf':
        base = os.path.splitext(os.path.basename(file_path))[0]
        dest = os.path.join(output_dir, f'{base}_{uuid.uuid4().hex[:8]}.pdf')
        shutil.copy2(file_path, dest)
        return dest

    # Immagini
    if ext in IMAGE_EXTENSIONS:
        return _convert_image_to_pdf(file_path, output_dir)

    # Testo / XML semplice
    if ext in TEXT_EXTENSIONS or ext in XML_EXTENSIONS:
        return _convert_txt_to_pdf(file_path, output_dir, lo_path)

    # HTML
    if ext in HTML_EXTENSIONS:
        return _convert_html_to_pdf(file_path, output_dir, lo_path)

    # DOCX / DOC / RTF
    if ext in DOCX_EXTENSIONS:
        return _convert_docx_to_pdf(file_path, output_dir, lo_path)

    # XLSX / XLS / CSV / ODS
    if ext in XLSX_EXTENSIONS:
        return _convert_xlsx_to_pdf(file_path, output_dir, lo_path)

    # PPTX / PPT / ODP
    if ext in PPTX_EXTENSIONS:
        return _convert_pptx_to_pdf(file_path, output_dir, lo_path)

    # ODT / ODG - formati nativi LibreOffice
    if ext in ODT_EXTENSIONS:
        if lo_path:
            return _convert_office_to_pdf(file_path, output_dir, lo_path)
        # Tentativo mammoth per ODT
        try:
            import mammoth, weasyprint
            with open(file_path, 'rb') as f:
                doc = mammoth.convert_to_html(f)
            base = os.path.splitext(os.path.basename(file_path))[0]
            dest = os.path.join(output_dir, f'{base}_{uuid.uuid4().hex[:8]}.pdf')
            weasyprint.HTML(string=f'<html><body>{doc.value}</body></html>').write_pdf(dest)
            return dest
        except Exception:
            pass
        raise RuntimeError(
            f'{ext} richiede LibreOffice (scaricalo da libreoffice.org)'
        )

    # Fallback generico
    if lo_path:
        return _convert_office_to_pdf(file_path, output_dir, lo_path)

    raise RuntimeError(f'Formato non supportato: {ext}')
