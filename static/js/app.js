/* ──────────────────────────────────────────────────────────────
   Split PDF 50 — Frontend JS
────────────────────────────────────────────────────────────── */

'use strict';

// ── Stato globale ─────────────────────────────────────────────────────────────
const state = {
  sourcePath:    null,
  folderName:    null,
  outputPath:    null,
  jobId:         null,
  eventSource:   null,
  currentStep:   0,
  totalFiles:    0,
  sourceIsTemp:  false,
  uploading:     false,
  isPdfMode:     false,   // true quando è stato droppato/caricato un PDF diretto
  pdfServerPath: null,    // path del PDF sul server (modalità PDF)
  pdfPages:      null,    // numero di pagine del PDF caricato
  resultPdfPath: null,    // path del PDF risultante (per post-elaborazione)
  postProcOp:    null,    // operazione post-proc in corso
};

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initDropZone();
  loadSystemInfo();
  updateStartButton();
  initRangeList('ranges-list');
  initRangeList('pp-ranges-list');
});

// ── Info sistema ──────────────────────────────────────────────────────────────
async function loadSystemInfo() {
  try {
    const res  = await fetch('/api/system-info');
    const info = await res.json();
    renderDepsWarning(info);
  } catch (e) { /* silenzioso */ }
}

function renderDepsWarning(info) {
  const isMac    = info.platform === 'darwin';
  const required = [];
  const optional = [];

  if (!info.can_convert_office) {
    required.push({
      name: 'Conversione documenti Office',
      desc: 'Serve Microsoft Office (già installato) oppure LibreOffice per convertire DOCX, XLSX, PPTX in PDF.',
      items: [
        { label: 'Microsoft Office', url: 'https://www.microsoft.com/it-it/microsoft-365', urlLabel: 'Info Microsoft 365', brew: null },
        { label: 'oppure LibreOffice (gratuito)', url: 'https://www.libreoffice.org/download/', urlLabel: 'Scarica LibreOffice', brew: isMac ? 'brew install libreoffice' : null },
      ],
    });
  } else if (!info.libreoffice && info.ms_office) {
    optional.push({
      name: 'LibreOffice (opzionale)',
      desc: 'Senza LibreOffice, i file ODT/ODS/ODP potrebbero non essere convertiti correttamente.',
      url: 'https://www.libreoffice.org/download/', urlLabel: 'Scarica LibreOffice',
      brew: isMac ? 'brew install libreoffice' : null,
    });
  }

  if (!info.tesseract_italian) {
    required.push({
      name: 'Tesseract + Lingua Italiana',
      desc: 'Necessario per applicare l\'OCR in italiano.',
      items: [{
        label: isMac ? 'Installa via Homebrew' : 'Scarica Tesseract',
        url:   isMac ? 'https://formulae.brew.sh/formula/tesseract-lang' : 'https://github.com/UB-Mannheim/tesseract/wiki',
        urlLabel: isMac ? 'Homebrew' : 'Scarica',
        brew: isMac ? 'brew install tesseract tesseract-lang' : null,
        note: !isMac ? 'Durante l\'installazione spunta: Additional language data → Italian' : null,
      }],
    });
  }

  if (!info.ghostscript) {
    required.push({
      name: 'Ghostscript',
      desc: 'Richiesto da ocrmypdf e per la compressione PDF.',
      items: [{
        label: 'Scarica Ghostscript',
        url:   isMac ? 'https://formulae.brew.sh/formula/ghostscript' : 'https://www.ghostscript.com/releases/',
        urlLabel: 'Scarica',
        brew: isMac ? 'brew install ghostscript' : null,
      }],
    });
  }

  const banner = document.getElementById('deps-warning');
  if (!banner) return;

  if (required.length === 0 && optional.length === 0) {
    banner.classList.add('hidden');
    return;
  }

  function renderItem(item) {
    return `<div style="display:flex;align-items:center;gap:8px;margin-top:6px">
      ${item.brew ? `<span class="btn-brew" onclick="copyBrew('${item.brew}')" title="Copia comando Homebrew">${item.brew}</span>` : ''}
      <a class="btn-download" href="${item.url}" target="_blank" rel="noopener">↓ ${item.urlLabel}</a>
      ${item.note ? `<span style="font-size:11px;color:#9A7020"><em>${item.note}</em></span>` : ''}
    </div>`;
  }

  function renderGroup(dep, isRequired) {
    const dismissBtn = !isRequired
      ? `<button class="dep-dismiss" onclick="this.closest('.dep-item').remove(); _checkOptionalSectionEmpty();" title="Chiudi">×</button>`
      : '';
    return `<div class="dep-item${isRequired ? '' : ' dep-item-optional'}">
      ${dismissBtn}
      <div class="dep-item-text">
        <div class="dep-name">${isRequired ? '' : '<span class="dep-badge-opt">opzionale</span> '}${dep.name}</div>
        <div class="dep-desc">${dep.desc}</div>
        ${dep.items ? dep.items.map(renderItem).join('') : renderItem(dep)}
      </div>
    </div>`;
  }

  banner.innerHTML = `
    ${required.length > 0 ? `
      <div class="deps-warning-title">Dipendenze mancanti — alcune funzioni non saranno disponibili</div>
      <div class="deps-list">${required.map(d => renderGroup(d, true)).join('')}</div>` : ''}
    ${optional.length > 0 ? `
      <div class="deps-warning-title" style="color:#5A6E65;font-size:12px;margin-top:${required.length > 0 ? '12px' : '0'}">
        Facoltativo — migliora la qualità di conversione</div>
      <div class="deps-list">${optional.map(d => renderGroup(d, false)).join('')}</div>` : ''}
    <div class="deps-warning-footer">Dopo l'installazione, riavvia l'app per aggiornare questo avviso.</div>`;

  banner.classList.remove('hidden');
}

function _checkOptionalSectionEmpty() {
  const banner = document.getElementById('deps-warning');
  if (!banner) return;
  if (banner.querySelectorAll('.dep-item').length === 0) banner.classList.add('hidden');
}

