# LOGIC HEADER
# Input:          HTTP requests from n8n (POST /process with receipt files) and the
#                 dashboard's browser JS (GET /runs, GET /flagged, POST /flagged/{id}/review).
# Transformation: Thin FastAPI routing layer — delegates all real logic to processor.py
#                 (extraction) and storage.py (persistence). Serves the static dashboard
#                 at / so the whole thing runs from a single process during local/demo use.
# Output:         JSON responses for the API routes; the dashboard HTML/JS/CSS for the
#                 browser routes.

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.processor import process_batch
from api.storage import Storage

app = FastAPI(
    title="Receipt Review Automation API",
    description=(
        "Wraps the receipt-invoice-extractor pipeline in an HTTP API so an "
        "n8n workflow (or anything else) can trigger a processing run and "
        "check whether any results need human review."
    ),
)

storage = Storage()

DASHBOARD_DIR = Path(__file__).parent / "dashboard"


@app.post("/process")
async def process(files: list[UploadFile], engine: str = "rule_based"):
    """Run the extractor on an uploaded batch of receipts. Returns a summary n8n can
    branch on: if flagged_count > 0, post a Slack review notification."""
    if not files:
        raise HTTPException(status_code=400, detail="no files provided")
    if engine not in ("rule_based", "ai", "ai_vision"):
        raise HTTPException(status_code=400, detail=f"unknown engine: {engine}")

    pairs = [(f.filename, f.file) for f in files]
    summary = process_batch(pairs, storage, engine=engine)
    return summary


@app.get("/runs")
async def get_runs(limit: int = 50):
    runs = storage.list_runs(limit=limit)
    return [vars(r) for r in runs]


@app.get("/flagged")
async def get_flagged(only_unreviewed: bool = False):
    items = storage.list_flagged_items(only_unreviewed=only_unreviewed)
    return [vars(i) for i in items]


@app.post("/flagged/{item_id}/review")
async def review_item(item_id: int):
    item = storage.get_flagged_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="flagged item not found")
    storage.mark_reviewed(item_id)
    return {"id": item_id, "reviewed": True}


@app.get("/health")
async def health():
    return {"status": "ok"}


# Dashboard: served last so /process, /runs, etc. above take priority over static files.
if DASHBOARD_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")
