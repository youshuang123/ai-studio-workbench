"""取消任务（3-1 新增）：queued / running / 已结束 三种路径。"""

import io

import pytest
from PIL import Image

from app import models
from app.db import SessionLocal
from app.services import model_client, runner


@pytest.fixture
def fake_image_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (256, 256), (30, 60, 90)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def enable_key(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "T2I_API_KEY", "test-key-not-real")


@pytest.fixture
def sync_runner(monkeypatch):
    monkeypatch.setattr(runner, "start_job", lambda job_id: runner.run_job(job_id))


def _create_job(client, project_id, asset_id):
    return client.post(
        f"/api/projects/{project_id}/generations",
        json={
            "source_asset_id": asset_id,
            "product_name": "取消测试杯",
            "category": "家居",
        },
    )


def test_cancel_queued_job_is_immediate(client, make_asset, enable_key, monkeypatch):
    """queued 状态下取消：直接 cancelled，不产生费用。"""
    pid, asset = make_asset()

    # 让 start_job 什么都不做，任务停在 queued
    monkeypatch.setattr(runner, "start_job", lambda job_id: None)
    job_id = _create_job(client, pid, asset["id"]).json()["job_id"]

    resp = client.post(f"/api/jobs/{job_id}/cancel")
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "cancelled"
    assert body["cancel_requested"] is False

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "cancelled"
    assert job["cost_fen"] == 0

    usage = client.get(f"/api/projects/{pid}/usage").json()
    assert usage["images"] == 0


def test_cancel_running_job_stops_at_checkpoint(
    client, make_asset, enable_key, sync_runner, fake_image_bytes, monkeypatch
):
    """running 中取消：模型返回后在检查点丢弃产物，不落盘、不记账。"""
    pid, asset = make_asset()

    def _slow_generate(prompt, negative_prompt=""):
        # 模拟"请求已在路上，用户点了取消"
        db = SessionLocal()
        try:
            job = (
                db.query(models.GenerationJob)
                .order_by(models.GenerationJob.created_at.desc())
                .first()
            )
            job.cancel_requested = True
            db.commit()
        finally:
            db.close()
        return fake_image_bytes

    monkeypatch.setattr(model_client, "generate_image", _slow_generate)
    job_id = _create_job(client, pid, asset["id"]).json()["job_id"]

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "cancelled"
    assert job["error_code"] == "CANCELLED"
    assert job["output_asset_id"] is None
    # 诚实告知：调用可能已产生费用
    assert "费用" in job["error_message"]

    usage = client.get(f"/api/projects/{pid}/usage").json()
    assert usage["images"] == 0
    # 也不应该留下产物资产
    detail = client.get(f"/api/projects/{pid}").json()
    assert [a for a in detail["assets"] if a["kind"] == "output"] == []


def test_cancel_succeeded_job_conflict(
    client, make_asset, enable_key, sync_runner, fake_image_bytes, monkeypatch
):
    pid, asset = make_asset()
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    job_id = _create_job(client, pid, asset["id"]).json()["job_id"]
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "succeeded"

    resp = client.post(f"/api/jobs/{job_id}/cancel")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "STATE_CONFLICT"


def test_cancel_missing_job(client):
    resp = client.post("/api/jobs/not-exist/cancel")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_cancel_is_idempotent_while_running(client, make_asset, enable_key, monkeypatch):
    pid, asset = make_asset()
    monkeypatch.setattr(runner, "start_job", lambda job_id: None)
    job_id = _create_job(client, pid, asset["id"]).json()["job_id"]

    # 手工置为 running
    db = SessionLocal()
    try:
        job = db.get(models.GenerationJob, job_id)
        job.status = "running"
        db.commit()
    finally:
        db.close()

    first = client.post(f"/api/jobs/{job_id}/cancel")
    second = client.post(f"/api/jobs/{job_id}/cancel")
    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["cancel_requested"] is True


def test_sse_reports_cancelled(client, make_asset, enable_key, monkeypatch):
    pid, asset = make_asset()
    monkeypatch.setattr(runner, "start_job", lambda job_id: None)
    job_id = _create_job(client, pid, asset["id"]).json()["job_id"]
    client.post(f"/api/jobs/{job_id}/cancel")

    with client.stream("GET", f"/api/jobs/{job_id}/events") as resp:
        text = "".join(resp.iter_text())

    assert "event: cancelled" in text
    assert "event: error" not in text
    assert "event: done" not in text


def test_job_out_includes_cancel_requested(client, make_asset, enable_key, monkeypatch):
    pid, asset = make_asset()
    monkeypatch.setattr(runner, "start_job", lambda job_id: None)
    job_id = _create_job(client, pid, asset["id"]).json()["job_id"]
    job = client.get(f"/api/jobs/{job_id}").json()
    assert "cancel_requested" in job
    assert job["cancel_requested"] is False
