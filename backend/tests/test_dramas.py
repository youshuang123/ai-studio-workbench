"""短剧线：分镜表生成、镜头编辑、关键帧、合成。"""

import io
import json

import pytest
from PIL import Image

from app import config, models
from app.db import SessionLocal
from app.services import compose, model_client, runner, storyboard

SCRIPT = """
林小满站在公司楼下的雨里，手里攥着一份被退回的方案。
她抬头看了一眼 28 楼的灯，还是亮的。
电话响起，是母亲：这么晚还不回来？
她说了句"马上"，把手机塞回口袋，转身走进雨里。
"""


@pytest.fixture
def fake_image_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (256, 256), (60, 90, 130)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def enable_keys(monkeypatch):
    monkeypatch.setattr(config, "T2I_API_KEY", "test-key")
    monkeypatch.setattr(config, "LLM_API_KEY", "test-key")


@pytest.fixture
def sync_runner(monkeypatch):
    monkeypatch.setattr(runner, "start_job", lambda jid: runner.run_job(jid))


MOCK_STORYBOARD = {
    "scenes": [
        {
            "title": "雨夜·公司楼下",
            "location": "写字楼门口",
            "time_of_day": "夜",
            "summary": "林小满被退稿后站在雨里",
            "shots": [
                {"shot_size": "中景", "camera": "平视", "action": "林小满站在雨中", "dialogue": "", "duration_sec": 3, "mood": "压抑", "continuity": "手拿方案"},
                {"shot_size": "特写", "camera": "仰拍", "action": "手里的方案被雨打湿", "dialogue": "", "duration_sec": 2.5, "mood": "委屈", "continuity": "同上"},
                {"shot_size": "全景", "camera": "俯拍", "action": "她抬头看高楼", "dialogue": "", "duration_sec": 4, "mood": "无力", "continuity": "灯光未灭"},
            ],
        },
        {
            "title": "雨夜·电话",
            "location": "街边",
            "time_of_day": "夜",
            "summary": "母亲来电",
            "shots": [
                {"shot_size": "近景", "camera": "平视", "action": "手机亮起，她接起", "dialogue": "妈，马上回去", "duration_sec": 3, "mood": "疲惫", "continuity": "雨未停"},
            ],
        },
    ]
}


# ── 纯函数 ──


def test_validate_storyboard_normalizes_fields():
    out = storyboard.validate_storyboard(MOCK_STORYBOARD)
    shots = [s for sc in out["scenes"] for s in sc["shots"]]
    assert len(shots) == 4
    assert all(s["shot_size"] in storyboard.SHOT_SIZES for s in shots)
    assert all(2 <= s["duration_sec"] <= 8 for s in shots)


def test_validate_clamps_bad_values():
    data = {
        "scenes": [
            {
                "title": "x",
                "shots": [
                    {"shot_size": "超广角", "camera": "无人机", "action": "a", "duration_sec": 99},
                ],
            }
        ]
    }
    out = storyboard.validate_storyboard(data)
    shot = out["scenes"][0]["shots"][0]
    assert shot["shot_size"] == "中景"  # 非法值回退
    assert shot["camera"] == "平视"
    assert shot["duration_sec"] == 8.0  # 被夹紧


def test_validate_drops_shots_without_action():
    data = {"scenes": [{"title": "x", "shots": [{"shot_size": "中景"}, {"shot_size": "中景", "action": "有动作"}]}]}
    out = storyboard.validate_storyboard(data)
    assert len(out["scenes"][0]["shots"]) == 1


def test_validate_empty_raises():
    with pytest.raises(storyboard.StoryboardError) as exc:
        storyboard.validate_storyboard({"scenes": []})
    assert exc.value.code == "STORYBOARD_INVALID"


def test_shot_prompt_includes_shot_and_style():
    shot = {"shot_size": "近景", "camera": "平视", "action": "她抬头", "mood": "疲惫", "character_ids": []}
    text = storyboard.shot_prompt(shot, {"location": "街边", "time_of_day": "夜"}, [], "都市")
    assert "近景" in text and "她抬头" in text and "街边" in text
    assert "文字" in text  # 负向约束


# ── 分镜表 API ──


