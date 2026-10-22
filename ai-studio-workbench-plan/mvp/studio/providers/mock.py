"""Offline mock provider: deterministic SVG placeholders + storyboard JSON.

This lets the entire product skeleton run without API keys, network, ffmpeg, or
Pillow. Real providers are adapters in `http.py` (or vendor-specific subclasses).
"""

from __future__ import annotations

import hashlib
import html
import json
import time
from pathlib import Path

from studio.models import GenerationRequest, GenerationResult
from studio.providers.base import Provider


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _color_for(request: GenerationRequest) -> str:
    explicit = str(request.metadata.get("color", "")).strip()
    if explicit.startswith("#") and len(explicit) in (4, 7):
        return explicit
    palette = ["#1f6feb", "#d97706", "#0f766e", "#7c3aed", "#be123c", "#0369a1"]
    return palette[int(_digest(request.prompt)[:8], 16) % len(palette)]


def _wrap(text: str, width: int = 42, max_lines: int = 5) -> list[str]:
    text = " ".join(text.split())
    lines = [text[i:i + width] for i in range(0, len(text), width)]
    return lines[:max_lines] or [""]


def _svg(request: GenerationRequest, label: str) -> str:
    color = _color_for(request)
    width, height = request.width, request.height
    lines = _wrap(request.prompt)
    text_block = "".join(
        f'<text x="48" y="{220 + i * 42}" font-family="Arial, sans-serif" '
        f'font-size="28" fill="#ffffff">{html.escape(line)}</text>'
        for i, line in enumerate(lines)
    )
    seed = request.seed if request.seed is not None else 0
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{color}"/>
      <stop offset="100%" stop-color="#111827"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <circle cx="{int(width * 0.78)}" cy="{int(height * 0.26)}" r="{int(min(width, height) * 0.18)}"
          fill="#ffffff" fill-opacity="0.12"/>
  <rect x="32" y="32" width="{width - 64}" height="{height - 64}" fill="none"
        stroke="#ffffff" stroke-opacity="0.35" stroke-width="2"/>
  <text x="48" y="96" font-family="Arial, sans-serif" font-size="24" fill="#ffffff"
        fill-opacity="0.85">{html.escape(label)}</text>
  {text_block}
  <text x="48" y="{height - 48}" font-family="Arial, sans-serif" font-size="20"
        fill="#ffffff" fill-opacity="0.65">seed {seed} · mock provider · {request.task}</text>
</svg>
"""


def _storyboard(_request: GenerationRequest) -> dict:
    shots = [
        ("S01", "雨夜便利店外", "全景", "固定", "小夏撑伞走到店门口，霓虹反光", "这雨，好像不会停了。", 5.0, "zoom_in"),
        ("S02", "便利店门口", "中景", "跟拍", "小夏收起伞，推门而入", "", 4.0, "pan_right"),
        ("S03", "便利店内", "近景", "固定", "店员抬头，两人对视", "欢迎光临。", 4.0, "zoom_out"),
        ("S04", "货架旁", "特写", "横移", "小夏拿起一盒热牛奶", "还是老样子。", 5.0, "pan_left"),
        ("S05", "收银台", "双人中景", "固定", "店员递过找零，小夏犹豫", "你……明天还来吗？", 6.0, "tilt_up"),
        ("S06", "便利店外", "远景", "拉远", "小夏撑伞离开，雨变小", "", 6.0, "zoom_out"),
    ]
    return {
        "title": "雨夜便利店",
        "characters": [
            {"name": "小夏", "look": "20 岁，短发，米色风衣，透明雨伞"},
            {"name": "店员", "look": "30 岁，黑框眼镜，深蓝围裙"},
        ],
        "shots": [
            {
                "shot_id": shot_id,
                "scene": scene,
                "shot_size": size,
                "camera": camera,
                "action": action,
                "dialogue": dialogue,
                "duration": duration,
                "motion": motion,
                "prompt": f"{scene}，{size}，{camera}，{action}，电影感，雨夜，霓虹，{dialogue or '无台词'}",
            }
            for shot_id, scene, size, camera, action, dialogue, duration, motion in shots
        ],
    }


class MockProvider(Provider):
    def generate(self, model: str, request: GenerationRequest, output_dir: Path) -> GenerationResult:
        started = time.time()
        output_dir.mkdir(parents=True, exist_ok=True)
        digest = _digest(json.dumps(request.to_dict(), ensure_ascii=False, sort_keys=True))[:12]

        if request.task in ("image.generate", "image.edit"):
            label = str(request.metadata.get("label") or request.task)
            path = output_dir / f"{request.task.replace('.', '_')}_{digest}.svg"
            path.write_text(_svg(request, label), encoding="utf-8")
        elif request.task == "llm.chat":
            if request.metadata.get("kind") == "storyboard":
                data = _storyboard(request)
            else:
                data = {"text": f"mock response: {request.prompt[:120]}"}
            path = output_dir / f"llm_{digest}.json"
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        elif request.task == "vision.qa":
            data = {
                "consistency": 0.92,
                "prompt_adherence": 0.88,
                "safety": 1.0,
                "issues": [],
            }
            path = output_dir / f"qa_{digest}.json"
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        elif request.task == "video.generate":
            data = {
                "kind": "mock-video-manifest",
                "duration_seconds": request.duration_seconds or 5.0,
                "prompt": request.prompt,
                "note": "Mock provider does not render video. Use light_motion preview.",
            }
            path = output_dir / f"video_{digest}.json"
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            raise ValueError(f"mock provider does not support task {request.task}")

        latency_ms = int((time.time() - started) * 1000) + 5
        return GenerationResult(
            provider=self.name,
            model=model,
            task=request.task,
            output_path=str(path),
            cost=0.0,  # gateway sets the real cost from the price table
            latency_ms=latency_ms,
            metadata={"digest": digest, "offline": True},
        )
