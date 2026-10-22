"""批次流程：校验 → 建批次 → 试跑闸门 → 批量 → 重试/取消/续跑 → 导出。"""

import io
import zipfile

import pytest
from PIL import Image

from app import config, models
from app.db import SessionLocal
from app.services import batch_runner, model_client

HEADER = "sku_code,product_name,category,color,selling_points,image_file\n"


def _csv(*rows: str) -> bytes:
    return (HEADER + "\n".join(rows) + "\n").encode("utf-8")


@pytest.fixture
def fake_image_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (128, 128), (20, 50, 80)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def enable_key(monkeypatch):
    monkeypatch.setattr(config, "T2I_API_KEY", "test-key-not-real")


@pytest.fixture
def sync_batch(monkeypatch):
    """批次启动同步化，测试才有确定结果。"""
    monkeypatch.setattr(
        batch_runner, "start_batch", lambda bid: batch_runner._run_batch(bid)
    )


def _upload_csv(client, project_id, content: bytes, name="skus.csv"):
    return client.post(
        f"/api/projects/{project_id}/batches",
        files={"file": (name, content, "text/csv")},
    )


def test_validate_does_not_create_batch(client, make_project, png_bytes):
    pid = make_project()["id"]
    # 上传一张图，让 image_file 能匹配
    client.post(
        f"/api/projects/{pid}/assets",
        files={"file": ("product.png", png_bytes, "image/png")},
    )
    resp = client.post(
        f"/api/projects/{pid}/batches/validate",
        files={"file": ("skus.csv", _csv("CUP-1,杯,家居,深蓝,保温,product.png"), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["valid"] == 1
    assert body["total"] == 1

    # 没有建任何批次
    assert client.get(f"/api/projects/{pid}").status_code == 200
    db = SessionLocal()
    try:
        assert db.query(models.Batch).count() == 0
    finally:
        db.close()


def test_create_batch_is_draft(client, make_project, png_bytes):
    pid = make_project()["id"]
    resp = _upload_csv(client, pid, _csv("CUP-1,杯,,,", "CUP-2,杯2,,,"))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "draft"
    assert body["total"] == 2
    assert body["created_jobs"] == 2


def test_confirm_requires_trial(client, make_project):
    pid = make_project()["id"]
    batch_id = _upload_csv(client, pid, _csv("CUP-1,杯,,,", "CUP-2,杯2,,,")).json()["id"]

    resp = client.post(f"/api/batches/{batch_id}/confirm")
    assert resp.status_code == 409
    assert "试跑" in resp.json()["error"]["message"]


def test_trial_then_confirm_runs_batch(
    client, make_project, enable_key, sync_batch, fake_image_bytes, monkeypatch
):
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    pid = make_project()["id"]
    batch_id = _upload_csv(
        client, pid, _csv("CUP-1,杯,,,", "CUP-2,杯2,,,", "CUP-3,杯3,,,")
    ).json()["id"]

    trial = client.post(f"/api/batches/{batch_id}/trial")
    assert trial.status_code == 200, trial.text
    assert trial.json()["job"]["status"] == "succeeded"

    confirm = client.post(f"/api/batches/{batch_id}/confirm")
    assert confirm.status_code == 202

    detail = client.get(f"/api/batches/{batch_id}").json()
    assert detail["status"] == "completed"
    assert detail["succeeded"] == 3
    assert detail["cost_fen"] == 3 * config.T2I_UNIT_PRICE_FEN
    # 每条都落了自己的 sku_code
    assert {i["sku_code"] for i in detail["items"]} == {"CUP-1", "CUP-2", "CUP-3"}


def test_one_failure_does_not_block_others(
    client, make_project, enable_key, sync_batch, fake_image_bytes, monkeypatch
):
    pid = make_project()["id"]
    batch_id = _upload_csv(
        client, pid, _csv("A-1,好,,,", "A-2,坏,,,", "A-3,好3,,,")
    ).json()["id"]

    def _flaky(prompt, negative_prompt=""):
        if "坏" in prompt:
            raise model_client.ModelError("MODEL_TIMEOUT", "超时")
        return fake_image_bytes

    monkeypatch.setattr(model_client, "generate_image", _flaky)

    client.post(f"/api/batches/{batch_id}/trial")  # 试跑第一条（好）
    client.post(f"/api/batches/{batch_id}/confirm")

    detail = client.get(f"/api/batches/{batch_id}").json()
    assert detail["succeeded"] >= 2
    assert detail["failed"] == 1
    bad = [i for i in detail["items"] if i["sku_code"] == "A-2"][0]
    assert bad["status"] == "failed"


def test_retry_single_item(
    client, make_project, enable_key, sync_batch, fake_image_bytes, monkeypatch
):
    pid = make_project()["id"]
    batch_id = _upload_csv(client, pid, _csv("B-1,会失败,,,")).json()["id"]

    monkeypatch.setattr(
        model_client,
        "generate_image",
        lambda p, n="": (_ for _ in ()).throw(model_client.ModelError("MODEL_TIMEOUT", "超时")),
    )
    client.post(f"/api/batches/{batch_id}/trial")
    item = client.get(f"/api/batches/{batch_id}").json()["items"][0]
    assert item["status"] == "failed"

    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    retry = client.post(f"/api/batches/{batch_id}/items/{item['id']}/retry")
    assert retry.status_code == 202
    assert retry.json()["item"]["status"] == "succeeded"


def test_resume_does_not_rerun_succeeded(
    client, make_project, enable_key, fake_image_bytes, monkeypatch
):
    """模拟中断：手动把批次置 paused，续跑后已成功的不能再跑一次。"""
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    calls = {"n": 0}

    def _counting(prompt, negative_prompt=""):
        calls["n"] += 1
        return fake_image_bytes

    monkeypatch.setattr(model_client, "generate_image", _counting)

    pid = make_project()["id"]
    batch_id = _upload_csv(client, pid, _csv("C-1,a,,,", "C-2,b,,,", "C-3,c,,,")).json()["id"]

    # 试跑第一条 + 再手动跑一条，然后把批次置 paused
    client.post(f"/api/batches/{batch_id}/trial")
    monkeypatch.setattr(
        batch_runner, "start_batch", lambda bid: batch_runner._run_batch(bid)
    )
    db = SessionLocal()
    try:
        batch = db.get(models.Batch, batch_id)
        batch.status = "paused"
        db.commit()
    finally:
        db.close()

    before = calls["n"]
    resume = client.post(f"/api/batches/{batch_id}/resume")
    assert resume.status_code == 202
    after = calls["n"]

    detail = client.get(f"/api/batches/{batch_id}").json()
    assert detail["succeeded"] == 3
    # 只新增了剩下 2 条，没有重跑已成功的 1 条
    assert after - before == 2


def test_batch_budget_skips_remaining(
    client, make_project, enable_key, sync_batch, fake_image_bytes, monkeypatch
):
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    pid = make_project()["id"]
    batch_id = _upload_csv(client, pid, _csv(*[f"D-{i},杯{i},,," for i in range(5)])).json()["id"]

    # 把批次预算压到只够 2 张
    db = SessionLocal()
    try:
        batch = db.get(models.Batch, batch_id)
        batch.budget_fen = config.T2I_UNIT_PRICE_FEN * 2
        db.commit()
    finally:
        db.close()

    client.post(f"/api/batches/{batch_id}/trial")
    client.post(f"/api/batches/{batch_id}/confirm")

    detail = client.get(f"/api/batches/{batch_id}").json()
    assert detail["succeeded"] <= 3  # 试跑 1 + 预算内 1-2 条
    assert detail["cost_fen"] <= config.T2I_UNIT_PRICE_FEN * 2
    skipped = [i for i in detail["items"] if i["status"] == "skipped"]
    assert skipped, "超出预算的行应标记 skipped"


def test_export_zip_contains_images_and_csv(
    client, make_project, enable_key, sync_batch, fake_image_bytes, monkeypatch
):
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    pid = make_project()["id"]
    batch_id = _upload_csv(client, pid, _csv("E-1,杯,,,", "E-2,杯2,,,")).json()["id"]
    client.post(f"/api/batches/{batch_id}/trial")
    client.post(f"/api/batches/{batch_id}/confirm")

    resp = client.get(f"/api/batches/{batch_id}/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert "清单.csv" in names
    assert "账单.csv" in names
    images = [n for n in names if n.startswith("images/")]
    assert len(images) == 2
    assert any("E-1" in n for n in images)


def test_export_empty_batch_rejected(client, make_project):
    pid = make_project()["id"]
    batch_id = _upload_csv(client, pid, _csv("F-1,杯,,,")).json()["id"]
    resp = client.get(f"/api/batches/{batch_id}/export")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "NOTHING_TO_EXPORT"


def test_skipped_row_for_missing_image(client, make_project):
    pid = make_project()["id"]
    resp = _upload_csv(client, pid, _csv("G-1,杯,,,,not-exist.png", "G-2,杯2,,,"))
    assert resp.status_code == 201
    detail = client.get(f"/api/batches/{resp.json()['id']}").json()
    skipped = [i for i in detail["items"] if i["status"] == "skipped"]
    assert len(skipped) == 1
    assert skipped[0]["error_code"] == "MISSING_IMAGE"


def test_batch_sse_ends_with_done(
    client, make_project, enable_key, sync_batch, fake_image_bytes, monkeypatch
):
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    pid = make_project()["id"]
    batch_id = _upload_csv(client, pid, _csv("H-1,杯,,,")).json()["id"]
    client.post(f"/api/batches/{batch_id}/trial")
    client.post(f"/api/batches/{batch_id}/confirm")

    with client.stream("GET", f"/api/batches/{batch_id}/events") as resp:
        text = "".join(resp.iter_text())
    assert "event: done" in text
    assert '"succeeded": 1' in text


def test_missing_project_404(client):
    resp = client.post(
        "/api/projects/not-exist/batches",
        files={"file": ("a.csv", _csv("X-1,杯,,,"), "text/csv")},
    )
    assert resp.status_code == 404
