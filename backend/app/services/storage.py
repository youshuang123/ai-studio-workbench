"""资产落盘与校验。

安全规则（AGENTS.md 底线 6）：
- 扩展名白名单 + Pillow 真实解码 + MIME 三者一致才接受；
- 磁盘文件名一律用 UUID，**不使用用户原始文件名**（防路径穿越）；
- 限制大小与像素尺寸（防解压炸弹）。
"""

import hashlib
import io
import uuid
from datetime import datetime, timezone

from PIL import Image, UnidentifiedImageError

from .. import config
from ..errors import bad_request


class SavedImage:
    def __init__(self, rel_path: str, mime: str, size: int, width: int, height: int, sha256: str):
        self.rel_path = rel_path
        self.mime = mime
        self.size = size
        self.width = width
        self.height = height
        self.sha256 = sha256


def _subdir() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}/{now.month:02d}"


def _abs_path(rel_path: str):
    """把相对路径解析到 ASSETS_DIR 内，并确保结果没有逃逸出去。"""
    base = config.ASSETS_DIR.resolve()
    target = (base / rel_path).resolve()
    if not str(target).startswith(str(base)):
        raise bad_request("非法的文件路径", "INVALID_PATH")
    return target


def abs_path_for(rel_path: str):
    return _abs_path(rel_path)


def validate_and_save(raw: bytes, original_filename: str) -> SavedImage:
    if not raw:
        raise bad_request("上传的文件是空的", "INVALID_FILE")
    if len(raw) > config.MAX_UPLOAD_BYTES:
        raise bad_request(
            f"文件过大：{len(raw) / 1024 / 1024:.1f} MB，上限 "
            f"{config.MAX_UPLOAD_BYTES // 1024 // 1024} MB",
            "FILE_TOO_LARGE",
        )

    try:
        probe = Image.open(io.BytesIO(raw))
        probe.verify()  # 真实解码校验，能挡住"改了后缀的 txt"
    except (UnidentifiedImageError, OSError, ValueError):
        raise bad_request("文件格式不对：请上传 png / jpg / webp 图片", "INVALID_FILE")

    # verify() 之后对象不可再用，重新打开读属性
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError, ValueError):
        raise bad_request("图片已损坏或无法解码", "INVALID_FILE")

    fmt = (img.format or "").upper()
    mime_by_fmt = {
        "PNG": "image/png",
        "JPEG": "image/jpeg",
        "WEBP": "image/webp",
    }
    mime = mime_by_fmt.get(fmt)
    if mime is None:
        raise bad_request("只支持 png / jpg / webp 图片", "INVALID_FILE")

    ext = config.ALLOWED_MIME[mime]
    # 扩展名与真实类型必须一致（防伪装）
    suffix = ""
    if "." in (original_filename or ""):
        suffix = original_filename.rsplit(".", 1)[1].lower()
    suffix = "jpeg" if suffix == "jpeg" else suffix
    ok_suffixes = {"png": {"png"}, "jpeg": {"jpg", "jpeg"}, "webp": {"webp"}}
    if suffix and suffix not in ok_suffixes[mime.split("/")[1]]:
        raise bad_request(
            f"文件扩展名与真实格式不一致（真实格式是 {fmt}）", "INVALID_FILE"
        )

    width, height = img.size
    if max(width, height) > config.MAX_IMAGE_SIDE:
        raise bad_request(
            f"图片尺寸过大：{width}×{height}，单边上限 {config.MAX_IMAGE_SIDE}px",
            "INVALID_FILE",
        )

    config.ensure_dirs()
    sub = _subdir()
    name = f"{uuid.uuid4().hex}.{ext}"
    rel_path = f"{sub}/{name}"
    target = _abs_path(rel_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)

    return SavedImage(
        rel_path=rel_path,
        mime=mime,
        size=len(raw),
        width=width,
        height=height,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def save_generated(raw: bytes, fmt: str = "PNG") -> SavedImage:
    """保存模型返回的图片（统一转 PNG，丢掉透明通道问题由 Pillow 处理）。"""
    if not raw:
        raise ValueError("模型返回了空图片")
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValueError("模型返回的内容不是图片")

    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()

    config.ensure_dirs()
    rel_path = f"{_subdir()}/{uuid.uuid4().hex}.png"
    target = _abs_path(rel_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)

    return SavedImage(
        rel_path=rel_path,
        mime="image/png",
        size=len(data),
        width=img.size[0],
        height=img.size[1],
        sha256=hashlib.sha256(data).hexdigest(),
    )


def write_sidecar(rel_path: str, meta: dict) -> None:
    """在图片同目录写一份 .json 元数据（prompt / model / cost）。"""
    import json

    target = _abs_path(rel_path)
    side = target.with_suffix(".json")
    side.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
