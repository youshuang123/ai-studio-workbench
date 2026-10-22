import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from .. import config, models
from ..db import get_db
from ..errors import AppError, bad_request, conflict, not_found
from ..services import compose, runner, storage, storyboard

router = APIRouter(prefix="/api", tags=["dramas"])


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def _shot_out(shot: models.DramaShot) -> dict:
    job = None
    if shot.job_id:
        pass  # 由调用方补充（避免 N+1）
    try:
        char_ids = json.loads(shot.character_ids or "[]")
    except json.JSONDecodeError:
        char_ids = []
    return {
        "id": shot.id,
        "scene_id": shot.scene_id,
        "index": shot.index,
        "shot_size": shot.shot_size,
        "camera": shot.camera,
        "action": shot.action,
        "dialogue": shot.dialogue,
        "duration_sec": shot.duration_sec,
        "continuity": shot.continuity,
        "mood": shot.mood,
        "character_ids": char_ids,
        "job_id": shot.job_id,
    }


def _character_out(c: models.DramaCharacter) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "appearance": c.appearance,
        "costume": c.costume,
        "personality": c.personality,
        "ref_asset_id": c.ref_asset_id,
    }


def _get_drama_or_404(drama_id: str, db: Session) -> models.Drama:
    drama = db.get(models.Drama, drama_id)
    if drama is None:
        raise not_found("短剧不存在")
    return drama


def _drama_detail(drama: models.Drama, db: Session) -> dict:
    scenes = (
        db.query(models.DramaScene)
        .filter(models.DramaScene.drama_id == drama.id)
        .order_by(models.DramaScene.index)
        .all()
    )
    shots = (
        db.query(models.DramaShot)
        .filter(models.DramaShot.drama_id == drama.id)
        .order_by(models.DramaShot.index)
        .all()
    )
    characters = (
        db.query(models.DramaCharacter)
        .filter(models.DramaCharacter.drama_id == drama.id)
        .order_by(models.DramaCharacter.created_at)
        .all()
    )

    job_ids = [s.job_id for s in shots if s.job_id]
    jobs = {}
    if job_ids:
        for j in db.query(models.GenerationJob).filter(models.GenerationJob.id.in_(job_ids)).all():
            jobs[j.id] = j

    shot_items = []
    for s in shots:
        item = _shot_out(s)
        j = jobs.get(s.job_id) if s.job_id else None
        if j is not None:
            item["job"] = {
                "id": j.id,
                "status": j.status,
                "stage": getattr(j, "stage", "draft") or "draft",
                "output_asset_id": j.output_asset_id,
                "cost_fen": j.cost_fen,
                "qa_score": getattr(j, "qa_score", None),
                "error_code": j.error_code,
                "error_message": j.error_message,
            }
        else:
            item["job"] = None
        shot_items.append(item)

    return {
        "id": drama.id,
        "project_id": drama.project_id,
        "title": drama.title,
        "script_text": drama.script_text,
        "style": drama.style,
        "status": drama.status,
        "video_path": drama.video_path,
        "created_at": _iso(drama.created_at),
        "scenes": [
            {
                "id": sc.id,
                "index": sc.index,
                "title": sc.title,
                "location": sc.location,
                "time_of_day": sc.time_of_day,
                "summary": sc.summary,
            }
            for sc in scenes
        ],
        "shots": shot_items,
        "characters": [_character_out(c) for c in characters],
    }


# ────────────────────────── 短剧 CRUD ──────────────────────────


@router.post("/projects/{project_id}/dramas", status_code=201)
def create_drama(project_id: str, body: dict, db: Session = Depends(get_db)):
    project = db.get(models.Project, project_id)
    if project is None:
        raise not_found("项目不存在")

    script = (body.get("script_text") or "").strip()
    if not script:
        raise bad_request("剧本文本不能为空", "SCRIPT_EMPTY")
    if len(script) > 8000:
        raise bad_request("剧本过长（上限 8000 字）", "SCRIPT_TOO_LONG")

    drama = models.Drama(
        project_id=project_id,
        title=(body.get("title") or "未命名短剧").strip()[:120],
        script_text=script,
        style=(body.get("style") or "都市").strip()[:40],
    )
    db.add(drama)
    db.commit()
    db.refresh(drama)
    return _drama_detail(drama, db)


