from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import config
from .db import init_db
from .errors import AppError
from .routers import assets, generations, projects
from .services import runner


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    interrupted = runner.mark_interrupted_jobs()
    if interrupted:
        # 只打数量，不打任务内容
        print(f"[startup] 已把 {interrupted} 个中断任务标记为可重试")
    yield


app = FastAPI(title="AI Studio 云端视觉创作工作台", version=config.APP_VERSION, lifespan=lifespan)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exc_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exc_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": "请求参数校验失败"}},
    )


@app.exception_handler(Exception)
async def unhandled_exc_handler(request: Request, exc: Exception):
    # 不泄露堆栈（AGENTS.md 底线 3）
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "服务出现内部错误，请稍后重试"}},
    )


app.include_router(projects.router)
app.include_router(assets.router)
app.include_router(generations.router)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": config.APP_VERSION,
        "t2i_configured": config.t2i_configured(),
        "t2i_model": config.T2I_MODEL,
        "unit_price_fen": config.T2I_UNIT_PRICE_FEN,
        "task_budget_fen": config.TASK_BUDGET_FEN,
    }
