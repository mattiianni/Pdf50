# Split PDF 50

Applicazione locale per convertire un'intera cartella (e tutte le sue sottocartelle) in PDF con OCR italiano, unire tutto in un unico file e suddividerlo automaticamente se supera i 50 MB.

---

## Prerequisiti

Installa questi programmi **prima** di avviare l'app:

### 1. Python 3.10+
- **Windows/macOS**: https://www.python.org/downloads/

### 2. LibreOffice
Converte DOCX, XLSX, PPT e tutti i formati Office in PDF.
- **Windows/macOS**: https://www.libreoffice.org/download/

### 3. Tesseract (OCR)
Motore OCR. Deve includere il **language pack italiano**.

**Windows:**
```
https://github.com/UB-Mannheim/tesseract/wiki
```
Durante l'installazione, seleziona "Additional language data → Italian".

**macOS:**
```bash
brew install tesseract tesseract-lang
```

### 4. Ghostscript
Richiesto da ocrmypdf per ottimizzare i PDF.

**Windows:** https://www.ghostscript.com/releases/

**macOS:**
```bash
brew install ghostscript
```

---

## Installazione e avvio

### Windows
```
Doppio click su: start.bat
```

### macOS / Linux
```bash
chmod +x start.sh
./start.sh
```

Al primo avvio vengono installate automaticamente le dipendenze Python.
Il browser si apre su `http://localhost:5000`.

---

## Funzionamento

1. **Trascina** la cartella nella drop zone (o clicca per sfogliare)
2. Scegli la **modalità di output**:
   - **Unico**: tutte le sottocartelle unite in un solo PDF
   - **Suddiviso**: un PDF per ogni sottocartella
3. Seleziona la **cartella di destinazione**
4. Clicca **Avvia Conversione**

### Pipeline
```
Scansione file
    ↓
Conversione → PDF
  • Immagini (JPG, PNG, TIFF, GIF, BMP, WebP) → img2pdf
  • Documenti Office (DOCX, XLSX, PPT, ODT...) → LibreOffice
  • File firmati P7M → estrazione contenuto → conversione
  • PDF → copia diretta
    ↓
OCR Italiano (ocrmypdf + Tesseract)
    ↓
Unione PDF (ordinata per cartella → data)
    ↓
Se risultato > 50 MB:
  • Salva il file completo
  • Crea sottocartella con le parti:
    NomeCartella_Parte 1 di N.pdf
    NomeCartella_Parte 2 di N.pdf
    ...
```

### Ordinamento file
1. Cartella (alfabetico A→Z)
2. Data nel nome del file (es. `20240115_fattura.pdf`)
3. Data di modifica del file (se nessuna data nel nome)

---

## Formati supportati

| Tipo | Formati |
|------|---------|
| Immagini | JPG, PNG, GIF, BMP, TIFF, WebP |
| Office | DOC, DOCX, XLS, XLSX, PPT, PPTX, ODT, ODS, ODP |
| PDF | PDF |
| Testo | TXT, RTF, CSV, HTML |
| Firmati | P7M (firma digitale italiana) |
| Altro | XML |

---

## Note tecniche

- L'app gira interamente **in locale**: nessun file viene inviato a server esterni
- I file temporanei vengono eliminati automaticamente al termine
- In caso di file corrotti o non convertibili, vengono saltati con un avviso nel log
- Il server è su `localhost:5000` e accetta connessioni solo locali
