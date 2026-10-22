export type ApiErrorCode =
  | "NETWORK_ERROR"
  | "VALIDATION_ERROR"
  | "NOT_FOUND"
  | "BUDGET_EXCEEDED"
  | "MODEL_NOT_CONFIGURED"
  | "STATE_CONFLICT"
  | "INVALID_FILE"
  | "FILE_TOO_LARGE"
  | "INTERNAL_ERROR"
  | string;

export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number;
  readonly userMessage: string;
  readonly retryable: boolean;

  constructor(code: ApiErrorCode, userMessage: string, status: number) {
    super(userMessage);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.userMessage = userMessage;
    this.retryable = isRetryable(code, status);
  }
}

const RETRYABLE_CODES = new Set([
  "NETWORK_ERROR",
  "INTERNAL_ERROR",
  "MODEL_TIMEOUT",
  "MODEL_UPSTREAM_ERROR",
  "MODEL_RATE_LIMITED",
  "MODEL_NETWORK_ERROR",
]);

function isRetryable(code: ApiErrorCode, status: number): boolean {
  if (RETRYABLE_CODES.has(code)) return true;
  if (code === "MODEL_NOT_CONFIGURED") return false;
  return status >= 500;
}

type ErrorBody = { error?: { code?: string; message?: string } };

async function toApiError(resp: Response): Promise<ApiError> {
  let code = "INTERNAL_ERROR";
  // 后端进程没起来时，Next 的同源代理会返回 500 + 非 JSON，这里给可操作的文案，
  // 而不是笼统的「内部错误」。
  let message =
    resp.status >= 500
      ? "服务暂时不可用，请确认后端已启动，再点重试"
      : "请求没成功，请稍后重试";
  try {
    const body = (await resp.json()) as ErrorBody;
    if (body?.error?.code) code = body.error.code;
    if (body?.error?.message) message = body.error.message;
  } catch {
    // 响应不是 JSON，保留默认文案，不暴露原始内容
  }
  return new ApiError(code, message, resp.status);
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(path, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" }),
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    });
  } catch {
    throw new ApiError("NETWORK_ERROR", "连不上服务，请确认后端已启动", 0);
  }

  if (!resp.ok) {
    throw await toApiError(resp);
  }
  if (resp.status === 204) {
    return undefined as T;
  }
  return (await resp.json()) as T;
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.userMessage;
  if (err instanceof Error) return err.message;
  return "出现了未知问题，请重试";
}
