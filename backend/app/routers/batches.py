import asyncio
import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from .. import config, models
from ..db import SessionLocal, get_db
from ..errors import AppError, bad_request, conflict, not_found
from ..services import batch_runner, csv_import, export_zip, model_client, prompt as prompt_service

router = APIRouter(prefix="/api", tags=["batches"])

TERMINAL_BATCH = {"completed", "cancelled", "stopped_over_budget"}


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def _batch_out(batch: models.Batch) -> dict:
    return {
        "id": batch.id,
        "project_id": batch.project_id,
        "name": batch.name,
        "status": batch.status,
        "total": batch.total,
        "succeeded": batch.succeeded,
        "failed": batch.failed,
        "cost_fen": batch.cost_fen,
        "budget_fen": batch.budget_fen,
        "confirmed_at": _iso(batch.confirmed_at),
        "created_at": _iso(batch.created_at),
        "finished_at": _iso(batch.finished_at),
    }


def _job_out(job: models.GenerationJob) -> dict:
    return {
        "id": job.id,
        "sku_code": job.sku_code,
        "product_name": job.product_name,
        "status": job.status,
        "cost_fen": job.cost_fen,
        "output_asset_id": job.output_asset_id,
        "error_code": job.error_code,
        "error_message": job.error_message,
    }


def _get_batch_or_404(batch_id: str, db: Session) -> models.Batch:
    batch = db.get(models.Batch, batch_id)
    if batch is None:
        raise not_found("批次不存在")
    return batch


@router.post("/projects/{project_id}/batches/validate")
async def validate_csv(project_id: str, file: UploadFile, db: Session = Depends(get_db)):
    """只校验，不建批次。"""
    project = db.get(models.Project, project_id)
    if project is None:
        raise not_found("项目不存在")

    raw = await file.read()
    if not raw:
        raise bad_request("文件是空的", "CSV_EMPTY")

    filenames = {
        a.filename
        for a in db.query(models.Asset)
        .filter(models.Asset.project_id == project_id, models.Asset.kind == "upload")
        .all()
    }

    try:
        result = csv_import.parse(raw, existing_filenames=filenames)
    except csv_import.CsvError as exc:
        raise bad_request(exc.message, exc.code)

    payload = result.to_dict()
    # 不把整份 rows 回给前端（可能很长），只回前 20 行预览
    payload["rows"] = payload["rows"][:20]
    payload["file_name"] = file.filename or "skus.csv"
    return payload


@router.post("/projects/{project_id}/batches", status_code=201)
async def create_batch(
    project_id: str,
    file: UploadFile,
    name: str = "",
    db: Session = Depends(get_db),
):
    """校验并建批次（draft，未确认不能批量）。"""
    project = db.get(models.Project, project_id)
    if project is None:
        raise not_found("项目不存在")

    raw = await file.read()
    if not raw:
        raise bad_request("文件是空的", "CSV_EMPTY")

    filenames = {
        a.filename
        for a in db.query(models.Asset)
        .filter(models.Asset.project_id == project_id, models.Asset.kind == "upload")
        .all()
    }
    try:
        result = csv_import.parse(raw, existing_filenames=filenames)
    except csv_import.CsvError as exc:
        raise bad_request(exc.message, exc.code)

    if result.valid == 0:
        raise bad_request("没有任何可执行的行，请检查 CSV 内容", "CSV_NO_VALID_ROWS")

    batch_name = (name or "").strip() or (file.filename or "批量任务").rsplit(".", 1)[0]
    batch = models.Batch(
        project_id=project_id,
        name=batch_name[:120],
        status="draft",
        total=result.total,
        budget_fen=config.BATCH_BUDGET_FEN,
    )
    db.add(batch)
    db.flush()

    # 为可执行行建 job；缺图行也建（status=skipped），便于展示与计数
    created = 0
    for row in result.rows:
        if row.skipped:
            db.add(
                models.GenerationJob(
                    project_id=project_id,
                    batch_id=batch.id,
                    status="skipped",
                    sku_code=row.sku_code,
                    product_name=row.product_name,
                    prompt="",
                    error_code="MISSING_IMAGE",
                    error_message=f"缺图：{row.image_file}",
                    finished_at=datetime.now(timezone.utc),
                )
            )
            created += 1
            continue
        if not row.ok:
            continue
        try:
            built = prompt_service.build_prompt(
                product_name=row.product_name,
                category=row.category,
                selling_points=row.selling_points,
                color=row.color,
            )
        except ValueError:
            continue
        db.add(
            models.GenerationJob(
                project_id=project_id,
                batch_id=batch.id,
                status="queued",
                sku_code=row.sku_code,
                product_name=row.product_name,
                prompt=built,
                negative_prompt=prompt_service.NEGATIVE_PROMPT,
                provider=config.T2I_BASE_URL,
                model=config.T2I_MODEL,
                unit_price_fen=config.T2I_UNIT_PRICE_FEN,
                budget_fen=config.BATCH_BUDGET_FEN,
            )
        )
        created += 1

    db.commit()
    db.refresh(batch)

    return {
        **_batch_out(batch),
        "created_jobs": created,
        "errors": result.errors,
        "missing_images": result.missing_images,
    }