def test_generate_storyboard_success(client, make_project, enable_keys, monkeypatch):
    monkeypatch.setattr(storyboard, "_chat", lambda *a, **k: json.dumps(MOCK_STORYBOARD))
    pid = make_project()["id"]

    drama = client.post(
        f"/api/projects/{pid}/dramas",
        json={"title": "雨夜", "script_text": SCRIPT, "style": "都市"},
    ).json()
    assert drama["shots"] == []

    resp = client.post(f"/api/dramas/{drama['id']}/storyboard", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["scenes"]) == 2
    assert len(body["shots"]) == 4
    assert body["shots"][0]["shot_size"] == "中景"
    assert body["status"] == "storyboard_ready"


def test_generate_storyboard_retries_on_bad_json(client, make_project, enable_keys, monkeypatch):
    calls = {"n": 0}

    def _chat(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return "这不是 JSON"
        return json.dumps(MOCK_STORYBOARD)

    monkeypatch.setattr(storyboard, "_chat", _chat)
    pid = make_project()["id"]
    drama = client.post(
        f"/api/projects/{pid}/dramas", json={"title": "t", "script_text": SCRIPT}
    ).json()

    resp = client.post(f"/api/dramas/{drama['id']}/storyboard", json={})
    assert resp.status_code == 200
    assert calls["n"] == 2
    assert resp.json()["llm_attempts"] == 2


def test_generate_storyboard_fails_after_retry(client, make_project, enable_keys, monkeypatch):
    monkeypatch.setattr(storyboard, "_chat", lambda *a, **k: "还是不是 JSON")
    pid = make_project()["id"]
    drama = client.post(
        f"/api/projects/{pid}/dramas", json={"title": "t", "script_text": SCRIPT}
    ).json()

    resp = client.post(f"/api/dramas/{drama['id']}/storyboard", json={})
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] in ("STORYBOARD_INVALID", "STORYBOARD_EMPTY")


def test_create_drama_rejects_empty_script(client, make_project):
    pid = make_project()["id"]
    resp = client.post(f"/api/projects/{pid}/dramas", json={"title": "t", "script_text": "  "})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SCRIPT_EMPTY"


# ── 镜头编辑 ──


@pytest.fixture
def drama_with_shots(client, make_project, enable_keys, monkeypatch):
    monkeypatch.setattr(storyboard, "_chat", lambda *a, **k: json.dumps(MOCK_STORYBOARD))
    pid = make_project()["id"]
    drama = client.post(
        f"/api/projects/{pid}/dramas", json={"title": "雨夜", "script_text": SCRIPT}
    ).json()
    client.post(f"/api/dramas/{drama['id']}/storyboard", json={})
    return client.get(f"/api/dramas/{drama['id']}").json()


def test_update_shot(client, drama_with_shots):
    drama = drama_with_shots
    shot = drama["shots"][0]
    resp = client.patch(
        f"/api/dramas/{drama['id']}/shots/{shot['id']}",
        json={"dialogue": "改过的台词", "duration_sec": 5},
    )
    assert resp.status_code == 200
    assert resp.json()["dialogue"] == "改过的台词"
    assert resp.json()["duration_sec"] == 5


def test_update_shot_clears_keyframe(client, drama_with_shots):
    drama = drama_with_shots
    shot = drama["shots"][0]
    # 假装有关键帧
    db = SessionLocal()
    try:
        s = db.get(models.DramaShot, shot["id"])
        s.job_id = "fake-job"
        db.commit()
    finally:
        db.close()

    client.patch(f"/api/dramas/{drama['id']}/shots/{shot['id']}", json={"action": "改了"})
    detail = client.get(f"/api/dramas/{drama['id']}").json()
    updated = [s for s in detail["shots"] if s["id"] == shot["id"]][0]
    assert updated["job_id"] is None  # 内容改了旧帧作废


def test_add_and_delete_shot(client, drama_with_shots):
    drama = drama_with_shots
    before = len(drama["shots"])
    created = client.post(
        f"/api/dramas/{drama['id']}/shots", json={"action": "新增镜头", "shot_size": "特写"}
    ).json()
    assert created["index"] == before + 1

    detail = client.get(f"/api/dramas/{drama['id']}").json()
    assert len(detail["shots"]) == before + 1

    client.delete(f"/api/dramas/{drama['id']}/shots/{created['id']}")
    detail = client.get(f"/api/dramas/{drama['id']}").json()
    assert len(detail["shots"]) == before
    # 序号连续
    assert [s["index"] for s in detail["shots"]] == list(range(1, before + 1))