function copyBrew(cmd) {
  navigator.clipboard.writeText(cmd).then(() => {
    document.querySelectorAll('.btn-brew').forEach(el => {
      if (el.textContent.trim() === cmd) {
        const orig = el.textContent;
        el.textContent = '✓ Copiato!';
        setTimeout(() => { el.textContent = orig; }, 1800);
      }
    });
  }).catch(() => {});
}

// ── Drop Zone ─────────────────────────────────────────────────────────────────

function handleDropZoneClick() {
  if (state.uploading) return;
  if (state.isPdfMode) return;
  selectSource();
}

function initDropZone() {
  const zone = document.getElementById('drop-zone');

  zone.addEventListener('dragenter', (e) => {
    e.preventDefault();
    zone.classList.add('drag-over');
    document.getElementById('drop-hint').classList.remove('hidden');
  });

  zone.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  });

  zone.addEventListener('dragleave', (e) => {
    if (!zone.contains(e.relatedTarget)) {
      zone.classList.remove('drag-over');
      document.getElementById('drop-hint').classList.add('hidden');
    }
  });

  zone.addEventListener('drop', async (e) => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    document.getElementById('drop-hint').classList.add('hidden');
    if (state.uploading) return;

    const items = Array.from(e.dataTransfer.items || []);
    if (items.length === 0) return;

    // Prova a ottenere l'entry FileSystem
    const firstEntry = items[0].webkitGetAsEntry ? items[0].webkitGetAsEntry() : null;

    if (firstEntry && firstEntry.isDirectory) {
      // È una cartella → pipeline normale
      await handleDroppedFolder(firstEntry);
    } else {
      // Sono file (uno o più) → gestione file singolo/multiplo
      const files = Array.from(e.dataTransfer.files || []);
      await handleDroppedFiles(files);
    }
  });
}

// ── Gestione cartella trascinata ───────────────────────────────────────────────

async function handleDroppedFolder(dirEntry) {
  state.uploading = true;
  setDropZoneStatus(`Raccogliendo file da "${dirEntry.name}"...`);

  try {
    const fileEntries = [];
    await traverseDir(dirEntry, fileEntries, '');

    if (fileEntries.length === 0) {
      setDropZoneStatus('Nessun file trovato nella cartella.');
      setTimeout(resetDropZoneStatus, 2500);
      return;
    }

    const formData = new FormData();
    formData.append('folder_name', dirEntry.name);

    for (let i = 0; i < fileEntries.length; i++) {
      setDropZoneStatus(`Preparazione ${i + 1} / ${fileEntries.length} file...`);
      const { fileEntry, relPath } = fileEntries[i];
      const file = await getFileFromEntry(fileEntry);
      formData.append('files', file, relPath);
    }

    setDropZoneStatus(`Invio al server (${fileEntries.length} file)...`);
    const res = await fetch('/api/upload-folder', { method: 'POST', body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${res.status}`);
    }

    const data = await res.json();
    state.sourcePath   = data.path;
    state.folderName   = data.folder_name || dirEntry.name;
    state.sourceIsTemp = true;
    exitPdfMode();
    showSourceInfo(data.path, data.file_count, state.folderName);
    updateStartButton();

  } catch (err) {
    setDropZoneStatus(`Errore: ${err.message}`);
    setTimeout(resetDropZoneStatus, 3000);
  } finally {
    state.uploading = false;
  }
}

// ── Gestione file trascinati (PDF o altri) ────────────────────────────────────

async function handleDroppedFiles(files) {
  if (files.length === 0) return;
  const file = files[0];   // gestiamo il primo file
  const ext  = file.name.split('.').pop().toLowerCase();

  state.uploading = true;
  setDropZoneStatus(`Caricamento "${file.name}"...`);

  try {
    const formData = new FormData();
    formData.append('file', file);

    const res = await fetch('/api/upload-file', { method: 'POST', body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${res.status}`);
    }

    const data = await res.json();

    if (data.is_pdf) {
      // Modalità PDF diretta
      enterPdfMode(data);
    } else {
      // File non-PDF: trattalo come cartella mono-file (pipeline normale)
      state.sourcePath   = data.tmp_dir;
      state.folderName   = file.name.replace(/\.[^.]+$/, '');
      state.sourceIsTemp = true;
      exitPdfMode();
      showSourceInfo(data.tmp_dir, 1, file.name);
      updateStartButton();
    }

  } catch (err) {
    setDropZoneStatus(`Errore: ${err.message}`);
    setTimeout(resetDropZoneStatus, 3000);
  } finally {
    state.uploading = false;
  }
}

// ── Modalità PDF diretta ──────────────────────────────────────────────────────

function enterPdfMode(data) {
  state.isPdfMode     = true;
  state.pdfServerPath = data.path;
  state.pdfPages      = data.pages;
  state.sourcePath    = null;
  state.folderName    = null;
  state.sourceIsTemp  = true;

  // Mostra info file PDF (riusa source-info con icona diversa)
  document.getElementById('drop-zone').classList.add('hidden');
  document.getElementById('source-info').classList.remove('hidden');
  document.getElementById('source-icon').textContent = '📄';
  document.getElementById('source-path-display').textContent = data.filename;
  document.getElementById('source-count').textContent =
    `${data.size_mb} MB${data.pages ? ' · ' + data.pages + ' pagine' : ''}`;

  // Nasconde il mode selector (Unico/Suddiviso), mostra pdf ops panel
  document.getElementById('mode-section').classList.add('hidden');
  document.getElementById('pdf-ops-panel').classList.remove('hidden');

  // Popola il label del range se le pagine sono note
  if (data.pages) {
    document.getElementById('range-total-label').textContent = `(totale: ${data.pages})`;
  }

  // Cambia testo pulsante avvio
  document.getElementById('btn-start').textContent = 'Avvia Elaborazione';
  document.getElementById('btn-start').onclick = startPdfOp;

  updatePdfOpOptions();
  updateStartButton();
}

