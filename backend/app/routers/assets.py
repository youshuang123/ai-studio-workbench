from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..errors import bad_request, not_found
from ..services import storage

router = APIRouter(tags=["assets"])


@router.post("/api/projects/{project_id}/assets", status_code=201)
async def upload_asset(
    project_id: str,
    file: UploadFile,
    db: Session = Depends(get_db),
):
    project = db.get(models.Project, project_id)
    if project is None:
        raise not_found("项目不存在")

    raw = await file.read()
    saved = storage.validate_and_save(raw, file.filename or "")

    asset = models.Asset(
        project_id=project_id,
        kind="upload",
        filename=(file.filename or "upload")[:255],
        path=saved.rel_path,
        mime=saved.mime,
        bytes=saved.size,
        width=saved.width,
        height=saved.height,
        sha256=saved.sha256,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    return {
        "id": asset.id,
        "project_id": asset.project_id,
        "kind": asset.kind,
        "filename": asset.filename,
        "mime": asset.mime,
        "bytes": asset.bytes,
        "width": asset.width,
        "height": asset.height,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
        "url": f"/api/assets/{asset.id}/file",
    }


def _get_asset_or_404(asset_id: str, db: Session) -> models.Asset:
    asset = db.get(models.Asset, asset_id)
    if asset is None:
        raise not_found("资产不存在")
    return asset


@router.get("/api/assets/{asset_id}/file")
def get_asset_file(asset_id: str, db: Session = Depends(get_db)):
    asset = _get_asset_or_404(asset_id, db)
    try:
        path = storage.abs_path_for(asset.path)
    except Exception:
        raise not_found("资产文件不可用")
    if not path.exists():
        raise not_found("资产文件不存在")
    return FileResponse(
        str(path),
        media_type=asset.mime,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/api/assets/{asset_id}/download")
def download_asset(asset_id: str, db: Session = Depends(get_db)):
    asset = _get_asset_or_404(asset_id, db)
    try:
        path = storage.abs_path_for(asset.path)
    except Exception:
        raise not_found("资产文件不可用")
    if not path.exists():
        raise not_found("资产文件不存在")

    suffix = path.suffix or ".png"
    name = (asset.filename or "asset").rsplit("/", 1)[-1]
    if not name.lower().endswith(suffix.lower()):
        name = f"{name}{suffix}"
    return FileResponse(
        str(path),
        media_type=asset.mime,
        filename=name,
        headers={"Cache-Control": "private, max-age=3600"},
    )
