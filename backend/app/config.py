"""配置读取。

约定：
- 所有配置来自环境变量或 backend/.env；.env 已在 .gitignore 中。
- 不在导入时创建目录（线上只读文件系统会失败），目录创建放在 ensure_dirs() 里，
  由应用启动时调用。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _int_yuan_to_fen(name: str, default_yuan: str) -> int:
    """金额统一用「分」的整数，避免浮点误差。"""
    raw = os.getenv(name, default_yuan)
    try:
        return int(round(float(raw) * 100))
    except ValueError:
        return int(round(float(default_yuan) * 100))


DATA_DIR = Path(os.getenv("DATA_DIR") or (BACKEND_DIR / "data")).resolve()
ASSETS_DIR = DATA_DIR / "assets"
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{DATA_DIR / 'app.db'}"

# ── 文生图 ──
T2I_BASE_URL = os.getenv("MODEL_T2I_BASE_URL", "https://api.siliconflow.cn/v1").rstrip("/")
T2I_API_KEY = os.getenv("MODEL_T2I_API_KEY", "").strip()
T2I_MODEL = os.getenv("MODEL_T2I_NAME", "Tongyi-MAI/Z-Image-Turbo").strip()
T2I_UNIT_PRICE_FEN = _int_yuan_to_fen("MODEL_T2I_UNIT_PRICE", "0.03")
T2I_TIMEOUT_SECONDS = int(os.getenv("MODEL_T2I_TIMEOUT", "60"))

# ── LLM（可选，本阶段未启用）──
LLM_BASE_URL = (os.getenv("MODEL_LLM_BASE_URL", "").strip() or T2I_BASE_URL).rstrip("/")
LLM_API_KEY = (os.getenv("MODEL_LLM_API_KEY", "").strip() or T2I_API_KEY)
LLM_MODEL = os.getenv("MODEL_LLM_NAME", "deepseek-ai/DeepSeek-V4-Flash").strip()
LLM_UNIT_PRICE_FEN = _int_yuan_to_fen("MODEL_LLM_UNIT_PRICE", "0.02")
LLM_TIMEOUT_SECONDS = int(os.getenv("MODEL_LLM_TIMEOUT", "120"))

# ── 预算守卫 ──
TASK_BUDGET_FEN = _int_yuan_to_fen("TASK_BUDGET_CNY", "5.00")

# ── 精修（2-3，图生图）──
EDIT_BASE_URL = os.getenv("MODEL_EDIT_BASE_URL", T2I_BASE_URL).rstrip("/")
EDIT_API_KEY = (os.getenv("MODEL_EDIT_API_KEY", "").strip() or T2I_API_KEY)
EDIT_MODEL = os.getenv("MODEL_EDIT_NAME", "Qwen/Qwen-Image-Edit-2509").strip()
EDIT_UNIT_PRICE_FEN = _int_yuan_to_fen("MODEL_EDIT_UNIT_PRICE", "0.30")
EDIT_TIMEOUT_SECONDS = int(os.getenv("MODEL_EDIT_TIMEOUT", "180"))

# ── 质检（2-3，VLM）──
VLM_BASE_URL = os.getenv("MODEL_VLM_BASE_URL", T2I_BASE_URL).rstrip("/")
VLM_API_KEY = (os.getenv("MODEL_VLM_API_KEY", "").strip() or T2I_API_KEY)
VLM_MODEL = os.getenv("MODEL_VLM_NAME", "Qwen/Qwen3-VL-8B-Instruct").strip()
VLM_UNIT_PRICE_FEN = _int_yuan_to_fen("MODEL_VLM_UNIT_PRICE", "0.003")
VLM_TIMEOUT_SECONDS = int(os.getenv("MODEL_VLM_TIMEOUT", "60"))

DELTA_E_THRESHOLD = float(os.getenv("DELTA_E_THRESHOLD", "3.0"))
BATCH_REFINE_LIMIT = int(os.getenv("BATCH_REFINE_LIMIT", "20"))
BATCH_REFINE_BUDGET_FEN = _int_yuan_to_fen("BATCH_REFINE_BUDGET_CNY", "5.00")

# ── 短剧（2-4）──
DRAMA_MAX_SHOTS = int(os.getenv("DRAMA_MAX_SHOTS", "40"))
COMPOSE_FPS = int(os.getenv("COMPOSE_FPS", "25"))
COMPOSE_MAX_SECONDS = int(os.getenv("COMPOSE_MAX_SECONDS", "180"))

# ── 批量（2-2）──
BATCH_CONCURRENCY = int(os.getenv("BATCH_CONCURRENCY", "3"))
BATCH_BUDGET_FEN = _int_yuan_to_fen("BATCH_BUDGET_CNY", "10.00")
BATCH_MAX_ROWS = int(os.getenv("BATCH_MAX_ROWS", "200"))

# ── 上传限制 ──
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
MAX_IMAGE_SIDE = int(os.getenv("MAX_IMAGE_SIDE", "8000"))
ALLOWED_MIME = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}

APP_VERSION = "2.1.0"


def ensure_dirs() -> None:
    """应用启动时调用；测试里也用它来准备临时目录。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def t2i_configured() -> bool:
    return bool(T2I_API_KEY)


def edit_configured() -> bool:
    return bool(EDIT_API_KEY)


def vlm_configured() -> bool:
    return bool(VLM_API_KEY)


def llm_configured() -> bool:
    return bool(LLM_API_KEY)
