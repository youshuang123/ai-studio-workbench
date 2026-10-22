import asyncio
import json

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

            if status in ("failed", "over_budget", "cancelled"):
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
