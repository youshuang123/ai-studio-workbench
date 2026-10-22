import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  ResultPanel,
  type FallbackResult,
} from "@/features/generation/components/ResultPanel";
import type { JobPhase } from "@/features/jobs/useJobEvents";

const noop = vi.fn();

function renderPanel(
  phase: JobPhase,
  isWorking = false,
  fallback: FallbackResult | null = null,
) {
  return render(
    <ResultPanel
      phase={phase}
      isWorking={isWorking}
      onRetry={noop}
      retrying={false}
      onRefresh={noop}
      fallback={fallback}
    />,
  );
}

describe("ResultPanel 状态覆盖", () => {
  it("idle：显示空结果说明，不是错误态", () => {
    renderPanel({ kind: "idle" });
    expect(screen.getByText("还没有生成结果")).toBeInTheDocument();
  });

  it("status + isWorking：显示阶段文案", () => {
    renderPanel({ kind: "status", stage: "calling" }, true);
    expect(screen.getByText("正在调用模型…")).toBeInTheDocument();
  });

  it("done：显示成本、耗时、下载", () => {
    renderPanel(
      {
        kind: "done",
        data: {
          job_id: "j1",
          asset_id: "a1",
          cost_fen: 3,
          elapsed_ms: 9600,
        },
      },
      false,
    );
    expect(screen.getByText("¥0.03")).toBeInTheDocument();
    expect(screen.getByText("9.6 秒")).toBeInTheDocument();
    expect(screen.getByText("下载原图")).toBeInTheDocument();
    expect(screen.getByAltText("生成的主图")).toBeInTheDocument();
  });

  it("fallback：刷新后仍显示最近一次结果", () => {
    renderPanel({ kind: "idle" }, false, {
      assetId: "a9",
      costFen: 3,
      elapsedMs: 9000,
    });
    expect(screen.getByAltText("生成的主图")).toBeInTheDocument();
    expect(screen.getByText(/最近一次生成的结果/)).toBeInTheDocument();
  });

  it("failed：可重试的错误显示重试按钮", () => {
    renderPanel({
      kind: "error",
      error: { code: "MODEL_TIMEOUT", message: "模型响应超时" },
    });
    expect(screen.getByText("模型响应超时")).toBeInTheDocument();
    expect(screen.getByText(/MODEL_TIMEOUT/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试一次" })).toBeInTheDocument();
  });

  it("failed：不可重试的错误不显示重试按钮", () => {
    renderPanel({
      kind: "error",
      error: { code: "BUDGET_EXCEEDED", message: "预算不足" },
    });
    expect(screen.queryByRole("button", { name: "重试一次" })).toBeNull();
    expect(screen.getByText(/重试也不会通过/)).toBeInTheDocument();
  });

  it("cancelled：显示已停止并能刷新", () => {
    renderPanel({ kind: "cancelled", message: "已取消，未产生费用" });
    expect(screen.getByText("已停止")).toBeInTheDocument();
    expect(screen.getByText("已取消，未产生费用")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "刷新看看" })).toBeInTheDocument();
  });

  it("cancelled 有兜底结果时，仍然显示「已停止」而不是旧图", () => {
    renderPanel({ kind: "cancelled", message: "已取消" }, false, {
      assetId: "a0",
      costFen: 3,
      elapsedMs: 9000,
    });
    expect(screen.getByText("已停止")).toBeInTheDocument();
    expect(screen.queryByAltText("生成的主图")).toBeNull();
  });

  it("disconnected：不冒充失败也不冒充成功", () => {
    renderPanel({ kind: "disconnected", message: "连接中断，任务可能仍在后台生成" });
    expect(screen.getByText("连接中断")).toBeInTheDocument();
    expect(screen.getByText(/中断不等于失败/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "刷新状态" })).toBeInTheDocument();
    expect(screen.queryByText("生成失败")).toBeNull();
  });
});