@router.get("/projects/{project_id}/dramas")
def list_dramas(project_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(models.Drama)
        .filter(models.Drama.project_id == project_id)
        .order_by(models.Drama.created_at.desc())
        .limit(20)
        .all()
    )
    return {
        "items": [
            {
                "id": d.id,
                "title": d.title,
                "style": d.style,
                "status": d.status,
                "created_at": _iso(d.created_at),
            }
            for d in rows
        ],
        "total": len(rows),
    }


@router.get("/dramas/{drama_id}")
def get_drama(drama_id: str, db: Session = Depends(get_db)):
    drama = _get_drama_or_404(drama_id, db)
    return _drama_detail(drama, db)


@router.post("/dramas/{drama_id}/storyboard")
def make_storyboard(drama_id: str, body: dict | None = None, db: Session = Depends(get_db)):
    """调 LLM 生成分镜表。默认覆盖现有分镜（append=true 则追加）。"""
    drama = _get_drama_or_404(drama_id, db)
    append = bool((body or {}).get("append"))
    script = (body or {}).get("script_text") or drama.script_text
    if (body or {}).get("script_text"):
        drama.script_text = str(body["script_text"])[:8000]

    characters = (
        db.query(models.DramaCharacter)
        .filter(models.DramaCharacter.drama_id == drama.id)
        .all()
    )
    try:
        result, attempts = storyboard.generate(
            script, [c.name for c in characters], drama.style
        )
    except storyboard.StoryboardError as exc:
        raise AppError(502, exc.code, exc.message)

    if not append:
        db.query(models.DramaShot).filter(models.DramaShot.drama_id == drama.id).delete()
        db.query(models.DramaScene).filter(models.DramaScene.drama_id == drama.id).delete()
        db.flush()

    start_index = (
        db.query(models.DramaShot).filter(models.DramaShot.drama_id == drama.id).count()
        if append
        else 0
    )
    scene_base = (
        db.query(models.DramaScene).filter(models.DramaScene.drama_id == drama.id).count()
        if append
        else 0
    )

    shot_no = start_index
    for sc in result["scenes"]:
        scene = models.DramaScene(
            drama_id=drama.id,
            index=scene_base + sc["index"],
            title=sc["title"],
            location=sc["location"],
            time_of_day=sc["time_of_day"],
            summary=sc["summary"],
        )
        db.add(scene)
        db.flush()
        for sh in sc["shots"]:
            shot_no += 1
            db.add(
                models.DramaShot(
                    drama_id=drama.id,
                    scene_id=scene.id,
                    index=shot_no,
                    shot_size=sh["shot_size"],
                    camera=sh["camera"],
                    action=sh["action"],
                    dialogue=sh["dialogue"],
                    duration_sec=sh["duration_sec"],
                    continuity=sh["continuity"],
                    mood=sh["mood"],
                )
            )
    drama.status = "storyboard_ready"
    db.commit()
    db.refresh(drama)
    detail = _drama_detail(drama, db)
    detail["llm_attempts"] = attempts
    return detail


# ────────────────────────── 镜头编辑 ──────────────────────────


@router.patch("/dramas/{drama_id}/shots/{shot_id}")
def update_shot(drama_id: str, shot_id: str, body: dict, db: Session = Depends(get_db)):
    shot = db.get(models.DramaShot, shot_id)
    if shot is None or shot.drama_id != drama_id:
        raise not_found("镜头不存在")

    allowed = {"shot_size", "camera", "action", "dialogue", "continuity", "mood"}
    for key in allowed:
        if key in body:
            setattr(shot, key, str(body[key])[:500])
    if "duration_sec" in body:
        try:
            shot.duration_sec = max(2.0, min(8.0, float(body["duration_sec"])))
        except (TypeError, ValueError):
            raise bad_request("时长必须是数字", "VALIDATION_ERROR")
    if "character_ids" in body and isinstance(body["character_ids"], list):
        shot.character_ids = json.dumps([str(x) for x in body["character_ids"]][:5])
    # 分镜内容改了，旧关键帧就不再对应 → 清空，等重新生成
    shot.job_id = None
    db.commit()
    db.refresh(shot)
    return _shot_out(shot)