function exitPdfMode() {
  state.isPdfMode     = false;
  state.pdfServerPath = null;
  state.pdfPages      = null;

  document.getElementById('mode-section').classList.remove('hidden');
  document.getElementById('pdf-ops-panel').classList.add('hidden');
  document.getElementById('source-icon').textContent = '📁';

  const btn = document.getElementById('btn-start');
  btn.textContent = 'Avvia Conversione';
  btn.onclick     = startJob;
}

// ── Range inputs (riusabile per setup e post-proc) ────────────────────────────

let _rangeCounter     = 0;
let _ppRangeCounter   = 0;

function initRangeList(listId) {
  const list = document.getElementById(listId);
  if (!list) return;
  list.innerHTML = '';
  if (listId === 'ranges-list')    { _rangeCounter   = 0; _addRangeRowTo(listId, _rangeCounter++); }
  if (listId === 'pp-ranges-list') { _ppRangeCounter = 0; _addRangeRowTo(listId, _ppRangeCounter++); }
}

function _addRangeRowTo(listId, idx) {
  const list   = document.getElementById(listId);
  const partN  = list.children.length + 1;
  const row    = document.createElement('div');
  row.className = 'range-row';
  row.id        = `${listId}-row-${idx}`;
  row.innerHTML = `
    <span class="range-label">Parte ${partN}:</span>
    <input type="number" class="range-from" placeholder="da" min="1" style="width:64px"/>
    <span class="range-sep">—</span>
    <input type="number" class="range-to"   placeholder="a"  min="1" style="width:64px"/>
    <button class="btn-range-remove" onclick="removeRangeRow('${listId}','${listId}-row-${idx}')">✕</button>`;
  list.appendChild(row);
  // Primo row: nascondi il pulsante rimozione
  if (partN === 1) row.querySelector('.btn-range-remove').style.display = 'none';
}

function addRangeRow() {
  _addRangeRowTo('ranges-list', _rangeCounter++);
  _refreshRangeLabels('ranges-list');
}

function addPpRangeRow() {
  _addRangeRowTo('pp-ranges-list', _ppRangeCounter++);
  _refreshRangeLabels('pp-ranges-list');
}

function removeRangeRow(listId, rowId) {
  const row = document.getElementById(rowId);
  if (row) row.remove();
  _refreshRangeLabels(listId);
}

function _refreshRangeLabels(listId) {
  const rows = document.getElementById(listId).querySelectorAll('.range-row');
  rows.forEach((r, i) => {
    r.querySelector('.range-label').textContent = `Parte ${i + 1}:`;
    const rmBtn = r.querySelector('.btn-range-remove');
    if (rmBtn) rmBtn.style.display = rows.length === 1 ? 'none' : '';
  });
}

// ── Raccoglie opzioni di naming ────────────────────────────────────────────────

function _collectNaming(radioName, customInputId) {
  const val = document.querySelector(`input[name="${radioName}"]:checked`)?.value || 'x_of_y';
  if (val === 'x')      return { part_label: 'Parte', show_total: false };
  if (val === 'x_of_y') return { part_label: 'Parte', show_total: true };
  // custom
  const label = (document.getElementById(customInputId)?.value || '').trim();
  return { part_label: label || 'Parte', show_total: true };
}

function _collectRanges(listId) {
  const rows   = document.getElementById(listId).querySelectorAll('.range-row');
  const ranges = [];
  for (const row of rows) {
    const from = parseInt(row.querySelector('.range-from').value, 10);
    const to   = parseInt(row.querySelector('.range-to').value,   10);
    if (isNaN(from) || isNaN(to) || from < 1 || to < from) return null;
    ranges.push([from, to]);
  }
  return ranges.length > 0 ? ranges : null;
}

// ── Aggiorna visibilità opzioni in base all'op scelta ─────────────────────────

function updatePdfOpOptions() {
  const op = document.querySelector('input[name="pdfop"]:checked')?.value || 'compress';

  const showCompress   = op === 'compress' || op === 'compress+split';
  const showSplitSize  = op === 'split-size' || op === 'compress+split';
  const showSplitRange = op === 'split-ranges';

  _show('pdfopts-compress',    showCompress);
  _show('pdfopts-split-size',  showSplitSize);
  _show('pdfopts-split-ranges', showSplitRange);
}

function _show(id, visible) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('hidden', !visible);
}

// ── Selezione tramite dialog nativo ───────────────────────────────────────────

async function selectSource() {
  if (state.sourceIsTemp && state.sourcePath) {
    fetch('/api/cleanup-temp', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path: state.sourcePath}),
    }).catch(() => {});
    state.sourceIsTemp = false;
  }

  try {
    const res  = await fetch('/api/dialog/source', {method: 'POST'});
    const data = await res.json();
    if (data.path) {
      state.sourcePath   = data.path;
      state.folderName   = data.path.split(/[/\\]/).filter(Boolean).pop() || null;
      state.sourceIsTemp = false;
      exitPdfMode();
      showSourceInfo(data.path, data.file_count);
      updateStartButton();
    }
  } catch (e) { console.error(e); }
}

async function selectOutput() {
  try {
    const res  = await fetch('/api/dialog/output', {method: 'POST'});
    const data = await res.json();
    if (data.path) {
      state.outputPath = data.path;
      const el = document.getElementById('output-path-display');
      el.textContent = data.path;
      el.classList.add('selected');
      updateStartButton();
    }
  } catch (e) { console.error(e); }
}

function showSourceInfo(path, fileCount, displayName) {
  document.getElementById('drop-zone').classList.add('hidden');
  document.getElementById('source-info').classList.remove('hidden');
  document.getElementById('source-path-display').textContent = displayName || path;
  document.getElementById('source-count').textContent = `${fileCount} file supportati trovati`;
}

function updateStartButton() {
  const btn = document.getElementById('btn-start');
  if (state.isPdfMode) {
    btn.disabled = !state.outputPath;
  } else {
    btn.disabled = !(state.sourcePath && state.outputPath);
  }
}

