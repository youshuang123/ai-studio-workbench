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
T2I_MODEL = os.getenv("MODEL_T2I_NAME", "black-forest-labs/FLUX.1-schnell").strip()
T2I_UNIT_PRICE_FEN = _int_yuan_to_fen("MODEL_T2I_UNIT_PRICE", "0.03")
T2I_TIMEOUT_SECONDS = int(os.getenv("MODEL_T2I_TIMEOUT", "60"))

# ── LLM（可选，本阶段未启用）──
LLM_BASE_URL = os.getenv("MODEL_LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
LLM_API_KEY = os.getenv("MODEL_LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("MODEL_LLM_NAME", "deepseek-chat").strip()

# ── 预算守卫 ──
TASK_BUDGET_FEN = _int_yuan_to_fen("TASK_BUDGET_CNY", "5.00")

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
