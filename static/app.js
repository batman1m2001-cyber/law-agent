// =============================================================================
// State
// =============================================================================

let docId = null;
let pollTimer = null;
let selectedArticle = null;
let lastData = null;
let activeTab = "obligations";

const $ = (id) => document.getElementById(id);

// =============================================================================
// Upload
// =============================================================================

const dropZone = $("dropZone");
const fileInput = $("fileInput");

dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("dragover");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("dragover");
  if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) handleFile(fileInput.files[0]);
});

async function handleFile(file) {
  $("fileName").textContent = file.name;
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/upload", { method: "POST", body: form });
  const data = await res.json();
  docId = data.doc_id;
  $("btnExtract").disabled = false;
  $("btnRetry").disabled = true;
  $("btnExcel").disabled = true;
  $("btnStop").disabled = true;
  pollOnce();
}

// =============================================================================
// Buttons
// =============================================================================

$("btnExtract").addEventListener("click", async () => {
  if (!docId) return;
  $("btnExtract").disabled = true;
  $("btnStop").disabled = false;
  await fetch("/api/extract", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id: docId, max_articles: -1 }),
  });
  startPolling();
});

$("btnStop").addEventListener("click", async () => {
  if (!docId) return;
  $("btnStop").disabled = true;
  await fetch("/api/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id: docId }),
  });
  // Keep polling to catch final state
});

$("btnRetry").addEventListener("click", async () => {
  if (!docId) return;
  $("btnRetry").disabled = true;
  $("btnStop").disabled = false;
  await fetch("/api/retry", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id: docId, max_articles: -1 }),
  });
  startPolling();
});

$("btnExcel").addEventListener("click", () => {
  if (!docId) return;
  window.open("/api/excel/" + docId);
});

// =============================================================================
// Tabs
// =============================================================================

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    activeTab = tab.dataset.tab;
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    renderDetail();
  });
});

// =============================================================================
// Polling
// =============================================================================

function startPolling() {
  $("progressSection").style.display = "block";
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(pollOnce, 1000);
}

async function pollOnce() {
  if (!docId) return;
  try {
    const res = await fetch("/api/status/" + docId);
    const data = await res.json();
    if (data.status === "not_found") return;
    lastData = data;
    renderStatus(data);
  } catch (e) {}
}

// =============================================================================
// Render
// =============================================================================

