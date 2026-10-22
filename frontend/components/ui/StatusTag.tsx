import { jobStateLabel, mapJobStatus } from "@/features/jobs/status";

const STYLES: Record<string, string> = {
  waiting: "bg-canvas text-smoke border-line",
  generating: "bg-accent-soft text-accent border-accent/30",
  success: "bg-success-soft text-success border-success/30",
  error: "bg-danger-soft text-danger border-danger/30",
  blocked: "bg-warn-soft text-warn border-warn/30",
  cancelled: "bg-canvas text-smoke border-line",
  stale: "bg-canvas text-smoke border-line",
};

export function StatusTag({ status }: { status: string | null | undefined }) {
  const state = mapJobStatus(status);
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs ${STYLES[state]}`}
    >
      {jobStateLabel(state)}
    </span>
  );
}
