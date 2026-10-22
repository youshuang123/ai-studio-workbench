export type JobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "over_budget"
  | "cancelled"
  | "unknown";

export type JobState =
  | "waiting"
  | "generating"
  | "success"
  | "error"
  | "blocked"
  | "cancelled"
  | "stale";

const MAP: Record<string, JobState> = {
  queued: "waiting",
  running: "generating",
  succeeded: "success",
  failed: "error",
  over_budget: "blocked",
  cancelled: "cancelled",
};

/** 未知状态一律走 stale：不当成成功，也不当成失败。 */
export function mapJobStatus(status: string | null | undefined): JobState {
  if (!status) return "stale";
  return MAP[status] ?? "stale";
}

export function jobStateLabel(state: JobState): string {
  switch (state) {
    case "waiting":
      return "排队中";
    case "generating":
      return "生成中";
    case "success":
      return "已完成";
    case "error":
      return "失败";
    case "blocked":
      return "超预算";
    case "cancelled":
      return "已取消";
    default:
      return "状态未知";
  }
}

export function isTerminal(status: string | null | undefined): boolean {
  return ["succeeded", "failed", "over_budget", "cancelled"].includes(status ?? "");
}