@router.post("/dramas/{drama_id}/shots", status_code=201)
def add_shot(drama_id: str, body: dict, db: Session = Depends(get_db)):
    drama = _get_drama_or_404(drama_id, db)
    after_id = body.get("after_shot_id")
    max_index = (
        db.query(models.DramaShot)
        .filter(models.DramaShot.drama_id == drama.id)
        .count()
    )
    scene_id = body.get("scene_id")
    shot = models.DramaShot(
        drama_id=drama.id,
        scene_id=scene_id,
        index=max_index + 1,
        shot_size=str(body.get("shot_size") or "中景")[:20],
        camera=str(body.get("camera") or "平视")[:20],
        action=str(body.get("action") or "（待补充）")[:500],
        dialogue=str(body.get("dialogue") or "")[:500],
        duration_sec=float(body.get("duration_sec") or 3),
        mood=str(body.get("mood") or "")[:40],
        continuity=str(body.get("continuity") or "")[:300],
    )
    db.add(shot)
    db.flush()

    if after_id:
        _reorder_after(db, drama.id, after_id, shot.id)

    db.commit()
    db.refresh(shot)
    return _shot_out(shot)


@router.delete("/dramas/{drama_id}/shots/{shot_id}")
def delete_shot(drama_id: str, shot_id: str, db: Session = Depends(get_db)):
    shot = db.get(models.DramaShot, shot_id)
    if shot is None or shot.drama_id != drama_id:
        raise not_found("镜头不存在")
    db.delete(shot)
    db.commit()
    _renumber(db, drama_id)
    return {"deleted": shot_id}


@router.post("/dramas/{drama_id}/shots/reorder")
def reorder_shots(drama_id: str, body: dict, db: Session = Depends(get_db)):
    ids = body.get("shot_ids") or []
    if not isinstance(ids, list) or not ids:
        raise bad_request("请提供镜头顺序", "VALIDATION_ERROR")
    shots = (
        db.query(models.DramaShot)
        .filter(models.DramaShot.drama_id == drama_id, models.DramaShot.id.in_(ids))
        .all()
    )
    by_id = {s.id: s for s in shots}
    for i, sid in enumerate(ids, start=1):
        if sid in by_id:
            by_id[sid].index = i
    db.commit()
    return {"ok": True, "count": len(ids)}


def _renumber(db: Session, drama_id: str) -> None:
    shots = (
        db.query(models.DramaShot)
        .filter(models.DramaShot.drama_id == drama_id)
        .order_by(models.DramaShot.index)
        .all()
    )
    for i, s in enumerate(shots, start=1):
        s.index = i
    db.commit()


def _reorder_after(db: Session, drama_id: str, after_id: str, new_id: str) -> None:
    shots = (
        db.query(models.DramaShot)
        .filter(models.DramaShot.drama_id == drama_id)
        .order_by(models.DramaShot.index)
        .all()
    )
    ordered = [s.id for s in shots if s.id != new_id]
    if after_id in ordered:
        pos = ordered.index(after_id) + 1
        ordered.insert(pos, new_id)
    else:
        ordered.append(new_id)
    by_id = {s.id: s for s in shots}
    for i, sid in enumerate(ordered, start=1):
        if sid in by_id:
            by_id[sid].index = i


# ────────────────────────── 角色 ──────────────────────────


@router.post("/dramas/{drama_id}/characters", status_code=201)
def add_character(drama_id: str, body: dict, db: Session = Depends(get_db)):
    drama = _get_drama_or_404(drama_id, db)
    name = (body.get("name") or "").strip()
    if not name:
        raise bad_request("角色名不能为空", "VALIDATION_ERROR")
    character = models.DramaCharacter(
        drama_id=drama.id,
        name=name[:40],
        appearance=str(body.get("appearance") or "")[:500],
        costume=str(body.get("costume") or "")[:300],
        personality=str(body.get("personality") or "")[:300],
    )
    db.add(character)
    db.commit()
    db.refresh(character)
    return _character_out(character)


@router.delete("/dramas/{drama_id}/characters/{char_id}")
def delete_character(drama_id: str, char_id: str, db: Session = Depends(get_db)):
    c = db.get(models.DramaCharacter, char_id)
    if c is None or c.drama_id != drama_id:
        raise not_found("角色不存在")
    db.delete(c)
    db.commit()
    return {"deleted": char_id}


