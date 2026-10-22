"""Light-motion preview: keyframes + CSS pan/zoom, no video model required.

Production can replace this with an FFmpeg worker. This module intentionally
uses only the standard library so the skeleton runs anywhere.
"""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any


MOTIONS = {"zoom_in", "zoom_out", "pan_left", "pan_right", "tilt_up", "tilt_down"}

CSS = """
:root { color-scheme: dark; }
body {
  margin: 0; background: #0b1020; color: #e5e7eb;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
}
header { padding: 20px 28px 8px; }
h1 { font-size: 20px; margin: 0 0 6px; }
.meta { color: #9ca3af; font-size: 13px; }
.stage {
  position: relative; width: min(1080px, 92vw); aspect-ratio: 16 / 9;
  margin: 18px auto; overflow: hidden; border-radius: 14px;
  background: #000; box-shadow: 0 18px 50px rgba(0,0,0,.45);
}
.slide { position: absolute; inset: 0; opacity: 0; transition: opacity .45s ease; }
.slide.active { opacity: 1; }
.slide img { width: 100%; height: 100%; object-fit: cover; transform-origin: center; }
.caption {
  position: absolute; left: 0; right: 0; bottom: 0; padding: 28px 26px 20px;
  background: linear-gradient(transparent, rgba(0,0,0,.78));
  font-size: 16px; line-height: 1.5;
}
.tag { color: #93c5fd; font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }
.timeline { width: min(1080px, 92vw); margin: 0 auto 32px; color: #9ca3af; font-size: 13px; }
@keyframes zoomIn { from { transform: scale(1); } to { transform: scale(1.12); } }
@keyframes zoomOut { from { transform: scale(1.12); } to { transform: scale(1); } }
@keyframes panLeft { from { transform: scale(1.08) translateX(0); } to { transform: scale(1.08) translateX(-5%); } }
@keyframes panRight { from { transform: scale(1.08) translateX(0); } to { transform: scale(1.08) translateX(5%); } }
@keyframes tiltUp { from { transform: scale(1.08) translateY(0); } to { transform: scale(1.08) translateY(-4%); } }
@keyframes tiltDown { from { transform: scale(1.08) translateY(0); } to { transform: scale(1.08) translateY(4%); } }
"""

JS = """
const slides = Array.from(document.querySelectorAll('.slide'));
let index = 0;
function show() {
  slides.forEach(s => s.classList.remove('active'));
  const slide = slides[index];
  if (!slide) return;
  slide.classList.add('active');
  const img = slide.querySelector('img');
  const motion = slide.dataset.motion || 'zoom_in';
  const duration = parseFloat(slide.dataset.duration || '5');
  img.style.animation = 'none';
  void img.offsetWidth;
  img.style.animation = `${motion} ${duration}s ease-in-out infinite alternate`;
  const nextInMs = duration * 1000;
  index = (index + 1) % slides.length;
  setTimeout(show, nextInMs);
}
show();
"""


def _rel(path: str | Path, base: Path) -> str:
    try:
        return os.path.relpath(Path(path), base)
    except ValueError:
        return str(path)


def build_preview(
    output_dir: str | Path,
    shots: list[dict[str, Any]],
    title: str = "轻动效预览",
) -> dict[str, Any]:
    """Write preview.html + preview.json. Returns the manifest."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    slides = []
    total = 0.0
    for shot in shots:
        duration = float(shot.get("duration", 5.0))
        total += duration
        motion = str(shot.get("motion", "zoom_in"))
        if motion not in MOTIONS:
            motion = "zoom_in"
        slides.append(
            {
                "shot_id": shot.get("shot_id", ""),
                "image": _rel(shot.get("image_path", ""), output_dir),
                "duration": duration,
                "motion": motion,
                "caption": shot.get("caption", ""),
                "scene": shot.get("scene", ""),
            }
        )

    cards = []
    for slide in slides:
        cards.append(
            f"""    <div class="slide" data-motion="{html.escape(slide['motion'])}" data-duration="{slide['duration']}">
      <img src="{html.escape(slide['image'])}" alt="{html.escape(slide['shot_id'])}">
      <div class="caption"><div class="tag">{html.escape(slide['shot_id'])} · {html.escape(slide['scene'])}</div>{html.escape(slide['caption'])}</div>
    </div>"""
        )

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>{html.escape(title)}</h1>
  <div class="meta">{len(slides)} 个镜头 · 约 {total:.0f} 秒 · 关键帧 + CSS 轻动效（骨架演示）</div>
</header>
<div class="stage">
{chr(10).join(cards)}
</div>
<div class="timeline">生产环境将此预览替换为 FFmpeg/时间线渲染；镜头、时长、运动参数已写入 preview.json。</div>
<script>{JS}</script>
</body>
</html>
"""
    html_path = output_dir / "preview.html"
    html_path.write_text(document, encoding="utf-8")
    manifest = {
        "kind": "light_motion_preview",
        "title": title,
        "total_duration_seconds": round(total, 2),
        "shots": slides,
        "html": str(html_path),
    }
    (output_dir / "preview.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest
