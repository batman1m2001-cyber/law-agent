"""Legal Obligation Extractor — Web UI.

Usage:
  uv run python app.py
  Open http://localhost:8000
"""

import asyncio
import json
import tempfile
import threading
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

load_dotenv()

from hush.core import Hush
from law_agent.workflow import graph
from law_agent.export import export

app = FastAPI()

# State
WORK_DIR = Path("work")
WORK_DIR.mkdir(exist_ok=True)
_running = {}  # doc_id → thread


def _get_json_path(doc_id: str) -> Path:
    return WORK_DIR / f"{doc_id}.json"


def _run_workflow(file_path: str, output_path: str, max_articles: int = -1):
    """Run workflow in background thread."""
    async def _inner():
        engine = Hush(graph, resources="resources.yaml")
        await engine.run({
            "file_path": file_path,
            "output_path": output_path,
            "max_articles": max_articles,
        })

    asyncio.run(_inner())


# =============================================================================
# API endpoints
# =============================================================================


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    """Upload document, save to work dir, return doc_id."""
    suffix = Path(file.filename).suffix
    doc_id = Path(file.filename).stem.replace(" ", "_")
    doc_path = WORK_DIR / f"{doc_id}{suffix}"
    content = await file.read()
    doc_path.write_bytes(content)
    return {"doc_id": doc_id, "filename": file.filename}


@app.post("/api/extract")
async def extract(body: dict):
    """Start extraction workflow in background."""
    doc_id = body.get("doc_id", "")
    max_articles = body.get("max_articles", -1)

    # Find the uploaded file
    doc_path = None
    for ext in (".doc", ".docx"):
        p = WORK_DIR / f"{doc_id}{ext}"
        if p.exists():
            doc_path = p
            break
    if not doc_path:
        return JSONResponse({"error": "Document not found"}, status_code=404)

    json_path = _get_json_path(doc_id)

    # Run in background thread
    t = threading.Thread(
        target=_run_workflow,
        args=(str(doc_path), str(json_path), max_articles),
        daemon=True,
    )
    t.start()
    _running[doc_id] = t

    return {"status": "started", "doc_id": doc_id}


@app.get("/api/status/{doc_id}")
async def status(doc_id: str):
    """Poll extraction status from JSON file."""
    json_path = _get_json_path(doc_id)
    if not json_path.exists():
        return {"status": "not_found"}

    data = json.loads(json_path.read_text(encoding="utf-8"))
    articles = data.get("articles", {})

    summary = {
        "doc_id": data.get("doc_id", ""),
        "metadata": data.get("metadata", {}),
        "total": len(articles),
        "done": sum(1 for a in articles.values() if a["status"] == "done"),
        "classified": sum(1 for a in articles.values() if a["status"] == "classified"),
        "pending": sum(1 for a in articles.values() if a["status"] == "pending"),
        "error": sum(1 for a in articles.values() if a["status"].startswith("error")),
        "skipped": sum(1 for a in articles.values() if a["status"] == "skipped"),
        "running": doc_id in _running and _running[doc_id].is_alive(),
        "articles": [],
    }

    for key, art in articles.items():
        entry = {
            "id": key,
            "title": art.get("title", ""),
            "status": art["status"],
            "error": art.get("error", ""),
            "obligations": art.get("obligations", []),
        }
        summary["articles"].append(entry)

    return summary


@app.post("/api/retry")
async def retry(body: dict):
    """Re-run workflow — skips done articles, uses cached classify."""
    doc_id = body.get("doc_id", "")
    max_articles = body.get("max_articles", -1)

    doc_path = None
    for ext in (".doc", ".docx"):
        p = WORK_DIR / f"{doc_id}{ext}"
        if p.exists():
            doc_path = p
            break
    if not doc_path:
        return JSONResponse({"error": "Document not found"}, status_code=404)

    json_path = _get_json_path(doc_id)

    t = threading.Thread(
        target=_run_workflow,
        args=(str(doc_path), str(json_path), max_articles),
        daemon=True,
    )
    t.start()
    _running[doc_id] = t

    return {"status": "started", "doc_id": doc_id}


@app.get("/api/excel/{doc_id}")
async def download_excel(doc_id: str):
    """Export current JSON to Excel and return file."""
    json_path = _get_json_path(doc_id)
    if not json_path.exists():
        return JSONResponse({"error": "Not found"}, status_code=404)

    excel_path = str(WORK_DIR / f"{doc_id}.xlsx")
    export(str(json_path), excel_path)
    return FileResponse(excel_path, filename=f"{doc_id}.xlsx")


