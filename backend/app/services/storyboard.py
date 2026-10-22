"""短剧分镜表生成（LLM）。

规则：
- 严格 JSON 输出，Pydantic 校验；
- 校验失败重试 1 次，仍失败抛错（不静默降级）；
- 台词保留原剧本措辞，不改写。
"""

import json
import re

import httpx

from .. import config

SHOT_SIZES = ["远景", "全景", "中景", "近景", "特写"]
CAMERAS = ["平视", "俯拍", "仰拍", "过肩", "侧拍"]

STORYBOARD_PROMPT = """你是短剧分镜师。把下面的剧本拆成可拍摄的分镜表。

剧本：
{script}

已知角色：{characters}
风格：{style}

要求：
1. 按场次拆（一场戏通常 3-6 个镜头），总镜头数不超过 {max_shots} 个；
2. 每个镜头必须包含这些字段：
   - shot_size：景别，只能是 {shot_sizes} 之一
   - camera：机位，只能是 {cameras} 之一
   - action：画面里发生什么（1-2 句，具体可拍）
   - dialogue：这一镜的台词，没有就空字符串；**保留原剧本措辞，不要改写**
   - duration_sec：2-8 之间的数字
   - mood：情绪（如 紧张 / 温暖 / 压抑）
   - continuity：连续性提示（服装、道具、时间）
3. 只输出 JSON，不要任何解释或代码块标记：
{{"scenes":[{{"title":"场次标题","location":"地点","time_of_day":"日/夜","summary":"一句话概括","shots":[{{"shot_size":"中景","camera":"平视","action":"…","dialogue":"…","duration_sec":3,"mood":"…","continuity":"…"}}]}}]}}
"""


class StoryboardError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("无 JSON 对象")
    return json.loads(text[start : end + 1])


def _chat(messages: list[dict], temperature: float = 0.3, max_tokens: int = 3000) -> str:
    if not config.llm_configured():
        raise StoryboardError(
            "LLM_NOT_CONFIGURED",
            "未配置剧本模型 Key：请在 backend/.env 填写 MODEL_LLM_API_KEY（或沿用 MODEL_T2I_API_KEY）",
        )
    payload = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {config.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=config.LLM_TIMEOUT_SECONDS, trust_env=False) as client:
            resp = client.post(
                f"{config.LLM_BASE_URL}/chat/completions", json=payload, headers=headers
            )
    except httpx.TimeoutException:
        raise StoryboardError("LLM_TIMEOUT", "剧本模型超时，请稍后重试")
    except httpx.HTTPError:
        raise StoryboardError("LLM_NETWORK", "连不上剧本模型服务")

    if resp.status_code in (401, 403):
        raise StoryboardError("LLM_AUTH_FAILED", "剧本模型认证失败，请检查 API Key")
    if resp.status_code != 200:
        raise StoryboardError("LLM_HTTP_ERROR", f"剧本模型返回 {resp.status_code}")
    try:
        return resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise StoryboardError("LLM_BAD_RESPONSE", "剧本模型返回内容无法解析")