function renderStatus(data) {
  const { total, done, classified, pending, error, skipped, running, articles } = data;
  const processed = done + skipped;

  // Progress
  $("progressSection").style.display = "block";
  const pct = total > 0 ? Math.round((processed / total) * 100) : 0;
  $("progressFill").style.width = pct + "%";
  $("progressCount").textContent = `${done} done · ${classified} classified · ${total} total`;

  if (running) {
    const inProgress = classified > 0
      ? `Classifying & generating actions... (${classified} classified, ${done} done)`
      : "Processing...";
    $("progressLabel").innerHTML = `<span class="spinner"></span>${inProgress}`;
    $("btnExtract").disabled = true;
    $("btnRetry").disabled = true;
    $("btnStop").disabled = false;
    $("btnExcel").disabled = done === 0;
  } else {
    $("btnStop").disabled = true;
    if (error > 0) {
      $("progressLabel").textContent = `Completed with ${error} error(s)`;
    } else if (pending > 0 || classified > 0) {
      $("progressLabel").textContent = `Paused — ${pending + classified} remaining`;
    } else {
      $("progressLabel").textContent = `Done — ${done} obligations extracted`;
    }
    $("btnExtract").disabled = false;
    $("btnRetry").disabled = error === 0 && pending === 0 && classified === 0;
    $("btnExcel").disabled = done === 0;
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  // Articles
  $("articlesSection").style.display = "block";
  renderArticles(articles);

  // Auto-select first article with obligations
  if (!selectedArticle && articles.length) {
    const first = articles.find((a) => a.obligations && a.obligations.length > 0) || articles[0];
    selectedArticle = first.id;
  }
  renderDetail();
}

function renderArticles(articles) {
  const list = $("articleList");
  list.innerHTML = articles.map((a) => `
    <div class="article-item ${selectedArticle === a.id ? "selected" : ""}" data-id="${a.id}">
      <div class="status-dot status-${a.status}"></div>
      <span class="article-id">${a.id}</span>
      <span class="article-title">${esc(a.title)}</span>
      <span class="article-status">${statusLabel(a.status)}</span>
    </div>
  `).join("");

  list.querySelectorAll(".article-item").forEach((el) => {
    el.addEventListener("click", () => {
      selectedArticle = el.dataset.id;
      renderArticles(lastData.articles);
      renderDetail();
    });
  });
}

function renderDetail() {
  if (!lastData || !selectedArticle) return;
  const art = lastData.articles.find((a) => a.id === selectedArticle);
  if (!art) return;

  const section = $("detailSection");
  section.style.display = "block";
  $("detailTitle").textContent = `${art.id}. ${art.title}`;

  // Show/hide panels
  $("panelObligations").style.display = activeTab === "obligations" ? "block" : "none";
  $("panelContent").style.display = activeTab === "content" ? "block" : "none";
  $("panelClassified").style.display = activeTab === "classified" ? "block" : "none";

  if (activeTab === "obligations") {
    renderObligations(art);
  } else if (activeTab === "content") {
    $("panelContent").innerHTML = art.text
      ? `<div class="article-text">${esc(art.text)}</div>`
      : '<div class="article-text" style="color:#555">No text available</div>';
  } else if (activeTab === "classified") {
    let pretty = art.classified_json || "";
    try { pretty = JSON.stringify(JSON.parse(pretty), null, 2); } catch (e) {}
    $("panelClassified").innerHTML = pretty
      ? `<div class="classify-json">${esc(pretty)}</div>`
      : '<div class="classify-json" style="color:#555">Not yet classified</div>';
  }
}

function renderObligations(art) {
  const panel = $("panelObligations");
  if (!art.obligations || !art.obligations.length) {
    const msg = art.status === "done"
      ? "No obligations found for this article."
      : art.status === "classified"
      ? "Classified — waiting for action generation..."
      : "Not yet processed.";
    panel.innerHTML = `<div style="color:#555;font-size:13px;padding:20px;text-align:center">${msg}</div>`;
    return;
  }

  panel.innerHTML = art.obligations.map((ob) => `
    <div class="obligation-card ${ob.loai}">
      <div class="ob-header">
        <span class="ob-dieu">Điều ${esc(ob.dieu)}</span>
        <span class="ob-loai ${ob.loai}">${loaiLabel(ob.loai)}</span>
      </div>
      ${ob.chu_the_tuong_tac || ob.chu_the_hoat_dong ? `
        <div class="ob-subjects">
          ${ob.chu_the_tuong_tac ? "👥 " + esc(ob.chu_the_tuong_tac) : ""}
          ${ob.chu_the_hoat_dong ? " · 🏢 " + esc(ob.chu_the_hoat_dong) : ""}
        </div>
      ` : ""}
      ${ob.hanh_dong ? `<div class="ob-action">${formatAction(ob.hanh_dong)}</div>` : ""}
    </div>
  `).join("");
}

// =============================================================================
// Helpers
// =============================================================================

function statusLabel(s) {
  return {
    pending: "⏳ pending",
    classified: "🏷 classified",
    done: "✓ done",
    error_classify: "✗ classify err",
    error_actions: "✗ actions err",
    skipped: "⊘ skipped",
  }[s] || s;
}

function loaiLabel(l) {
  return { bat_buoc: "Bắt buộc", quyen: "Quyền", dinh_nghia: "Định nghĩa" }[l] || l;
}

function formatAction(text) {
  return esc(text)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/\n/g, "<br>");
}

function esc(s) {
  if (!s) return "";
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
