"""
Split PDF 50 - Server Flask locale
Avvia il server su http://localhost:5000
"""

import os
import sys
import json
import time
import shutil
import threading
import tempfile
import uuid
import subprocess
import webbrowser
from datetime import datetime
from collections import defaultdict

from flask import Flask, request, jsonify, Response, send_from_directory

sys.path.insert(0, os.path.dirname(__file__))

from core import file_scanner, converter, ocr_processor, pdf_merger, pdf_splitter

app = Flask(__name__, static_folder='static')
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024 * 1024   # 10 GB max upload

# Storage in-memory dei job
jobs = {}
jobs_lock = threading.Lock()

LIMIT_BYTES = 50 * 1024 * 1024   # 50 MB


# ─────────────────────────────────────────────────────────────────────────────
# Helper: dialog cartella nativo (Windows / macOS / Linux)
# ─────────────────────────────────────────────────────────────────────────────

def open_folder_dialog(title: str = 'Seleziona cartella') -> str:
    if sys.platform == 'win32':
        ps = f"""
Add-Type -AssemblyName System.Windows.Forms
$d = New-Object System.Windows.Forms.FolderBrowserDialog
$d.Description = "{title}"
$d.ShowNewFolderButton = $true
[void][System.Windows.Forms.Application]::EnableVisualStyles()
if ($d.ShowDialog() -eq 'OK') {{ Write-Output $d.SelectedPath }}
"""
        try:
            r = subprocess.run(
                ['powershell', '-NonInteractive', '-WindowStyle', 'Hidden', '-Command', ps],
                capture_output=True, text=True, timeout=120
            )
            path = r.stdout.strip()
            return path if path else None
        except Exception:
            pass

    elif sys.platform == 'darwin':
        try:
            r = subprocess.run(
                ['osascript', '-e',
                 f'set f to POSIX path of (choose folder with prompt "{title}")'],
                capture_output=True, text=True, timeout=120
            )
            path = r.stdout.strip().rstrip('\n')
            return path if path else None
        except Exception:
            pass

    else:
        try:
            r = subprocess.run(
                ['zenity', '--file-selection', '--directory', f'--title={title}'],
                capture_output=True, text=True, timeout=120
            )
            path = r.stdout.strip()
            return path if path else None
        except Exception:
            pass

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Helper: emissione eventi SSE
# ─────────────────────────────────────────────────────────────────────────────

def _emit(job_id: str, event: dict):
    event['ts'] = datetime.now().strftime('%H:%M:%S')
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]['events'].append(event)


def _is_cancelled(job_id: str) -> bool:
    with jobs_lock:
        return jobs.get(job_id, {}).get('cancelled', False)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline comune: converti + OCR una lista di file → lista PDF OCR
# ─────────────────────────────────────────────────────────────────────────────

