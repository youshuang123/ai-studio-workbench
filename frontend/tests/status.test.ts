import { describe, expect, it } from "vitest";

import { isTerminal, jobStateLabel, mapJobStatus } from "@/features/jobs/status";

describe("mapJobStatus", () => {
  it("后端状态映射到界面状态", () => {
    expect(mapJobStatus("queued")).toBe("waiting");
    expect(mapJobStatus("running")).toBe("generating");
    expect(mapJobStatus("succeeded")).toBe("success");
    expect(mapJobStatus("failed")).toBe("error");
    expect(mapJobStatus("over_budget")).toBe("blocked");
    expect(mapJobStatus("cancelled")).toBe("cancelled");
    expect(mapJobStatus("disconnected")).toBe("disconnected");
  });

  it("未知状态走 stale，不当成成功也不当成失败", () => {
    expect(mapJobStatus("something_new")).toBe("stale");
    expect(mapJobStatus(null)).toBe("stale");
    expect(mapJobStatus(undefined)).toBe("stale");
  });
});

describe("jobStateLabel", () => {
  it("每个状态都有中文文案", () => {
    expect(jobStateLabel("waiting")).toBe("排队中");
    expect(jobStateLabel("generating")).toBe("生成中");
    expect(jobStateLabel("success")).toBe("已完成");
    expect(jobStateLabel("error")).toBe("失败");
    expect(jobStateLabel("blocked")).toBe("超预算");
    expect(jobStateLabel("cancelled")).toBe("已停止");
    expect(jobStateLabel("disconnected")).toBe("连接中断");
    expect(jobStateLabel("stale")).toBe("状态未知");
  });
});

describe("isTerminal", () => {
  it("终态判定", () => {
    expect(isTerminal("succeeded")).toBe(true);
    expect(isTerminal("failed")).toBe(true);
    expect(isTerminal("over_budget")).toBe(true);
    expect(isTerminal("running")).toBe(false);
    expect(isTerminal(null)).toBe(false);
  });
});
