"""Compressione PDF tramite Ghostscript, con avanzamento pagina per pagina."""
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time

# Se Ghostscript non completa nessuna pagina per questo tempo lo consideriamo
# bloccato. Non c'è un limite sul tempo totale: un PDF da 1000 pagine può
# richiedere parecchi minuti, ed è giusto lasciarlo finire.
STALL_TIMEOUT = 600

_RE_TOTAL = re.compile(rb'Processing pages \d+ through (\d+)')
_RE_PAGE = re.compile(rb'^Page (\d+)')


def find_ghostscript() -> str:
    for cmd in ['gs', 'gswin64c', 'gswin32c']:
        if shutil.which(cmd):
            return cmd
    return None


def compress_pdf(input_path: str, output_path: str, quality: str = 'ebook',
                 progress_cb=None, cancel_check=None, log_cb=None) -> dict:
    """
    Comprimi un PDF con Ghostscript.
    quality: 'screen' (72 dpi) | 'ebook' (150 dpi) | 'printer' (300 dpi)

    progress_cb(page, total)  chiamata a ogni pagina completata (total può
                              essere 0 finché Ghostscript non l'ha annunciato)
    cancel_check() -> bool    se ritorna True il processo viene terminato
    log_cb(level, message)    messaggi per il pannello log (info|warning|error)

    Ritorna dict con chiavi: ok, orig_mb, size_mb, reduction_pct, error, cancelled
    """
    gs = find_ghostscript()
    if not gs:
        return {'ok': False, 'error': 'Ghostscript non trovato (brew install ghostscript)'}

    if quality not in ('screen', 'ebook', 'printer'):
        quality = 'ebook'

    orig_bytes = os.path.getsize(input_path)

    # Scrive in un file temporaneo nella stessa cartella e rinomina solo alla
    # fine: niente PDF a metà se si annulla o se Ghostscript fallisce.
    out_dir = os.path.dirname(os.path.abspath(output_path)) or '.'
    fd, tmp_out = tempfile.mkstemp(prefix='.compress_', suffix='.pdf', dir=out_dir)
    os.close(fd)

    # Senza -dQUIET Ghostscript stampa "Processing pages 1 through N." e poi
    # "Page K" per ogni pagina: è la base della barra di avanzamento.
    cmd = [
        gs, '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4',
        f'-dPDFSETTINGS=/{quality}', '-dNOPAUSE', '-dBATCH',
        f'-sOutputFile={tmp_out}', input_path,
    ]

    log = log_cb or (lambda level, msg: None)
    popen_kw = {}
    if os.name == 'posix':
        popen_kw['start_new_session'] = True   # per killare l'intero gruppo

    proc = None
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                stdin=subprocess.DEVNULL, **popen_kw)
        log('info', f'Ghostscript avviato (qualità: {quality}, '
                    f'{orig_bytes / (1024 * 1024):.1f} MB in ingresso)')

        # stderr letto in un thread: avvisi di riparazione del PDF ecc.
        # Le righe ripetute (es. centinaia di "Ignoring wrong pointing object")
        # vengono raggruppate in un solo messaggio con il conteggio.
        err_tail = []
        err_counts = {}

        def _read_stderr():
            for raw in iter(proc.stderr.readline, b''):
                line = raw.decode('utf-8', 'replace').strip()
                if not line:
                    continue
                err_tail.append(line)
                del err_tail[:-30]
                key = re.sub(r'\d+', 'N', line)
                n = err_counts.get(key, 0) + 1
                err_counts[key] = n
                if n == 1:
                    log('warning', f'Ghostscript: {line}')

        import threading
        t_err = threading.Thread(target=_read_stderr, daemon=True)
        t_err.start()

        total = 0
        last_page_at = time.monotonic()
        state = {'stalled': False, 'cancelled': False, 'last_page_at': last_page_at}

        def _watchdog():
            # Controlla annullamento e stallo anche mentre readline() è bloccata
            while proc.poll() is None:
                if cancel_check and cancel_check():
                    state['cancelled'] = True
                    _kill(proc)
                    return
                if time.monotonic() - state['last_page_at'] > STALL_TIMEOUT:
                    state['stalled'] = True
                    _kill(proc)
                    return
                time.sleep(0.3)

        threading.Thread(target=_watchdog, daemon=True).start()

        for line in iter(proc.stdout.readline, b''):
            m = _RE_TOTAL.search(line)
            if m:
                total = int(m.group(1))
                log('info', f'Pagine da comprimere: {total}')
                if progress_cb:
                    progress_cb(0, total)
                continue
            m = _RE_PAGE.match(line)
            if m:
                state['last_page_at'] = time.monotonic()
                if progress_cb:
                    progress_cb(int(m.group(1)), total)
                continue
            # Errori/avvisi che Ghostscript scrive su stdout
            txt = line.decode('utf-8', 'replace').strip()
            if txt and ('Error' in txt or 'Warning' in txt or txt.startswith('****')):
                key = re.sub(r'\d+', 'N', txt)
                n = err_counts.get(key, 0) + 1
                err_counts[key] = n
                if n == 1:
                    log('warning', f'Ghostscript: {txt}')
        proc.wait()
        t_err.join(timeout=2)

        repeated = [(k, n) for k, n in err_counts.items() if n > 1]
        for k, n in repeated:
            log('warning', f'(messaggio ripetuto {n} volte: {k})')
        if any('wrong pointing object' in k or 'xref' in k.lower() for k in err_counts):
            log('info', 'Il PDF ha la tabella interna degli oggetti danneggiata: '
                        'Ghostscript la ripara, ma questo rallenta la compressione.')

        if state['cancelled']:
            return {'ok': False, 'cancelled': True, 'error': 'Compressione annullata'}
        if state['stalled']:
            return {'ok': False, 'error':
                    f'Ghostscript bloccato: nessuna pagina completata in {STALL_TIMEOUT // 60} minuti'}
        if proc.returncode != 0:
            err = '\n'.join(err_tail).strip()
            return {'ok': False, 'error': err[-1500:] or 'Errore Ghostscript sconosciuto'}
        if not os.path.isfile(tmp_out) or os.path.getsize(tmp_out) == 0:
            return {'ok': False, 'error': 'File di output vuoto'}

        # mkstemp crea il file con permessi 600: riporta ai permessi normali
        _umask = os.umask(0); os.umask(_umask)
        os.chmod(tmp_out, 0o666 & ~_umask)
        os.replace(tmp_out, output_path)
        out_bytes = os.path.getsize(output_path)
        reduction = round((1 - out_bytes / orig_bytes) * 100, 1) if orig_bytes else 0
        return {
            'ok': True,
            'orig_mb': round(orig_bytes / (1024 * 1024), 2),
            'size_mb': round(out_bytes / (1024 * 1024), 2),
            'reduction_pct': reduction,
        }
    except Exception as e:
        if proc and proc.poll() is None:
            _kill(proc)
        return {'ok': False, 'error': str(e)}
    finally:
        if os.path.exists(tmp_out):
            try:
                os.remove(tmp_out)
            except OSError:
                pass


def _kill(proc):
    try:
        if os.name == 'posix':
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        else:
            proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
