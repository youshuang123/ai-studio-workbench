"""Quality and safety checks.

The skeleton uses deterministic heuristics so the demo can run offline. In
production, replace `consistency` / `safety` with VLM/API calls and keep the
same report shape.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from studio.models import GenerationRequest, GenerationResult, QAReport, ReferencePack

DEFAULT_FORBIDDEN = ["暴力", "恐怖", "色情", "未成年人", "自杀", "仇恨"]


class QAChecker:
    def __init__(self, config: dict[str, Any] | None = None):
        config = config or {}
        self.consistency_threshold = float(config.get("consistency_threshold", 0.85))
        self.prompt_adherence_threshold = float(config.get("prompt_adherence_threshold", 0.70))

    def check(
        self,
        asset_id: str,
        request: GenerationRequest,
        result: GenerationResult,
        reference_pack: ReferencePack | None = None,
    ) -> QAReport:
        issues: list[str] = []
        path = Path(result.output_path)

        file_ok = path.exists() and path.stat().st_size > 0
        if not file_ok:
            issues.append("输出文件不存在或为空")

        if reference_pack:
            consistency = 0.92 if reference_pack.kind in ("sku", "character") else 0.86
        else:
            consistency = 0.84 if request.reference_images else 0.80

        adherence = 0.90 if len(request.prompt) >= 24 else 0.68
        if adherence < self.prompt_adherence_threshold:
            issues.append("prompt 过短，可能不足以约束生成结果")

        forbidden = list(DEFAULT_FORBIDDEN)
        if reference_pack:
            forbidden += reference_pack.forbidden
        safety = 1.0
        hits = [word for word in forbidden if word and word in request.prompt]
        if hits:
            safety = 0.0
            issues.append("命中禁止词：" + "、".join(hits))

        scores = {
            "consistency": round(consistency, 4),
            "prompt_adherence": round(adherence, 4),
            "safety": round(safety, 4),
        }
        passed = (
            file_ok
            and consistency >= self.consistency_threshold
            and adherence >= self.prompt_adherence_threshold
            and safety >= 1.0
        )
        return QAReport(asset_id=asset_id, passed=passed, scores=scores, issues=issues)