// Attraversa ricorsivamente una FileSystemDirectoryEntry
async function traverseDir(dirEntry, result, basePath) {
  const reader  = dirEntry.createReader();
  const entries = await readAllEntries(reader);
  for (const entry of entries) {
    const relPath = basePath ? `${basePath}/${entry.name}` : entry.name;
    if (entry.isFile) result.push({fileEntry: entry, relPath});
    else if (entry.isDirectory) await traverseDir(entry, result, relPath);
  }
}

function readAllEntries(reader) {
  return new Promise((resolve, reject) => {
    const all = [];
    function readBatch() {
      reader.readEntries(entries => {
        if (entries.length === 0) resolve(all);
        else { all.push(...entries); readBatch(); }
      }, reject);
    }
    readBatch();
  });
}

function getFileFromEntry(fe) {
  return new Promise((resolve, reject) => fe.file(resolve, reject));
}

function setDropZoneStatus(msg) {
  document.getElementById('drop-title').classList.add('hidden');
  document.getElementById('drop-sub').classList.add('hidden');
  const el = document.getElementById('drop-status');
  el.textContent = msg;
  el.classList.remove('hidden');
}

function resetDropZoneStatus() {
  document.getElementById('drop-title').classList.remove('hidden');
  document.getElementById('drop-sub').classList.remove('hidden');
  const el = document.getElementById('drop-status');
  el.textContent = '';
  el.classList.add('hidden');
}

// ── Avvio job cartella (pipeline normale) ─────────────────────────────────────

