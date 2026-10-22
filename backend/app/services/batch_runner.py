"""批量执行器：进程内线程池 + 数据库状态。

设计（2-2 技术开发文档 §2）：
- 并发基于 ThreadPoolExecutor，默认 3，可通过 BATCH_CONCURRENCY 调；
- 每行是一个 GenerationJob（复用 2-1 的执行逻辑）；
- 已成功的不重跑（省钱 + PRD FR-013 硬要求）；
- 进程重启：running 的批次转 paused(INTERRUPTED)，其下 queued/running 的 job 保持可重试。
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import select

from .. import config, models
from ..db import SessionLocal
from . import model_client, prompt as prompt_service, runner, storage


def _now() -> datetime:
    return datetime.now(timezone.utc)


_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None

# 并发下的预算预约：batch_id -> 已预约但尚未记账的金额（分）
# 为什么需要：3 个 worker 同时读 DB 会都看到"还没花"，一起冲过预算上限
_reserved: dict[str, int] = {}


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=max(1, config.BATCH_CONCURRENCY),
                thread_name_prefix="batch",
            )
        return _executor


def start_batch(batch_id: str) -> None:
    """启动批次：交给线程池，不阻塞请求。"""
    _get_executor().submit(_run_batch, batch_id)


def _run_batch(batch_id: str) -> None:
    db = SessionLocal()
    try:
        batch = db.get(models.Batch, batch_id)
        if batch is None or batch.status not in ("queued", "paused"):
            return

        batch.status = "running"
        if batch.started_at is None:
            batch.started_at = _now()
        db.commit()

        jobs = (
            db.query(models.GenerationJob)
            .filter(
                models.GenerationJob.batch_id == batch_id,
                models.GenerationJob.status.in_(["queued", "failed"]),
            )
            .order_by(models.GenerationJob.created_at)
            .all()
        )
        job_ids = [j.id for j in jobs]
    finally:
        db.close()

    # 逐条执行；用固定 worker 池控制并发
    executor = _get_executor()
    futures = [executor.submit(_run_one, job_id) for job_id in job_ids]
    for f in futures:
        try:
            f.result()
        except Exception:  # noqa: BLE001 单条异常不影响整体
            continue

    _finalize(batch_id)


def _run_one(job_id: str) -> None:
    """单条执行：先原子地预约预算，再调用 runner 的状态机。"""
    db = SessionLocal()
    batch_id: str | None = None
    price = 0
    reserved_ok = False
    try:
        job = db.get(models.GenerationJob, job_id)
        if job is None:
            return
        batch = db.get(models.Batch, job.batch_id) if job.batch_id else None
        price = job.unit_price_fen or 0
        if batch is not None:
            batch_id = batch.id
            if not _reserve_budget(db, batch.id, price, batch.budget_fen):
                job.status = "skipped"
                job.error_code = "BUDGET_EXCEEDED"
                job.error_message = "批次预算已用完，本行未执行"
                job.finished_at = _now()
                db.commit()
                return
            reserved_ok = True
        job.status = "queued"
        db.commit()
        job_id_final = job.id
    finally:
        db.close()

    try:
        runner.run_job(job_id_final)
    finally:
        if reserved_ok and batch_id:
            _release_reservation(batch_id, price)


def _reserve_budget(db, batch_id: str, price: int, budget_fen: int) -> bool:
    """原子预约。已记账金额 + 已预约金额 + 本次 ≤ 预算才放行。"""
    with _lock:
        committed = _batch_spent(db, batch_id)
        pending = _reserved.get(batch_id, 0)
        if committed + pending + price > budget_fen:
            return False
        _reserved[batch_id] = pending + price
        return True


def _release_reservation(batch_id: str, price: int) -> None:
    """执行结束后释放预约（实际成本已写入 DB）。"""
    with _lock:
        _reserved[batch_id] = max(0, _reserved.get(batch_id, 0) - price)


def reset_reservations() -> None:
    """服务启动/测试之间重置预约表。"""
    with _lock:
        _reserved.clear()


def _batch_spent(db, batch_id: str) -> int:
    total = (
        db.query(models.GenerationJob)
        .filter(
            models.GenerationJob.batch_id == batch_id,
            models.GenerationJob.status == "succeeded",
        )
        .with_entities(models.GenerationJob.cost_fen)
        .all()
    )
    return sum(row[0] or 0 for row in total)


def _finalize(batch_id: str) -> None:
    db = SessionLocal()
    try:
        batch = db.get(models.Batch, batch_id)
        if batch is None:
            return

        jobs = (
            db.query(models.GenerationJob)
            .filter(models.GenerationJob.batch_id == batch_id)
            .all()
        )
        succeeded = len([j for j in jobs if j.status == "succeeded"])
        failed = len([j for j in jobs if j.status in ("failed", "over_budget")])
        skipped = len([j for j in jobs if j.status == "skipped"])
        cost = sum(j.cost_fen or 0 for j in jobs if j.status == "succeeded")

        batch.succeeded = succeeded
        batch.failed = failed
        batch.cost_fen = cost
        batch.total = len(jobs)
        batch.finished_at = _now()

        if batch.status == "running":
            if failed or skipped:
                batch.status = "completed"  # 部分成功也归 completed，明细在 failed/skipped 计数里
            else:
                batch.status = "completed"
        db.commit()
    finally:
        db.close()


def mark_interrupted_batches() -> int:
    """服务启动时：running 的批次转 paused(INTERRUPTED)，可续跑。"""
    db = SessionLocal()
    try:
        rows = (
            db.query(models.Batch).filter(models.Batch.status == "running").all()
        )
        for batch in rows:
            batch.status = "paused"
        db.commit()
        return len(rows)
    finally:
        db.close()


def create_jobs_for_batch(db, batch: models.Batch, rows: list) -> int:
    """为可执行行创建 job（skipped 行也建 job 但状态为 skipped，便于前端展示）。"""
    created = 0
    for row in rows:
        if row.skipped:
            job = models.GenerationJob(
                project_id=batch.project_id,
                batch_id=batch.id,
                status="skipped",
                product_name=row.product_name,
                prompt="",
                error_code="MISSING_IMAGE",
                error_message=f"缺图：{row.image_file}",
                finished_at=_now(),
            )
            db.add(job)
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
        job = models.GenerationJob(
            project_id=batch.project_id,
            batch_id=batch.id,
            status="queued",
            product_name=row.product_name,
            prompt=built,
            negative_prompt=prompt_service.NEGATIVE_PROMPT,
            provider=config.T2I_BASE_URL,
            model=config.T2I_MODEL,
            unit_price_fen=config.T2I_UNIT_PRICE_FEN,
            budget_fen=batch.budget_fen,
        )
        db.add(job)
        created += 1
    db.commit()
    return created
