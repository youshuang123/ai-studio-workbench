"use client";

import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import type { JobDoneEvent, JobErrorEvent, JobStage } from "@/features/jobs/useJobEvents";
import { formatDuration, formatFen } from "@/lib/utils/format";

const STAGE_TEXT: Record<string, string> = {
  preparing: "正在准备…",
  calling: "正在调用模型…",
};

export function ResultPanel({
  stage,
  done,
  error,
  isWorking,
  onRetry,
  retrying,
}: {
  stage: JobStage;
  done: JobDoneEvent | null;
  error: JobErrorEvent | null;
  isWorking: boolean;
  onRetry: () => void;
  retrying: boolean;
}) {
  if (done) {
    return (
      <div className="flex flex-col gap-4">
        <div className="overflow-hidden rounded-xl border border-line bg-surface">
          <img
            src={`/api/assets/${done.asset_id}/file`}
            alt="生成的主图"
            className="mx-auto block max-h-[520px] w-full object-contain"
          />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-smoke">
            <div className="flex gap-1">
              <dt>成本</dt>
              <dd className="font-medium text-ink">{formatFen(done.cost_fen)}</dd>
            </div>
            <div className="flex gap-1">
              <dt>耗时</dt>
              <dd className="font-medium text-ink">{formatDuration(done.elapsed_ms)}</dd>
            </div>
          </dl>
          <a
            href={`/api/assets/${done.asset_id}/download`}
            className="inline-flex items-center justify-center rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            下载原图
          </a>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col gap-4">
        <div className="rounded-xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger">
          <p className="font-medium">生成失败</p>
          <p className="mt-1">{error.message}</p>
          <p className="mt-1 text-xs opacity-70">错误码：{error.code}</p>
        </div>
        <Button onClick={onRetry} loading={retrying}>
          重试
        </Button>
      </div>
    );
  }

  if (isWorking) {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2 text-sm text-smoke">
          <span
            aria-hidden="true"
            className="size-3.5 animate-spin rounded-full border-2 border-accent border-t-transparent"
          />
          {STAGE_TEXT[stage] ?? "正在生成…"}
        </div>
        <Skeleton className="aspect-square w-full max-w-[520px]" />
      </div>
    );
  }

  return (
    <div className="flex min-h-[320px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-line bg-surface px-6 py-12 text-center">
      <p className="text-sm font-medium text-ink">还没有生成结果</p>
      <p className="text-xs text-smoke">
        上传商品图、填写信息后点「生成主图」，结果会显示在这里。
      </p>
    </div>
  );
}
