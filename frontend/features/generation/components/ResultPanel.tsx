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
    ? {
        assetId: done.asset_id,
        costFen: done.cost_fen,
        elapsedMs: done.elapsed_ms,
        isLatest: true,
      }
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
        {/* 相纸卡：图在纸里，24px 圆角 + 1px 发丝边 */}
        <div className="overflow-hidden rounded-[24px] border border-hairline bg-canvas p-2">
          <img
            src={`/api/assets/${shown.assetId}/file`}
            alt="生成的主图"
            className="mx-auto block max-h-[560px] w-full rounded-[16px] object-contain"
          />
        </div>

        {!shown.isLatest && (
          <p className="text-[12px] text-helper">
            这是最近一次生成的结果，刷新页面后仍会显示。
          </p>
        )}

        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-hairline pt-4">
          <dl className="flex flex-wrap gap-x-8 gap-y-1">
            <div className="flex items-baseline gap-2">
              <dt className="text-[10px] font-semibold uppercase tracking-[0.14em] text-helper">
                成本
              </dt>
              <dd className="text-[15px] font-medium text-ink">{formatFen(shown.costFen)}</dd>
            </div>
            <div className="flex items-baseline gap-2">
              <dt className="text-[10px] font-semibold uppercase tracking-[0.14em] text-helper">
                耗时
              </dt>
              <dd className="text-[15px] font-medium text-ink">
                {formatDuration(shown.elapsedMs)}
              </dd>
            </div>
          </dl>
          <a
            href={`/api/assets/${shown.assetId}/download`}
            className="inline-flex items-center justify-center rounded-[28px] border border-ink px-5 py-2.5 text-[14px] font-medium text-ink transition-colors hover:bg-ink hover:text-canvas"
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
        <div className="rounded-[20px] bg-blush px-5 py-4">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8c2b25]">
            生成失败
          </p>
          <p className="mt-1.5 text-[15px] text-[#6f221d]">{error.message}</p>
          <p className="mt-1 text-[12px] text-[#8c2b25]/70">错误码：{error.code}</p>
        </div>
        <div>
          <Button onClick={onRetry} loading={retrying}>
            重试一次
          </Button>
        </div>
      </div>
    );
  }

  if (isWorking) {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2.5 text-[14px] text-helper">
          <span
            aria-hidden="true"
            className="size-3.5 animate-spin rounded-full border-2 border-ink border-t-transparent"
          />
          {STAGE_TEXT[stage] ?? "正在生成…"}
        </div>
        <Skeleton className="aspect-square w-full max-w-[520px]" />
        <p className="text-[12px] text-fog">通常 6-12 秒。关掉页面也不影响后台生成，回来刷新即可。</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-[340px] flex-col items-center justify-center gap-2 rounded-[20px] border border-dashed border-divider bg-sky/30 px-6 py-12 text-center">
      <p className="text-[15px] font-medium text-ink">还没有生成结果</p>
      <p className="max-w-[36ch] text-[13px] leading-relaxed text-helper">
        上传商品图、填好信息，点「生成主图」。第一张图大约 10 秒。
      </p>
    </div>
  );
}