def test_reorder_shots(client, drama_with_shots):
    drama = drama_with_shots
    ids = [s["id"] for s in drama["shots"]]
    reversed_ids = list(reversed(ids))
    resp = client.post(f"/api/dramas/{drama['id']}/shots/reorder", json={"shot_ids": reversed_ids})
    assert resp.status_code == 200

    detail = client.get(f"/api/dramas/{drama['id']}").json()
    assert [s["id"] for s in detail["shots"]] == reversed_ids


def test_shot_from_other_drama_is_404(client, drama_with_shots, make_project):
    other = client.post(
        f"/api/projects/{make_project()['id']}/dramas",
        json={"title": "别的", "script_text": "剧本"},
    ).json()
    shot = drama_with_shots["shots"][0]
    resp = client.patch(f"/api/dramas/{other['id']}/shots/{shot['id']}", json={"action": "x"})
    assert resp.status_code == 404


# ── 角色 ──


def test_add_character(client, drama_with_shots):
    drama = drama_with_shots
    resp = client.post(
        f"/api/dramas/{drama['id']}/characters",
        json={"name": "林小满", "appearance": "25 岁女性，齐肩黑发", "costume": "米色针织衫"},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "林小满"
    assert resp.json()["ref_asset_id"] is None


def test_character_ref_generation(client, drama_with_shots, enable_keys, sync_runner, fake_image_bytes, monkeypatch):
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    drama = drama_with_shots
    c = client.post(
        f"/api/dramas/{drama['id']}/characters", json={"name": "林小满", "appearance": "黑发"}
    ).json()

    resp = client.post(f"/api/dramas/{drama['id']}/characters/{c['id']}/ref")
    assert resp.status_code == 200, resp.text
    assert resp.json()["ref_asset_id"]
    assert resp.json()["cost_fen"] == config.T2I_UNIT_PRICE_FEN


# ── 关键帧 ──


def test_generate_keyframes(client, drama_with_shots, enable_keys, sync_runner, fake_image_bytes, monkeypatch):
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    drama = drama_with_shots

    resp = client.post(f"/api/dramas/{drama['id']}/keyframes", json={})
    assert resp.status_code == 202, resp.text
    assert resp.json()["created"] == len(drama["shots"])

    detail = client.get(f"/api/dramas/{drama['id']}").json()
    with_frames = [s for s in detail["shots"] if s["job"] and s["job"]["status"] == "succeeded"]
    assert len(with_frames) == len(drama["shots"])


def test_generate_keyframes_noop_when_all_present(
    client, drama_with_shots, enable_keys, sync_runner, fake_image_bytes, monkeypatch
):
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    drama = drama_with_shots
    client.post(f"/api/dramas/{drama['id']}/keyframes", json={})

    resp = client.post(f"/api/dramas/{drama['id']}/keyframes", json={})
    assert resp.status_code == 409


# ── 合成 ──


def test_compose_requires_keyframes(client, drama_with_shots):
    drama = drama_with_shots
    resp = client.post(f"/api/dramas/{drama['id']}/compose")
    assert resp.status_code == 409
    assert "没有关键帧" in resp.json()["error"]["message"]


def test_compose_produces_mp4(client, drama_with_shots, enable_keys, sync_runner, fake_image_bytes, monkeypatch):
    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    drama = drama_with_shots
    client.post(f"/api/dramas/{drama['id']}/keyframes", json={})

    resp = client.post(f"/api/dramas/{drama['id']}/compose")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["duration_sec"] and body["duration_sec"] > 3
    assert body["size"] == [720, 720]

    video = client.get(f"/api/dramas/{drama['id']}/video")
    assert video.status_code == 200
    assert video.headers["content-type"] == "video/mp4"
    assert len(video.content) > 10_000


def test_motion_by_shot_size():
    assert compose.motion_for("远景") == "zoom_in"
    assert compose.motion_for("中景") == "pan_right"
    assert compose.motion_for("特写") == "zoom_in_up"


def test_export_zip(client, drama_with_shots, enable_keys, sync_runner, fake_image_bytes, monkeypatch):
    import zipfile

    monkeypatch.setattr(model_client, "generate_image", lambda p, n="": fake_image_bytes)
    drama = drama_with_shots
    client.post(f"/api/dramas/{drama['id']}/keyframes", json={})
    client.post(f"/api/dramas/{drama['id']}/compose")

    resp = client.get(f"/api/dramas/{drama['id']}/export")
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert "分镜表.csv" in names
    assert "成片.mp4" in names
    assert any(n.startswith("keyframes/") for n in names)


def test_drama_from_other_project_404(client):
    resp = client.get("/api/dramas/not-exist")
    assert resp.status_code == 404
