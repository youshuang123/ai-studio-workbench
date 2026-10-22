from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from ..errors import not_found

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def _asset_url(asset_id: str) -> str:
    return f"/api/assets/{asset_id}/file"


def _asset_out(asset: models.Asset) -> dict:
    return {
        "id": asset.id,
        "project_id": asset.project_id,
        "kind": asset.kind,
        "filename": asset.filename,
        "mime": asset.mime,
        "bytes": asset.bytes,
        "width": asset.width,
        "height": asset.height,
        "created_at": _iso(asset.created_at),
        "url": _asset_url(asset.id),
    }


def _job_brief(job: models.GenerationJob) -> dict:
    elapsed_ms = None
    if job.started_at and job.finished_at:
        elapsed_ms = int((job.finished_at - job.started_at).total_seconds() * 1000)
    return {
        "id": job.id,
        "status": job.status,
        "product_name": job.product_name,
        "output_asset_id": job.output_asset_id,
        "cost_fen": job.cost_fen,
        "elapsed_ms": elapsed_ms,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "stage": getattr(job, "stage", "draft") or "draft",
        "refined_from": getattr(job, "refined_from", None),
        "delta_e": getattr(job, "delta_e", None),
        "qa_score": getattr(job, "qa_score", None),
        "qa_detail": getattr(job, "qa_detail", "") or "",
        "created_at": _iso(job.created_at),
    }


@router.post("", status_code=201)
def create_project(body: schemas.ProjectCreate, db: Session = Depends(get_db)):
    project = models.Project(name=body.name, description=body.description)
    db.add(project)
    db.commit()
    db.refresh(project)
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "created_at": _iso(project.created_at),
    }


@router.get("")
def list_projects(db: Session = Depends(get_db)):
    asset_counts = dict(
        db.query(models.Asset.project_id, func.count(models.Asset.id))
        .group_by(models.Asset.project_id)
        .all()
    )
    job_counts = dict(
        db.query(models.GenerationJob.project_id, func.count(models.GenerationJob.id))
        .group_by(models.GenerationJob.project_id)
        .all()
    )
    projects = db.query(models.Project).order_by(models.Project.created_at.desc()).all()
    items = [
        {
            "id": p.id,
            "name": p.name,
            "asset_count": asset_counts.get(p.id, 0),
            "job_count": job_counts.get(p.id, 0),
            "created_at": _iso(p.created_at),
        }
        for p in projects
    ]
    return {"items": items, "total": len(items)}


@router.get("/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(models.Project, project_id)
    if project is None:
        raise not_found("项目不存在")

    assets = (
        db.query(models.Asset)
        .filter(models.Asset.project_id == project_id)
        .order_by(models.Asset.created_at.desc())
        .limit(50)
        .all()
    )
    jobs = (
        db.query(models.GenerationJob)
        .filter(models.GenerationJob.project_id == project_id)
        .order_by(models.GenerationJob.created_at.desc())
        .limit(20)
        .all()
    )
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "created_at": _iso(project.created_at),
        "assets": [_asset_out(a) for a in assets],
        "recent_jobs": [_job_brief(j) for j in jobs],
    }


@router.get("/{project_id}/usage")
def get_usage(project_id: str, db: Session = Depends(get_db)):
    project = db.get(models.Project, project_id)
    if project is None:
        raise not_found("项目不存在")

    rows = (
        db.query(
            models.GenerationJob.model,
            func.count(models.GenerationJob.id),
            func.coalesce(func.sum(models.GenerationJob.cost_fen), 0),
        )
        .filter(
            models.GenerationJob.project_id == project_id,
            models.GenerationJob.status == "succeeded",
        )
        .group_by(models.GenerationJob.model)
        .all()
    )
    by_model = [
        {"model": model or "未知模型", "images": count, "cost_fen": int(cost or 0)}
        for model, count, cost in rows
    ]
    total = sum(item["cost_fen"] for item in by_model)
    images = sum(item["images"] for item in by_model)
    return {"total_fen": total, "images": images, "by_model": by_model}