async function startJob() {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const body = {
    source_path:   state.sourcePath,
    output_path:   state.outputPath,
    mode,
    source_is_temp: state.sourceIsTemp,
    folder_name:   state.folderName || null,
  };

  let res;
  try {
    res = await fetch('/api/start', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
  } catch (e) {
    alert('Impossibile avviare l\'elaborazione: ' + e.message);
    return;
  }

  const data = await res.json();
  if (!data.job_id) {
    alert('Errore: ' + (data.error || 'Risposta non valida dal server'));
    return;
  }

  state.jobId      = data.job_id;
  state.currentStep = 0;
  state.totalFiles  = 0;

  document.getElementById('setup-card').classList.add('hidden');
  document.getElementById('progress-card').classList.remove('hidden');
  document.getElementById('steps-indicator').classList.remove('hidden');
  document.getElementById('btn-cancel').style.display = '';
  connectSSE(data.job_id);
}

// ── Avvio operazione PDF diretta ──────────────────────────────────────────────

async function startPdfOp() {
  const op = document.querySelector('input[name="pdfop"]:checked')?.value;
  if (!op) { alert('Seleziona un\'operazione'); return; }

  const pdfPath   = state.pdfServerPath;
  const outputDir = state.outputPath;

  // Mostra progress card semplificata (senza step indicator)
  document.getElementById('setup-card').classList.add('hidden');
  document.getElementById('steps-indicator').classList.add('hidden');
  document.getElementById('progress-card').classList.remove('hidden');
  document.getElementById('btn-cancel').style.display = 'none';
  document.getElementById('progress-bar').style.width = '30%';
  document.getElementById('progress-step-label').textContent = 'Elaborazione in corso...';

  try {
    let result;

    // --- Comprimi (solo o come primo step) ---
    let workingPdf = pdfPath;
    if (op === 'compress' || op === 'compress+split') {
      const quality = document.querySelector('input[name="quality"]:checked')?.value || 'ebook';
      document.getElementById('progress-step-label').textContent = 'Compressione con Ghostscript...';
      document.getElementById('progress-bar').style.width = '40%';

      const res  = await fetch('/api/post/compress', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({pdf_path: pdfPath, quality, output_dir: outputDir}),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'Errore compressione');

      if (op === 'compress') {
        result = {type: 'compress', ...data};
      } else {
        workingPdf = data.output_path;
      }
    }

    // --- Dividi per dimensione ---
    if (op === 'split-size' || op === 'compress+split') {
      const mbVal  = document.querySelector('input[name="split-mb"]:checked')?.value || '50';
      const target = mbVal === 'custom'
        ? (parseFloat(document.getElementById('custom-mb').value) || 50)
        : parseFloat(mbVal);
      const naming = _collectNaming('naming-ss', 'custom-naming-ss');

      document.getElementById('progress-step-label').textContent = 'Divisione per dimensione...';
      document.getElementById('progress-bar').style.width = '70%';

      const res  = await fetch('/api/post/split-size', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({pdf_path: workingPdf, target_mb: target, output_dir: outputDir, ...naming}),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'Errore divisione');
      result = {type: 'split', ...data, compressData: (op === 'compress+split' ?
        {orig_mb: undefined, size_mb: undefined} : undefined)};
    }

    // --- Estrai testo ---
    if (op === 'extract-text') {
      document.getElementById('progress-step-label').textContent = 'Estrazione testo...';
      document.getElementById('progress-bar').style.width = '60%';

      const res  = await fetch('/api/post/extract-text', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({pdf_path: pdfPath, output_dir: outputDir}),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'Errore estrazione testo');
      result = {type: 'extract-text', ...data};
    }

    // --- Dividi per range ---
    if (op === 'split-ranges') {
      const ranges = _collectRanges('ranges-list');
      if (!ranges) { alert('Inserisci range validi (es. da:1 a:80)'); return; }
      const naming = _collectNaming('naming-sr', 'custom-naming-sr');

      document.getElementById('progress-step-label').textContent = 'Divisione per range...';
      document.getElementById('progress-bar').style.width = '70%';

      const res  = await fetch('/api/post/split-ranges', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({pdf_path: workingPdf, ranges, output_dir: outputDir, ...naming}),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'Errore divisione');
      result = {type: 'split-ranges', ...data};
    }

    document.getElementById('progress-bar').style.width = '100%';
    document.getElementById('progress-step-label').textContent = 'Completato';

    setTimeout(() => showPdfOpResult(result, op), 600);

  } catch (e) {
    document.getElementById('progress-step-label').textContent = 'Errore: ' + e.message;
    document.getElementById('progress-bar').style.width = '0%';
    setTimeout(() => {
      document.getElementById('progress-card').classList.add('hidden');
      document.getElementById('setup-card').classList.remove('hidden');
      document.getElementById('steps-indicator').classList.remove('hidden');
    }, 2000);
  }
}

function showPdfOpResult(result, op) {
  document.getElementById('progress-card').classList.add('hidden');
  document.getElementById('result-card').classList.remove('hidden');

  const container = document.getElementById('result-content');

  if (result.type === 'extract-text') {
    const pagesNote = result.pages_with_text < result.pages
      ? ` <span style="color:var(--warn);font-size:12px">(${result.pages - result.pages_with_text} pag. senza testo saltate)</span>`
      : '';
    container.innerHTML = `
      <div class="result-header">
        <div class="result-icon">📄</div>
        <div>
          <div class="result-title">Testo estratto con successo</div>
          <div class="result-subtitle">${result.filename}</div>
        </div>
      </div>
      <div class="result-stats">
        <div class="stat-box">
          <div class="stat-value">${result.size_kb} KB</div>
          <div class="stat-label">Dimensione .txt</div>
        </div>
        <div class="stat-box">
          <div class="stat-value">${result.chars.toLocaleString('it-IT')}</div>
          <div class="stat-label">Caratteri</div>
        </div>
        <div class="stat-box">
          <div class="stat-value">${result.pages_with_text}/${result.pages}</div>
          <div class="stat-label">Pagine con testo${pagesNote}</div>
        </div>
      </div>`;
    // Nessun post-processing per file di testo
    return;
  }

  if (result.type === 'compress') {
    const saved = result.orig_mb - result.size_mb;
    container.innerHTML = `
      <div class="result-header">
        <div class="result-icon">🗜</div>
        <div>
          <div class="result-title">PDF compresso con successo</div>
          <div class="result-subtitle">${result.filename}</div>
        </div>
      </div>
      <div class="result-stats">
        <div class="stat-box">
          <div class="stat-value">${result.orig_mb} MB</div>
          <div class="stat-label">Dimensione originale</div>
        </div>
        <div class="stat-box">
          <div class="stat-value">${result.size_mb} MB</div>
          <div class="stat-label">Dopo compressione</div>
        </div>
        <div class="stat-box">
          <div class="stat-value">−${result.reduction_pct}%</div>
          <div class="stat-label">Riduzione</div>
        </div>
      </div>`;

    // Offri di dividere il compresso
    state.resultPdfPath = result.output_path;
    document.getElementById('postproc-section').classList.remove('hidden');
    _setupPostProcBtns(['split-size', 'split-ranges']);

  } else {
    // split (per dimensione o per range)
    const parts  = result.parts || [];
    const label  = result.type === 'split-ranges' ? 'Divisione per range' : 'Divisione per dimensione';
    container.innerHTML = `
      <div class="result-header">
        <div class="result-icon">✂</div>
        <div>
          <div class="result-title">${label} completata</div>
          <div class="result-subtitle">Cartella: ${result.split_dir || state.outputPath}</div>
        </div>
      </div>
      <div class="result-stats">
        <div class="stat-box">
          <div class="stat-value">${parts.length}</div>
          <div class="stat-label">Parti create</div>
        </div>
        <div class="stat-box">
          <div class="stat-value">${Math.max(...parts.map(p => p.size_mb)).toFixed(1)} MB</div>
          <div class="stat-label">Parte più grande</div>
        </div>
        <div class="stat-box">
          <div class="stat-value">${parts.reduce((s,p)=>s+p.num_pages,0)}</div>
          <div class="stat-label">Pagine totali</div>
        </div>
      </div>
      <div>
        <div class="option-label" style="margin-bottom:8px">File creati</div>
        <div class="parts-list">
          ${parts.map((p,i) => `
            <div class="part-item">
              <div class="part-num">${i+1}</div>
              <div class="part-info">
                <div class="part-name">${p.name}</div>
                <div class="part-meta">${p.size_mb} MB · ${p.num_pages} pagine (${p.pages})</div>
              </div>
            </div>`).join('')}
        </div>
      </div>`;
  }
}

// ── Post-elaborazione inline nel risultato (dopo pipeline cartella) ─────────────

function _setupPostProcBtns(allowedOps) {
  const btns = document.querySelectorAll('#postproc-section .btn-postproc');
  const opMap = {'compress':'compress','split-size':'split-size','split-ranges':'split-ranges','compress+split':'compress+split'};
  btns.forEach(btn => {
    const op = btn.getAttribute('onclick').match(/'([^']+)'/)?.[1];
    btn.style.display = (!allowedOps || allowedOps.includes(op)) ? '' : 'none';
  });
}

function showPostProc(op) {
  state.postProcOp = op;
  const inline = document.getElementById('postproc-inline');
  inline.classList.remove('hidden');

  ['compress','split-size','split-ranges'].forEach(k => {
    _show(`ppopt-${k}`, false);
  });

  const showCompress   = op === 'compress' || op === 'compress+split';
  const showSplitSize  = op === 'split-size' || op === 'compress+split';
  const showSplitRange = op === 'split-ranges';

  _show('ppopt-compress',     showCompress);
  _show('ppopt-split-size',   showSplitSize);
  _show('ppopt-split-ranges', showSplitRange);

  // Aggiorna totale pagine se disponibile
  if (showSplitRange && state.resultPdfPath) {
    fetch('/api/post/page-count', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({pdf_path: state.resultPdfPath}),
    }).then(r => r.json()).then(d => {
      if (d.ok) document.getElementById('pp-range-total-label').textContent = `(totale: ${d.pages})`;
    }).catch(() => {});
    // Reset range list
    initRangeList('pp-ranges-list');
  }

  document.getElementById('postproc-result').classList.add('hidden');
  document.getElementById('btn-apply-postproc').disabled = false;
  document.getElementById('btn-apply-postproc').textContent = 'Applica';
}

