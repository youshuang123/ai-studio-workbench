"""质检（VLM 打分 + 精修流程）测试。"""

import io
import json

import pytest
from PIL import Image

from app import config, models
from app.db import SessionLocal
from app.services import model_client, qa, runner


@pytest.fixture
def fake_image_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (128, 128), (25, 55, 95)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def enable_keys(monkeypatch):
    monkeypatch.setattr(config, "T2I_API_KEY", "test-key")
    monkeypatch.setattr(config, "EDIT_API_KEY", "test-key")
    monkeypatch.setattr(config, "VLM_API_KEY", "test-key")


@pytest.fixture
def sync_runner(monkeypatch):
    monkeypatch.setattr(runner, "start_job", lambda jid: runner.run_job(jid))


@pytest.fixture
def pass_qa(monkeypatch):
    """默认质检通过，避免测试依赖外网。"""
    monkeypatch.setattr(
        qa,
        "evaluate",
        lambda *a, **k: {
            "ok": True,
            "follows_description": 3,
            "no_text_or_watermark": 3,
            "product_complete": 3,
            "background_clean": 3,
            "total": 12,
            "issues": [],
            "verdict": "pass",
        },
    )


def _draft(client, pid, asset_id):
    resp = client.post(
        f"/api/projects/{pid}/generations",
        json={"source_asset_id": asset_id, "product_name": "保温杯"},
    )
    return resp.json()["job_id"]


# ── 纯函数 ──


def test_normalize_fills_missing_dims():
    out = qa.normalize({"follows_description": 3})
    assert out["follows_description"] == 3
    assert out["no_text_or_watermark"] == 2  # 缺失补默认
    assert out["color_consistency"] is None  # 无参考图时不参与
    assert out["total"] == 3 + 2 * 3
    assert out["max_total"] == 12


def test_normalize_with_reference_includes_color_dim():
    out = qa.normalize({"follows_description": 3, "color_consistency": 3}, has_reference=True)
    assert out["color_consistency"] == 3
    assert out["max_total"] == 15


def test_verdict_thresholds():
    # 按平均分判定：4 维总分 12 → 平均 3.0 pass；10 → 2.5 pass
    assert qa.verdict_for(12, 4) == "pass"
    assert qa.verdict_for(10, 4) == "pass"
    assert qa.verdict_for(9, 4) == "warn"
    assert qa.verdict_for(8, 4) == "warn"
    assert qa.verdict_for(6, 4) == "fail"
    # 5 维（有参考图）
    assert qa.verdict_for(13, 5) == "pass"
    assert qa.verdict_for(10, 5) == "warn"
    assert qa.verdict_for(6, 5) == "fail"


def test_clamp_score_bounds():
    assert qa.clamp_score(99) == 3
    assert qa.clamp_score(-5) == 1
    assert qa.clamp_score("x") == 2


def test_issues_are_limited():
    out = qa.normalize(
        {"follows_description": 3, "no_text_or_watermark": 1, "issues": ["a"] * 20}
    )
    assert len(out["issues"]) == 5


# ── 精修流程 ──


def test_refine_creates_new_job_and_keeps_draft(
    client, make_asset, enable_keys, sync_runner, fake_image_bytes, pass_qa, monkeypatch
):
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    monkeypatch.setattr(model_client, "generate_edit", lambda p, src, mime="image/png": fake_image_bytes)

    pid, asset = make_asset()
    draft_id = _draft(client, pid, asset["id"])
    assert client.get(f"/api/jobs/{draft_id}").json()["status"] == "succeeded"

    resp = client.post(f"/api/jobs/{draft_id}/refine")
    assert resp.status_code == 202, resp.text
    refined_id = resp.json()["job_id"]
    assert refined_id != draft_id

    refined = client.get(f"/api/jobs/{refined_id}").json()
    assert refined["status"] == "succeeded"
    assert refined["stage"] == "refined"
    assert refined["refined_from"] == draft_id
    assert refined["unit_price_fen"] == config.EDIT_UNIT_PRICE_FEN

    # 草稿还在，没被覆盖
    draft = client.get(f"/api/jobs/{draft_id}").json()
    assert draft["status"] == "succeeded"
    assert draft["output_asset_id"] != refined["output_asset_id"]


def test_refine_runs_qa_and_records_score(
    client, make_asset, enable_keys, sync_runner, fake_image_bytes, pass_qa, monkeypatch
):
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    monkeypatch.setattr(model_client, "generate_edit", lambda p, src, mime="image/png": fake_image_bytes)

    pid, asset = make_asset()
    draft_id = _draft(client, pid, asset["id"])
    refined_id = client.post(f"/api/jobs/{draft_id}/refine").json()["job_id"]

    refined = client.get(f"/api/jobs/{refined_id}").json()
    assert refined["qa_score"] == 12
    detail = json.loads(refined["qa_detail"])
    assert detail["verdict"] == "pass"
    # 同色图，ΔE 应该接近 0
    assert refined["delta_e"] is not None
    assert refined["delta_e"] < 1


