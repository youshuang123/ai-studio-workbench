"""统一错误结构：{"error": {"code": "...", "message": "..."}}。

规则（AGENTS.md 底线 3）：错误不泄露堆栈；SSE 必须以 done 或 error 收尾。
"""


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def not_found(message: str = "资源不存在") -> AppError:
    return AppError(404, "NOT_FOUND", message)


def bad_request(message: str, code: str = "VALIDATION_ERROR") -> AppError:
    return AppError(400, code, message)


def conflict(message: str, code: str = "STATE_CONFLICT") -> AppError:
    return AppError(409, code, message)


def budget_exceeded(message: str) -> AppError:
    return AppError(402, "BUDGET_EXCEEDED", message)
