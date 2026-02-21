/* ──────────────────────────────────────────────────────────────
   Split PDF 50 — Frontend JS
   Gestisce: selezione cartelle, avvio job, SSE live log, risultati
────────────────────────────────────────────────────────────── */

'use strict';

// ── Stato globale ─────────────────────────────────────────────────────────────
const state = {
  sourcePath: null,
  folderName: null,      // nome originale della cartella (usato per nominare il PDF)
  outputPath: null,
  jobId: null,
  eventSource: null,
  currentStep: 0,
  totalFiles: 0,
  sourceIsTemp: false,   // true se la sorgente è una cartella uploadata via drag-drop
  uploading: false,      // true durante l'upload di una cartella trascinata
};

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initDropZone();
  loadSystemInfo();
  updateStartButton();
});

// ── Info sistema ──────────────────────────────────────────────────────────────
async function loadSystemInfo() {
  try {
    const res = await fetch('/api/system-info');
    const info = await res.json();
    renderDepsWarning(info);
  } catch (e) {
    // silenzioso
  }
}

function renderDepsWarning(info) {
  const isMac = info.platform === 'darwin';
  const required = [];   // blocca il funzionamento
  const optional = [];   // migliora la qualità

  // ── CONVERSIONE OFFICE (DOCX / XLSX / PPTX) ──────────────────────────────
  // OK se: Microsoft Office installato OPPURE LibreOffice installato
  // (docx2pdf usa Office COM, LibreOffice è il fallback)
  if (!info.can_convert_office) {
    required.push({
      name: 'Conversione documenti Office',
      desc: 'Serve Microsoft Office (già installato) oppure LibreOffice per convertire DOCX, XLSX, PPTX in PDF.',
      items: [
        {
          label: 'Microsoft Office',
          url: 'https://www.microsoft.com/it-it/microsoft-365',
          urlLabel: 'Info Microsoft 365',
          brew: null,
        },
        {
          label: 'oppure LibreOffice (gratuito)',
          url: 'https://www.libreoffice.org/download/',
          urlLabel: 'Scarica LibreOffice',
          brew: isMac ? 'brew install libreoffice' : null,
        },
      ],
    });
  } else if (!info.libreoffice && info.ms_office) {
    // Office trovato, LibreOffice no → tutto OK per formati Office standard
    // Ma ODT/ODS/ODP nativi di LibreOffice avranno qualità ridotta
    optional.push({
      name: 'LibreOffice (opzionale)',
      desc: 'Senza LibreOffice, i file ODT/ODS/ODP potrebbero non essere convertiti correttamente. Per DOCX/XLSX/PPTX Microsoft Office è già sufficiente.',
      url: 'https://www.libreoffice.org/download/',
      urlLabel: 'Scarica LibreOffice',
      brew: isMac ? 'brew install libreoffice' : null,
    });
  }

  // ── OCR ITALIANO ──────────────────────────────────────────────────────────
  if (!info.tesseract_italian) {
    required.push({
      name: 'Tesseract + Lingua Italiana',
      desc: 'Necessario per applicare l\'OCR e rendere i PDF ricercabili in italiano.',
      items: [
        {
          label: isMac ? 'Installa via Homebrew' : 'Scarica Tesseract',
          url: isMac
            ? 'https://formulae.brew.sh/formula/tesseract-lang'
            : 'https://github.com/UB-Mannheim/tesseract/wiki',
          urlLabel: isMac ? 'Homebrew' : 'Scarica',
          brew: isMac ? 'brew install tesseract tesseract-lang' : null,
          note: !isMac ? 'Durante l\'installazione spunta: Additional language data → Italian' : null,
        },
      ],
    });
  }

  // ── GHOSTSCRIPT ───────────────────────────────────────────────────────────
  if (!info.ghostscript) {
    required.push({
      name: 'Ghostscript',
      desc: 'Richiesto da ocrmypdf per ottimizzare i PDF dopo l\'OCR.',
      items: [
        {
          label: 'Scarica Ghostscript',
          url: isMac
            ? 'https://formulae.brew.sh/formula/ghostscript'
            : 'https://www.ghostscript.com/releases/',
          urlLabel: 'Scarica',
          brew: isMac ? 'brew install ghostscript' : null,
        },
      ],
    });
  }

  const banner = document.getElementById('deps-warning');
  if (!banner) return;

  // Se tutto OK: banner nascosto
  if (required.length === 0 && optional.length === 0) {
    banner.classList.add('hidden');
    return;
  }

  // ── Rendering banner ──────────────────────────────────────────────────────
  function renderItem(item) {
    return `
      <div style="display:flex;align-items:center;gap:8px;margin-top:6px">
        ${item.brew
          ? `<span class="btn-brew" onclick="copyBrew('${item.brew}')" title="Copia comando Homebrew">${item.brew}</span>`
          : ''}
        <a class="btn-download" href="${item.url}" target="_blank" rel="noopener">
          ↓ ${item.urlLabel}
        </a>
        ${item.note ? `<span style="font-size:11px;color:#9A7020"><em>${item.note}</em></span>` : ''}
      </div>`;
  }

  function renderGroup(dep, isRequired) {
    const dismissBtn = !isRequired
      ? `<button class="dep-dismiss" onclick="this.closest('.dep-item').remove(); _checkOptionalSectionEmpty();" title="Chiudi">×</button>`
      : '';
    return `
      <div class="dep-item${isRequired ? '' : ' dep-item-optional'}">
        ${dismissBtn}
        <div class="dep-item-text">
          <div class="dep-name">${isRequired ? '' : '<span class="dep-badge-opt">opzionale</span> '}${dep.name}</div>
          <div class="dep-desc">${dep.desc}</div>
          ${dep.items
            ? dep.items.map(renderItem).join('')
            : renderItem(dep)}
        </div>
      </div>`;
  }

  banner.innerHTML = `
    ${required.length > 0 ? `
      <div class="deps-warning-title">
        Dipendenze mancanti — alcune funzioni non saranno disponibili
      </div>
      <div class="deps-list">
        ${required.map(d => renderGroup(d, true)).join('')}
      </div>
    ` : ''}
    ${optional.length > 0 ? `
      <div class="deps-warning-title" style="color:#5A6E65;font-size:12px;margin-top:${required.length > 0 ? '12px' : '0'}">
        Facoltativo — migliora la qualità di conversione
      </div>
      <div class="deps-list">
        ${optional.map(d => renderGroup(d, false)).join('')}
      </div>
    ` : ''}
    <div class="deps-warning-footer">
      Dopo l'installazione, riavvia l'app per aggiornare questo avviso.
    </div>
  `;

  banner.classList.remove('hidden');
}

