"""任务执行器：数据库任务表 + 后台线程。

不用 Redis/Celery 的理由见《技术适配声明》§3（并发只需 20 图 / 3 视频）。
进程重启时，残留的 running 任务会被标记为 failed(INTERRUPTED)，不假装还在跑。
"""

import threading
from datetime import datetime, timezone

from .. import models
from ..db import SessionLocal
from . import model_client, storage


def _now() -> datetime:
    return datetime.now(timezone.utc)


TERMINAL_STATUSES = {"succeeded", "failed", "over_budget", "cancelled"}


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
        db.commit()

        try:
            raw = model_client.generate_image(job.prompt, job.negative_prompt)
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
