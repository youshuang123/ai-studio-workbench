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


REFINE_PROMPT_SUFFIX = (
    "\n\n精修要求：\n"
    "1. 严格保持商品的形状、比例、结构、颜色不变，只改善背景和光线。\n"
    "2. 画面中不得出现任何文字、字母、数字、汉字、标签、水印、装饰图案、色块、边框。\n"
    "3. 除商品本身与纯白背景外，不要添加任何其他元素。\n"
    "\n"
    "English constraints: Clean product photography on a pure white background. "
    "Preserve the product's exact shape, proportions, structure and color. "
    "ABSOLUTELY NO TEXT, no letters, no numbers, no Chinese characters, no logos, "
    "no labels, no watermarks, no badges, no decorative graphics, no borders. "
    "Nothing but the product and the white background."
)


def generate_edit(prompt: str, source_image: bytes, mime: str = "image/png") -> bytes:
    """图生图精修（Qwen-Image-Edit 等）。输入为原图二进制。"""
    if not config.edit_configured():
        raise ModelError(
            "EDIT_NOT_CONFIGURED",
            "未配置精修模型 Key，请在 backend/.env 填写 MODEL_EDIT_API_KEY（或沿用 MODEL_T2I_API_KEY）",
        )

    import base64

    url = f"{config.EDIT_BASE_URL}/images/generations"
    payload = {
        "model": config.EDIT_MODEL,
        "prompt": prompt + REFINE_PROMPT_SUFFIX,
        "image": "data:" + mime + ";base64," + base64.b64encode(source_image).decode(),
        "image_size": "1024x1024",
    }
    headers = {
        "Authorization": f"Bearer {config.EDIT_API_KEY}",
        "Content-Type": "application/json",
    }

    last_error: ModelError | None = None
    for attempt in range(2):
        try:
            with httpx.Client(timeout=config.EDIT_TIMEOUT_SECONDS, trust_env=False) as client:
                resp = client.post(url, json=payload, headers=headers)
            if resp.status_code in (401, 403):
                raise ModelError("MODEL_AUTH_FAILED", "精修模型认证失败，请检查 API Key")
            if resp.status_code == 429:
                raise ModelError("MODEL_RATE_LIMITED", "精修模型限流，请稍后重试")
            if resp.status_code >= 500:
                last_error = ModelError("MODEL_UPSTREAM_ERROR", "精修服务暂时不可用")
                continue
            if resp.status_code != 200:
                raise ModelError("MODEL_BAD_REQUEST", "精修请求参数有误")
            return _extract_image_bytes(resp.json())
        except ModelError:
            raise
        except httpx.TimeoutException:
            last_error = ModelError("MODEL_TIMEOUT", "精修超时，可重试")
        except httpx.HTTPError:
            last_error = ModelError("MODEL_NETWORK_ERROR", "连接精修服务失败")
        except (KeyError, ValueError, TypeError):
            last_error = ModelError("MODEL_BAD_RESPONSE", "精修返回内容无法解析")

    raise last_error or ModelError("MODEL_UNKNOWN_ERROR", "精修失败，请稍后重试")


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
