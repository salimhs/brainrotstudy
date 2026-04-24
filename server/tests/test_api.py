"""HTTP contract tests using FastAPI's TestClient. Pipeline is stubbed."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Prevent the background pipeline from firing — we're only testing HTTP wiring.
    import brainrotstudy.main as main

    monkeypatch.setattr(main, "submit_job", lambda job_id: None)
    # ensure app picks up the freshly monkeypatched attributes
    importlib.reload
    return TestClient(main.app)


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_config_endpoint(client: TestClient) -> None:
    r = client.get("/config")
    assert r.status_code == 200
    body = r.json()
    assert "llm" in body
    assert "tts" in body


def test_create_topic_job(client: TestClient) -> None:
    r = client.post(
        "/jobs",
        json={"topic": "Big O notation", "options": {"length_sec": 45}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert body["input_kind"] == "topic"
    assert body["title"] == "Big O notation"
    assert body["options"]["length_sec"] == 45


def test_create_file_job(client: TestClient, tmp_path: Path) -> None:
    upload = tmp_path / "notes.md"
    upload.write_text("# Hello\n- bullet one\n- bullet two\n")
    r = client.post(
        "/jobs",
        files={"file": ("notes.md", upload.read_bytes(), "text/markdown")},
        data={"options": json.dumps({"length_sec": 60})},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["input_kind"] == "file"
    assert body["input_filename"] == "notes.md"


def test_reject_empty_topic(client: TestClient) -> None:
    r = client.post("/jobs", json={"topic": "  ", "options": {}})
    assert r.status_code == 400


def test_reject_bad_extension(client: TestClient) -> None:
    r = client.post(
        "/jobs",
        files={"file": ("x.docx", b"hi", "application/octet-stream")},
        data={"options": "{}"},
    )
    assert r.status_code == 400


def test_get_and_delete_job(client: TestClient) -> None:
    r = client.post("/jobs", json={"topic": "Deleteme"})
    job_id = r.json()["id"]
    r = client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    r = client.delete(f"/jobs/{job_id}")
    assert r.status_code == 200
    r = client.get(f"/jobs/{job_id}")
    assert r.status_code == 404


def test_download_missing_asset_returns_404(client: TestClient) -> None:
    r = client.post("/jobs", json={"topic": "topic"})
    job_id = r.json()["id"]
    r = client.get(f"/jobs/{job_id}/download/video")
    assert r.status_code == 404
