"""文生图客户端（OpenAI 兼容接口）。

设计要点：
- 业务代码不绑死供应商：换供应商只改 base_url + model 名；
- trust_env=False：直连国内服务，不经系统代理（PRD D7：数据不出境）；
- 超时/失败有限重试；错误码归一化，**不泄露 Key**。
"""

import base64
import time

import httpx

from .. import config


class ModelError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _ensure_configured() -> None:
    if not config.t2i_configured():
        raise ModelError(
            "MODEL_NOT_CONFIGURED",
            "未配置模型 API Key，请在 backend/.env 的 MODEL_T2I_API_KEY= 后填写",
        )


def generate_image(prompt: str, negative_prompt: str = "") -> bytes:
    _ensure_configured()

    url = f"{config.T2I_BASE_URL}/images/generations"
    payload = {
        "model": config.T2I_MODEL,
        "prompt": prompt if not negative_prompt else f"{prompt}\n\n避免出现：{negative_prompt}",
        "image_size": "1024x1024",
        "batch_size": 1,
        "num_inference_steps": 4,
    }
    headers = {
        "Authorization": f"Bearer {config.T2I_API_KEY}",
        "Content-Type": "application/json",
    }

    last_error: ModelError | None = None
    for attempt in range(2):  # 有限重试：最多 2 次
        try:
            with httpx.Client(timeout=config.T2I_TIMEOUT_SECONDS, trust_env=False) as client:
                resp = client.post(url, json=payload, headers=headers)
            if resp.status_code in (401, 403):
                raise ModelError("MODEL_AUTH_FAILED", "模型认证失败，请检查 API Key 是否正确")
            if resp.status_code == 429:
                raise ModelError("MODEL_RATE_LIMITED", "模型服务限流，请稍后重试")
            if resp.status_code >= 500:
                last_error = ModelError("MODEL_UPSTREAM_ERROR", "模型服务暂时不可用，请稍后重试")
                continue
            if resp.status_code != 200:
                raise ModelError("MODEL_BAD_REQUEST", "模型请求参数有误，请检查商品信息")

            data = resp.json()
            return _extract_image_bytes(data)
        except ModelError:
            raise
        except httpx.TimeoutException:
            last_error = ModelError("MODEL_TIMEOUT", "模型响应超时，可重试")
        except httpx.HTTPError:
            last_error = ModelError("MODEL_NETWORK_ERROR", "连接模型服务失败，请检查网络")
        except (KeyError, ValueError, TypeError):
            last_error = ModelError("MODEL_BAD_RESPONSE", "模型返回内容无法解析")

        if attempt == 0:
            time.sleep(0.5)

    raise last_error or ModelError("MODEL_UNKNOWN_ERROR", "模型调用失败，请稍后重试")


def _extract_image_bytes(data: dict) -> bytes:
    """兼容两种返回：b64_json 或 url。"""
    items = data.get("data") or data.get("images") or []
    if not items:
        raise ModelError("MODEL_BAD_RESPONSE", "模型没有返回图片")
    first = items[0]

    if isinstance(first, dict) and first.get("b64_json"):
        return base64.b64decode(first["b64_json"])

    url = None
    if isinstance(first, dict):
        url = first.get("url")
    elif isinstance(first, str):
        url = first

    if not url:
        raise ModelError("MODEL_BAD_RESPONSE", "模型返回里没有图片地址")

    with httpx.Client(timeout=config.T2I_TIMEOUT_SECONDS, trust_env=False) as client:
        resp = client.get(url)
    if resp.status_code != 200:
        raise ModelError("MODEL_DOWNLOAD_FAILED", "下载生成结果失败，请重试")
    return resp.content
