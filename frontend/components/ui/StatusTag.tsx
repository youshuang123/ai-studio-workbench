import { jobStateLabel, mapJobStatus } from "@/features/jobs/status";

/**
 * 状态胶囊：pastel 底 + 深色文字 + 大写小字（DESIGN.md Eyebrow Label Pill）
 * 失败/超预算从彩虹谱里取一色做 12% 调浅，不新增色相。
 */
const STYLES: Record<string, string> = {
  waiting: "bg-hairline text-helper",
  generating: "bg-sky text-teal",
  success: "bg-mint text-ink",
  error: "bg-blush text-[#8c2b25]",
  blocked: "bg-peach text-[#8a4b12]",
  cancelled: "bg-hairline text-helper",
  stale: "bg-hairline text-quiet",
};

export function StatusTag({ status }: { status: string | null | undefined }) {
  const state = mapJobStatus(status);
  return <span className={`chip ${STYLES[state]}`}>{jobStateLabel(state)}</span>;
}
