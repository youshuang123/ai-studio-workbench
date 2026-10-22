import io
import json

import pytest
from PIL import Image

from app import config, models
from app.db import SessionLocal
from app.services import model_client, runner


@pytest.fixture
def fake_image_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (1024, 1024), (240, 240, 240)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def enable_key(monkeypatch):
    monkeypatch.setattr(config, "T2I_API_KEY", "test-key-not-real")


@pytest.fixture
def sync_runner(monkeypatch):
    """让后台线程变成同步执行，测试结果才是确定的。"""
    monkeypatch.setattr(runner, "start_job", lambda job_id: runner.run_job(job_id))


def _create(client, pid, asset_id, **overrides):
    payload = {
        "source_asset_id": asset_id,
        "product_name": "红色保温杯",
        "category": "家居",
        "selling_points": "24 小时保温",
        "color": "红色",
    }
    payload.update(overrides)
    return client.post(f"/api/projects/{pid}/generations", json=payload)


def test_generate_success(client, make_asset, enable_key, sync_runner, fake_image_bytes, monkeypatch):
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    pid, asset = make_asset()

    resp = _create(client, pid, asset["id"])
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "succeeded"
    assert job["output_asset_id"]
    assert job["cost_fen"] == config.T2I_UNIT_PRICE_FEN

    # 产物能读出来
    file_resp = client.get(f"/api/assets/{job['output_asset_id']}/file")
    assert file_resp.status_code == 200
    assert Image.open(io.BytesIO(file_resp.content)).size == (1024, 1024)

    # 成本已归集
    usage = client.get(f"/api/projects/{pid}/usage").json()
    assert usage["images"] == 1
    assert usage["total_fen"] == config.T2I_UNIT_PRICE_FEN

    # 元数据侧车文件写出来了
    db = SessionLocal()
    try:
        out_asset = db.get(models.Asset, job["output_asset_id"])
        side = (config.ASSETS_DIR / out_asset.path).with_suffix(".json")
        assert side.exists()
        meta = json.loads(side.read_text(encoding="utf-8"))
        assert meta["job_id"] == job_id
        assert "prompt" in meta
    finally:
        db.close()


def test_generate_without_key_returns_503(client, make_asset):
    pid, asset = make_asset()
    resp = _create(client, pid, asset["id"])
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "MODEL_NOT_CONFIGURED"


def test_generate_model_timeout_then_retry(
    client, make_asset, enable_key, sync_runner, fake_image_bytes, monkeypatch
):
    pid, asset = make_asset()

    def _timeout(p, n=""):
        raise model_client.ModelError("MODEL_TIMEOUT", "模型响应超时，可重试")

    monkeypatch.setattr(model_client, "generate_image", _timeout)
    resp = _create(client, pid, asset["id"])
    job_id = resp.json()["job_id"]

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert job["error_code"] == "MODEL_TIMEOUT"

    # 修好之后重试成功
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    retry = client.post(f"/api/jobs/{job_id}/retry")
    assert retry.status_code == 202
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "succeeded"


def test_retry_succeeded_job_conflict(client, make_asset, enable_key, sync_runner, fake_image_bytes, monkeypatch):
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    pid, asset = make_asset()
    job_id = _create(client, pid, asset["id"]).json()["job_id"]

    resp = client.post(f"/api/jobs/{job_id}/retry")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "STATE_CONFLICT"


def test_budget_exceeded_on_create(client, make_asset, enable_key, sync_runner):
    pid, asset = make_asset()
    resp = _create(client, pid, asset["id"], budget_cny=0.01)
    assert resp.status_code == 402
    assert resp.json()["error"]["code"] == "BUDGET_EXCEEDED"


def test_budget_exceeded_on_retry_when_spent(
    client, make_asset, enable_key, sync_runner, fake_image_bytes, monkeypatch
):
    pid, asset = make_asset()

    # 第一张：成功，花掉一个单价（0.03 元）
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    first = _create(client, pid, asset["id"], budget_cny=0.03)
    assert first.status_code == 202
    assert client.get(f"/api/jobs/{first.json()['job_id']}").json()["status"] == "succeeded"

    # 第二张：先让它失败
    def _timeout(p, n=""):
        raise model_client.ModelError("MODEL_TIMEOUT", "超时")

    monkeypatch.setattr(model_client, "generate_image", _timeout)
    second = _create(client, pid, asset["id"], budget_cny=0.03)
    assert second.status_code == 202
    second_job = second.json()["job_id"]
    assert client.get(f"/api/jobs/{second_job}").json()["status"] == "failed"

    # 项目已花 0.03，这次再花 0.03 会超过 0.03 的预算 → 重试应被拦
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    retry = client.post(f"/api/jobs/{second_job}/retry")
    assert retry.status_code == 402
    assert retry.json()["error"]["code"] == "BUDGET_EXCEEDED"
    assert "预算不足" in retry.json()["error"]["message"]


def test_source_asset_must_belong_to_project(client, make_project, make_asset, enable_key):
    pid_a, asset_a = make_asset()
    pid_b = make_project("另一个项目")["id"]
    resp = _create(client, pid_b, asset_a["id"])
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_SOURCE_ASSET"


def test_mark_interrupted_jobs():
    db = SessionLocal()
    try:
        project = models.Project(name="中断测试")
        db.add(project)
        db.flush()
        job = models.GenerationJob(project_id=project.id, status="running")
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    count = runner.mark_interrupted_jobs()
    assert count >= 1

    db = SessionLocal()
    try:
        job = db.get(models.GenerationJob, job_id)
        assert job.status == "failed"
        assert job.error_code == "INTERRUPTED"
    finally:
        db.close()


def test_sse_done_event(client, make_asset, enable_key, sync_runner, fake_image_bytes, monkeypatch):
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    pid, asset = make_asset()
    job_id = _create(client, pid, asset["id"]).json()["job_id"]

    with client.stream("GET", f"/api/jobs/{job_id}/events") as resp:
        assert resp.status_code == 200
        text = "".join(resp.iter_text())

    assert "event: done" in text
    assert '"job_id"' in text
    assert "event: error" not in text


def test_sse_error_event(client, make_asset, enable_key, sync_runner, monkeypatch):
    monkeypatch.setattr(
        model_client,
        "generate_image",
        lambda p, n="": (_ for _ in ()).throw(
            model_client.ModelError("MODEL_AUTH_FAILED", "模型认证失败，请检查 API Key")
        ),
    )
    pid, asset = make_asset()
    job_id = _create(client, pid, asset["id"]).json()["job_id"]

    with client.stream("GET", f"/api/jobs/{job_id}/events") as resp:
        text = "".join(resp.iter_text())

    assert "event: error" in text
    assert "MODEL_AUTH_FAILED" in text
    assert "test-key-not-real" not in text  # 不泄露 Key


def test_sse_missing_job(client):
    with client.stream("GET", "/api/jobs/not-exist/events") as resp:
        text = "".join(resp.iter_text())
    assert "event: error" in text
    assert "NOT_FOUND" in text
