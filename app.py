"""Legal Obligation Extractor — Web API.

Usage:
  uv run python app.py
  Open http://localhost:8000
"""

import asyncio
import json
import threading
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from hush.core import Hush
from law_agent.workflow import graph
from law_agent.export import export

app = FastAPI()

WORK_DIR = Path("work")
WORK_DIR.mkdir(exist_ok=True)

_running = {}


def _run_workflow(file_path: str, output_path: str, max_articles: int = -1):
    async def _inner():
        engine = Hush(graph, resources="resources.yaml")
        await engine.run({
            "file_path": file_path,
            "output_path": output_path,
            "max_articles": max_articles,
        })
    asyncio.run(_inner())


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix
    doc_id = Path(file.filename).stem.replace(" ", "_")
    doc_path = WORK_DIR / f"{doc_id}{suffix}"
    doc_path.write_bytes(await file.read())
    return {"doc_id": doc_id, "filename": file.filename}


@app.post("/api/extract")
async def extract_api(body: dict):
    doc_id = body.get("doc_id", "")
    max_articles = body.get("max_articles", -1)

    doc_path = _find_doc(doc_id)
    if not doc_path:
        return JSONResponse({"error": "Document not found"}, status_code=404)

    json_path = WORK_DIR / f"{doc_id}.json"
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
    json_path = WORK_DIR / f"{doc_id}.json"
    if not json_path.exists():
        return {"status": "not_found"}

    data = json.loads(json_path.read_text(encoding="utf-8"))
    articles = data.get("articles", {})

    return {
        "doc_id": data.get("doc_id", ""),
        "metadata": data.get("metadata", {}),
        "total": len(articles),
        "done": sum(1 for a in articles.values() if a["status"] == "done"),
        "classified": sum(1 for a in articles.values() if a["status"] == "classified"),
        "pending": sum(1 for a in articles.values() if a["status"] == "pending"),
        "error": sum(1 for a in articles.values() if a["status"].startswith("error")),
        "skipped": sum(1 for a in articles.values() if a["status"] == "skipped"),
        "running": doc_id in _running and _running[doc_id].is_alive(),
        "articles": [
            {
                "id": key,
                "title": art.get("title", ""),
                "status": art["status"],
                "error": art.get("error", ""),
                "obligations": art.get("obligations", []),
                "text": art.get("text", ""),
                "classified_json": art.get("classified_json", ""),
            }
            for key, art in articles.items()
        ],
    }


@app.post("/api/retry")
async def retry(body: dict):
    doc_id = body.get("doc_id", "")
    max_articles = body.get("max_articles", -1)

    doc_path = _find_doc(doc_id)
    if not doc_path:
        return JSONResponse({"error": "Document not found"}, status_code=404)

    json_path = WORK_DIR / f"{doc_id}.json"
    t = threading.Thread(
        target=_run_workflow,
        args=(str(doc_path), str(json_path), max_articles),
        daemon=True,
    )
    t.start()
    _running[doc_id] = t
    return {"status": "started", "doc_id": doc_id}


@app.post("/api/stop")
async def stop(body: dict):
    doc_id = body.get("doc_id", "")
    t = _running.get(doc_id)
    if t and t.is_alive():
        # Can't kill thread gracefully — just remove from tracking
        # The thread will finish its current article then stop on next poll
        _running.pop(doc_id, None)
        return {"status": "stopping", "doc_id": doc_id}
    return {"status": "not_running"}


@app.get("/api/excel/{doc_id}")
async def download_excel(doc_id: str):
    json_path = WORK_DIR / f"{doc_id}.json"
    if not json_path.exists():
        return JSONResponse({"error": "Not found"}, status_code=404)
    excel_path = str(WORK_DIR / f"{doc_id}.xlsx")
    export(str(json_path), excel_path)
    return FileResponse(excel_path, filename=f"{doc_id}.xlsx")


def _find_doc(doc_id: str):
    for ext in (".doc", ".docx"):
        p = WORK_DIR / f"{doc_id}{ext}"
        if p.exists():
            return p
    return None


app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
