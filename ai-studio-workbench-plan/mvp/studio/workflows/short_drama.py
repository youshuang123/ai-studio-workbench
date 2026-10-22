"""Short-drama workflow: script -> storyboard -> keyframes -> light-motion preview."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from studio.consistency import character_reference_pack, shot_prompt
from studio.gateway import BudgetExceeded, Gateway, ProviderError
from studio.light_motion import build_preview
from studio.models import AssetRecord, GenerationRequest
from studio.qa import QAChecker
from studio.store import Store


def load_script(path: str | Path) -> str:
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"script is empty: {path}")
    return text


def _load_storyboard(result_path: str) -> dict[str, Any]:
    data = json.loads(Path(result_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("shots"):
        raise ValueError("LLM did not return a storyboard with shots")
    return data


def run_short_drama(
    store: Store,
    gateway: Gateway,
    qa: QAChecker,
    script_text: str,
    run_id: str | None = None,
    character_name: str = "小夏",
    look: str = "20 岁，短发，米色风衣，透明雨伞",
) -> dict[str, Any]:
    run_id = run_id or store.new_run_id("drama")
    run_dir = store.run_dir(run_id)
    assets_dir = run_dir / "assets"

    storyboard_request = GenerationRequest(
        task="llm.chat",
        prompt=(
            "你是短剧分镜师。把下面的剧本拆成 JSON 分镜表，"
            "每个镜头包含 shot_id、scene、shot_size、camera、action、dialogue、"
            "duration、motion、prompt。只输出 JSON。\n\n" + script_text[:4000]
        ),
        quality="standard",
        metadata={"kind": "storyboard", "label": "storyboard"},
    )
    storyboard_result = gateway.generate(storyboard_request, run_id, assets_dir)
    storyboard = _load_storyboard(storyboard_result.output_path)

    pack = character_reference_pack(character_name, look)
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "type": "short_drama",
        "title": storyboard.get("title", "未命名短剧"),
        "character": pack.to_dict(),
        "storyboard_path": str(Path(storyboard_result.output_path).relative_to(run_dir)),
        "shots": [],
        "qa": [],
        "errors": [],
        "total_cost": 0.0,
        "currency": gateway.currency,
        "stopped_reason": "",
    }

    preview_shots: list[dict[str, Any]] = []
    stop = False
    for index, shot in enumerate(storyboard["shots"]):
        if stop:
            break
        prompt = shot_prompt(character_name, look, shot)
        request = GenerationRequest(
            task="image.generate",
            prompt=prompt,
            quality="standard",
            seed=pack.seed + index,
            width=1024,
            height=576,
            metadata={
                "shot_id": shot.get("shot_id"),
                "reference_pack_id": pack.id,
                "color": pack.color,
                "label": f"{shot.get('shot_id')} · 关键帧",
            },
        )
        asset_id = f"{pack.id}-{shot.get('shot_id', index + 1)}"
        try:
            result = gateway.generate(request, run_id, assets_dir)
        except BudgetExceeded as exc:
            manifest["stopped_reason"] = f"预算停止：{exc}"
            stop = True
            break
        except ProviderError as exc:
            manifest["errors"].append({"shot_id": shot.get("shot_id"), "error": str(exc)})
            continue

        report = qa.check(asset_id, request, result, pack)
        relative = str(Path(result.output_path).relative_to(run_dir))
        record = AssetRecord(
            asset_id=asset_id,
            kind="keyframe",
            path=relative,
            provider=result.provider,
            model=result.model,
            seed=request.seed,
            reference_pack_id=pack.id,
            cost=result.cost,
            qa_passed=report.passed,
            metadata={"shot_id": shot.get("shot_id"), "cached": result.cached},
        )
        manifest["shots"].append({**shot, "asset": record.to_dict(), "qa": report.to_dict()})
        manifest["qa"].append(report.to_dict())
        preview_shots.append(
            {
                "shot_id": shot.get("shot_id", ""),
                "image_path": result.output_path,
                "duration": float(shot.get("duration", 5.0)),
                "motion": shot.get("motion", "zoom_in"),
                "caption": shot.get("dialogue") or shot.get("action", ""),
                "scene": shot.get("scene", ""),
            }
        )

    preview = build_preview(run_dir, preview_shots, manifest["title"])
    manifest["preview"] = preview
    manifest["total_cost"] = round(gateway.budget.spent, 6)
    store.save_json(run_dir / "manifest.json", manifest)
    store.save_text(run_dir / "report.md", render_report(manifest))
    return manifest


def render_report(manifest: dict[str, Any]) -> str:
    lines = [
        f"# 短剧运行报告 `{manifest['run_id']}`",
        "",
        f"- 标题：{manifest['title']}",
        f"- 角色：{manifest['character']['name']}",
        f"- 镜头数：{len(manifest['shots'])}",
        f"- 总成本：¥{manifest['total_cost']:.4f}",
        f"- 轻动效预览：`{manifest['preview']['html']}`",
    ]
    if manifest.get("stopped_reason"):
        lines.append(f"- ⛔ {manifest['stopped_reason']}")
    if manifest.get("errors"):
        lines.append(f"- 失败镜头：{len(manifest['errors'])}")
    lines += [
        "",
        "| 镜头 | 场景 | 时长 | 运动 | 成本 | QA | 文件 |",
        "|---|---|---:|---|---:|---|---|",
    ]
    for shot in manifest["shots"]:
        asset = shot["asset"]
        qa = shot["qa"]
        status = "✅" if qa.get("passed") else "❌"
        lines.append(
            f"| {shot.get('shot_id', '')} | {shot.get('scene', '')} | "
            f"{shot.get('duration', 0)}s | {shot.get('motion', '')} | "
            f"¥{asset['cost']:.4f} | {status} | `{asset['path']}` |"
        )
    lines += [
        "",
        "> 打开 `preview.html` 查看关键帧 + CSS 轻动效预览；"
        "生产环境替换为 FFmpeg/时间线渲染。",
    ]
    return "\n".join(lines) + "\n"