def test_refine_rejects_unfinished_job(client, make_asset, enable_keys, monkeypatch):
    monkeypatch.setattr(runner, "start_job", lambda jid: None)  # 任务停在 queued
    pid, asset = make_asset()
    draft_id = _draft(client, pid, asset["id"])

    resp = client.post(f"/api/jobs/{draft_id}/refine")
    assert resp.status_code == 409


def test_refine_rejects_refined_job(
    client, make_asset, enable_keys, sync_runner, fake_image_bytes, pass_qa, monkeypatch
):
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    monkeypatch.setattr(model_client, "generate_edit", lambda p, src, mime="image/png": fake_image_bytes)

    pid, asset = make_asset()
    draft_id = _draft(client, pid, asset["id"])
    refined_id = client.post(f"/api/jobs/{draft_id}/refine").json()["job_id"]

    resp = client.post(f"/api/jobs/{refined_id}/refine")
    assert resp.status_code == 409


def test_refine_failure_keeps_draft(
    client, make_asset, enable_keys, sync_runner, fake_image_bytes, pass_qa, monkeypatch
):
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)

    def _boom(p, src, mime="image/png"):
        raise model_client.ModelError("MODEL_TIMEOUT", "精修超时")

    monkeypatch.setattr(model_client, "generate_edit", _boom)

    pid, asset = make_asset()
    draft_id = _draft(client, pid, asset["id"])
    refined_id = client.post(f"/api/jobs/{draft_id}/refine").json()["job_id"]

    refined = client.get(f"/api/jobs/{refined_id}").json()
    assert refined["status"] == "failed"
    assert refined["error_code"] == "MODEL_TIMEOUT"

    draft = client.get(f"/api/jobs/{draft_id}").json()
    assert draft["status"] == "succeeded"
    assert draft["output_asset_id"]


def test_refine_without_edit_key(client, make_asset, monkeypatch):
    monkeypatch.setattr(config, "T2I_API_KEY", "test-key")
    monkeypatch.setattr(config, "EDIT_API_KEY", "")
    monkeypatch.setattr(runner, "start_job", lambda jid: None)
    pid, asset = make_asset()
    draft_id = _draft(client, pid, asset["id"])

    resp = client.post(f"/api/jobs/{draft_id}/refine")
    # 草稿能建（T2I 可用），精修因缺 Key 被拒
    assert resp.status_code in (409, 503)


def test_qa_endpoint_reruns(client, make_asset, enable_keys, sync_runner, fake_image_bytes, pass_qa, monkeypatch):
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    monkeypatch.setattr(model_client, "generate_edit", lambda p, src, mime="image/png": fake_image_bytes)

    pid, asset = make_asset()
    draft_id = _draft(client, pid, asset["id"])
    refined_id = client.post(f"/api/jobs/{draft_id}/refine").json()["job_id"]

    resp = client.post(f"/api/jobs/{refined_id}/qa")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["qa_score"] == 12


def test_qa_endpoint_handles_vlm_not_configured(client, make_asset, enable_keys, monkeypatch):
    monkeypatch.setattr(config, "VLM_API_KEY", "")
    monkeypatch.setattr(runner, "start_job", lambda jid: None)
    pid, asset = make_asset()
    draft_id = _draft(client, pid, asset["id"])
    resp = client.post(f"/api/jobs/{draft_id}/qa")
    # 草稿未成功 → 409；若成功则 503
    assert resp.status_code in (409, 503)


# ── 批量精修 ──


def test_batch_refine_limits_and_cost(
    client, make_project, make_asset, enable_keys, sync_runner, fake_image_bytes, pass_qa, monkeypatch
):
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    monkeypatch.setattr(model_client, "generate_edit", lambda p, src, mime="image/png": fake_image_bytes)

    from app.services import batch_runner

    monkeypatch.setattr(batch_runner, "start_batch", lambda bid: batch_runner._run_batch(bid))

    pid, asset = make_asset()
    csv = "sku_code,product_name\nR-1,杯1\nR-2,杯2\n"
    batch_id = client.post(
        f"/api/projects/{pid}/batches",
        files={"file": ("r.csv", csv.encode("utf-8"), "text/csv")},
    ).json()["id"]
    client.post(f"/api/batches/{batch_id}/trial")
    client.post(f"/api/batches/{batch_id}/confirm")

    items = client.get(f"/api/batches/{batch_id}").json()["items"]
    ids = [i["id"] for i in items if i["status"] == "succeeded"]
    assert ids

    resp = client.post(f"/api/batches/{batch_id}/refine", json={"item_ids": ids})
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["created"] == len(ids)
    assert body["estimated_cost_fen"] == config.EDIT_UNIT_PRICE_FEN * len(ids)


def test_batch_refine_rejects_too_many(client, make_project, enable_keys):
    pid = make_project()["id"]
    csv = "sku_code,product_name\n" + "\n".join(f"X-{i},杯{i}" for i in range(3))
    batch_id = client.post(
        f"/api/projects/{pid}/batches",
        files={"file": ("x.csv", csv.encode("utf-8"), "text/csv")},
    ).json()["id"]

    too_many = [f"id-{i}" for i in range(config.BATCH_REFINE_LIMIT + 1)]
    resp = client.post(f"/api/batches/{batch_id}/refine", json={"item_ids": too_many})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "TOO_MANY_ITEMS"
