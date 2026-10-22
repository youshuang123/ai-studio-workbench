"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, Eyebrow } from "@/components/ui/Card";
import { StatusTag } from "@/components/ui/StatusTag";
import {
  cancelJob,
  createGeneration,
  fetchProject,
  fetchUsage,
  refineJob,
  retryJob,
} from "@/features/api/client";
import type { Asset, ProjectDetail, Usage } from "@/features/api/types";
import { UploadBox } from "@/features/generation/components/UploadBox";
import { ResultPanel } from "@/features/generation/components/ResultPanel";
import { useJobEvents } from "@/features/jobs/useJobEvents";
import {
  DeltaBadge,
  QaBadge,
  QaDetailList,
  parseQaDetail,
} from "@/features/qa/components";
import { errorMessage } from "@/lib/api/client";
import { formatFen, formatTime } from "@/lib/utils/format";

type Form = {
  product_name: string;
  category: string;
  selling_points: string;
  color: string;
};

const EMPTY_FORM: Form = {
  product_name: "",
  category: "",
  selling_points: "",
  color: "",
};

const inputClass =
  "rounded-[16px] border border-divider bg-canvas px-4 py-2.5 text-[14px] text-ink outline-none placeholder:text-fog focus:border-ink";

export default function ProjectPage() {
  const params = useParams<{ id: string }>();
  const projectId = Array.isArray(params?.id) ? params.id[0] : (params?.id ?? "");

  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [form, setForm] = useState<Form>(EMPTY_FORM);
  const [sourceAssetId, setSourceAssetId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [jobId, setJobId] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);

  const load = useCallback(async () => {
    if (!projectId) return;
    try {
      const [d, u] = await Promise.all([fetchProject(projectId), fetchUsage(projectId)]);
      setDetail(d);
      setUsage(u);
      setLoadError(null);
      const uploads = d.assets.filter((a) => a.kind === "upload");
      setSourceAssetId((prev) => prev ?? uploads[0]?.id ?? null);
    } catch (err) {
      setLoadError(errorMessage(err));
    }
  }, [projectId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const [cancelling, setCancelling] = useState(false);
  const [refineJobId, setRefineJobId] = useState<string | null>(null);
  const [refining, setRefining] = useState(false);
  const [refineNotice, setRefineNotice] = useState<string | null>(null);

  const { phase, isWorking, stopWaiting } = useJobEvents(jobId, load);
  const refineEvents = useJobEvents(refineJobId, load);

  const uploads = useMemo(
    () => (detail?.assets ?? []).filter((a) => a.kind === "upload"),
    [detail],
  );
  const outputs = useMemo(
    () => (detail?.assets ?? []).filter((a) => a.kind === "output"),
    [detail],
  );

  const refinedDetailRaw = useMemo(() => {
    const job = detail?.recent_jobs.find(
      (j) => j.stage === "refined" && j.status === "succeeded" && j.output_asset_id,
    );
    return (job as { qa_detail?: string } | undefined)?.qa_detail ?? "";
  }, [detail]);

  const latestRefined = useMemo(() => {
    const job = detail?.recent_jobs.find(
      (j) => j.stage === "refined" && j.status === "succeeded" && j.output_asset_id,
    );
    if (!job || !job.output_asset_id) return null;
    return {
      assetId: job.output_asset_id,
      deltaE: job.delta_e ?? null,
      qaScore: job.qa_score ?? null,
      jobId: job.id,
    };
  }, [detail]);

  const latestSuccess = useMemo(() => {
    const job = detail?.recent_jobs.find(
      (j) => j.status === "succeeded" && j.output_asset_id && (j.stage ?? "draft") !== "refined",
    );
    if (!job || !job.output_asset_id) return null;
    return {
      assetId: job.output_asset_id,
      costFen: job.cost_fen,
      elapsedMs: job.elapsed_ms ?? null,
    };
  }, [detail]);

  const currentSource: Asset | null = useMemo(
    () => uploads.find((a) => a.id === sourceAssetId) ?? uploads[0] ?? null,
    [uploads, sourceAssetId],
  );

  async function handleGenerate() {
    if (!currentSource || submitting) return;
    setFormError(null);
    if (!form.product_name.trim()) {
      setFormError("商品名称必填");
      return;
    }
    setSubmitting(true);
    setJobId(null);
    try {
      const resp = await createGeneration(projectId, {
        source_asset_id: currentSource.id,
        product_name: form.product_name.trim(),
        category: form.category.trim(),
        selling_points: form.selling_points.trim(),
        color: form.color.trim(),
      });
      setJobId(resp.job_id);
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCancel() {
    if (!jobId || cancelling) return;
    setCancelling(true);
    setFormError(null);
    try {
      await cancelJob(jobId);
      // 让 SSE 收尾；服务端会推 cancelled 事件，这里兜底刷新一次
      await load();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setCancelling(false);
    }
  }

  async function handleRefine() {
    const latest = latestSuccess;
    if (!latest || refining) return;
    // 找到对应的 job id
    const job = detail?.recent_jobs.find(
      (j) => j.status === "succeeded" && j.output_asset_id === latest.assetId,
    );
    if (!job) return;
    setRefining(true);
    setFormError(null);
    setRefineNotice(null);
    try {
      const resp = await refineJob(job.id);
      setRefineJobId(resp.job_id);
      setRefineNotice("精修中，约 27 秒。完成后会显示对比和质检分。");
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setRefining(false);
    }
  }

  async function handleRetry() {
    if (!jobId || retrying) return;
    setRetrying(true);
    try {
      const resp = await retryJob(jobId);
      setJobId(null);
      await Promise.resolve();
      setJobId(resp.job_id);
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setRetrying(false);
    }
  }

  if (loadError) {
    return (
      <div className="flex flex-col gap-4">
        <Link href="/" className="text-[14px] text-teal hover:underline">
          ← 返回项目列表
        </Link>
        <div className="rounded-[20px] bg-blush px-5 py-4 text-[14px] text-[#8c2b25]">
          {loadError}
        </div>
        <div>
          <Button variant="quiet" onClick={() => void load()}>
            重试
          </Button>
        </div>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="flex flex-col gap-4">
        <div className="h-4 w-24 animate-pulse rounded bg-hairline" />
        <div className="h-10 w-1/3 animate-pulse rounded bg-hairline" />
        <div className="grid gap-6 md:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
          <div className="h-72 animate-pulse rounded-[24px] bg-hairline" />
          <div className="h-72 animate-pulse rounded-[24px] bg-hairline" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-4">
        <Link href="/" className="w-fit text-[13px] text-teal hover:underline">
          ← 返回项目列表
        </Link>
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div className="min-w-0">
            <Eyebrow>项目</Eyebrow>
            <h1 className="display-tight mt-1.5 truncate text-[30px] text-ink md:text-[36px]">
              {detail.name}
            </h1>
            <p className="mt-2 text-[13px] text-helper">
              创建于 {formatTime(detail.created_at)} · {detail.assets.length} 个素材
            </p>
          </div>
          <div className="flex items-end gap-6">
            <Link
              href={`/projects/${projectId}/batch`}
              className="rounded-[28px] border border-ink px-4 py-2 text-[13px] font-medium text-ink transition-colors hover:bg-ink hover:text-canvas"
            >
              SKU 批量
            </Link>
            <Link
              href={`/projects/${projectId}/dramas`}
              className="rounded-[28px] border border-ink px-4 py-2 text-[13px] font-medium text-ink transition-colors hover:bg-ink hover:text-canvas"
            >
              短剧
            </Link>
            <div>
              <Eyebrow>累计成本</Eyebrow>
              <p className="mt-1 text-[22px] font-medium tracking-[-0.02em] text-ink">
                {formatFen(usage?.total_fen ?? 0)}
              </p>
            </div>
            <div>
              <Eyebrow>生成张数</Eyebrow>
              <p className="mt-1 text-[22px] font-medium tracking-[-0.02em] text-ink">
                {usage?.images ?? 0}
              </p>
            </div>
          </div>
        </div>
      </header>

      <div className="grid gap-6 md:grid-cols-[minmax(0,380px)_minmax(0,1fr)] md:items-start">
        <Card className="flex flex-col gap-6">
          <UploadBox
            projectId={projectId}
            asset={currentSource}
            onUploaded={(asset) => {
              setSourceAssetId(asset.id);
              void load();
            }}
          />

          <div className="border-t border-hairline" />

          <div className="flex flex-col gap-4">
            <Eyebrow>02 · 商品信息</Eyebrow>

            <label className="flex flex-col gap-1.5">
              <span className="text-[12px] text-helper">
                商品名称 <span className="text-[#8c2b25]">*</span>
              </span>
              <input
                value={form.product_name}
                onChange={(e) => setForm({ ...form, product_name: e.target.value })}
                placeholder="例如：316 不锈钢保温杯"
                maxLength={50}
                className={inputClass}
              />
            </label>

            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1.5">
                <span className="text-[12px] text-helper">类目</span>
                <input
                  value={form.category}
                  onChange={(e) => setForm({ ...form, category: e.target.value })}
                  placeholder="家居"
                  maxLength={50}
                  className={inputClass}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-[12px] text-helper">主色</span>
                <input
                  value={form.color}
                  onChange={(e) => setForm({ ...form, color: e.target.value })}
                  placeholder="雾霾蓝"
                  maxLength={20}
                  className={inputClass}
                />
              </label>
            </div>

            <label className="flex flex-col gap-1.5">
              <span className="text-[12px] text-helper">卖点</span>
              <textarea
                value={form.selling_points}
                onChange={(e) => setForm({ ...form, selling_points: e.target.value })}
                placeholder="24 小时保温，316 不锈钢内胆"
                maxLength={200}
                rows={2}
                className={`resize-none ${inputClass}`}
              />
            </label>

            {formError && (
              <div className="rounded-[16px] bg-blush px-4 py-3 text-[13px] text-[#8c2b25]">
                {formError}
              </div>
            )}

            <Button
              onClick={handleGenerate}
              loading={submitting}
              disabled={!currentSource || isWorking}
              className="w-full"
              aria-busy={submitting || isWorking}
            >
              {isWorking ? "生成中…" : "生成主图"}
            </Button>

            {isWorking && (
              <div className="flex flex-col gap-2 rounded-[16px] bg-sky/40 px-4 py-3">
                <p className="text-[12px] leading-relaxed text-teal">
                  不想等了？「停止等待」只是关掉这个页面的进度，任务还在后台跑；
                  「取消任务」会让它真的停下。
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="quiet"
                    onClick={stopWaiting}
                    aria-label="停止等待，任务继续在后台生成"
                  >
                    停止等待
                  </Button>
                  <Button
                    variant="quiet"
                    onClick={handleCancel}
                    loading={cancelling}
                    aria-label="取消任务，让后端停止生成"
                  >
                    取消任务
                  </Button>
                </div>
              </div>
            )}

            {!currentSource && (
              <p className="text-[12px] text-fog">先上传商品图才能生成。</p>
            )}
          </div>
        </Card>

        <Card className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <Eyebrow>03 · 生成结果</Eyebrow>
            {isWorking && <StatusTag status="running" />}
          </div>
          <ResultPanel
            phase={phase}
            isWorking={isWorking}
            onRetry={handleRetry}
            retrying={retrying}
            onRefresh={() => void load()}
            fallback={latestSuccess}
          />

          {/* 精修：只对成功的草稿开放 */}
          {latestSuccess && phase.kind !== "cancelled" && (
            <div className="flex flex-col gap-3 border-t border-hairline pt-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-col gap-1">
                  <Eyebrow>精修（图生图）</Eyebrow>
                  <p className="text-[12px] leading-relaxed text-helper">
                    草稿只按文字描述画，可能不像你的商品。精修会参考这张图重绘，保留形状和颜色，约 ¥0.30/张。
                  </p>
                </div>
                <Button
                  variant="quiet"
                  onClick={handleRefine}
                  loading={refining || refineEvents.isWorking}
                  disabled={refining || refineEvents.isWorking}
                >
                  {refineEvents.isWorking ? "精修中…" : "精修成主图（≈¥0.30）"}
                </Button>
              </div>

              {refineNotice && (
                <p className="text-[12px] text-teal" role="status">
                  {refineNotice}
                </p>
              )}
              {refineEvents.phase.kind === "error" && (
                <p className="text-[12px] text-[#8c2b25]">
                  精修失败：{refineEvents.phase.error.message}
                </p>
              )}

              {latestRefined && (
                <div className="flex flex-col gap-3 rounded-[20px] bg-sky/30 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <DeltaBadge deltaE={latestRefined.deltaE} />
                    <QaBadge
                      score={latestRefined.qaScore}
                      max={parseQaDetail(refinedDetailRaw)?.max_total ?? 12}
                    />
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <figure className="flex flex-col gap-1.5">
                      <img
                        src={`/api/assets/${latestSuccess.assetId}/file`}
                        alt="草稿"
                        className="w-full rounded-[14px] border border-hairline bg-canvas"
                      />
                      <figcaption className="text-center text-[11px] text-helper">
                        草稿（¥0.03）
                      </figcaption>
                    </figure>
                    <figure className="flex flex-col gap-1.5">
                      <img
                        src={`/api/assets/${latestRefined.assetId}/file`}
                        alt="精修"
                        className="w-full rounded-[14px] border border-ink/20 bg-canvas"
                      />
                      <figcaption className="text-center text-[11px] text-ink">
                        精修（¥0.30）
                      </figcaption>
                    </figure>
                  </div>
                  <QaDetailList detail={parseQaDetail(refinedDetailRaw)} />
                  <a
                    href={`/api/assets/${latestRefined.assetId}/download`}
                    className="w-fit rounded-[28px] border border-ink px-4 py-2 text-[13px] font-medium text-ink hover:bg-ink hover:text-canvas"
                  >
                    下载精修图
                  </a>
                </div>
              )}
            </div>
          )}
        </Card>
      </div>

      {(outputs.length > 0 || detail.recent_jobs.length > 0) && (
        <section className="flex flex-col gap-4">
          <div className="flex items-baseline justify-between">
            <h2 className="text-[19px] font-medium tracking-[-0.01em] text-ink">历史</h2>
            {outputs.length > 0 && (
              <span className="text-[12px] text-helper">{outputs.length} 张作品</span>
            )}
          </div>

          {outputs.length > 0 && (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
              {outputs.slice(0, 10).map((a) => (
                <a
                  key={a.id}
                  href={a.url}
                  target="_blank"
                  rel="noreferrer"
                  className="group block overflow-hidden rounded-[24px] border border-hairline bg-canvas p-1.5 shadow-[var(--shadow-subtle)] transition-transform duration-200 hover:-translate-y-0.5"
                >
                  <img
                    src={a.url}
                    alt={a.filename}
                    className="aspect-square w-full rounded-[18px] object-cover"
                  />
                </a>
              ))}
            </div>
          )}

          {detail.recent_jobs.length > 0 && (
            <div className="overflow-hidden rounded-[24px] border border-hairline bg-canvas">
              <table className="w-full text-left text-[14px]">
                <thead className="bg-sky/40">
                  <tr>
                    <th className="px-4 py-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-helper">
                      商品
                    </th>
                    <th className="px-4 py-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-helper">
                      状态
                    </th>
                    <th className="px-4 py-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-helper">
                      成本
                    </th>
                    <th className="px-4 py-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-helper">
                      时间
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {detail.recent_jobs.map((job) => (
                    <tr key={job.id} className="border-t border-hairline">
                      <td className="max-w-[10rem] truncate px-4 py-3 text-ink">
                        {job.product_name || "—"}
                      </td>
                      <td className="px-4 py-3">
                        <StatusTag status={job.status} />
                      </td>
                      <td className="px-4 py-3 text-helper">{formatFen(job.cost_fen)}</td>
                      <td className="px-4 py-3 text-[12px] text-helper">
                        {formatTime(job.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      <footer className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-hairline pt-6 text-[12px] text-helper">
        <span>阶段 2-2 · 单张主图端到端</span>
        <Link href="/" className="text-teal hover:underline">
          返回列表
        </Link>
      </footer>
    </div>
  );
}