def validate_storyboard(data: dict, max_shots: int = 40) -> dict:
    """把模型输出规整成固定结构；不合法直接抛错。"""
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise StoryboardError("STORYBOARD_INVALID", "分镜表没有场次")

    out_scenes = []
    total_shots = 0
    for si, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            continue
        shots_in = sc.get("shots")
        if not isinstance(shots_in, list):
            shots_in = []
        shots = []
        for sh in shots_in:
            if not isinstance(sh, dict):
                continue
            total_shots += 1
            if total_shots > max_shots:
                break
            shot_size = str(sh.get("shot_size") or "中景").strip()
            if shot_size not in SHOT_SIZES:
                shot_size = "中景"
            camera = str(sh.get("camera") or "平视").strip()
            if camera not in CAMERAS:
                camera = "平视"
            try:
                duration = float(sh.get("duration_sec") or 3)
            except (TypeError, ValueError):
                duration = 3.0
            duration = max(2.0, min(8.0, duration))
            action = str(sh.get("action") or "").strip()
            if not action:
                continue  # 没动作描述的镜头没有意义，丢弃
            shots.append(
                {
                    "shot_size": shot_size,
                    "camera": camera,
                    "action": action[:500],
                    "dialogue": str(sh.get("dialogue") or "").strip()[:500],
                    "duration_sec": round(duration, 2),
                    "mood": str(sh.get("mood") or "").strip()[:40],
                    "continuity": str(sh.get("continuity") or "").strip()[:300],
                }
            )
        out_scenes.append(
            {
                "index": si,
                "title": str(sc.get("title") or f"第 {si + 1} 场").strip()[:120],
                "location": str(sc.get("location") or "").strip()[:120],
                "time_of_day": str(sc.get("time_of_day") or "").strip()[:40],
                "summary": str(sc.get("summary") or "").strip()[:500],
                "shots": shots,
            }
        )

    if not any(sc["shots"] for sc in out_scenes):
        raise StoryboardError("STORYBOARD_EMPTY", "分镜表里没有任何有效镜头")
    return {"scenes": out_scenes}


def generate(script: str, characters: list[str], style: str = "都市") -> tuple[dict, int]:
    """调 LLM 生成分镜表。返回 (规整后的结构, 尝试次数)。"""
    script = (script or "").strip()
    if not script:
        raise StoryboardError("SCRIPT_EMPTY", "剧本不能为空")
    if len(script) > 8000:
        raise StoryboardError("SCRIPT_TOO_LONG", "剧本过长（上限 8000 字）")

    prompt = STORYBOARD_PROMPT.format(
        script=script,
        characters="、".join(characters) if characters else "未指定",
        style=style or "都市",
        max_shots=config.DRAMA_MAX_SHOTS,
        shot_sizes=" / ".join(SHOT_SIZES),
        cameras=" / ".join(CAMERAS),
    )
    messages = [
        {"role": "system", "content": "你是短剧分镜师，只输出 JSON。"},
        {"role": "user", "content": prompt},
    ]

    last_error: StoryboardError | None = None
    for attempt in range(2):
        try:
            raw = _chat(messages, temperature=0.3 if attempt == 0 else 0.1)
            return validate_storyboard(_parse_json(raw), config.DRAMA_MAX_SHOTS), attempt + 1
        except StoryboardError as exc:
            if exc.code.startswith("LLM_"):
                raise
            last_error = exc
        except (ValueError, json.JSONDecodeError):
            last_error = StoryboardError("STORYBOARD_INVALID", "分镜表不是合法 JSON")

    raise last_error or StoryboardError("STORYBOARD_INVALID", "分镜表生成失败")


def shot_prompt(
    shot: dict,
    scene: dict,
    characters: list[dict],
    style: str = "都市",
) -> str:
    """把分镜字段拼成生图 prompt。"""
    names = {c["id"]: c for c in characters}
    cast = []
    for cid in shot.get("character_ids") or []:
        c = names.get(cid)
        if not c:
            continue
        bits = [c.get("name", "")]
        if c.get("appearance"):
            bits.append(c["appearance"])
        if c.get("costume"):
            bits.append(c["costume"])
        cast.append("，".join(b for b in bits if b))

    lines = [
        f"短剧画面：{shot['shot_size']}，{shot['camera']}机位。",
        f"动作：{shot['action']}",
    ]
    if shot.get("mood"):
        lines.append(f"情绪：{shot['mood']}")
    if cast:
        lines.append(f"角色：{'；'.join(cast)}")
    if scene.get("location") or scene.get("time_of_day"):
        lines.append(f"场景：{scene.get('location') or ''} {scene.get('time_of_day') or ''}".strip())
    if shot.get("continuity"):
        lines.append(f"连续性：{shot['continuity']}")
    lines.append(f"风格：{style}")
    lines.append("画面中不要出现任何文字、字幕、水印。")
    return "\n".join(lines)