async function applyPostProc() {
  const op = state.postProcOp;
  if (!op || !state.resultPdfPath || !state.outputPath) return;

  const btn = document.getElementById('btn-apply-postproc');
  btn.disabled = true;
  btn.textContent = 'Elaborazione...';

  const resultDiv = document.getElementById('postproc-result');
  resultDiv.classList.add('hidden');

  try {
    let workingPdf = state.resultPdfPath;
    let compressInfo = null;

    // Compressione
    if (op === 'compress' || op === 'compress+split') {
      const quality = document.querySelector('input[name="pp-quality"]:checked')?.value || 'ebook';
      const res  = await fetch('/api/post/compress', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({pdf_path: state.resultPdfPath, quality, output_dir: state.outputPath}),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error);
      compressInfo = data;
      workingPdf   = data.output_path;
    }

    // Split per dimensione
    if (op === 'split-size' || op === 'compress+split') {
      const mbVal  = document.querySelector('input[name="pp-split-mb"]:checked')?.value || '50';
      const target = mbVal === 'custom'
        ? (parseFloat(document.getElementById('pp-custom-mb').value) || 50)
        : parseFloat(mbVal);
      const naming = _collectNaming('pp-naming-ss', 'pp-custom-naming-ss');

      const res  = await fetch('/api/post/split-size', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({pdf_path: workingPdf, target_mb: target, output_dir: state.outputPath, ...naming}),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error);

      resultDiv.innerHTML = renderPostProcSplitResult(data.parts, compressInfo);
      resultDiv.classList.remove('hidden');
      btn.textContent = 'Applicato ✓';
      return;
    }

    // Split per range
    if (op === 'split-ranges') {
      const ranges = _collectRanges('pp-ranges-list');
      if (!ranges) { alert('Inserisci range validi'); btn.disabled = false; btn.textContent = 'Applica'; return; }
      const naming = _collectNaming('pp-naming-sr', 'pp-custom-naming-sr');

      const res  = await fetch('/api/post/split-ranges', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({pdf_path: workingPdf, ranges, output_dir: state.outputPath, ...naming}),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error);

      resultDiv.innerHTML = renderPostProcSplitResult(data.parts, compressInfo);
      resultDiv.classList.remove('hidden');
      btn.textContent = 'Applicato ✓';
      return;
    }

    // Solo compressione
    if (op === 'compress' && compressInfo) {
      resultDiv.innerHTML = `<div class="postproc-result-box">
        🗜 Compresso: <strong>${compressInfo.filename}</strong> —
        ${compressInfo.orig_mb} MB → <strong>${compressInfo.size_mb} MB</strong>
        (−${compressInfo.reduction_pct}%)
      </div>`;
      resultDiv.classList.remove('hidden');
      btn.textContent = 'Applicato ✓';
    }

  } catch (e) {
    resultDiv.innerHTML = `<div class="postproc-result-box error">Errore: ${e.message}</div>`;
    resultDiv.classList.remove('hidden');
    btn.disabled    = false;
    btn.textContent = 'Applica';
  }
}

function renderPostProcSplitResult(parts, compressInfo) {
  const compressNote = compressInfo
    ? `<div class="postproc-compress-note">
        🗜 Compresso prima: ${compressInfo.orig_mb} MB → ${compressInfo.size_mb} MB (−${compressInfo.reduction_pct}%)
       </div>` : '';
  return `${compressNote}
    <div class="option-label" style="margin-bottom:6px">Parti create (${parts.length})</div>
    <div class="parts-list" style="max-height:200px">
      ${parts.map((p,i) => `<div class="part-item">
        <div class="part-num">${i+1}</div>
        <div class="part-info">
          <div class="part-name">${p.name}</div>
          <div class="part-meta">${p.size_mb} MB · ${p.num_pages} pagine (${p.pages})</div>
        </div>
      </div>`).join('')}
    </div>`;
}

// ── SSE: aggiornamenti live ───────────────────────────────────────────────────

function connectSSE(jobId, cursor = 0) {
  if (state.eventSource) state.eventSource.close();
  const es = new EventSource(`/api/jobs/${jobId}/stream?cursor=${cursor}`);
  state.eventSource = es;

  es.onmessage = (e) => handleEvent(JSON.parse(e.data));
  es.onerror   = () => {
    es.close();
    setTimeout(() => {
      if (state.jobId === jobId) connectSSE(jobId, getCurrentCursor());
    }, 2000);
  };
}

let _lastCursor = 0;
function getCurrentCursor() { return _lastCursor; }

function handleEvent(event) {
  if (event.idx !== undefined) _lastCursor = event.idx + 1;

  switch (event.type) {
    case 'step':
      setActiveStep(event.step, event.label);
      document.getElementById('progress-step-label').textContent = event.label;
      break;
    case 'scan_done':
      state.totalFiles = event.total;
      break;
    case 'progress':
      updateProgress(event);
      break;
    case 'split_progress':
      document.getElementById('progress-step-label').textContent =
        `Divisione: ${event.label || ''} (parte ${event.current} di ${event.total})`;
      break;
    case 'folder_start':
      addLogEntry(`── Cartella ${event.current}/${event.total}: "${event.folder}" (${event.file_count} file)`, 'info');
      break;
    case 'log':
      addLogEntry(event.message, event.level || 'info', event.ts);
      break;
    case 'done':
      handleDone(event);
      break;
    case 'fatal_error':
      handleFatalError(event);
      break;
    case 'eos':
      if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }
      break;
    case 'heartbeat':
      break;
  }
}

function updateProgress(event) {
  const bar      = document.getElementById('progress-bar');
  const fileEl   = document.getElementById('progress-current-file');
  const countEl  = document.getElementById('progress-count');
  if (event.percent !== undefined) bar.style.width = event.percent + '%';
  if (event.file)   fileEl.textContent  = `${event.operation}: ${event.file.split(/[/\\]/).pop()}`;
  if (event.current && event.total) countEl.textContent = `${event.current} / ${event.total}`;
}

