"use client";

import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import type { JobDoneEvent, JobErrorEvent, JobStage } from "@/features/jobs/useJobEvents";
import { formatDuration, formatFen } from "@/lib/utils/format";

const STAGE_TEXT: Record<string, string> = {
  preparing: "正在准备…",
  calling: "正在调用模型…",
};

export type FallbackResult = {
  assetId: string;
  costFen: number;
  elapsedMs: number | null;
};

export function ResultPanel({
  stage,
  done,
  error,
  isWorking,
  onRetry,
  retrying,
  fallback = null,
}: {
  stage: JobStage;
  done: JobDoneEvent | null;
  error: JobErrorEvent | null;
  isWorking: boolean;
  onRetry: () => void;
  retrying: boolean;
  fallback?: FallbackResult | null;
}) {
  // 刷新后 done 会丢；用后端最近一次成功任务兜底，避免"刚生成的图刷新就没了"
  const shown = done
    ? { assetId: done.asset_id, costFen: done.cost_fen, elapsedMs: done.elapsed_ms, isLatest: true }
    : fallback
      ? {
          assetId: fallback.assetId,
          costFen: fallback.costFen,
          elapsedMs: fallback.elapsedMs,
          isLatest: false,
        }
      : null;

  if (shown) {
    return (
      <div className="flex flex-col gap-4">
        <div className="overflow-hidden rounded-xl border border-line bg-surface">
          <img
            src={`/api/assets/${shown.assetId}/file`}
            alt="生成的主图"
            className="mx-auto block max-h-[520px] w-full object-contain"
          />
        </div>
        {!shown.isLatest && (
          <p className="text-xs text-smoke">下面是最近一次生成的结果（刷新页面后仍会显示）</p>
        )}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-smoke">
            <div className="flex gap-1">
              <dt>成本</dt>
              <dd className="font-medium text-ink">{formatFen(shown.costFen)}</dd>
            </div>
            <div className="flex gap-1">
              <dt>耗时</dt>
              <dd className="font-medium text-ink">{formatDuration(shown.elapsedMs)}</dd>
            </div>
          </dl>
          <a
            href={`/api/assets/${shown.assetId}/download`}
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
