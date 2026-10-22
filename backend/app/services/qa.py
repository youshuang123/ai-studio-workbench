"""质检（2-3）：VLM 四维打分 + ΔE 颜色一致性。

设计要点：
- VLM 返回必须是严格 JSON，解析失败不崩，记为 qa_failed；
- ΔE 是本地计算，免费；
- 质检失败不影响精修结果本身（图已经出好了）。
"""

import base64
import json
import re

import httpx

from .. import config

QA_PROMPT = """你是电商主图质检员。请检查这张商品图，只输出一个 JSON 对象，不要任何解释。

评分维度（每项 1-3 分）：
1. follows_description：是否符合商品描述（{product_name}，类目 {category}，主色 {color}）
   1=明显不是这个商品  2=大致相似  3=完全一致
2. no_text_or_watermark：是否有文字、logo、促销标签、水印
   1=有明显文字/水印  2=有很淡的水印  3=干净无文字
3. product_complete：商品是否完整
   1=被裁切或明显变形  2=轻微不完整  3=完整居中
4. background_clean：背景是否干净
   1=杂乱  2=有阴影或杂物  3=纯白干净
5. color_consistency（仅当提供参考图时评分，否则填 null）：与参考图的商品颜色是否一致
   1=明显变色  2=轻微偏差  3=完全一致

输出格式（严格 JSON，不加代码块标记）：
{{"follows_description":3,"no_text_or_watermark":3,"product_complete":3,"background_clean":3,"color_consistency":3,"issues":[],"verdict":"pass"}}

verdict 规则：所有有效维度平均 >=2.5 为 pass，>=1.8 为 warn，否则 fail。"""

DIMENSIONS = [
    "follows_description",
    "no_text_or_watermark",
    "product_complete",
    "background_clean",
    "color_consistency",
]


def _to_data_url(raw: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64," + base64.b64encode(raw).decode()


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("无 JSON")
    return json.loads(text[start : end + 1])


def clamp_score(value, default: int = 2) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(3, n))


def verdict_for(total: int, dims: int = 4) -> str:
    """按平均分判定，避免维度数量变化后阈值失真。"""
    if dims <= 0:
        return "warn"
    avg = total / dims
    if avg >= 2.5:
        return "pass"
    if avg >= 1.8:
        return "warn"
    return "fail"


def normalize(raw_scores: dict, has_reference: bool = False) -> dict:
    """把模型返回规整成固定结构。

    color_consistency 只在有参考图时参与评分；没有参考图时给 None 并从总分里剔除。
    """
    scores: dict = {}
    for dim in DIMENSIONS:
        if dim == "color_consistency" and not has_reference:
            scores[dim] = None
            continue
        scores[dim] = clamp_score(raw_scores.get(dim))
    active = [v for v in scores.values() if isinstance(v, int)]
    total = sum(active)
    dims = len(active)
    issues = raw_scores.get("issues")
    if not isinstance(issues, list):
        issues = []
    issues = [str(i)[:200] for i in issues][:5]
    return {
        **scores,
        "total": total,
        "max_total": dims * 3,
        "issues": issues,
        "verdict": verdict_for(total, dims),
    }


def evaluate(
    image_bytes: bytes,
    product_name: str = "",
    category: str = "",
    color: str = "",
    reference_bytes: bytes | None = None,
) -> dict:
    """调用 VLM 打分。传 reference_bytes 时会同时评估颜色一致性。"""
    if not config.vlm_configured():
        return {"ok": False, "error": "VLM_NOT_CONFIGURED", "message": "未配置 VLM Key"}

    # 双图输入：先参考图（草稿），再精修图
    content: list[dict] = []
    if reference_bytes:
        content.append(
            {"type": "image_url", "image_url": {"url": _to_data_url(reference_bytes)}}
        )
    content.append({"type": "image_url", "image_url": {"url": _to_data_url(image_bytes)}})

    instruction = QA_PROMPT.format(
        product_name=product_name or "未知商品",
        category=category or "未指定",
        color=color or "未指定",
    )
    if reference_bytes:
        instruction = (
            "第一张图是原图（草稿），第二张是要检查的精修图。" + instruction
        )
    content.append({"type": "text", "text": instruction})

    payload = {
        "model": config.VLM_MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.1,
        "max_tokens": 400,
    }
    headers = {
        "Authorization": f"Bearer {config.VLM_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=config.VLM_TIMEOUT_SECONDS, trust_env=False) as client:
            resp = client.post(
                f"{config.VLM_BASE_URL}/chat/completions", json=payload, headers=headers
            )
        if resp.status_code != 200:
            return {
                "ok": False,
                "error": f"VLM_HTTP_{resp.status_code}",
                "message": "质检服务返回异常，稍后可重跑",
            }
        answer = resp.json()["choices"][0]["message"]["content"]
        data = normalize(_parse_json(answer), has_reference=bool(reference_bytes))
        data["ok"] = True
        return data
    except (KeyError, IndexError, TypeError):
        return {"ok": False, "error": "VLM_BAD_RESPONSE", "message": "质检结果无法解析"}
    except ValueError:
        return {"ok": False, "error": "VLM_BAD_JSON", "message": "质检返回的不是 JSON"}
    except httpx.TimeoutException:
        return {"ok": False, "error": "VLM_TIMEOUT", "message": "质检超时"}
    except httpx.HTTPError:
        return {"ok": False, "error": "VLM_NETWORK", "message": "连不上质检服务"}
