# LOGIC HEADER
# Input:          FastAPI TestClient requests against api.main:app, with storage
#                 redirected to a temp db per test.
# Transformation: Exercise /process, /runs, /flagged, and /flagged/{id}/review over HTTP,
#                 the same way n8n and the dashboard will call them.
# Output:         Pass/fail assertions.

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.main as main_module
from api.storage import Storage


@pytest.fixture
def client(isolated_cwd, monkeypatch):
    # Give this test its own storage instance so runs from other tests don't leak in.
    test_storage = Storage(db_path=isolated_cwd / "test.db")
    monkeypatch.setattr(main_module, "storage", test_storage)
    return TestClient(main_module.app)


def _receipt_png_bytes(make_receipt_image, tmp_path, name, vendor, date, total):
    path = make_receipt_image(tmp_path / name, vendor, date, total)
    return path.read_bytes()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_process_then_list_runs(client, make_receipt_image, tmp_path):
    content = _receipt_png_bytes(make_receipt_image, tmp_path, "r1.png",
                                  "Corner Cafe", "2026-01-05", "12.50")
    resp = client.post("/process", files=[("files", ("r1.png", content, "image/png"))])
    assert resp.status_code == 200
    body = resp.json()
    assert body["files_processed"] == 1

    runs_resp = client.get("/runs")
    assert runs_resp.status_code == 200
    assert len(runs_resp.json()) == 1


def test_process_no_files_rejected(client):
    resp = client.post("/process", files=[])
    assert resp.status_code == 422  # FastAPI validation: files field required


def test_process_unknown_engine_rejected(client, make_receipt_image, tmp_path):
    content = _receipt_png_bytes(make_receipt_image, tmp_path, "r1.png",
                                  "Corner Cafe", "2026-01-05", "12.50")
    resp = client.post("/process?engine=not_a_real_engine",
                        files=[("files", ("r1.png", content, "image/png"))])
    assert resp.status_code == 400


def test_flagged_review_flow(client, make_receipt_image, tmp_path):
    p1_bytes = _receipt_png_bytes(make_receipt_image, tmp_path, "r1.png",
                                   "Corner Cafe", "2026-01-05", "12.50")
    # Duplicate upload to guarantee a flagged item deterministically.
    client.post("/process", files=[("files", ("r1.png", p1_bytes, "image/png"))])
    resp = client.post("/process", files=[
        ("files", ("r1.png", p1_bytes, "image/png")),
        ("files", ("r1_copy.png", p1_bytes, "image/png")),
    ])
    assert resp.status_code == 200

    flagged_resp = client.get("/flagged")
    assert flagged_resp.status_code == 200
    flagged = flagged_resp.json()
    assert len(flagged) >= 1

    item_id = flagged[0]["id"]
    review_resp = client.post(f"/flagged/{item_id}/review")
    assert review_resp.status_code == 200
    assert review_resp.json()["reviewed"] is True

    unreviewed_resp = client.get("/flagged?only_unreviewed=true")
    remaining_ids = [i["id"] for i in unreviewed_resp.json()]
    assert item_id not in remaining_ids


def test_review_unknown_id_404(client):
    resp = client.post("/flagged/999999/review")
    assert resp.status_code == 404
