// =============================================================================
// State
// =============================================================================

let docId = null;
let pollTimer = null;
let selectedArticle = null;
let lastData = null;

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

dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("dragover");
});

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

  // Check if JSON already exists from previous run
  pollOnce();
}

// =============================================================================
// Buttons
// =============================================================================

$("btnExtract").addEventListener("click", async () => {
  if (!docId) return;
  $("btnExtract").disabled = true;

  await fetch("/api/extract", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id: docId, max_articles: -1 }),
  });

  startPolling();
});

$("btnRetry").addEventListener("click", async () => {
  if (!docId) return;
  $("btnRetry").disabled = true;

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
  } catch (e) {
    // Ignore fetch errors during polling
  }
}

// =============================================================================
// Render
// =============================================================================

function renderStatus(data) {
  const { total, done, classified, pending, error, skipped, running, articles } =
    data;
  const processed = done + skipped;

  // Progress
  $("progressSection").style.display = "block";
  const pct = total > 0 ? Math.round((processed / total) * 100) : 0;
  $("progressFill").style.width = pct + "%";
  $("progressCount").textContent = `${done} done / ${total} total`;

  if (running) {
    $("progressLabel").innerHTML =
      '<span class="spinner"></span>Processing...';
    $("btnExtract").disabled = true;
    $("btnRetry").disabled = true;
  } else {
    if (error > 0) {
      $("progressLabel").textContent = `Completed with ${error} error(s)`;
    } else if (pending > 0 || classified > 0) {
      $("progressLabel").textContent =
        `Paused — ${pending + classified} remaining`;
    } else {
      $("progressLabel").textContent = "Done";
    }
    $("btnExtract").disabled = false;
    $("btnRetry").disabled =
      error === 0 && pending === 0 && classified === 0;
    $("btnExcel").disabled = done === 0;

    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  // Articles
  $("articlesSection").style.display = "block";
  renderArticles(articles);

  // Auto-select first article with obligations
  if (!selectedArticle && articles.length) {
    const first =
      articles.find((a) => a.obligations && a.obligations.length > 0) ||
      articles[0];
    selectedArticle = first.id;
  }

  renderObligations(articles);
}

function renderArticles(articles) {
  const list = $("articleList");
  list.innerHTML = articles
    .map(
      (a) => `
    <div class="article-item ${selectedArticle === a.id ? "selected" : ""}"
         data-id="${a.id}">
      <div class="status-dot status-${a.status}"></div>
      <span class="article-id">${a.id}</span>
      <span class="article-title">${esc(a.title)}</span>
      <span class="article-status">${statusLabel(a.status)}</span>
    </div>
  `
    )
    .join("");

  // Click handlers
  list.querySelectorAll(".article-item").forEach((el) => {
    el.addEventListener("click", () => {
      selectedArticle = el.dataset.id;
      renderArticles(lastData.articles);
      renderObligations(lastData.articles);
    });
  });
}

function renderObligations(articles) {
  const art = articles.find((a) => a.id === selectedArticle);
  const section = $("obligationsSection");
  const list = $("obligationsList");

  if (!art || !art.obligations || !art.obligations.length) {
    section.style.display = "none";
    return;
  }

  section.style.display = "block";
  $("obligationsTitle").textContent =
    `Obligations — ${art.id}. ${art.title}`;

  list.innerHTML = art.obligations
    .map(
      (ob) => `
    <div class="obligation-card ${ob.loai}">
      <div class="ob-header">
        <span class="ob-dieu">Điều ${esc(ob.dieu)}</span>
        <span class="ob-loai ${ob.loai}">${loaiLabel(ob.loai)}</span>
      </div>
      ${
        ob.chu_the_tuong_tac || ob.chu_the_hoat_dong
          ? `<div class="ob-subjects">
              ${ob.chu_the_tuong_tac ? "👥 " + esc(ob.chu_the_tuong_tac) : ""}
              ${ob.chu_the_hoat_dong ? " · 🏢 " + esc(ob.chu_the_hoat_dong) : ""}
             </div>`
          : ""
      }
      ${
        ob.hanh_dong
          ? `<div class="ob-action">${formatAction(ob.hanh_dong)}</div>`
          : ""
      }
    </div>
  `
    )
    .join("");
}

// =============================================================================
// Helpers
// =============================================================================

function statusLabel(s) {
  const labels = {
    pending: "⏳ pending",
    classified: "🏷 classified",
    done: "✓ done",
    error_classify: "✗ classify err",
    error_actions: "✗ actions err",
    skipped: "⊘ skipped",
  };
  return labels[s] || s;
}

function loaiLabel(l) {
  const labels = {
    bat_buoc: "Bắt buộc",
    quyen: "Quyền",
    dinh_nghia: "Định nghĩa",
  };
  return labels[l] || l;
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