@router.post("/dramas/{drama_id}/characters/{char_id}/ref")
def make_character_ref(drama_id: str, char_id: str, db: Session = Depends(get_db)):
    """生成角色参考图（文生图，¥0.03）。同步执行，约 10 秒。"""
    c = db.get(models.DramaCharacter, char_id)
    if c is None or c.drama_id != drama_id:
        raise not_found("角色不存在")
    if not config.t2i_configured():
        raise AppError(503, "MODEL_NOT_CONFIGURED", "未配置模型 API Key")

    drama = _get_drama_or_404(drama_id, db)
    prompt = (
        f"角色定妆照：{c.name}。{c.appearance}。{c.costume}。"
        f"正面半身，纯白背景，影棚布光，清晰五官。风格：{drama.style}。"
        "画面中不要出现任何文字、水印。"
    )
    job = models.GenerationJob(
        project_id=drama.project_id,
        status="queued",
        product_name=f"{c.name}-定妆照",
        prompt=prompt,
        negative_prompt="text, watermark, logo, extra fingers, deformed",
        provider=config.T2I_BASE_URL,
        model=config.T2I_MODEL,
        unit_price_fen=config.T2I_UNIT_PRICE_FEN,
        budget_fen=config.T2I_UNIT_PRICE_FEN * 10,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    runner.run_job(job.id)
    db.refresh(job)
    if job.status == "succeeded" and job.output_asset_id:
        c.ref_asset_id = job.output_asset_id
        db.commit()
        db.refresh(c)
        return {**_character_out(c), "job_status": job.status, "cost_fen": job.cost_fen}
    raise AppError(502, job.error_code or "REF_FAILED", job.error_message or "定妆照生成失败")


# ────────────────────────── 关键帧 ──────────────────────────


@router.post("/dramas/{drama_id}/keyframes", status_code=202)
def make_keyframes(drama_id: str, body: dict | None = None, db: Session = Depends(get_db)):
    """为缺关键帧的镜头批量生成（文生图草稿，¥0.03/张）。"""
    drama = _get_drama_or_404(drama_id, db)
    if not config.t2i_configured():
        raise AppError(503, "MODEL_NOT_CONFIGURED", "未配置模型 API Key")

    only_ids = (body or {}).get("shot_ids")
    query = db.query(models.DramaShot).filter(models.DramaShot.drama_id == drama.id)
    if only_ids:
        query = query.filter(models.DramaShot.id.in_(only_ids))
    shots = query.order_by(models.DramaShot.index).all()

    todo = [s for s in shots if not s.job_id]
    if not todo:
        raise conflict("所有镜头都有关键帧了")

    scenes = {
        sc.id: sc
        for sc in db.query(models.DramaScene)
        .filter(models.DramaScene.drama_id == drama.id)
        .all()
    }
    characters = [
        _character_out(c)
        for c in db.query(models.DramaCharacter)
        .filter(models.DramaCharacter.drama_id == drama.id)
        .all()
    ]

    created = []
    for shot in todo:
        scene = scenes.get(shot.scene_id) or {"location": "", "time_of_day": ""}
        prompt = storyboard.shot_prompt(
            {
                "shot_size": shot.shot_size,
                "camera": shot.camera,
                "action": shot.action,
                "mood": shot.mood,
                "continuity": shot.continuity,
                "character_ids": json.loads(shot.character_ids or "[]"),
            },
            {"location": scene.location if hasattr(scene, "location") else scene.get("location"),
             "time_of_day": scene.time_of_day if hasattr(scene, "time_of_day") else scene.get("time_of_day")},
            characters,
            drama.style,
        )
        job = models.GenerationJob(
            project_id=drama.project_id,
            status="queued",
            product_name=f"第{shot.index}镜-{shot.shot_size}",
            prompt=prompt,
            negative_prompt="text, watermark, subtitle, logo",
            provider=config.T2I_BASE_URL,
            model=config.T2I_MODEL,
            unit_price_fen=config.T2I_UNIT_PRICE_FEN,
            budget_fen=config.T2I_UNIT_PRICE_FEN * 20,
        )
        db.add(job)
        db.flush()
        shot.job_id = job.id
        created.append(job.id)
    drama.status = "keyframes_generating"
    db.commit()

    for jid in created:
        runner.start_job(jid)

    return {
        "created": len(created),
        "job_ids": created,
        "estimated_cost_fen": config.T2I_UNIT_PRICE_FEN * len(created),
    }


@router.post("/dramas/{drama_id}/shots/{shot_id}/keyframe", status_code=202)
def regen_keyframe(drama_id: str, shot_id: str, db: Session = Depends(get_db)):
    shot = db.get(models.DramaShot, shot_id)
    if shot is None or shot.drama_id != drama_id:
        raise not_found("镜头不存在")
    shot.job_id = None
    db.commit()
    return make_keyframes(drama_id, {"shot_ids": [shot_id]}, db)


# ────────────────────────── 合成与导出 ──────────────────────────


@router.post("/dramas/{drama_id}/compose")
def compose_video(drama_id: str, db: Session = Depends(get_db)):
    drama = _get_drama_or_404(drama_id, db)
    shots = (
        db.query(models.DramaShot)
        .filter(models.DramaShot.drama_id == drama.id)
        .order_by(models.DramaShot.index)
        .all()
    )
    if not shots:
        raise conflict("还没有分镜，无法合成")

    missing = []
    inputs = []
    for s in shots:
        job = db.get(models.GenerationJob, s.job_id) if s.job_id else None
        asset = (
            db.get(models.Asset, job.output_asset_id)
            if job and job.output_asset_id and job.status == "succeeded"
            else None
        )
        if asset is None:
            missing.append(s.index)
            continue
        inputs.append(
            {
                "index": s.index,
                "path": storage.abs_path_for(asset.path),
                "duration_sec": s.duration_sec,
                "shot_size": s.shot_size,
            }
        )

    if missing:
        raise conflict(f"还有 {len(missing)} 个镜头没有关键帧：第 {', '.join(map(str, missing[:10]))} 镜")

    out_dir = config.DATA_DIR / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{drama.id}.mp4"

    try:
        compose.compose(inputs, out_path, size=720, fps=config.COMPOSE_FPS)
    except compose.ComposeError as exc:
        raise AppError(502, exc.code, exc.message)

    drama.video_path = str(out_path.relative_to(config.DATA_DIR))
    drama.status = "video_ready"
    db.commit()

    info = compose.probe(out_path)
    return {"ok": True, "video_path": drama.video_path, **info}


@router.get("/dramas/{drama_id}/video")
def get_video(drama_id: str, db: Session = Depends(get_db)):
    drama = _get_drama_or_404(drama_id, db)
    if not drama.video_path:
        raise not_found("还没有合成视频")
    path = config.DATA_DIR / drama.video_path
    if not path.exists():
        raise not_found("视频文件不存在")
    return FileResponse(path, media_type="video/mp4", filename=f"{drama.title}.mp4")


@router.get("/dramas/{drama_id}/export")
def export_drama(drama_id: str, db: Session = Depends(get_db)):
    """导出 ZIP：视频 + 分镜表 CSV + 关键帧。"""
    import csv
    import io
    import tempfile
    import zipfile
    from starlette.background import BackgroundTask

    drama = _get_drama_or_404(drama_id, db)
    shots = (
        db.query(models.DramaShot)
        .filter(models.DramaShot.drama_id == drama.id)
        .order_by(models.DramaShot.index)
        .all()
    )
    if not shots:
        raise bad_request("还没有分镜，无法导出", "NOTHING_TO_EXPORT")

    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.close()

    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
        # 分镜表
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(
            ["序号", "景别", "机位", "动作", "台词", "时长秒", "情绪", "连续性", "关键帧状态"]
        )
        for s in shots:
            job = db.get(models.GenerationJob, s.job_id) if s.job_id else None
            w.writerow(
                [
                    s.index,
                    s.shot_size,
                    s.camera,
                    s.action,
                    s.dialogue,
                    s.duration_sec,
                    s.mood,
                    s.continuity,
                    job.status if job else "未生成",
                ]
            )
        zf.writestr("分镜表.csv", "\ufeff" + buf.getvalue())

        # 关键帧
        for s in shots:
            job = db.get(models.GenerationJob, s.job_id) if s.job_id else None
            asset = db.get(models.Asset, job.output_asset_id) if job and job.output_asset_id else None
            if asset is None:
                continue
            p = storage.abs_path_for(asset.path)
            if p.exists():
                zf.write(p, f"keyframes/shot-{s.index:02d}.png")

        # 视频
        if drama.video_path:
            vp = config.DATA_DIR / drama.video_path
            if vp.exists():
                zf.write(vp, "成片.mp4")

    def cleanup():
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    safe = "".join(ch for ch in (drama.title or "drama") if ch.isalnum() or ch in "-_")[:40]
    return FileResponse(
        tmp.name,
        media_type="application/zip",
        filename=f"{safe or 'drama'}.zip",
        background=BackgroundTask(cleanup),
    )