function _checkOptionalSectionEmpty() {
  // Se non rimangono item opzionali, nasconde l'intero banner (se non ci sono nemmeno required)
  const banner = document.getElementById('deps-warning');
  if (!banner) return;
  const remaining = banner.querySelectorAll('.dep-item');
  if (remaining.length === 0) {
    banner.classList.add('hidden');
  }
}

function copyBrew(cmd) {
  navigator.clipboard.writeText(cmd).then(() => {
    // Feedback visivo temporaneo
    const els = document.querySelectorAll('.btn-brew');
    els.forEach(el => {
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

    const firstItem = items[0];
    const entry = firstItem.webkitGetAsEntry ? firstItem.webkitGetAsEntry() : null;

    if (!entry || !entry.isDirectory) {
      // Nessuna cartella rilevata → apri il dialog nativo come fallback
      await selectSource();
      return;
    }

    await handleDroppedFolder(entry);
  });
}

// ── Gestione cartella trascinata ───────────────────────────────────────────────

async function handleDroppedFolder(dirEntry) {
  state.uploading = true;
  setDropZoneStatus(`Raccogliendo file da "${dirEntry.name}"...`);

  try {
    // 1. Traversa l'albero directory e raccoglie tutti i file
    const fileEntries = [];
    await traverseDir(dirEntry, fileEntries, '');

    if (fileEntries.length === 0) {
      setDropZoneStatus('Nessun file trovato nella cartella.');
      setTimeout(resetDropZoneStatus, 2500);
      return;
    }

    // 2. Converti FileSystemFileEntry → File (con progresso)
    const formData = new FormData();
    formData.append('folder_name', dirEntry.name);

    for (let i = 0; i < fileEntries.length; i++) {
      setDropZoneStatus(`Preparazione ${i + 1} / ${fileEntries.length} file...`);
      const { fileEntry, relPath } = fileEntries[i];
      const file = await getFileFromEntry(fileEntry);
      formData.append('files', file, relPath);
    }

    // 3. Invia al server
    setDropZoneStatus(`Invio al server (${fileEntries.length} file)...`);
    const res = await fetch('/api/upload-folder', { method: 'POST', body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${res.status}`);
    }

    const data = await res.json();

    // 4. Successo → mostra info sorgente
    state.sourcePath = data.path;
    state.folderName = data.folder_name || dirEntry.name;
    state.sourceIsTemp = true;
    showSourceInfo(data.path, data.file_count, state.folderName);
    updateStartButton();

  } catch (err) {
    setDropZoneStatus(`Errore: ${err.message}`);
    setTimeout(resetDropZoneStatus, 3000);
  } finally {
    state.uploading = false;
  }
}

// Attraversa ricorsivamente una FileSystemDirectoryEntry
async function traverseDir(dirEntry, result, basePath) {
  const reader = dirEntry.createReader();
  const entries = await readAllEntries(reader);
  for (const entry of entries) {
    const relPath = basePath ? `${basePath}/${entry.name}` : entry.name;
    if (entry.isFile) {
      result.push({ fileEntry: entry, relPath });
    } else if (entry.isDirectory) {
      await traverseDir(entry, result, relPath);
    }
  }
}

// Legge TUTTI gli entry da un DirectoryReader (gestisce il limite di 100)
function readAllEntries(reader) {
  return new Promise((resolve, reject) => {
    const all = [];
    function readBatch() {
      reader.readEntries((entries) => {
        if (entries.length === 0) {
          resolve(all);
        } else {
          all.push(...entries);
          readBatch();
        }
      }, reject);
    }
    readBatch();
  });
}

// Converte un FileSystemFileEntry in un oggetto File
function getFileFromEntry(fileEntry) {
  return new Promise((resolve, reject) => fileEntry.file(resolve, reject));
}

// Mostra un messaggio di stato nella drop zone (nasconde il testo normale)
function setDropZoneStatus(msg) {
  document.getElementById('drop-title').classList.add('hidden');
  document.getElementById('drop-sub').classList.add('hidden');
  const el = document.getElementById('drop-status');
  el.textContent = msg;
  el.classList.remove('hidden');
}

// Ripristina l'aspetto normale della drop zone
function resetDropZoneStatus() {
  document.getElementById('drop-title').classList.remove('hidden');
  document.getElementById('drop-sub').classList.remove('hidden');
  const el = document.getElementById('drop-status');
  el.textContent = '';
  el.classList.add('hidden');
}

// ── Selezione cartelle ────────────────────────────────────────────────────────
async function selectSource() {
  // Se si stava usando una cartella uploadata, puliscila sul server
  if (state.sourceIsTemp && state.sourcePath) {
    fetch('/api/cleanup-temp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: state.sourcePath }),
    }).catch(() => {});
    state.sourceIsTemp = false;
  }

  try {
    const res = await fetch('/api/dialog/source', { method: 'POST' });
    const data = await res.json();

    if (data.path) {
      state.sourcePath = data.path;
      state.folderName = data.path.split(/[/\\]/).filter(Boolean).pop() || null;
      state.sourceIsTemp = false;
      showSourceInfo(data.path, data.file_count);
      updateStartButton();
    }
  } catch (e) {
    console.error('Errore selezione sorgente:', e);
  }
}

async function selectOutput() {
  try {
    const res = await fetch('/api/dialog/output', { method: 'POST' });
    const data = await res.json();

    if (data.path) {
      state.outputPath = data.path;
      const display = document.getElementById('output-path-display');
      display.textContent = data.path;
      display.classList.add('selected');
      updateStartButton();
    }
  } catch (e) {
    console.error('Errore selezione output:', e);
  }
}

function showSourceInfo(path, fileCount, displayName) {
  const dropZone = document.getElementById('drop-zone');
  const sourceInfo = document.getElementById('source-info');

  dropZone.classList.add('hidden');
  sourceInfo.classList.remove('hidden');

  document.getElementById('source-path-display').textContent = displayName || path;
  document.getElementById('source-count').textContent =
    `${fileCount} file supportati trovati`;
}

function updateStartButton() {
  const btn = document.getElementById('btn-start');
  btn.disabled = !(state.sourcePath && state.outputPath);
}

// ── Avvio job ─────────────────────────────────────────────────────────────────
async function startJob() {
  const mode = document.querySelector('input[name="mode"]:checked').value;

  const body = {
    source_path: state.sourcePath,
    output_path: state.outputPath,
    mode: mode,
    source_is_temp: state.sourceIsTemp,
    folder_name: state.folderName || null,
  };

  let res;
  try {
    res = await fetch('/api/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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

  state.jobId = data.job_id;
  state.currentStep = 0;
  state.totalFiles = 0;

  // Mostra la card progresso
  document.getElementById('setup-card').classList.add('hidden');
  document.getElementById('progress-card').classList.remove('hidden');

  // Connetti SSE
  connectSSE(data.job_id);
}

// ── SSE: aggiornamenti live ───────────────────────────────────────────────────
function connectSSE(jobId, cursor = 0) {
  if (state.eventSource) {
    state.eventSource.close();
  }

  const es = new EventSource(`/api/jobs/${jobId}/stream?cursor=${cursor}`);
  state.eventSource = es;

  es.onmessage = (e) => {
    const event = JSON.parse(e.data);
    handleEvent(event);
  };

  es.onerror = () => {
    // Tentativo di riconnessione automatica
    es.close();
    setTimeout(() => {
      if (state.jobId === jobId) {
        const lastIdx = getCurrentCursor();
        connectSSE(jobId, lastIdx);
      }
    }, 2000);
  };
}

let _lastCursor = 0;

function getCurrentCursor() {
  return _lastCursor;
}

function handleEvent(event) {
  if (event.idx !== undefined) {
    _lastCursor = event.idx + 1;
  }

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
      addLogEntry(
        `── Cartella ${event.current}/${event.total}: "${event.folder}" (${event.file_count} file)`,
        'info'
      );
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
      if (state.eventSource) {
        state.eventSource.close();
        state.eventSource = null;
      }
      break;

    case 'heartbeat':
      break;
  }
}

// ── Aggiornamento UI progresso ────────────────────────────────────────────────
function updateProgress(event) {
  const bar = document.getElementById('progress-bar');
  const fileEl = document.getElementById('progress-current-file');
  const countEl = document.getElementById('progress-count');

  if (event.percent !== undefined) {
    bar.style.width = event.percent + '%';
  }

  if (event.file) {
    // Mostra solo il nome file (non il percorso intero)
    const fileName = event.file.split(/[/\\]/).pop();
    fileEl.textContent = `${event.operation}: ${fileName}`;
  }

  if (event.current && event.total) {
    countEl.textContent = `${event.current} / ${event.total}`;
  }
}

function setActiveStep(stepNum, label) {
  // Aggiorna gli indicatori di step (1-5)
  for (let i = 1; i <= 5; i++) {
    const el = document.getElementById(`step-${i}`);
    if (!el) continue;

    el.classList.remove('active', 'done');

    if (i < stepNum) {
      el.classList.add('done');
      // Aggiorna anche la linea tra gli step
      const lines = document.querySelectorAll('.step-line');
      if (lines[i - 1]) lines[i - 1].classList.add('done');
    } else if (i === stepNum) {
      el.classList.add('active');
    }
  }

  state.currentStep = stepNum;
}

// ── Log live ──────────────────────────────────────────────────────────────────
function addLogEntry(message, level = 'info', ts = null) {
  if (!message || !message.trim()) return;

  const panel = document.getElementById('log-panel');
  const entry = document.createElement('div');
  entry.className = `log-entry ${mapLevel(level)}`;

  // Mappa caratteri speciali in classi visive
  let displayLevel = level;
  if (message.startsWith('✓') || message.startsWith('✔')) displayLevel = 'success';

  entry.className = `log-entry ${mapLevel(displayLevel)}`;

  const tsEl = document.createElement('span');
  tsEl.className = 'log-ts';
  tsEl.textContent = ts || now();

  const msgEl = document.createElement('span');
  msgEl.className = 'log-msg';
  msgEl.textContent = message;

  entry.appendChild(tsEl);
  entry.appendChild(msgEl);
  panel.appendChild(entry);

  // Auto-scroll verso il basso
  panel.scrollTop = panel.scrollHeight;
}

function mapLevel(level) {
  const map = { info: 'info', warning: 'warning', warn: 'warning',
                error: 'error', success: 'success' };
  return map[level] || 'info';
}

function now() {
  return new Date().toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function clearLog() {
  document.getElementById('log-panel').innerHTML = '';
}

// ── Elaborazione completata ───────────────────────────────────────────────────
function handleDone(event) {
  // Marca tutti gli step come completati
  for (let i = 1; i <= 5; i++) {
    const el = document.getElementById(`step-${i}`);
    if (el) el.classList.remove('active'), el.classList.add('done');
  }
  document.querySelectorAll('.step-line').forEach(l => l.classList.add('done'));
  document.getElementById('progress-bar').style.width = '100%';
  document.getElementById('progress-step-label').textContent = 'Completato';

  addLogEntry('Elaborazione completata con successo.', 'success');

  // Nascondi il pulsante Annulla
  document.getElementById('btn-cancel').style.display = 'none';

  // Mostra la card risultati dopo un breve ritardo
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

  attachLogToResult();
}

// Clona il log panel nella result card con badge di avviso se ci sono errori
function attachLogToResult() {
  const logPanel = document.getElementById('log-panel');
  const section  = document.getElementById('result-log-section');
  if (!section || !logPanel) return;

  const errorCount = logPanel.querySelectorAll('.log-entry.error').length;
  const warnCount  = logPanel.querySelectorAll('.log-entry.warning').length;
  const issueCount = errorCount + warnCount;
  const totalCount = logPanel.querySelectorAll('.log-entry').length;

  if (totalCount === 0) return;

  // Clone del log (l'originale rimane nel progress-card per il reset)
  const logClone = logPanel.cloneNode(true);
  logClone.removeAttribute('id');
  logClone.classList.add('hidden', 'result-log-panel');

  let badgeClass   = 'result-log-badge';
  let badgeContent;

  if (issueCount > 0) {
    badgeClass  += ' result-log-badge--warn';
    const label  = issueCount === 1 ? 'segnalazione' : 'segnalazioni';
    badgeContent = `<span>⚠ ${issueCount} ${label} durante l'elaborazione</span>
                    <button class="btn-log-show">Mostra log</button>`;
  } else {
    badgeContent = `<span>Elaborazione completata senza avvisi</span>
                    <button class="btn-log-show">Mostra log</button>`;
  }

  section.innerHTML = `<div class="${badgeClass}">${badgeContent}</div>`;
  section.appendChild(logClone);

  const badge = section.querySelector('.result-log-badge');
  section.querySelector('.btn-log-show').addEventListener('click', () => {
    const hidden = logClone.classList.toggle('hidden');
    section.querySelector('.btn-log-show').textContent =
      hidden ? 'Mostra log' : 'Nascondi log';
    badge.style.borderRadius = hidden ? '8px' : '8px 8px 0 0';
    if (!hidden) logClone.scrollTop = logClone.scrollHeight;
  });
}

function renderUnifiedResult(event) {
  const isSplit = event.result_type === 'split';
  const errors = event.errors || [];

  let html = `
    <div class="result-header">
      <div class="result-icon">${isSplit ? '✂' : '✓'}</div>
      <div>
        <div class="result-title">${isSplit ? 'PDF creato e suddiviso' : 'PDF creato con successo'}</div>
        <div class="result-subtitle">Cartella di output: ${event.output_path}</div>
      </div>
    </div>

    <div class="result-stats">
      <div class="stat-box">
        <div class="stat-value">${event.size_mb} MB</div>
        <div class="stat-label">Dimensione totale</div>
      </div>
      <div class="stat-box">
        <div class="stat-value">${event.total_pages || '—'}</div>
        <div class="stat-label">Pagine totali</div>
      </div>
      <div class="stat-box">
        <div class="stat-value">${isSplit ? event.total_parts : 1}</div>
        <div class="stat-label">${isSplit ? 'Parti create' : 'File creato'}</div>
      </div>
    </div>
  `;

  if (isSplit && event.parts && event.parts.length > 0) {
    html += `
      <div>
        <div class="option-label" style="margin-bottom:8px">File creati nella cartella "${event.output_path}"</div>
        <div class="parts-list">
          ${event.parts.map((p, i) => `
            <div class="part-item">
              <div class="part-num">${i + 1}</div>
              <div class="part-info">
                <div class="part-name">${p.name}</div>
                <div class="part-meta">${p.size_mb} MB · ${p.num_pages} pagine (${p.pages})</div>
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  if (errors.length > 0) {
    html += renderErrors(errors);
  }

  return html;
}

function renderPerFolderResult(event) {
  const results = event.results || [];
  const errors = event.errors || [];
  const totalParts = results.reduce((s, r) => s + (r.result_type === 'split' ? r.total_parts : 1), 0);

  let html = `
    <div class="result-header">
      <div class="result-icon">✓</div>
      <div>
        <div class="result-title">${results.length} PDF creati</div>
        <div class="result-subtitle">Cartella di output: ${event.output_path}</div>
      </div>
    </div>

    <div class="result-stats">
      <div class="stat-box">
        <div class="stat-value">${results.length}</div>
        <div class="stat-label">Sottocartelle</div>
      </div>
      <div class="stat-box">
        <div class="stat-value">${totalParts}</div>
        <div class="stat-label">File PDF totali</div>
      </div>
      <div class="stat-box">
        <div class="stat-value">${errors.length}</div>
        <div class="stat-label">File saltati</div>
      </div>
    </div>
  `;

  if (results.length > 0) {
    html += `
      <div>
        <div class="option-label" style="margin-bottom:8px">Riepilogo per cartella</div>
        <div class="parts-list">
          ${results.map((r, i) => `
            <div class="part-item">
              <div class="part-num">${i + 1}</div>
              <div class="part-info">
                <div class="part-name">${r.folder}</div>
                <div class="part-meta">
                  ${r.size_mb} MB · ${r.total_pages || '—'} pagine
                  ${r.result_type === 'split' ? ` · ${r.total_parts} parti` : ''}
                </div>
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  if (errors.length > 0) {
    html += renderErrors(errors);
  }

  return html;
}

function renderErrors(errors) {
  return `
    <div class="error-box">
      <div class="error-box-title">File non elaborati (${errors.length})</div>
      <div class="error-list">
        ${errors.slice(0, 20).map(e => `<div>• ${e.file}: ${e.error}</div>`).join('')}
        ${errors.length > 20 ? `<div>... e altri ${errors.length - 20} file</div>` : ''}
      </div>
    </div>
  `;
}

// ── Errore fatale ─────────────────────────────────────────────────────────────
function handleFatalError(event) {
  addLogEntry(`ERRORE CRITICO: ${event.message}`, 'error');

  document.getElementById('progress-step-label').textContent = 'Errore';
  document.getElementById('btn-cancel').style.display = 'none';

  const container = document.getElementById('result-content');
  container.innerHTML = `
    <div class="result-header">
      <div class="result-icon" style="background:#FEF0EF;color:#C0392B">✕</div>
      <div>
        <div class="result-title">Errore durante l'elaborazione</div>
        <div class="result-subtitle">${event.message}</div>
      </div>
    </div>
    ${event.detail ? `<pre style="font-size:11px;color:#666;overflow:auto;max-height:200px;background:#F8F8F8;padding:12px;border-radius:8px">${event.detail}</pre>` : ''}
  `;

  setTimeout(() => {
    document.getElementById('progress-card').classList.add('hidden');
    document.getElementById('result-card').classList.remove('hidden');
  }, 1000);
}

// ── Annulla job ───────────────────────────────────────────────────────────────
async function cancelJob() {
  if (!state.jobId) return;
  if (!confirm('Vuoi annullare l\'elaborazione in corso?')) return;

  try {
    await fetch(`/api/jobs/${state.jobId}/cancel`, { method: 'POST' });
    addLogEntry('Annullamento richiesto...', 'warning');
  } catch (e) {
    console.error(e);
  }
}

// ── Reset ─────────────────────────────────────────────────────────────────────
function resetApp() {
  // Chiudi SSE se aperto
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }

  // Se la sorgente era una cartella uploadata e non è stato avviato alcun job
  // (il job la pulisce da solo nel suo finally), puliscila ora
  if (state.sourceIsTemp && state.sourcePath && !state.jobId) {
    fetch('/api/cleanup-temp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: state.sourcePath }),
    }).catch(() => {});
  }

  // Reset stato
  state.sourcePath = null;
  state.folderName = null;
  state.outputPath = null;
  state.jobId = null;
  state.currentStep = 0;
  state.totalFiles = 0;
  state.sourceIsTemp = false;
  state.uploading = false;
  _lastCursor = 0;

  resetDropZoneStatus();

  // Reset UI
  document.getElementById('drop-zone').classList.remove('hidden');
  document.getElementById('source-info').classList.add('hidden');
  document.getElementById('output-path-display').textContent = 'Nessuna cartella selezionata';
  document.getElementById('output-path-display').classList.remove('selected');
  document.getElementById('progress-bar').style.width = '0%';
  document.getElementById('progress-current-file').textContent = '';
  document.getElementById('progress-count').textContent = '';
  document.getElementById('progress-step-label').textContent = 'Elaborazione in corso...';
  document.getElementById('log-panel').innerHTML = '';
  document.getElementById('result-log-section').innerHTML = '';
  document.getElementById('btn-cancel').style.display = '';

  // Reset step indicators
  for (let i = 1; i <= 5; i++) {
    const el = document.getElementById(`step-${i}`);
    if (el) el.classList.remove('active', 'done');
  }
  document.querySelectorAll('.step-line').forEach(l => l.classList.remove('done'));

  // Mostra setup card
  document.getElementById('result-card').classList.add('hidden');
  document.getElementById('progress-card').classList.add('hidden');
  document.getElementById('setup-card').classList.remove('hidden');

  // Reset modalità a "unico"
  document.getElementById('mode-unified').checked = true;

  updateStartButton();
}
