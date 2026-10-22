import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch, errorMessage } from "@/lib/api/client";

function mockFetch(impl: () => Promise<Response>) {
  vi.stubGlobal("fetch", vi.fn(impl));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiFetch", () => {
  it("成功时返回解析后的 JSON", async () => {
    mockFetch(async () => new Response(JSON.stringify({ ok: 1 }), { status: 200 }));
    await expect(apiFetch<{ ok: number }>("/api/x")).resolves.toEqual({ ok: 1 });
  });

  it("把后端错误结构归一化成 ApiError", async () => {
    mockFetch(
      async () =>
        new Response(
          JSON.stringify({ error: { code: "BUDGET_EXCEEDED", message: "预算不足" } }),
          { status: 402 },
        ),
    );
    await expect(apiFetch("/api/x")).rejects.toMatchObject({
      code: "BUDGET_EXCEEDED",
      userMessage: "预算不足",
      retryable: false,
    });
  });

  it("响应不是 JSON 时用默认文案，不暴露原始内容", async () => {
    mockFetch(async () => new Response("<html>boom</html>", { status: 500 }));
    await expect(apiFetch("/api/x")).rejects.toMatchObject({
      code: "INTERNAL_ERROR",
      retryable: true,
    });
  });

  it("网络失败归一化成 NETWORK_ERROR", async () => {
    mockFetch(async () => {
      throw new TypeError("failed to fetch");
    });
    await expect(apiFetch("/api/x")).rejects.toMatchObject({
      code: "NETWORK_ERROR",
      userMessage: "连不上服务，请确认后端已启动",
    });
  });

  it("204 返回 undefined", async () => {
    mockFetch(async () => new Response(null, { status: 204 }));
    await expect(apiFetch("/api/x")).resolves.toBeUndefined();
  });
});

describe("ApiError", () => {
  it("5xx 默认可重试，模型未配置不可重试", () => {
    expect(new ApiError("INTERNAL_ERROR", "x", 500).retryable).toBe(true);
    expect(new ApiError("MODEL_NOT_CONFIGURED", "x", 503).retryable).toBe(false);
    expect(new ApiError("VALIDATION_ERROR", "x", 400).retryable).toBe(false);
  });
});

describe("errorMessage", () => {
  it("优先返回用户可读文案", () => {
    expect(errorMessage(new ApiError("NOT_FOUND", "项目不存在", 404))).toBe("项目不存在");
    expect(errorMessage(new Error("boom"))).toBe("boom");
    expect(errorMessage("??")).toBe("出现了未知问题，请重试");
  });
});
