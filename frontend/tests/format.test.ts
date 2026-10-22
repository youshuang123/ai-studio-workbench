import { describe, expect, it } from "vitest";

import { formatBytes, formatDuration, formatFen, formatTime } from "@/lib/utils/format";

describe("formatFen", () => {
  it("把分格式化成元，保留两位", () => {
    expect(formatFen(3)).toBe("¥0.03");
    expect(formatFen(150)).toBe("¥1.50");
    expect(formatFen(0)).toBe("¥0.00");
  });

  it("空值与异常值不显示 NaN", () => {
    expect(formatFen(null)).toBe("¥0.00");
    expect(formatFen(undefined)).toBe("¥0.00");
  });
});

describe("formatBytes", () => {
  it("按量级切换单位", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.0 MB");
  });
});

describe("formatDuration", () => {
  it("秒级与毫秒级", () => {
    expect(formatDuration(820)).toBe("820 毫秒");
    expect(formatDuration(8200)).toBe("8.2 秒");
    expect(formatDuration(null)).toBe("—");
  });
});

describe("formatTime", () => {
  it("无时区的字符串按 UTC 解析，不返回 Invalid Date", () => {
    const text = formatTime("2026-10-22T03:47:57.352345");
    expect(text).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
  });

  it("空值显示占位符", () => {
    expect(formatTime(null)).toBe("—");
    expect(formatTime("not-a-date")).toBe("—");
  });
});
