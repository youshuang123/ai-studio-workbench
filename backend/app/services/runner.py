"""任务执行器：数据库任务表 + 后台线程。

不用 Redis/Celery 的理由见《技术适配声明》§3（并发只需 20 图 / 3 视频）。
进程重启时，残留的 running 任务会被标记为 failed(INTERRUPTED)，不假装还在跑。
"""

import threading
from datetime import datetime, timezone

from .. import models
from ..db import SessionLocal
from . import color_delta, model_client, qa, storage


def _now() -> datetime:
    return datetime.now(timezone.utc)


TERMINAL_STATUSES = {"succeeded", "failed", "over_budget", "cancelled"}


def _run_qa(db, job: models.GenerationJob, out_rel_path: str) -> None:
    """ΔE + VLM 打分，写回 job。任何失败都不影响出图结果。"""
    src_job = db.get(models.GenerationJob, job.refined_from)
    if src_job is None or not src_job.output_asset_id:
        return
    src_asset = db.get(models.Asset, src_job.output_asset_id)
    out_asset_path = storage.abs_path_for(out_rel_path)
    if src_asset is None or not out_asset_path.exists():
        return

    src_path = storage.abs_path_for(src_asset.path)
    if not src_path.exists():
        return

    # 1) 颜色一致性
    try:
        cmp = color_delta.compare_bytes(src_path.read_bytes(), out_asset_path.read_bytes())
        job.delta_e = cmp["delta_e"]
    except Exception:  # noqa: BLE001
        job.delta_e = None

    # 2) VLM 打分
    result = qa.evaluate(
        out_asset_path.read_bytes(),
        product_name=job.product_name or "",
        reference_bytes=src_path.read_bytes(),
    )
    if result.get("ok"):
        job.qa_score = result["total"]
        job.qa_detail = __import__("json").dumps(result, ensure_ascii=False)
    else:
        job.qa_detail = __import__("json").dumps(
            {"ok": False, "error": result.get("error"), "message": result.get("message")},
            ensure_ascii=False,
        )
    db.commit()


def mark_interrupted_jobs() -> int:
    """应用启动时调用：把上次残留的 running 任务标记为可重试的失败。"""
    db = SessionLocal()
    try:
        rows = (
            db.query(models.GenerationJob)
            .filter(models.GenerationJob.status.in_(["queued", "running"]))
            .all()
        )
        for job in rows:
            job.status = "failed"
            job.error_code = "INTERRUPTED"
            job.error_message = "服务重启导致任务中断，可重试"
            job.finished_at = _now()
        db.commit()
        return len(rows)
    finally:
        db.close()


def start_job(job_id: str) -> None:
    thread = threading.Thread(target=run_job, args=(job_id,), daemon=True)
    thread.start()


def run_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(models.GenerationJob, job_id)
        if job is None or job.status not in ("queued",):
            return

        job.status = "running"
        job.started_at = _now()
        job.attempts = (job.attempts or 0) + 1
        job.cancel_requested = False
        db.commit()

        try:
            # 精修走图生图；草稿走文生图
            if job.stage == "refined" and job.refined_from:
                src_job = db.get(models.GenerationJob, job.refined_from)
                src_asset = (
                    db.get(models.Asset, src_job.output_asset_id)
                    if src_job and src_job.output_asset_id
                    else None
                )
                if src_asset is None:
                    raise model_client.ModelError("SOURCE_MISSING", "找不到要精修的草稿图")
                src_path = storage.abs_path_for(src_asset.path)
                if not src_path.exists():
                    raise model_client.ModelError("SOURCE_MISSING", "草稿图文件已丢失")
                raw_src = src_path.read_bytes()
                raw = model_client.generate_edit(job.prompt, raw_src, src_asset.mime)
            else:
                raw = model_client.generate_image(job.prompt, job.negative_prompt)

            # 检查点 1：模型返回后再看一次是否被取消
            db.refresh(job)
            if job.cancel_requested:
                job.status = "cancelled"
                job.error_code = "CANCELLED"
                job.error_message = "已取消。本次调用可能已产生费用，请以供应商账单为准"
                job.finished_at = _now()
                db.commit()
                return

            saved = storage.save_generated(raw)

            asset = models.Asset(
                project_id=job.project_id,
                kind="output",
                filename=f"{job.product_name or '主图'}.png",
                path=saved.rel_path,
                mime=saved.mime,
                bytes=saved.size,
                width=saved.width,
                height=saved.height,
                sha256=saved.sha256,
            )
            db.add(asset)
            db.flush()

            job.output_asset_id = asset.id
            job.status = "succeeded"
            job.cost_fen = job.unit_price_fen
            job.finished_at = _now()

            db.add(
                models.UsageRecord(
                    job_id=job.id,
                    project_id=job.project_id,
                    unit="image",
                    amount=1,
                    cost_fen=job.unit_price_fen,
                )
            )
            db.commit()

            # 精修图自动质检：ΔE（本地免费）+ VLM 打分
            if job.stage == "refined" and job.refined_from:
                try:
                    _run_qa(db, job, saved.rel_path)
                except Exception:  # noqa: BLE001 质检失败不影响出图
                    db.rollback()

            storage.write_sidecar(
                saved.rel_path,
                {
                    "job_id": job.id,
                    "project_id": job.project_id,
                    "product_name": job.product_name,
                    "prompt": job.prompt,
                    "negative_prompt": job.negative_prompt,
                    "model": job.model,
                    "provider": job.provider,
                    "unit_price_fen": job.unit_price_fen,
                    "cost_fen": job.cost_fen,
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                },
            )
        except model_client.ModelError as exc:
            db.refresh(job)
            if job.cancel_requested:
                job.status = "cancelled"
                job.error_code = "CANCELLED"
                job.error_message = "已取消"
                job.finished_at = _now()
                db.commit()
                return
            job.status = "failed"
            job.error_code = exc.code
            job.error_message = exc.message
            job.finished_at = _now()
            db.commit()
        except Exception:  # noqa: BLE001 不把堆栈暴露出去
            job.status = "failed"
            job.error_code = "INTERNAL_ERROR"
            job.error_message = "生成过程出现内部错误，可重试"
            job.finished_at = _now()
            db.commit()
    finally:
        db.close()
