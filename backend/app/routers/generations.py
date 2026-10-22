import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import config, models, schemas
from ..db import SessionLocal, get_db
from ..errors import AppError, budget_exceeded, conflict, not_found
from ..services import budget, prompt as prompt_service, runner

router = APIRouter(prefix="/api", tags=["generations"])

TERMINAL = {"succeeded", "failed", "over_budget", "cancelled"}
SSE_MAX_SECONDS = 180
HEARTBEAT_SECONDS = 10


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _job_out(job: models.GenerationJob) -> dict:
    elapsed_ms = None
    if job.started_at and job.finished_at:
        elapsed_ms = int((job.finished_at - job.started_at).total_seconds() * 1000)
    return {
        "id": job.id,
        "project_id": job.project_id,
        "status": job.status,
        "product_name": job.product_name,
        "output_asset_id": job.output_asset_id,
        "cost_fen": job.cost_fen,
        "unit_price_fen": job.unit_price_fen,
        "elapsed_ms": elapsed_ms,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "cancel_requested": bool(getattr(job, "cancel_requested", False)),
        "stage": getattr(job, "stage", "draft") or "draft",
        "refined_from": getattr(job, "refined_from", None),
        "delta_e": getattr(job, "delta_e", None),
        "qa_score": getattr(job, "qa_score", None),
        "qa_detail": getattr(job, "qa_detail", "") or "",
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


@router.post("/projects/{project_id}/generations", status_code=202)
def create_generation(
    project_id: str,
    body: schemas.GenerationCreate,
    db: Session = Depends(get_db),
):
    project = db.get(models.Project, project_id)
    if project is None:
        raise not_found("项目不存在")

    source = db.get(models.Asset, body.source_asset_id)
    if source is None or source.project_id != project_id or source.kind != "upload":
        raise AppError(400, "INVALID_SOURCE_ASSET", "请先在本项目上传一张商品图")

    if not config.t2i_configured():
        raise AppError(
            503,
            "MODEL_NOT_CONFIGURED",
            "未配置模型 API Key：请在 backend/.env 的 MODEL_T2I_API_KEY= 后填写后重启服务",
        )

    budget_fen = (
        int(round(body.budget_cny * 100)) if body.budget_cny else config.TASK_BUDGET_FEN
    )
    ok, reason = budget.check_budget(config.T2I_UNIT_PRICE_FEN, 0, budget_fen)
    if not ok:
        raise budget_exceeded(reason)

    try:
        built_prompt = prompt_service.build_prompt(
            product_name=body.product_name,
            category=body.category,
            selling_points=body.selling_points,
            color=body.color,
        )
    except ValueError as exc:
        raise AppError(400, "VALIDATION_ERROR", str(exc))

    job = models.GenerationJob(
        project_id=project_id,
        status="queued",
        product_name=body.product_name,
        prompt=built_prompt,
        negative_prompt=prompt_service.NEGATIVE_PROMPT,
        source_asset_id=source.id,
        provider=config.T2I_BASE_URL,
        model=config.T2I_MODEL,
        unit_price_fen=config.T2I_UNIT_PRICE_FEN,
        budget_fen=budget_fen,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    runner.start_job(job.id)
    return {"job_id": job.id, "status": job.status}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(models.GenerationJob, job_id)
    if job is None:
        raise not_found("任务不存在")
    return _job_out(job)


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(models.GenerationJob, job_id)
    if job is None:
        raise not_found("任务不存在")
    if job.status not in ("failed", "over_budget"):
        raise conflict("只有失败或超预算的任务可以重试")

    if not config.t2i_configured():
        raise AppError(
            503,
            "MODEL_NOT_CONFIGURED",
            "未配置模型 API Key，请在 backend/.env 填写 MODEL_T2I_API_KEY 后重启服务",
        )

    spend = (
        db.query(models.UsageRecord)
        .filter(models.UsageRecord.project_id == job.project_id)
        .with_entities(models.UsageRecord.cost_fen)
        .all()
    )
    spent_fen = sum(row[0] or 0 for row in spend)
    ok, reason = budget.check_budget(job.unit_price_fen, spent_fen, job.budget_fen)
    if not ok:
        raise budget_exceeded(reason)

    job.status = "queued"
    job.error_code = ""
    job.error_message = ""
    job.started_at = None
    job.finished_at = None
    db.commit()

    runner.start_job(job.id)
    return {"job_id": job.id, "status": job.status}


@router.post("/jobs/{job_id}/cancel", status_code=202)
def cancel_job(job_id: str, db: Session = Depends(get_db)):
    """取消任务。

    - queued：直接置 cancelled
    - running：置 cancel_requested，执行器在检查点停止（已发出的 HTTP 请求无法中断，
      费用可能已产生，因此提示按账单为准）
    - 已结束：409
    """
    job = db.get(models.GenerationJob, job_id)
    if job is None:
        raise not_found("任务不存在")

    if job.status == "queued":
        job.status = "cancelled"
        job.error_code = "CANCELLED_BY_USER"
        job.error_message = "已取消，未产生费用"
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        return {"job_id": job.id, "status": job.status, "cancel_requested": False}

    if job.status == "running":
        if job.cancel_requested:
            return {"job_id": job.id, "status": job.status, "cancel_requested": True}
        job.cancel_requested = True
        db.commit()
        return {"job_id": job.id, "status": job.status, "cancel_requested": True}

    raise conflict("任务已结束，无法取消")


@router.post("/jobs/{job_id}/refine", status_code=202)
def refine_job(job_id: str, db: Session = Depends(get_db)):
    """精修：用草稿图做图生图（约 ¥0.30/张）。不自动重试，失败由用户手动点。"""
    src = db.get(models.GenerationJob, job_id)
    if src is None:
        raise not_found("任务不存在")
    if src.status != "succeeded" or not src.output_asset_id:
        raise conflict("只有生成成功的任务才能精修")
    if (src.stage or "draft") != "draft":
        raise conflict("精修图不能再精修")

    if not config.edit_configured():
        raise AppError(503, "EDIT_NOT_CONFIGURED", "未配置精修模型 Key")

    ok, reason = budget.check_budget(config.EDIT_UNIT_PRICE_FEN, 0, config.EDIT_UNIT_PRICE_FEN * 100)
    if not ok:
        raise budget_exceeded(reason)

    job = models.GenerationJob(
        project_id=src.project_id,
        batch_id=src.batch_id,
        sku_code=src.sku_code or "",
        status="queued",
        stage="refined",
        refined_from=src.id,
        product_name=src.product_name,
        prompt=src.prompt,
        negative_prompt=src.negative_prompt,
        source_asset_id=src.output_asset_id,
        provider=config.EDIT_BASE_URL,
        model=config.EDIT_MODEL,
        unit_price_fen=config.EDIT_UNIT_PRICE_FEN,
        budget_fen=config.EDIT_UNIT_PRICE_FEN * 10,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    runner.start_job(job.id)
    return {"job_id": job.id, "status": job.status, "stage": "refined"}


@router.post("/jobs/{job_id}/qa")
def rerun_qa(job_id: str, db: Session = Depends(get_db)):
    """重跑质检（VLM 一次约 ¥0.003）。"""
    job = db.get(models.GenerationJob, job_id)
    if job is None:
        raise not_found("任务不存在")
    if job.status != "succeeded" or not job.output_asset_id:
        raise conflict("只有成功的任务才能质检")
    if not config.vlm_configured():
        raise AppError(503, "VLM_NOT_CONFIGURED", "未配置 VLM Key")

    asset = db.get(models.Asset, job.output_asset_id)
    if asset is None:
        raise not_found("产物不存在")

    from ..services import color_delta, qa, storage

    out_path = storage.abs_path_for(asset.path)

    # 精修图：把草稿图一并送给 VLM，额外评估颜色一致性
    ref_bytes = None
    if (job.stage or "draft") == "refined" and job.refined_from:
        src_job = db.get(models.GenerationJob, job.refined_from)
        if src_job and src_job.output_asset_id:
            src_asset = db.get(models.Asset, src_job.output_asset_id)
            if src_asset:
                src_path = storage.abs_path_for(src_asset.path)
                if src_path.exists():
                    ref_bytes = src_path.read_bytes()

    result = qa.evaluate(
        out_path.read_bytes(),
        product_name=job.product_name or "",
        reference_bytes=ref_bytes,
    )
    if result.get("ok"):
        job.qa_score = result["total"]
        job.qa_detail = json.dumps(result, ensure_ascii=False)
        db.commit()
        return {"ok": True, "qa_score": job.qa_score, "qa_detail": result}
    return {"ok": False, "error": result.get("error"), "message": result.get("message")}


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str):
    """SSE：必须且只能以 done 或 error 收尾。"""

    async def event_stream():
        loop = asyncio.get_event_loop()
        started = loop.time()
        last_heartbeat = started
        last_status = None

        yield _sse("status", {"stage": "preparing", "message": "正在准备…"})

        while True:
            db = SessionLocal()
            try:
                job = db.get(models.GenerationJob, job_id)
                if job is None:
                    yield _sse(
                        "error",
                        {"error": {"code": "NOT_FOUND", "message": "任务不存在"}},
                    )
                    return
                status = job.status
                output_asset_id = job.output_asset_id
                cost_fen = job.cost_fen
                error_code = job.error_code
                error_message = job.error_message
                elapsed_ms = None
                if job.started_at and job.finished_at:
                    elapsed_ms = int((job.finished_at - job.started_at).total_seconds() * 1000)
            finally:
                db.close()

            if status != last_status:
                if status == "running":
                    yield _sse("status", {"stage": "calling", "message": "正在调用模型…"})
                last_status = status

            if status == "succeeded":
                yield _sse(
                    "done",
                    {
                        "job_id": job_id,
                        "asset_id": output_asset_id,
                        "cost_fen": cost_fen,
                        "elapsed_ms": elapsed_ms,
                    },
                )
                return

            if status == "cancelled":
                yield _sse(
                    "cancelled",
                    {
                        "job_id": job_id,
                        "message": error_message or "已取消",
                        "output_asset_id": output_asset_id,
                    },
                )
                return

            if status in ("failed", "over_budget"):
                yield _sse(
                    "error",
                    {
                        "error": {
                            "code": error_code or "JOB_FAILED",
                            "message": error_message or "生成失败，可重试",
                        }
                    },
                )
                return

            now = loop.time()
            if now - started > SSE_MAX_SECONDS:
                yield _sse(
                    "error",
                    {"error": {"code": "SSE_TIMEOUT", "message": "等待超时，请刷新查看结果"}},
                )
                return
            if now - last_heartbeat >= HEARTBEAT_SECONDS:
                yield _sse("heartbeat", {"ts": int(now - started)})
                last_heartbeat = now

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
