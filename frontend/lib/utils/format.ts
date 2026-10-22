/** 金额：后端一律用「分」的整数传来，这里只负责显示。 */
export function formatFen(fen: number | null | undefined): string {
  const value = typeof fen === "number" && Number.isFinite(fen) ? fen : 0;
  return `¥${(value / 100).toFixed(2)}`;
}

export function formatBytes(bytes: number | null | undefined): string {
  const value = typeof bytes === "number" && bytes > 0 ? bytes : 0;
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(0)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

export function formatDuration(ms: number | null | undefined): string {
  if (typeof ms !== "number" || ms <= 0) return "—";
  if (ms < 1000) return `${ms} 毫秒`;
  return `${(ms / 1000).toFixed(1)} 秒`;
}

/** 后端返回的是 UTC ISO 字符串；统一显示成本地时间。 */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const raw = /[zZ]|[+-]\d{2}:\d{2}$/.test(iso) ? iso : `${iso}Z`;
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return "—";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}