def _convert_and_ocr(
    job_id: str,
    files: list,
    tmp_dir: str,
    lo_path: str,
    step_convert: int,
    step_ocr: int,
    label_prefix: str = '',
) -> tuple:
    """
    Converte e applica OCR a una lista di file.
    Ritorna (ocr_pdfs, errors).
    """

    def log(msg, level='info'):
        _emit(job_id, {'type': 'log', 'message': msg, 'level': level})

    def progress(current, total, filename, operation, step):
        pct = int(current / total * 100) if total > 0 else 0
        _emit(job_id, {
            'type': 'progress',
            'step': step,
            'current': current,
            'total': total,
            'file': (label_prefix + filename) if label_prefix else filename,
            'operation': operation,
            'percent': pct,
        })

    convert_dir = os.path.join(tmp_dir, f'conv_{uuid.uuid4().hex[:6]}')
    ocr_dir = os.path.join(tmp_dir, f'ocr_{uuid.uuid4().hex[:6]}')
    os.makedirs(convert_dir, exist_ok=True)
    os.makedirs(ocr_dir, exist_ok=True)

    converted_pdfs = []
    errors = []
    total = len(files)

    # ── Conversione ──────────────────────────────────────────────────────────
    for i, fi in enumerate(files):
        if _is_cancelled(job_id):
            return [], errors

        rel = fi['rel_path'] if fi.get('rel_folder') else fi['name']
        progress(i + 1, total, rel, 'Conversione', step_convert)
        log(f'[{i+1}/{total}] Conversione: {rel}')

        try:
            pdf_path = converter.convert_to_pdf(fi['path'], convert_dir, lo_path)
            converted_pdfs.append({'path': pdf_path, 'name': fi['name'], 'index': i})
            log(f'  ✓ Convertito')
        except Exception as e:
            errors.append({'file': rel, 'error': str(e)})
            log(f'  ⚠ Saltato: {e}', 'warning')

    if not converted_pdfs:
        return [], errors

    # ── OCR ──────────────────────────────────────────────────────────────────
    ocr_pdfs = []
    total_conv = len(converted_pdfs)

    for i, item in enumerate(converted_pdfs):
        if _is_cancelled(job_id):
            return [], errors

        progress(i + 1, total_conv, item['name'], 'OCR Italiano', step_ocr)
        log(f'[{i+1}/{total_conv}] OCR: {item["name"]}')

        ocr_out = os.path.join(ocr_dir, f'ocr_{i:05d}.pdf')
        try:
            ocr_processor.apply_ocr(item['path'], ocr_out)
            log(f'  ✓ OCR applicato')
        except Exception as e:
            shutil.copy2(item['path'], ocr_out)
            log(f'  ⚠ OCR fallito, usato PDF senza OCR: {e}', 'warning')

        ocr_pdfs.append(ocr_out)

    return ocr_pdfs, errors


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline: salva / split un PDF unito
# ─────────────────────────────────────────────────────────────────────────────