function setActiveStep(stepNum, label) {
  for (let i = 1; i <= 5; i++) {
    const el = document.getElementById(`step-${i}`);
    if (!el) continue;
    el.classList.remove('active', 'done');
    if (i < stepNum) {
      el.classList.add('done');
      const lines = document.querySelectorAll('.step-line');
      if (lines[i - 1]) lines[i - 1].classList.add('done');
    } else if (i === stepNum) el.classList.add('active');
  }
  state.currentStep = stepNum;
}

function addLogEntry(message, level = 'info', ts = null) {
  if (!message || !message.trim()) return;
  const panel = document.getElementById('log-panel');
  const entry = document.createElement('div');
  let displayLevel = level;
  if (message.startsWith('✓') || message.startsWith('✔')) displayLevel = 'success';
  entry.className = `log-entry ${mapLevel(displayLevel)}`;
  const tsEl  = document.createElement('span'); tsEl.className  = 'log-ts';  tsEl.textContent  = ts || now();
  const msgEl = document.createElement('span'); msgEl.className = 'log-msg'; msgEl.textContent = message;
  entry.appendChild(tsEl); entry.appendChild(msgEl);
  panel.appendChild(entry);
  panel.scrollTop = panel.scrollHeight;
}

function mapLevel(l) {
  return ({info:'info', warning:'warning', warn:'warning', error:'error', success:'success'})[l] || 'info';
}