# =============================================================================
# HTML UI
# =============================================================================


@app.get("/")
async def index():
    return HTMLResponse(HTML)


HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Legal Obligation Extractor</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace;
    background: #1a1a2e; color: #e0e0e0; min-height: 100vh;
  }
  .container { max-width: 1100px; margin: 0 auto; padding: 24px; }

  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px 0; border-bottom: 1px solid #2a2a4a; margin-bottom: 24px;
  }
  header h1 { font-size: 18px; color: #c4b5fd; font-weight: 600; }
  header .badge {
    font-size: 11px; background: #2a2a4a; color: #a78bfa; padding: 4px 10px;
    border-radius: 12px;
  }

  /* Upload area */
  .upload-area {
    border: 2px dashed #3a3a5c; border-radius: 12px; padding: 32px;
    text-align: center; cursor: pointer; transition: all 0.2s;
    margin-bottom: 20px; position: relative;
  }
  .upload-area:hover { border-color: #7c3aed; background: #1e1e38; }
  .upload-area.dragover { border-color: #a78bfa; background: #1e1e38; }
  .upload-area input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
  .upload-area .icon { font-size: 36px; margin-bottom: 8px; }
  .upload-area .hint { color: #888; font-size: 13px; }
  .file-name { color: #a78bfa; font-size: 14px; margin-top: 6px; }

  /* Buttons */
  .btn-row { display: flex; gap: 10px; margin-bottom: 20px; }
  .btn {
    padding: 8px 20px; border: none; border-radius: 8px; cursor: pointer;
    font-family: inherit; font-size: 13px; font-weight: 600; transition: all 0.15s;
  }
  .btn-primary { background: #7c3aed; color: white; }
  .btn-primary:hover { background: #6d28d9; }
  .btn-primary:disabled { background: #3a3a5c; color: #666; cursor: not-allowed; }
  .btn-secondary { background: #2a2a4a; color: #c4b5fd; }
  .btn-secondary:hover { background: #3a3a5c; }
  .btn-secondary:disabled { background: #1e1e38; color: #444; cursor: not-allowed; }

  /* Progress bar */
  .progress-section { margin-bottom: 20px; display: none; }
  .progress-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 8px; font-size: 13px;
  }
  .progress-header .count { color: #a78bfa; }
  .progress-bar {
    height: 6px; background: #2a2a4a; border-radius: 3px; overflow: hidden;
  }
  .progress-fill {
    height: 100%; background: linear-gradient(90deg, #7c3aed, #a78bfa);
    border-radius: 3px; transition: width 0.5s ease;
  }

  /* Article list */
  .articles-section { margin-bottom: 20px; }
  .articles-section h2 {
    font-size: 14px; color: #888; margin-bottom: 12px;
    text-transform: uppercase; letter-spacing: 1px;
  }
  .article-list { display: flex; flex-direction: column; gap: 2px; }
  .article-item {
    display: flex; align-items: center; gap: 10px; padding: 10px 14px;
    background: #1e1e38; border-radius: 8px; font-size: 13px; cursor: pointer;
    transition: background 0.15s; border-left: 3px solid transparent;
  }
  .article-item:hover { background: #252545; }
  .article-item.selected { background: #252545; border-left-color: #7c3aed; }
  .article-item .status-dot {
    width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
  }
  .status-pending { background: #555; }
  .status-classified { background: #f59e0b; }
  .status-done { background: #10b981; }
  .status-error_classify, .status-error_actions { background: #ef4444; }
  .status-skipped { background: #6b7280; }
  .article-item .article-id { color: #a78bfa; min-width: 65px; font-weight: 600; }
  .article-item .article-title { flex: 1; color: #ccc; }
  .article-item .article-status {
    font-size: 11px; padding: 2px 8px; border-radius: 10px; background: #2a2a4a;
  }

  /* Obligations panel */
  .obligations-section { margin-bottom: 20px; display: none; }
  .obligations-section h2 {
    font-size: 14px; color: #888; margin-bottom: 12px;
    text-transform: uppercase; letter-spacing: 1px;
  }
  .obligation-card {
    background: #1e1e38; border-radius: 8px; padding: 14px 16px;
    margin-bottom: 8px; border-left: 3px solid #3a3a5c;
  }
  .obligation-card.bat_buoc { border-left-color: #ef4444; }
  .obligation-card.quyen { border-left-color: #3b82f6; }
  .obligation-card.dinh_nghia { border-left-color: #6b7280; }
  .ob-header {
    display: flex; gap: 10px; align-items: center; margin-bottom: 8px;
  }
  .ob-dieu { color: #a78bfa; font-weight: 600; font-size: 13px; }
  .ob-loai {
    font-size: 10px; padding: 2px 8px; border-radius: 10px;
    text-transform: uppercase; font-weight: 600;
  }
  .ob-loai.bat_buoc { background: #7f1d1d; color: #fca5a5; }
  .ob-loai.quyen { background: #1e3a5f; color: #93c5fd; }
  .ob-loai.dinh_nghia { background: #2a2a4a; color: #9ca3af; }
  .ob-subjects { font-size: 12px; color: #888; margin-bottom: 6px; }
  .ob-action {
    font-size: 12px; color: #ccc; white-space: pre-wrap; line-height: 1.6;
    background: #161628; padding: 10px 12px; border-radius: 6px; margin-top: 8px;
  }

  /* Empty state */
  .empty { color: #555; font-size: 13px; text-align: center; padding: 40px; }

  /* Spinner */
  @keyframes spin { to { transform: rotate(360deg); } }
  .spinner {
    display: inline-block; width: 14px; height: 14px;
    border: 2px solid #3a3a5c; border-top-color: #a78bfa;
    border-radius: 50%; animation: spin 0.8s linear infinite;
    vertical-align: middle; margin-right: 6px;
  }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Legal Obligation Extractor</h1>
    <span class="badge">Powered by Hush AI</span>
  </header>

  <!-- Upload -->
  <div class="upload-area" id="dropZone">
    <input type="file" id="fileInput" accept=".doc,.docx">
    <div class="icon">📄</div>
    <div>Drop .doc / .docx file here</div>
    <div class="hint">or click to browse</div>
    <div class="file-name" id="fileName"></div>
  </div>

  <!-- Buttons -->
  <div class="btn-row">
    <button class="btn btn-primary" id="btnExtract" disabled>Extract</button>
    <button class="btn btn-secondary" id="btnRetry" disabled>Retry Failed</button>
    <button class="btn btn-secondary" id="btnExcel" disabled>Download Excel</button>
  </div>

  <!-- Progress -->
  <div class="progress-section" id="progressSection">
    <div class="progress-header">
      <span id="progressLabel"><span class="spinner"></span>Processing...</span>
      <span class="count" id="progressCount">0/0</span>
    </div>
    <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
  </div>

  <!-- Articles -->
  <div class="articles-section" id="articlesSection" style="display:none">
    <h2>Articles</h2>
    <div class="article-list" id="articleList"></div>
  </div>

  <!-- Obligations -->
  <div class="obligations-section" id="obligationsSection">
    <h2 id="obligationsTitle">Obligations</h2>
    <div id="obligationsList"></div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
let docId = null;
let pollTimer = null;
let selectedArticle = null;

// Upload
const dropZone = $('dropZone');
const fileInput = $('fileInput');

dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault(); dropZone.classList.remove('dragover');
  if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => { if (fileInput.files.length) handleFile(fileInput.files[0]); });

async function handleFile(file) {
  $('fileName').textContent = file.name;
  const form = new FormData();
  form.append('file', file);
  const res = await fetch('/api/upload', { method: 'POST', body: form });
  const data = await res.json();
  docId = data.doc_id;
  $('btnExtract').disabled = false;
  $('btnRetry').disabled = true;
  $('btnExcel').disabled = true;
  // Check if JSON already exists
  pollOnce();
}

// Extract
$('btnExtract').addEventListener('click', async () => {
  if (!docId) return;
  $('btnExtract').disabled = true;
  await fetch('/api/extract', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ doc_id: docId, max_articles: -1 }),
  });
  startPolling();
});

// Retry
$('btnRetry').addEventListener('click', async () => {
  if (!docId) return;
  $('btnRetry').disabled = true;
  await fetch('/api/retry', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ doc_id: docId, max_articles: -1 }),
  });
  startPolling();
});

// Excel
$('btnExcel').addEventListener('click', () => {
  if (!docId) return;
  window.open('/api/excel/' + docId);
});

// Polling
function startPolling() {
  $('progressSection').style.display = 'block';
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(pollOnce, 1000);
}

async function pollOnce() {
  if (!docId) return;
  try {
    const res = await fetch('/api/status/' + docId);
    const data = await res.json();
    if (data.status === 'not_found') return;
    renderStatus(data);
  } catch (e) {}
}

function renderStatus(data) {
  const { total, done, classified, pending, error, skipped, running, articles } = data;
  const processed = done + skipped;

  // Progress
  $('progressSection').style.display = 'block';
  const pct = total > 0 ? Math.round((processed / total) * 100) : 0;
  $('progressFill').style.width = pct + '%';
  $('progressCount').textContent = `${done} done / ${total} total`;

  if (running) {
    $('progressLabel').innerHTML = '<span class="spinner"></span>Processing...';
    $('btnExtract').disabled = true;
    $('btnRetry').disabled = true;
  } else {
    if (error > 0) {
      $('progressLabel').textContent = `Completed with ${error} error(s)`;
    } else if (pending > 0 || classified > 0) {
      $('progressLabel').textContent = `Paused — ${pending + classified} remaining`;
    } else {
      $('progressLabel').textContent = 'Done';
    }
    $('btnExtract').disabled = false;
    $('btnRetry').disabled = error === 0 && pending === 0 && classified === 0;
    $('btnExcel').disabled = done === 0;
    if (!running && pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  // Articles
  $('articlesSection').style.display = 'block';
  const list = $('articleList');
  list.innerHTML = articles.map(a => `
    <div class="article-item ${selectedArticle === a.id ? 'selected' : ''}"
         onclick="selectArticle('${a.id}')">
      <div class="status-dot status-${a.status}"></div>
      <span class="article-id">${a.id}</span>
      <span class="article-title">${esc(a.title)}</span>
      <span class="article-status">${statusLabel(a.status)}</span>
    </div>
  `).join('');

  // Auto-select first done article if none selected
  if (!selectedArticle && articles.length) {
    const first = articles.find(a => a.obligations.length > 0) || articles[0];
    selectArticle(first.id, articles);
  } else {
    renderObligations(articles);
  }
}

function selectArticle(id, articles) {
  selectedArticle = id;
  // Re-render with selection if articles not passed
  if (!articles) pollOnce();
  else renderObligations(articles);
}

function renderObligations(articles) {
  const art = articles.find(a => a.id === selectedArticle);
  const section = $('obligationsSection');
  const list = $('obligationsList');

  if (!art || !art.obligations.length) {
    section.style.display = 'none';
    return;
  }

  section.style.display = 'block';
  $('obligationsTitle').textContent = `Obligations — ${art.id}. ${art.title}`;

  list.innerHTML = art.obligations.map(ob => `
    <div class="obligation-card ${ob.loai}">
      <div class="ob-header">
        <span class="ob-dieu">Điều ${ob.dieu}</span>
        <span class="ob-loai ${ob.loai}">${loaiLabel(ob.loai)}</span>
      </div>
      ${ob.chu_the_tuong_tac || ob.chu_the_hoat_dong ? `
        <div class="ob-subjects">
          ${ob.chu_the_tuong_tac ? '👥 ' + esc(ob.chu_the_tuong_tac) : ''}
          ${ob.chu_the_hoat_dong ? ' · 🏢 ' + esc(ob.chu_the_hoat_dong) : ''}
        </div>
      ` : ''}
      ${ob.hanh_dong ? `<div class="ob-action">${formatAction(ob.hanh_dong)}</div>` : ''}
    </div>
  `).join('');

  // Re-render article list selection
  document.querySelectorAll('.article-item').forEach(el => {
    const id = el.querySelector('.article-id').textContent;
    el.classList.toggle('selected', id === selectedArticle);
  });
}

function statusLabel(s) {
  return {
    pending: '⏳ pending',
    classified: '🏷 classified',
    done: '✓ done',
    error_classify: '✗ classify error',
    error_actions: '✗ actions error',
    skipped: '⊘ skipped',
  }[s] || s;
}

function loaiLabel(l) {
  return { bat_buoc: 'Bắt buộc', quyen: 'Quyền', dinh_nghia: 'Định nghĩa' }[l] || l;
}

function formatAction(text) {
  return esc(text)
    .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
    .replace(/\n/g, '<br>');
}

function esc(s) {
  if (!s) return '';
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
