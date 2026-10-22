"""轻动效合成（FFmpeg）：按景别选运镜 + 交叉转场。

2-4a 已验证的管线，这里做成可配置：
- 远景/全景：缓慢推近
- 中景：水平平移
- 近景/特写：轻微推近 + 上移
- 镜头之间 xfade 0.4s
"""

import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg

TRANSITION = 0.4


class ComposeError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def motion_for(shot_size: str) -> str:
    if shot_size in ("远景", "全景"):
        return "zoom_in"
    if shot_size in ("近景", "特写"):
        return "zoom_in_up"
    return "pan_right"


def _filter_for(motion: str, frames: int, fps: int, size: int) -> str:
    """返回 zoompan/fade 滤镜串。输入已 scale 到 2×size 以留出运镜余量。"""
    base = f"scale={size * 2}:{size * 2}"

    if motion == "zoom_in":
        zp = (
            f"zoompan=z='min(1+0.0016*on,1.12)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        )
    elif motion == "zoom_in_up":
        zp = (
            f"zoompan=z='min(1+0.0010*on,1.07)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)-on*0.35'"
        )
    else:  # pan_right
        zp = (
            f"zoompan=z='1.10':"
            f"x='(iw-iw/zoom)*on/{max(1, frames - 1)}':y='ih/2-(ih/zoom/2)'"
        )

    fade = f"fade=t=in:st=0:d=0.3"
    return f"{base},{zp}:d={frames}:s={size}x{size}:fps={fps},{fade},setsar=1"


def compose(
    shots: list[dict],
    out_path: Path,
    size: int = 720,
    fps: int = 25,
) -> Path:
    """shots: [{"path": Path, "duration_sec": float, "shot_size": str}, ...]

    返回输出文件路径。
    """
    if not shots:
        raise ComposeError("NO_SHOTS", "没有可合成的镜头")

    for s in shots:
        if not Path(s["path"]).exists():
            raise ComposeError("MISSING_KEYFRAME", f"镜头关键帧文件丢失：{s.get('index', '?')}")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    inputs: list[str] = []
    filters: list[str] = []
    durations: list[float] = []

    for i, s in enumerate(shots):
        duration = max(2.0, min(8.0, float(s.get("duration_sec") or 3)))
        durations.append(duration)
        frames = max(2, int(duration * fps))
        inputs += ["-i", str(s["path"])]
        motion = motion_for(s.get("shot_size") or "中景")
        filters.append(f"[{i}:v]{_filter_for(motion, frames, fps, size)}[v{i}]")

    # 交叉淡化拼接
    prev = "v0"
    for i in range(1, len(shots)):
        out = f"x{i}"
        offset = sum(durations[:i]) - TRANSITION * i
        if offset <= 0:
            offset = 0.01
        filters.append(
            f"[{prev}][v{i}]xfade=transition=fade:duration={TRANSITION}:offset={offset:.2f}[{out}]"
        )
        prev = out

    cmd = [
        _ffmpeg(), "-y", *inputs,
        "-filter_complex", ";".join(filters),
        "-map", f"[{prev}]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
        "-movflags", "+faststart",
        str(out_path),
    ]

    with tempfile.NamedTemporaryFile("w+", suffix=".log", delete=False) as log:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        log.write(proc.stderr or "")
        log_path = log.name

    if proc.returncode != 0:
        tail = (proc.stderr or "")[-800:]
        raise ComposeError("FFMPEG_FAILED", f"视频合成失败：{tail[:300]}")

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise ComposeError("FFMPEG_EMPTY", "视频合成没有产出文件")

    try:
        Path(log_path).unlink(missing_ok=True)
    except OSError:
        pass

    return out_path


def probe(path: Path) -> dict:
    """读取视频时长/尺寸，用于验收时核对。"""
    proc = subprocess.run([_ffmpeg(), "-i", str(path)], capture_output=True, text=True)
    text = proc.stderr or ""
    duration = None
    size = None
    for line in text.splitlines():
        if "Duration:" in line and duration is None:
            stamp = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = stamp.split(":")
            duration = round(int(h) * 3600 + int(m) * 60 + float(s), 2)
        if "Video:" in line and size is None:
            import re

            m = re.search(r"(\d{2,5})x(\d{2,5})", line)
            if m:
                size = (int(m.group(1)), int(m.group(2)))
    return {"duration_sec": duration, "size": size, "bytes": path.stat().st_size}