def _save_or_split(
    job_id: str,
    merged_path: str,
    output_dir: str,
    pdf_name: str,
) -> dict:
    """
    Se il PDF è ≤ 50 MB → salvalo direttamente.
    Se > 50 MB → salva l'originale + crea le parti nella sotto-cartella.
    Ritorna un dict con i risultati.
    """

    def log(msg, level='info'):
        _emit(job_id, {'type': 'log', 'message': msg, 'level': level})

    merged_size = os.path.getsize(merged_path)
    merged_mb = merged_size / (1024 * 1024)
    total_pages = pdf_merger.get_page_count(merged_path)

    os.makedirs(output_dir, exist_ok=True)

    if merged_size <= LIMIT_BYTES:
        final_path = os.path.join(output_dir, f'{pdf_name}.pdf')
        shutil.copy2(merged_path, final_path)
        log(f'✓ Salvato: {pdf_name}.pdf ({merged_mb:.1f} MB, {total_pages} pag.)')
        return {
            'result_type': 'single',
            'file': final_path,
            'size_mb': round(merged_mb, 2),
            'total_pages': total_pages,
        }
    else:
        log(f'⚠ {pdf_name}.pdf supera 50 MB ({merged_mb:.1f} MB) → divisione')

        # Salva il file completo
        original_final = os.path.join(output_dir, f'{pdf_name}.pdf')
        shutil.copy2(merged_path, original_final)
        log(f'  Originale salvato: {pdf_name}.pdf ({merged_mb:.1f} MB)')

        # Crea la cartella per le parti
        split_dir = os.path.join(output_dir, pdf_name)
        os.makedirs(split_dir, exist_ok=True)
        log(f'  Cartella creata: {pdf_name}/')

        def split_cb(part_num, total_parts):
            _emit(job_id, {
                'type': 'split_progress',
                'label': pdf_name,
                'current': part_num,
                'total': total_parts,
            })

        parts = pdf_splitter.split_pdf_by_size(
            merged_path, split_dir, pdf_name, progress_callback=split_cb
        )

        for part in parts:
            log(
                f'  ✓ {part["name"]} — '
                f'{part["num_pages"]} pag., {part["size_mb"]} MB '
                f'(pagine {part["pages"]})'
            )

        log(f'✓ Divisione completata: {len(parts)} parti')

        return {
            'result_type': 'split',
            'original_file': original_final,
            'split_dir': split_dir,
            'parts': parts,
            'total_parts': len(parts),
            'size_mb': round(merged_mb, 2),
            'total_pages': total_pages,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Modalità 1: PDF UNICO (tutte le sottocartelle unite)
# ─────────────────────────────────────────────────────────────────────────────

def _run_unified(job_id: str, source_path: str, output_path: str):

    def log(msg, level='info'):
        _emit(job_id, {'type': 'log', 'message': msg, 'level': level})

    lo_path = converter.find_libreoffice()
    tmp_dir = None

    try:
        tmp_dir = tempfile.mkdtemp(prefix='splitpdf50_u_')

        # Step 1: Scansione
        _emit(job_id, {'type': 'step', 'step': 1, 'label': 'Scansione file'})
        log(f'Scansione: {source_path}')
        files = file_scanner.scan(source_path)
        total_files = len(files)

        if total_files == 0:
            _emit(job_id, {'type': 'fatal_error',
                           'message': 'Nessun file supportato trovato.'})
            return

        log(f'Trovati {total_files} file')
        _emit(job_id, {'type': 'scan_done', 'total': total_files})

        # Step 2 + 3: Converti + OCR
        _emit(job_id, {'type': 'step', 'step': 2, 'label': 'Conversione in PDF'})
        ocr_pdfs, errors = _convert_and_ocr(
            job_id, files, tmp_dir, lo_path,
            step_convert=2, step_ocr=3
        )

        if _is_cancelled(job_id):
            return

        if not ocr_pdfs:
            _emit(job_id, {'type': 'fatal_error',
                           'message': 'Nessun file convertito con successo.'})
            return

        # Step 4: Unione
        _emit(job_id, {'type': 'step', 'step': 4, 'label': 'Unione PDF'})
        log(f'Unione di {len(ocr_pdfs)} PDF...')

        with jobs_lock:
            folder_name = jobs[job_id].get('folder_name') or \
                          os.path.basename(source_path.rstrip('/\\'))
        merged_path = os.path.join(tmp_dir, f'{folder_name}_merged.pdf')

        ok = pdf_merger.merge_pdfs(ocr_pdfs, merged_path)
        if not ok:
            _emit(job_id, {'type': 'fatal_error',
                           'message': "Errore durante l'unione dei PDF."})
            return

        merged_mb = os.path.getsize(merged_path) / (1024 * 1024)
        total_pages = pdf_merger.get_page_count(merged_path)
        log(f'✓ Unione completata: {total_pages} pagine, {merged_mb:.1f} MB')

        # Step 5: Salva / Split
        _emit(job_id, {'type': 'step', 'step': 5, 'label': 'Salvataggio'})
        result = _save_or_split(job_id, merged_path, output_path, folder_name)

        if errors:
            log(f'')
            log(f'File non elaborati ({len(errors)}):', 'warning')
            for e in errors:
                log(f'  • {e["file"]}: {e["error"]}', 'warning')

        log('Elaborazione completata.')
        _emit(job_id, {**result, 'type': 'done', 'errors': errors,
                       'output_path': output_path, 'mode': 'unified'})

    except Exception as e:
        import traceback
        _emit(job_id, {'type': 'fatal_error', 'message': str(e),
                       'detail': traceback.format_exc()})
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        with jobs_lock:
            if job_id in jobs:
                jobs[job_id]['status'] = 'done'
                if jobs[job_id].get('source_is_temp', False):
                    shutil.rmtree(source_path, ignore_errors=True)
        _emit(job_id, {'type': 'eos'})


# ─────────────────────────────────────────────────────────────────────────────
# Modalità 2: PDF PER SOTTOCARTELLA
# ─────────────────────────────────────────────────────────────────────────────

def _run_per_folder(job_id: str, source_path: str, output_path: str):
    """
    Crea un PDF separato per ogni prima-livello di sottocartella.
    I file nella radice vengono inclusi in un PDF con il nome della cartella sorgente.
    """

    def log(msg, level='info'):
        _emit(job_id, {'type': 'log', 'message': msg, 'level': level})

    lo_path = converter.find_libreoffice()
    tmp_dir = None

    try:
        tmp_dir = tempfile.mkdtemp(prefix='splitpdf50_p_')

        # Step 1: Scansione
        _emit(job_id, {'type': 'step', 'step': 1, 'label': 'Scansione file'})
        log(f'Scansione: {source_path}')
        files = file_scanner.scan(source_path)
        total_files = len(files)

        if total_files == 0:
            _emit(job_id, {'type': 'fatal_error',
                           'message': 'Nessun file supportato trovato.'})
            return

        log(f'Trovati {total_files} file')
        _emit(job_id, {'type': 'scan_done', 'total': total_files})

        # Raggruppa per prima sottocartella (livello 1)
        with jobs_lock:
            root_folder_name = jobs[job_id].get('folder_name') or \
                               os.path.basename(source_path.rstrip('/\\'))
        groups = defaultdict(list)

        for fi in files:
            rel_folder = fi.get('rel_folder', '')
            if not rel_folder or rel_folder == '.':
                group_key = root_folder_name
            else:
                # Prima componente del percorso relativo
                parts = rel_folder.replace('\\', '/').split('/')
                group_key = parts[0]
            groups[group_key].append(fi)

        # Se tutti i file finiscono in un unico gruppo di primo livello,
        # prova a scendere al livello successivo per produrre più gruppi.
        # Se anche quello è unico (o non esiste), e il nome non è già il
        # nome della cartella radice, prefissa con "radice - gruppo"
        # (es. "RENDICONTI - DICH.SPESA IVSALBIS").
        if len(groups) == 1:
            only_key = next(iter(groups))
            drill = defaultdict(list)
            for fi in groups[only_key]:
                rf = fi.get('rel_folder', '')
                parts = rf.replace('\\', '/').split('/') if rf else []
                if len(parts) >= 2 and parts[0] == only_key:
                    full_key = f'{only_key} - {parts[1]}'
                    drill[full_key].append(fi)
                else:
                    drill[only_key].append(fi)
            if len(drill) > 1:
                log(f'  → unico gruppo "{only_key}", scendo al livello successivo')
                groups = drill
            elif only_key != root_folder_name:
                # Unico sottogruppo e non si può scendere: prefissa con il nome radice
                new_key = f'{root_folder_name} - {only_key}'
                log(f'  → unico gruppo "{only_key}", rinominato in "{new_key}"')
                groups = {new_key: groups[only_key]}

        group_keys = sorted(groups.keys(), key=lambda k: k.lower())
        total_groups = len(group_keys)
        log(f'Sottocartelle da elaborare: {total_groups}')

        all_errors = []
        all_results = []

        for g_idx, group_key in enumerate(group_keys):
            if _is_cancelled(job_id):
                log('Annullato.', 'warning')
                return

            group_files = groups[group_key]
            log(f'')
            log(f'── Sottocartella {g_idx+1}/{total_groups}: "{group_key}" ({len(group_files)} file)')
            _emit(job_id, {
                'type': 'folder_start',
                'folder': group_key,
                'current': g_idx + 1,
                'total': total_groups,
                'file_count': len(group_files),
            })

            sub_tmp = os.path.join(tmp_dir, f'group_{g_idx:03d}')
            os.makedirs(sub_tmp, exist_ok=True)

            # Converti + OCR per questo gruppo
            _emit(job_id, {'type': 'step', 'step': 2,
                           'label': f'Conversione: {group_key}'})
            ocr_pdfs, errors = _convert_and_ocr(
                job_id, group_files, sub_tmp, lo_path,
                step_convert=2, step_ocr=3,
                label_prefix=f'{group_key}/',
            )

            if _is_cancelled(job_id):
                return

            all_errors.extend(errors)

            if not ocr_pdfs:
                log(f'  ⚠ Nessun file convertito per "{group_key}", saltato.', 'warning')
                continue

            # Unione del gruppo
            log(f'  Unione di {len(ocr_pdfs)} PDF per "{group_key}"...')
            merged_path = os.path.join(sub_tmp, f'{group_key}_merged.pdf')
            ok = pdf_merger.merge_pdfs(ocr_pdfs, merged_path)

            if not ok:
                log(f'  ✗ Unione fallita per "{group_key}"', 'error')
                all_errors.append({'file': group_key, 'error': 'Unione fallita'})
                continue

            merged_mb = os.path.getsize(merged_path) / (1024 * 1024)
            log(f'  ✓ Unione: {merged_mb:.1f} MB')

            # Salva / split per questo gruppo
            _emit(job_id, {'type': 'step', 'step': 5,
                           'label': f'Salvataggio: {group_key}'})
            result = _save_or_split(job_id, merged_path, output_path, group_key)
            result['folder'] = group_key
            all_results.append(result)

        if all_errors:
            log(f'')
            log(f'File non elaborati ({len(all_errors)}):', 'warning')
            for e in all_errors:
                log(f'  • {e["file"]}: {e["error"]}', 'warning')

        log('')
        log(f'Elaborazione completata. {total_groups} PDF creati.')
        _emit(job_id, {
            'type': 'done',
            'mode': 'per_folder',
            'output_path': output_path,
            'results': all_results,
            'total_groups': total_groups,
            'errors': all_errors,
        })

    except Exception as e:
        import traceback
        _emit(job_id, {'type': 'fatal_error', 'message': str(e),
                       'detail': traceback.format_exc()})
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        with jobs_lock:
            if job_id in jobs:
                jobs[job_id]['status'] = 'done'
                if jobs[job_id].get('source_is_temp', False):
                    shutil.rmtree(source_path, ignore_errors=True)
        _emit(job_id, {'type': 'eos'})


# ─────────────────────────────────────────────────────────────────────────────
# Route: frontend
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


# ─────────────────────────────────────────────────────────────────────────────
# Route: dialog cartella
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/dialog/source', methods=['POST'])
def dialog_source():
    path = open_folder_dialog('Seleziona la cartella da elaborare')
    if path and os.path.isdir(path):
        files = file_scanner.scan(path)
        return jsonify({'path': path, 'file_count': len(files)})
    return jsonify({'path': None, 'file_count': 0})


@app.route('/api/dialog/output', methods=['POST'])
def dialog_output():
    path = open_folder_dialog('Seleziona la cartella di destinazione')
    if path:
        return jsonify({'path': path})
    return jsonify({'path': None})


# ─────────────────────────────────────────────────────────────────────────────
# Route: upload cartella drag-and-drop
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/upload-folder', methods=['POST'])
def upload_folder():
    """
    Riceve i file di una cartella trascinata dal browser.
    Il client invia i file come multipart con il percorso relativo come filename.
    Salva tutto in una cartella temporanea e restituisce il percorso.
    """
    folder_name = request.form.get('folder_name', 'Cartella')
    files = request.files.getlist('files')

    if not files:
        return jsonify({'error': 'Nessun file ricevuto'}), 400

    tmp_dir = tempfile.mkdtemp(prefix='splitpdf50_up_')

    try:
        for f in files:
            rel_path = f.filename.replace('\\', '/')
            # Sicurezza: rimuovi eventuali path traversal
            safe_parts = [p for p in rel_path.split('/') if p and p != '..']
            if not safe_parts:
                continue
            dest = os.path.join(tmp_dir, *safe_parts)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            f.save(dest)

        files_found = file_scanner.scan(tmp_dir)
        return jsonify({
            'path': tmp_dir,
            'folder_name': folder_name,
            'file_count': len(files_found),
        })

    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/upload-file', methods=['POST'])
def upload_file():
    """
    Upload di un singolo file (PDF o altro).
    Ritorna path sul server, metadati e flag is_pdf.
    """
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'Nessun file ricevuto'}), 400

    filename = os.path.basename((f.filename or 'file').replace('\\', '/'))
    tmp_dir = tempfile.mkdtemp(prefix='splitpdf50_up_')
    dest = os.path.join(tmp_dir, filename)
    f.save(dest)

    ext = os.path.splitext(filename)[1].lower()
    size_mb = round(os.path.getsize(dest) / (1024 * 1024), 2)

    pages = None
    if ext == '.pdf':
        try:
            pages = pdf_merger.get_page_count(dest)
        except Exception:
            pass

    return jsonify({
        'path':     dest,
        'tmp_dir':  tmp_dir,
        'filename': filename,
        'ext':      ext,
        'is_pdf':   ext == '.pdf',
        'size_mb':  size_mb,
        'pages':    pages,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Route: post-elaborazione PDF (compress / split-size / split-ranges)
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/post/compress', methods=['POST'])
def post_compress():
    from core import pdf_compressor
    data = request.get_json() or {}
    pdf_path   = data.get('pdf_path',   '').strip()
    quality    = data.get('quality',    'ebook')
    output_dir = (data.get('output_dir') or '').strip()

    if not pdf_path or not os.path.isfile(pdf_path):
        return jsonify({'ok': False, 'error': 'File non trovato'}), 400

    if not output_dir:
        output_dir = os.path.dirname(pdf_path)
    os.makedirs(output_dir, exist_ok=True)

    base = os.path.splitext(os.path.basename(pdf_path))[0]
    out  = os.path.join(output_dir, f'{base}_compresso.pdf')

    result = pdf_compressor.compress_pdf(pdf_path, out, quality)
    if result['ok']:
        result['output_path'] = out
        result['filename']    = os.path.basename(out)
    return jsonify(result)


@app.route('/api/post/split-size', methods=['POST'])
def post_split_size():
    data = request.get_json() or {}
    pdf_path   = data.get('pdf_path',  '').strip()
    target_mb  = float(data.get('target_mb', 46))
    output_dir = (data.get('output_dir') or '').strip()

    if not pdf_path or not os.path.isfile(pdf_path):
        return jsonify({'ok': False, 'error': 'File non trovato'}), 400

    if not output_dir:
        output_dir = os.path.dirname(pdf_path)
    os.makedirs(output_dir, exist_ok=True)

    base    = os.path.splitext(os.path.basename(pdf_path))[0]
    sub_dir = os.path.join(output_dir, base)
    os.makedirs(sub_dir, exist_ok=True)

    part_label = (data.get('part_label') or 'Parte').strip() or 'Parte'
    show_total = bool(data.get('show_total', True))

    try:
        target_bytes = int(target_mb * 1024 * 1024)
        parts = pdf_splitter.split_pdf_by_size(
            pdf_path, sub_dir, base, target_bytes=target_bytes,
            part_label=part_label, show_total=show_total,
        )
        return jsonify({'ok': True, 'parts': parts, 'split_dir': sub_dir})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/post/split-ranges', methods=['POST'])
def post_split_ranges():
    data = request.get_json() or {}
    pdf_path   = data.get('pdf_path',  '').strip()
    ranges     = data.get('ranges',    [])   # [[start, end], ...]
    output_dir = (data.get('output_dir') or '').strip()

    if not pdf_path or not os.path.isfile(pdf_path):
        return jsonify({'ok': False, 'error': 'File non trovato'}), 400
    if not ranges:
        return jsonify({'ok': False, 'error': 'Nessun range specificato'}), 400

    if not output_dir:
        output_dir = os.path.dirname(pdf_path)
    os.makedirs(output_dir, exist_ok=True)

    part_label = (data.get('part_label') or 'Parte').strip() or 'Parte'
    show_total = bool(data.get('show_total', True))

    try:
        parts = pdf_splitter.split_by_ranges(pdf_path, ranges, output_dir,
                                             part_label=part_label, show_total=show_total)
        return jsonify({'ok': True, 'parts': parts})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/post/page-count', methods=['POST'])
def post_page_count():
    data = request.get_json() or {}
    pdf_path = data.get('pdf_path', '').strip()
    if not pdf_path or not os.path.isfile(pdf_path):
        return jsonify({'ok': False, 'error': 'File non trovato'}), 400
    try:
        pages = pdf_merger.get_page_count(pdf_path)
        return jsonify({'ok': True, 'pages': pages})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/cleanup-temp', methods=['POST'])
def cleanup_temp():
    """Elimina una cartella temporanea di upload non più necessaria."""
    data = request.get_json() or {}
    path = data.get('path', '').strip()
    tmp_base = tempfile.gettempdir()
    # Sicurezza: elimina solo percorsi dentro la cartella temp di sistema
    if path and os.path.isabs(path):
        try:
            common = os.path.commonpath([os.path.abspath(path), tmp_base])
            if common == tmp_base:
                shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass
    return jsonify({'ok': True})


# ─────────────────────────────────────────────────────────────────────────────
# Route: avvio job
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/start', methods=['POST'])
def start_job():
    data = request.get_json()
    source = data.get('source_path', '').strip()
    output = data.get('output_path', '').strip()
    mode = data.get('mode', 'unified')   # 'unified' | 'per_folder'
    source_is_temp = bool(data.get('source_is_temp', False))
    # Nome della cartella di origine (passato dal client; fallback al basename del path)
    folder_name = (data.get('folder_name') or '').strip() or \
                  os.path.basename(source.rstrip('/\\'))

    if not source or not os.path.isdir(source):
        return jsonify({'error': 'Cartella sorgente non valida'}), 400
    if not output:
        return jsonify({'error': 'Cartella di destinazione non specificata'}), 400
    if mode not in ('unified', 'per_folder'):
        return jsonify({'error': 'Modalità non valida'}), 400

    job_id = uuid.uuid4().hex

    with jobs_lock:
        jobs[job_id] = {
            'events': [],
            'status': 'running',
            'cancelled': False,
            'source': source,
            'output': output,
            'mode': mode,
            'folder_name': folder_name,
            'source_is_temp': source_is_temp,
            'created_at': time.time(),
        }

    target = _run_unified if mode == 'unified' else _run_per_folder
    t = threading.Thread(target=target, args=(job_id, source, output), daemon=True)
    t.start()

    return jsonify({'job_id': job_id, 'mode': mode})


# ─────────────────────────────────────────────────────────────────────────────
# Route: SSE stream eventi job
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/jobs/<job_id>/stream')
def job_stream(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job non trovato'}), 404

    cursor = int(request.args.get('cursor', 0))

    def generate():
        idx = cursor
        while True:
            with jobs_lock:
                job = jobs.get(job_id)
                if not job:
                    break
                events = job['events']
                status = job['status']

            while idx < len(events):
                event = events[idx]
                yield f'data: {json.dumps({**event, "idx": idx})}\n\n'
                idx += 1
                if event.get('type') == 'eos':
                    return

            if status == 'done':
                break

            time.sleep(0.15)

    return Response(
        generate(),
        content_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# Route: annulla job
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/jobs/<job_id>/cancel', methods=['POST'])
def cancel_job(job_id):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]['cancelled'] = True
    return jsonify({'ok': True})


# ─────────────────────────────────────────────────────────────────────────────
# Route: info di sistema
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/system-info')
def system_info():
    lo = converter.find_libreoffice()
    ms_office = converter.has_microsoft_office()
    ocr_ok = ocr_processor.is_available()
    ita_ok = ocr_processor.has_italian_tessdata()
    gs_ok = ocr_processor.has_ghostscript()

    # Può convertire DOCX/XLSX/PPTX se ha almeno uno tra Office e LibreOffice
    can_convert_office = ms_office or (lo is not None)

    info = {
        'libreoffice': lo is not None,
        'libreoffice_path': lo,
        'ms_office': ms_office,
        'can_convert_office': can_convert_office,
        'ocrmypdf': ocr_ok,
        'tesseract_italian': ita_ok,
        'ghostscript': gs_ok,
        'platform': sys.platform,
    }

    try:
        import pypdf
        info['pypdf_version'] = pypdf.__version__
    except Exception:
        info['pypdf_version'] = None

    return jsonify(info)


# ─────────────────────────────────────────────────────────────────────────────
# Avvio
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = 5000
    url = f'http://localhost:{port}'

    print(f'\n  Split PDF 50')
    print(f'  ─────────────────────────')
    print(f'  Apri: {url}')
    print(f'  Ctrl+C per fermare.\n')

    def open_browser():
        time.sleep(1.5)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host='127.0.0.1', port=port, debug=False, threaded=True)