@router.get("/projects/{project_id}/batches")
def list_batches(project_id: str, db: Session = Depends(get_db)):
    """最近 5 个批次；刷新页面后前端用它找回上一次的批次。"""
    project = db.get(models.Project, project_id)
    if project is None:
        raise not_found("项目不存在")
    rows = (
        db.query(models.Batch)
        .filter(models.Batch.project_id == project_id)
        .order_by(models.Batch.created_at.desc())
        .limit(5)
        .all()
    )
    return {"items": [_batch_out(b) for b in rows], "total": len(rows)}


@router.get("/batches/{batch_id}")
def get_batch(batch_id: str, db: Session = Depends(get_db)):
    batch = _get_batch_or_404(batch_id, db)
    jobs = (
        db.query(models.GenerationJob)
        .filter(models.GenerationJob.batch_id == batch_id)
        .order_by(models.GenerationJob.created_at)
        .all()
    )
    return {**_batch_out(batch), "items": [_job_out(j) for j in jobs]}


@router.post("/batches/{batch_id}/trial", status_code=200)
def trial_batch(batch_id: str, db: Session = Depends(get_db)):
    """试跑第一条可执行行，同步等结果（最长 ~60s）。"""
    batch = _get_batch_or_404(batch_id, db)

    job = (
        db.query(models.GenerationJob)
        .filter(
            models.GenerationJob.batch_id == batch_id,
            models.GenerationJob.status == "queued",
        )
        .order_by(models.GenerationJob.created_at)
        .first()
    )
    if job is None:
        raise conflict("没有可试跑的行")

    if not config.t2i_configured():
        raise AppError(
            503,
            "MODEL_NOT_CONFIGURED",
            "未配置模型 API Key：请在 backend/.env 的 MODEL_T2I_API_KEY= 后填写后重启服务",
        )

    job.status = "queued"
    db.commit()
    from ..services import runner

    runner.run_job(job.id)
    db.refresh(job)
    return {"job": _job_out(job), "batch": _batch_out(batch)}


@router.post("/batches/{batch_id}/confirm", status_code=202)
def confirm_batch(batch_id: str, db: Session = Depends(get_db)):
    """确认批量：draft → queued，必须有成功试跑。"""
    batch = _get_batch_or_404(batch_id, db)
    if batch.status != "draft":
        raise conflict(f"当前状态 {batch.status} 不能确认")

    succeeded = (
        db.query(models.GenerationJob)
        .filter(
            models.GenerationJob.batch_id == batch_id,
            models.GenerationJob.status == "succeeded",
        )
        .count()
    )
    if succeeded == 0:
        raise conflict("先试跑一条并看到结果，再确认批量")

    if not config.t2i_configured():
        raise AppError(503, "MODEL_NOT_CONFIGURED", "未配置模型 API Key")

    batch.status = "queued"
    batch.confirmed_at = datetime.now(timezone.utc)
    db.commit()

    batch_runner.start_batch(batch.id)
    return _batch_out(batch)


@router.post("/batches/{batch_id}/resume", status_code=202)
def resume_batch(batch_id: str, db: Session = Depends(get_db)):
    batch = _get_batch_or_404(batch_id, db)
    if batch.status != "paused":
        raise conflict(f"当前状态 {batch.status} 不能继续")
    batch.status = "queued"
    db.commit()
    batch_runner.start_batch(batch.id)
    return _batch_out(batch)


