"""
Applicazione OCR italiano ai PDF tramite ocrmypdf.
ocrmypdf usa Tesseract (motore OCR) + Ghostscript (ottimizzazione PDF).
"""

import os
import shutil


def is_available() -> bool:
    """Verifica che ocrmypdf e Tesseract siano installati."""
    try:
        import ocrmypdf
        # Verifica che il language pack italiano sia disponibile
        import tesserocr
        return True
    except ImportError:
        pass

    try:
        import ocrmypdf
        return True
    except ImportError:
        return False


def has_italian_tessdata() -> bool:
    """Verifica che il pack lingua italiana di Tesseract sia installato."""
    try:
        import subprocess
        result = subprocess.run(
            ['tesseract', '--list-langs'],
            capture_output=True, text=True, timeout=10
        )
        return 'ita' in result.stdout or 'ita' in result.stderr
    except Exception:
        return False


def apply_ocr(input_pdf: str, output_pdf: str, language: str = 'ita') -> bool:
    """
    Applica OCR al PDF specificato e salva il risultato.

    Args:
        input_pdf:  percorso PDF sorgente
        output_pdf: percorso PDF destinazione (con testo OCR)
        language:   codice lingua Tesseract (default: 'ita' = italiano)

    Returns:
        True se l'OCR è andato a buon fine, False altrimenti.
    """
    try:
        import ocrmypdf

        ocrmypdf.ocr(
            input_pdf,
            output_pdf,
            language=language,
            # force_ocr=True → applica OCR anche se il PDF ha già testo
            force_ocr=True,
            # Ottimizzazione leggera (1 = veloce, 2 = standard, 3 = aggressivo)
            optimize=1,
            # Disabilita la progress bar (usiamo il nostro sistema di log)
            progress_bar=False,
            # Non fallire su pagine con errori, salta solo quella pagina
            skip_big=True,
            # Risoluzione minima per OCR (DPI)
            oversample=0,
        )

        # Verifica che il file di output esista e non sia vuoto
        if os.path.isfile(output_pdf) and os.path.getsize(output_pdf) > 0:
            return True

        return False

    except Exception as e:
        # Se ocrmypdf fallisce per qualsiasi motivo (file corrotto, DRM, ecc.)
        # copiamo il PDF originale senza OCR
        err_msg = str(e).lower()

        # Errori "accettabili": pagine già con testo perfetto, DRM, ecc.
        # In questi casi, copia l'originale senza sollevare eccezioni
        try:
            shutil.copy2(input_pdf, output_pdf)
        except Exception:
            pass

        raise RuntimeError(f'OCR fallito: {e}')
