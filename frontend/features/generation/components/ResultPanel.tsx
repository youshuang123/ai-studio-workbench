"use client";

import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import type {
  JobDoneEvent,
  JobErrorEvent,
  JobPhase,
  JobStage,
} from "@/features/jobs/useJobEvents";
import { formatDuration, formatFen } from "@/lib/utils/format";

const STAGE_TEXT: Record<string, string> = {
  preparing: "正在准备…",
  calling: "正在调用模型…",
};

/** 不可重试的错误码（重试也过不去，给了按钮只会浪费钱和时间） */
const NO_RETRY_CODES = new Set([
  "BUDGET_EXCEEDED",
  "MODEL_NOT_CONFIGURED",
  "INVALID_SOURCE_ASSET",
  "VALIDATION_ERROR",
]);

export type FallbackResult = {
  assetId: string;
  costFen: number;
  elapsedMs: number | null;
};

export function ResultPanel({
  phase,
  isWorking,
  onRetry,
  retrying,
  onRefresh,
  fallback = null,
}: {
  phase: JobPhase;
  isWorking: boolean;
  onRetry: () => void;
  retrying: boolean;
  onRefresh: () => void;
  fallback?: FallbackResult | null;
}) {
  // ── 成功：本次结果优先；没有本次结果时，用后端最近一次成功结果兜底（刷新后不丢） ──
  //    注意：cancelled / error 时不显示兜底图，否则会把"刚取消了"错当成"已成功"
  const fallbackAllowed =
    phase.kind === "idle" || phase.kind === "status" || phase.kind === "disconnected";

  const shown =
    phase.kind === "done"
      ? {
          assetId: phase.data.asset_id,
          costFen: phase.data.cost_fen,
          elapsedMs: phase.data.elapsed_ms,
          isLatest: true,
        }
      : fallbackAllowed && fallback
        ? {
            assetId: fallback.assetId,
            costFen: fallback.costFen,
            elapsedMs: fallback.elapsedMs,
            isLatest: false,
          }
        : null;

  const showWorking = isWorking && phase.kind !== "done";

  if (phase.kind === "done" || (!isWorking && shown)) {
    return (
      <div className="flex flex-col gap-4">
        <div className="overflow-hidden rounded-[24px] border border-hairline bg-canvas p-2">
          <img
            src={`/api/assets/${shown!.assetId}/file`}
            alt="生成的主图"
            className="mx-auto block max-h-[560px] w-full rounded-[16px] object-contain"
          />
        </div>

        {!shown!.isLatest && (
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
              <dd className="text-[15px] font-medium text-ink">
                {formatFen(shown!.costFen)}
              </dd>
            </div>
            <div className="flex items-baseline gap-2">
              <dt className="text-[10px] font-semibold uppercase tracking-[0.14em] text-helper">
                耗时
              </dt>
              <dd className="text-[15px] font-medium text-ink">
                {formatDuration(shown!.elapsedMs)}
              </dd>
            </div>
          </dl>
          <a
            href={`/api/assets/${shown!.assetId}/download`}
            className="inline-flex items-center justify-center rounded-[28px] border border-ink px-5 py-2.5 text-[14px] font-medium text-ink transition-colors hover:bg-ink hover:text-canvas"
          >
            下载原图
          </a>
        </div>
      </div>
    );
  }

  // ── 已取消 ──
  if (phase.kind === "cancelled") {
    return (
      <div className="flex flex-col gap-4">
        <div className="rounded-[20px] bg-hairline px-5 py-4">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-quiet">
            已停止
          </p>
          <p className="mt-1.5 text-[15px] text-body">{phase.message}</p>
          <p className="mt-1 text-[12px] text-helper">
            已经生成成功的图不会被删除。
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button onClick={onRefresh}>刷新看看</Button>
        </div>
      </div>
    );
  }

  // ── 失败 ──
  if (phase.kind === "error") {
    const err: JobErrorEvent = phase.error;
    const canRetry = !NO_RETRY_CODES.has(err.code);
    return (
      <div className="flex flex-col gap-4" role="alert">
        <div className="rounded-[20px] bg-blush px-5 py-4">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8c2b25]">
            生成失败
          </p>
          <p className="mt-1.5 text-[15px] text-[#6f221d]">{err.message}</p>
          <p className="mt-1 text-[12px] text-[#8c2b25]/70">错误码：{err.code}</p>
        </div>
        <div className="flex flex-wrap gap-3">
          {canRetry ? (
            <Button onClick={onRetry} loading={retrying}>
              重试一次
            </Button>
          ) : (
            <p className="text-[13px] text-helper">
              这个问题重试也不会通过，先按上面的提示处理。
            </p>
          )}
        </div>
      </div>
    );
  }

  // ── 连接中断 ──
  if (phase.kind === "disconnected") {
    return (
      <div className="flex flex-col gap-4" role="status">
        <div className="rounded-[20px] bg-peach px-5 py-4">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8a4b12]">
            连接中断
          </p>
          <p className="mt-1.5 text-[15px] text-[#6b3a0e]">{phase.message}</p>
          <p className="mt-1 text-[12px] text-[#8a4b12]/80">
            中断不等于失败——任务可能已经完成，刷新是最快的确认方式。
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button onClick={onRefresh}>刷新状态</Button>
        </div>
      </div>
    );
  }

  // ── 生成中 ──
  if (showWorking) {
    const stage = phase.kind === "status" ? (phase.stage as JobStage) : "";
    return (
      <div className="flex flex-col gap-3" role="status" aria-live="polite">
        <div className="flex items-center gap-2.5 text-[14px] text-helper">
          <span
            aria-hidden="true"
            className="size-3.5 animate-spin rounded-full border-2 border-ink border-t-transparent"
          />
          {STAGE_TEXT[stage] ?? "正在生成…"}
        </div>
        <Skeleton className="aspect-square w-full max-w-[520px]" />
        <p className="text-[12px] text-fog">
          通常 6-12 秒。关掉页面也不影响后台生成，回来刷新即可。
        </p>
      </div>
    );
  }

  // ── 空闲 ──
  return (
    <div className="flex min-h-[340px] flex-col items-center justify-center gap-2 rounded-[20px] border border-dashed border-divider bg-sky/30 px-6 py-12 text-center">
      <p className="text-[15px] font-medium text-ink">还没有生成结果</p>
      <p className="max-w-[36ch] text-[13px] leading-relaxed text-helper">
        上传商品图、填好信息，点「生成主图」。第一张图大约 10 秒。
      </p>
    </div>
  );
}