@router.post("/batches/{batch_id}/cancel", status_code=202)
def cancel_batch(batch_id: str, db: Session = Depends(get_db)):
    batch = _get_batch_or_404(batch_id, db)
    if batch.status in TERMINAL_BATCH:
        raise conflict("批次已结束")

    batch.status = "cancelled"
    batch.finished_at = datetime.now(timezone.utc)
    db.query(models.GenerationJob).filter(
        models.GenerationJob.batch_id == batch_id,
        models.GenerationJob.status == "queued",
    ).update({"status": "cancelled", "error_code": "CANCELLED_BY_USER"})
    db.commit()
    return _batch_out(batch)


@router.post("/batches/{batch_id}/items/{item_id}/retry", status_code=202)
def retry_item(batch_id: str, item_id: str, db: Session = Depends(get_db)):
    job = db.get(models.GenerationJob, item_id)
    if job is None or job.batch_id != batch_id:
        raise not_found("任务不存在")
    if job.status not in ("failed", "over_budget", "skipped"):
        raise conflict("只有失败、超预算或跳过的行可以重试")

    if job.status == "skipped":
        raise conflict("缺图的行请先上传对应图片再重试")

    if not config.t2i_configured():
        raise AppError(503, "MODEL_NOT_CONFIGURED", "未配置模型 API Key")

    job.status = "queued"
    job.error_code = ""
    job.error_message = ""
    job.finished_at = None
    db.commit()

    from ..services import runner

    runner.run_job(job.id)
    db.refresh(job)
    return {"item": _job_out(job), "batch": _batch_out(batch_id and _get_batch_or_404(batch_id, db))}


@router.get("/batches/{batch_id}/events")
async def batch_events(batch_id: str):
    """批次进度 SSE：progress / item / done / error。"""

    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def stream():
        loop = asyncio.get_event_loop()
        started = loop.time()
        last_heartbeat = started
        last_signature = None

        yield _sse("progress", {"status": "running", "message": "正在执行批次…"})

        while True:
            db = SessionLocal()
            try:
                batch = db.get(models.Batch, batch_id)
                if batch is None:
                    yield _sse("error", {"error": {"code": "NOT_FOUND", "message": "批次不存在"}})
                    return
                jobs = (
                    db.query(models.GenerationJob)
                    .filter(models.GenerationJob.batch_id == batch_id)
                    .all()
                )
                status = batch.status
                total = batch.total
                succeeded = len([j for j in jobs if j.status == "succeeded"])
                failed = len([j for j in jobs if j.status in ("failed", "over_budget", "skipped")])
                cost = sum(j.cost_fen or 0 for j in jobs if j.status == "succeeded")
                items = [
                    {
                        "id": j.id,
                        "sku_code": j.sku_code,
                        "status": j.status,
                        "cost_fen": j.cost_fen or 0,
                    }
                    for j in jobs
                    if j.status in ("succeeded", "failed", "over_budget", "skipped")
                ]
            finally:
                db.close()

            signature = (succeeded, failed, status)
            if signature != last_signature:
                yield _sse(
                    "progress",
                    {
                        "total": total,
                        "succeeded": succeeded,
                        "failed": failed,
                        "cost_fen": cost,
                        "status": status,
                    },
                )
                if last_signature is not None:
                    for item in items:
                        yield _sse("item", item)
                last_signature = signature

            if status in TERMINAL_BATCH or status == "paused":
                yield _sse(
                    "done",
                    {
                        "status": status,
                        "total": total,
                        "succeeded": succeeded,
                        "failed": failed,
                        "cost_fen": cost,
                    },
                )
                return

            now = loop.time()
            if now - started > 600:
                yield _sse("error", {"error": {"code": "SSE_TIMEOUT", "message": "等待超时，请刷新"}})
                return
            if now - last_heartbeat >= 10:
                yield _sse("heartbeat", {"ts": int(now - started)})
                last_heartbeat = now

            await asyncio.sleep(0.8)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/batches/{batch_id}/export")
def export_batch(batch_id: str, db: Session = Depends(get_db)):
    batch = _get_batch_or_404(batch_id, db)
    jobs = (
        db.query(models.GenerationJob)
        .filter(models.GenerationJob.batch_id == batch_id)
        .order_by(models.GenerationJob.created_at)
        .all()
    )
    if not any(j.status == "succeeded" for j in jobs):
        raise bad_request("这个批次还没有成功的图，无法导出", "NOTHING_TO_EXPORT")

    path, download_name = export_zip.build_zip(db, batch, jobs)

    def cleanup():
        try:
            os.unlink(path)
        except OSError:
            pass

    from starlette.background import BackgroundTask

    return FileResponse(
        path,
        media_type="application/zip",
        filename=download_name,
        background=BackgroundTask(cleanup),
    )