function now() {
  return new Date().toLocaleTimeString('it-IT', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
}

function clearLog() { document.getElementById('log-panel').innerHTML = ''; }

// ── Elaborazione completata (pipeline cartella) ───────────────────────────────

function handleDone(event) {
  for (let i = 1; i <= 5; i++) {
    const el = document.getElementById(`step-${i}`);
    if (el) { el.classList.remove('active'); el.classList.add('done'); }
  }
  document.querySelectorAll('.step-line').forEach(l => l.classList.add('done'));
  document.getElementById('progress-bar').style.width = '100%';
  document.getElementById('progress-step-label').textContent = 'Completato';
  addLogEntry('Elaborazione completata con successo.', 'success');
  document.getElementById('btn-cancel').style.display = 'none';
  setTimeout(() => showResult(event), 800);
}

function showResult(event) {
  document.getElementById('progress-card').classList.add('hidden');
  document.getElementById('result-card').classList.remove('hidden');

  const container = document.getElementById('result-content');
  if (event.mode === 'unified') {
    container.innerHTML = renderUnifiedResult(event);
  } else {
    container.innerHTML = renderPerFolderResult(event);
  }

  // Offri post-elaborazione solo se il risultato è un singolo PDF
  if (event.mode === 'unified' && event.result_type === 'single' && event.file) {
    state.resultPdfPath = event.file;
    document.getElementById('postproc-section').classList.remove('hidden');
    _setupPostProcBtns(null);  // tutti i bottoni visibili
  } else {
    document.getElementById('postproc-section').classList.add('hidden');
  }

  attachLogToResult();
}

function renderUnifiedResult(event) {
  const isSplit = event.result_type === 'split';
  const errors  = event.errors || [];
  let html = `
    <div class="result-header">
      <div class="result-icon">${isSplit ? '✂' : '✓'}</div>
      <div>
        <div class="result-title">${isSplit ? 'PDF creato e suddiviso' : 'PDF creato con successo'}</div>
        <div class="result-subtitle">Cartella di output: ${event.output_path}</div>
      </div>
    </div>
    <div class="result-stats">
      <div class="stat-box"><div class="stat-value">${event.size_mb} MB</div><div class="stat-label">Dimensione totale</div></div>
      <div class="stat-box"><div class="stat-value">${event.total_pages || '—'}</div><div class="stat-label">Pagine totali</div></div>
      <div class="stat-box"><div class="stat-value">${isSplit ? event.total_parts : 1}</div><div class="stat-label">${isSplit ? 'Parti create' : 'File creato'}</div></div>
    </div>`;
  if (isSplit && event.parts?.length > 0) {
    html += `<div>
      <div class="option-label" style="margin-bottom:8px">File creati</div>
      <div class="parts-list">
        ${event.parts.map((p,i) => `<div class="part-item">
          <div class="part-num">${i+1}</div>
          <div class="part-info">
            <div class="part-name">${p.name}</div>
            <div class="part-meta">${p.size_mb} MB · ${p.num_pages} pagine (${p.pages})</div>
          </div>
        </div>`).join('')}
      </div></div>`;
  }
  if (errors.length > 0) html += renderErrors(errors);
  return html;
}

function renderPerFolderResult(event) {
  const results    = event.results || [];
  const errors     = event.errors  || [];
  const totalParts = results.reduce((s,r) => s + (r.result_type === 'split' ? r.total_parts : 1), 0);
  let html = `
    <div class="result-header">
      <div class="result-icon">✓</div>
      <div>
        <div class="result-title">${results.length} PDF creati</div>
        <div class="result-subtitle">Cartella di output: ${event.output_path}</div>
      </div>
    </div>
    <div class="result-stats">
      <div class="stat-box"><div class="stat-value">${results.length}</div><div class="stat-label">Sottocartelle</div></div>
      <div class="stat-box"><div class="stat-value">${totalParts}</div><div class="stat-label">File PDF totali</div></div>
      <div class="stat-box"><div class="stat-value">${errors.length}</div><div class="stat-label">File saltati</div></div>
    </div>`;
  if (results.length > 0) {
    html += `<div>
      <div class="option-label" style="margin-bottom:8px">Riepilogo per cartella</div>
      <div class="parts-list">
        ${results.map((r,i) => `<div class="part-item">
          <div class="part-num">${i+1}</div>
          <div class="part-info">
            <div class="part-name">${r.folder}</div>
            <div class="part-meta">${r.size_mb} MB · ${r.total_pages||'—'} pagine${r.result_type==='split'?' · '+r.total_parts+' parti':''}</div>
          </div>
        </div>`).join('')}
      </div></div>`;
  }
  if (errors.length > 0) html += renderErrors(errors);
  return html;
}

function renderErrors(errors) {
  return `<div class="error-box">
    <div class="error-box-title">File non elaborati (${errors.length})</div>
    <div class="error-list">
      ${errors.slice(0,20).map(e => `<div>• ${e.file}: ${e.error}</div>`).join('')}
      ${errors.length > 20 ? `<div>... e altri ${errors.length-20} file</div>` : ''}
    </div></div>`;
}

function attachLogToResult() {
  const logPanel  = document.getElementById('log-panel');
  const section   = document.getElementById('result-log-section');
  if (!section || !logPanel) return;
  const errorCount = logPanel.querySelectorAll('.log-entry.error').length;
  const warnCount  = logPanel.querySelectorAll('.log-entry.warning').length;
  const issueCount = errorCount + warnCount;
  const totalCount = logPanel.querySelectorAll('.log-entry').length;
  if (totalCount === 0) return;

  const logClone = logPanel.cloneNode(true);
  logClone.removeAttribute('id');
  logClone.classList.add('hidden', 'result-log-panel');

  let badgeClass = 'result-log-badge';
  let badgeContent;
  if (issueCount > 0) {
    badgeClass  += ' result-log-badge--warn';
    const label  = issueCount === 1 ? 'segnalazione' : 'segnalazioni';
    badgeContent = `<span>⚠ ${issueCount} ${label} durante l'elaborazione</span><button class="btn-log-show">Mostra log</button>`;
  } else {
    badgeContent = `<span>Elaborazione completata senza avvisi</span><button class="btn-log-show">Mostra log</button>`;
  }

  section.innerHTML = `<div class="${badgeClass}">${badgeContent}</div>`;
  section.appendChild(logClone);

  const badge = section.querySelector('.result-log-badge');
  section.querySelector('.btn-log-show').addEventListener('click', () => {
    const hidden = logClone.classList.toggle('hidden');
    section.querySelector('.btn-log-show').textContent = hidden ? 'Mostra log' : 'Nascondi log';
    badge.style.borderRadius = hidden ? '8px' : '8px 8px 0 0';
    if (!hidden) logClone.scrollTop = logClone.scrollHeight;
  });
}

function handleFatalError(event) {
  addLogEntry(`ERRORE CRITICO: ${event.message}`, 'error');
  document.getElementById('progress-step-label').textContent = 'Errore';
  document.getElementById('btn-cancel').style.display = 'none';
  document.getElementById('result-content').innerHTML = `
    <div class="result-header">
      <div class="result-icon" style="background:#FEF0EF;color:#C0392B">✕</div>
      <div>
        <div class="result-title">Errore durante l'elaborazione</div>
        <div class="result-subtitle">${event.message}</div>
      </div>
    </div>
    ${event.detail ? `<pre style="font-size:11px;color:#666;overflow:auto;max-height:200px;background:#F8F8F8;padding:12px;border-radius:8px">${event.detail}</pre>` : ''}`;
  setTimeout(() => {
    document.getElementById('progress-card').classList.add('hidden');
    document.getElementById('result-card').classList.remove('hidden');
  }, 1000);
}

async function cancelJob() {
  if (!state.jobId) return;
  if (!confirm('Vuoi annullare l\'elaborazione in corso?')) return;
  try { await fetch(`/api/jobs/${state.jobId}/cancel`, {method: 'POST'}); } catch (e) {}
  addLogEntry('Annullamento richiesto...', 'warning');
}

// ── Reset ─────────────────────────────────────────────────────────────────────

function resetApp() {
  if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }

  if (state.sourceIsTemp && state.sourcePath && !state.jobId) {
    fetch('/api/cleanup-temp', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path: state.sourcePath}),
    }).catch(() => {});
  }

  Object.assign(state, {
    sourcePath: null, folderName: null, outputPath: null, jobId: null,
    eventSource: null, currentStep: 0, totalFiles: 0, sourceIsTemp: false,
    uploading: false, isPdfMode: false, pdfServerPath: null, pdfPages: null,
    resultPdfPath: null, postProcOp: null,
  });
  _lastCursor = 0;

  resetDropZoneStatus();

  document.getElementById('drop-zone').classList.remove('hidden');
  document.getElementById('source-info').classList.add('hidden');
  document.getElementById('source-icon').textContent = '📁';
  document.getElementById('output-path-display').textContent = 'Nessuna cartella selezionata';
  document.getElementById('output-path-display').classList.remove('selected');
  document.getElementById('progress-bar').style.width = '0%';
  document.getElementById('progress-current-file').textContent = '';
  document.getElementById('progress-count').textContent = '';
  document.getElementById('progress-step-label').textContent = 'Elaborazione in corso...';
  document.getElementById('log-panel').innerHTML = '';
  document.getElementById('result-log-section').innerHTML = '';
  document.getElementById('btn-cancel').style.display = '';
  document.getElementById('steps-indicator').classList.remove('hidden');
  document.getElementById('postproc-section').classList.add('hidden');
  document.getElementById('postproc-inline').classList.add('hidden');
  document.getElementById('postproc-result').classList.add('hidden');

  exitPdfMode();

  for (let i = 1; i <= 5; i++) {
    const el = document.getElementById(`step-${i}`);
    if (el) el.classList.remove('active', 'done');
  }
  document.querySelectorAll('.step-line').forEach(l => l.classList.remove('done'));

  document.getElementById('result-card').classList.add('hidden');
  document.getElementById('progress-card').classList.add('hidden');
  document.getElementById('setup-card').classList.remove('hidden');
  document.getElementById('mode-unified').checked = true;

  initRangeList('ranges-list');
  initRangeList('pp-ranges-list');
  updateStartButton();
}
