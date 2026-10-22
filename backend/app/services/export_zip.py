"""导出 ZIP：图片 + 清单.csv + 账单.csv。

规则（2-2 技术开发文档 §6.5）：
- 流式写入临时文件，不把整包读进内存；
- 图片名用 sku_code（中文文件名在部分系统会乱码）；
- 同名（同 SKU 多次生成）→ CUP-001_2.png；
- ZIP 不落库，返回后由响应流处理。
"""

import csv
import io
import re
import tempfile
import zipfile
from datetime import datetime, timezone

from .. import models


def _safe_name(raw: str, fallback: str) -> str:
    """只保留字母数字、下划线、连字符、中文，其余替换为下划线。"""
    text = (raw or "").strip() or fallback
    text = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", text, flags=re.UNICODE)
    return text[:60] or fallback


def build_zip(db, batch: models.Batch, jobs: list) -> tuple[str, str]:
    """返回 (临时文件路径, 下载文件名)。调用方负责删除临时文件。"""
    succeeded = [j for j in jobs if j.status == "succeeded" and j.output_asset_id]

    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.close()

    used: dict[str, int] = {}

    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
        # ── 图片 ──
        for job in succeeded:
            asset = db.get(models.Asset, job.output_asset_id)
            if asset is None:
                continue
            from . import storage

            try:
                path = storage.abs_path_for(asset.path)
            except Exception:  # noqa: BLE001 路径异常时跳过，不影响整包
                continue
            if not path.exists():
                continue

            base = _safe_name(job.sku_code or "", f"item_{job.id[:8]}")
            count = used.get(base, 0) + 1
            used[base] = count
            filename = f"images/{base}.png" if count == 1 else f"images/{base}_{count}.png"
            zf.write(path, filename)

        # ── 清单 ──
        manifest = io.StringIO()
        writer = csv.writer(manifest)
        writer.writerow(
            ["sku_code", "product_name", "status", "cost_fen", "error_code", "finished_at"]
        )
        for job in jobs:
            writer.writerow(
                [
                    job.sku_code or "",
                    job.product_name or "",
                    job.status,
                    job.cost_fen or 0,
                    job.error_code or "",
                    job.finished_at.isoformat() if job.finished_at else "",
                ]
            )
        zf.writestr("清单.csv", "\ufeff" + manifest.getvalue())  # BOM 让 Excel 正确识别中文

        # ── 账单 ──
        by_model: dict[str, dict] = {}
        for job in succeeded:
            key = job.model or "未知模型"
            entry = by_model.setdefault(key, {"images": 0, "cost_fen": 0})
            entry["images"] += 1
            entry["cost_fen"] += job.cost_fen or 0

        bill = io.StringIO()
        bwriter = csv.writer(bill)
        bwriter.writerow(["model", "images", "cost_fen", "cost_yuan"])
        for model, agg in by_model.items():
            bwriter.writerow(
                [model, agg["images"], agg["cost_fen"], f"{agg['cost_fen'] / 100:.2f}"]
            )
        bwriter.writerow([])
        bwriter.writerow(
            ["合计", sum(v["images"] for v in by_model.values()), sum(v["cost_fen"] for v in by_model.values()), f"{sum(v['cost_fen'] for v in by_model.values()) / 100:.2f}"]
        )
        zf.writestr("账单.csv", "\ufeff" + bill.getvalue())

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    download_name = f"{_safe_name(batch.name, 'batch')}-{stamp}.zip"
    return tmp.name, download_name
