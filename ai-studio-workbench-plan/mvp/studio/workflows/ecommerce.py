"""E-commerce batch workflow: SKU -> main/scene images -> QA -> manifest."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from studio.consistency import ecommerce_prompt, ecommerce_reference_pack
from studio.gateway import BudgetExceeded, Gateway, ProviderError
from studio.models import AssetRecord, GenerationRequest
from studio.qa import QAChecker
from studio.store import Store

TEMPLATE_SIZES = {
    "main": (1024, 1024),
    "scene": (1024, 1024),
    "detail": (1024, 1024),
}


def load_skus(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    skus = []
    for row in rows:
        clean = {str(k).strip(): (v or "").strip() for k, v in row.items() if k}
        if clean.get("sku"):
            skus.append(clean)
    if not skus:
        raise ValueError(f"no SKU rows found in {path}")
    return skus


def run_ecommerce(
    store: Store,
    gateway: Gateway,
    qa: QAChecker,
    skus: list[dict[str, Any]],
    run_id: str | None = None,
    templates: tuple[str, ...] = ("main", "scene"),
) -> dict[str, Any]:
    run_id = run_id or store.new_run_id("ecom")
    run_dir = store.run_dir(run_id)
    assets_dir = run_dir / "assets"
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "type": "ecommerce",
        "templates": list(templates),
        "skus": len(skus),
        "assets": [],
        "qa": [],
        "errors": [],
        "total_cost": 0.0,
        "currency": gateway.currency,
        "stopped_reason": "",
    }

    stop = False
    for sku in skus:
        pack = ecommerce_reference_pack(sku)
        for template in templates:
            if stop:
                break
            width, height = TEMPLATE_SIZES.get(template, (1024, 1024))
            prompt = ecommerce_prompt(sku, template)
            request = GenerationRequest(
                task="image.generate",
                prompt=prompt,
                quality="standard",
                seed=pack.seed,
                width=width,
                height=height,
                metadata={
                    "sku": sku.get("sku"),
                    "template": template,
                    "reference_pack_id": pack.id,
                    "color": pack.color,
                    "label": f"{sku.get('sku')} · {template}",
                },
            )
            asset_id = f"{pack.id}-{template}-{len(manifest['assets']) + 1}"
            try:
                result = gateway.generate(request, run_id, assets_dir)
            except BudgetExceeded as exc:
                manifest["stopped_reason"] = f"预算停止：{exc}"
                stop = True
                break
            except ProviderError as exc:
                manifest["errors"].append({"asset_id": asset_id, "error": str(exc)})
                continue

            report = qa.check(asset_id, request, result, pack)
            relative = str(Path(result.output_path).relative_to(run_dir))
            record = AssetRecord(
                asset_id=asset_id,
                kind="image",
                path=relative,
                provider=result.provider,
                model=result.model,
                seed=request.seed,
                reference_pack_id=pack.id,
                cost=result.cost,
                qa_passed=report.passed,
                metadata={"sku": sku.get("sku"), "template": template, "cached": result.cached},
            )
            manifest["assets"].append(record.to_dict())
            manifest["qa"].append(report.to_dict())

    manifest["total_cost"] = round(gateway.budget.spent, 6)
    store.save_json(run_dir / "manifest.json", manifest)
    store.save_text(run_dir / "report.md", render_report(manifest))
    return manifest


def render_report(manifest: dict[str, Any]) -> str:
    lines = [
        f"# 电商素材运行报告 `{manifest['run_id']}`",
        "",
        f"- SKU 数：{manifest['skus']}",
        f"- 模板：{', '.join(manifest['templates'])}",
        f"- 产出资产：{len(manifest['assets'])}",
        f"- 总成本：¥{manifest['total_cost']:.4f}",
        f"- 币种：{manifest['currency']}",
    ]
    if manifest.get("stopped_reason"):
        lines.append(f"- ⛔ {manifest['stopped_reason']}")
    if manifest.get("errors"):
        lines.append(f"- 失败任务：{len(manifest['errors'])}")
    lines += [
        "",
        "| 资产 | 模板 | 成本 | QA | 文件 |",
        "|---|---|---:|---|---|",
    ]
    qa_by_id = {item["asset_id"]: item for item in manifest["qa"]}
    for asset in manifest["assets"]:
        report = qa_by_id.get(asset["asset_id"], {})
        status = "✅" if report.get("passed") else "❌"
        lines.append(
            f"| {asset['asset_id']} | {asset['metadata'].get('template', '')} | "
            f"¥{asset['cost']:.4f} | {status} | `{asset['path']}` |"
        )
    lines += ["", "> 打开 `preview` 类 HTML 或直接查看 `assets/` 下的 SVG 占位图。"]
    return "\n".join(lines) + "\n"
