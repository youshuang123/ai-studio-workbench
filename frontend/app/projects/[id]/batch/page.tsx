"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, Eyebrow } from "@/components/ui/Card";
import { StatusTag } from "@/components/ui/StatusTag";
import {
  cancelBatch,
  confirmBatch,
  createBatch,
  exportUrl,
  fetchBatch,
  listBatches,
  resumeBatch,
  refineItems,
  retryItem,
  subscribeBatch,
  trialBatch,
  validateCsv,
} from "@/features/batch/client";
import type { Batch, BatchProgress, ValidateResult } from "@/features/batch/types";
import { fetchProject } from "@/features/api/client";
import type { ProjectDetail } from "@/features/api/types";
import { DeltaBadge, QaBadge } from "@/features/qa/components";
import { errorMessage } from "@/lib/api/client";
import { formatFen } from "@/lib/utils/format";

const inputClass =
  "rounded-[16px] border border-divider bg-canvas px-4 py-2.5 text-[14px] text-ink outline-none placeholder:text-fog focus:border-ink";

export default function BatchPage() {
  const params = useParams<{ id: string }>();
  const projectId = Array.isArray(params?.id) ? params.id[0] : (params?.id ?? "");

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ValidateResult | null>(null);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [progress, setProgress] = useState<BatchProgress | null>(null);
  const [trialAssetId, setTrialAssetId] = useState<string | null>(null);

  const [busy, setBusy] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const unsubRef = useRef<null | (() => void)>(null);

  const reloadBatch = useCallback(async (id: string) => {
    const b = await fetchBatch(id);
    setBatch(b);
    setProgress({
      total: b.total,
      succeeded: b.succeeded,
      failed: b.failed,
      cost_fen: b.cost_fen,
      status: b.status,
    });
  }, []);

  // 刷新页面后找回最近一个批次（批次状态不放在 URL 里，靠后端兜底）
  useEffect(() => {
    fetchProject(projectId)
      .then(setProject)
      .catch((e) => setError(errorMessage(e)));

    listBatches(projectId)
      .then(async (res) => {
        const latest = res.items[0];
        if (!latest) return;
        const full = await fetchBatch(latest.id);
        setBatch(full);
        setProgress({
          total: full.total,
          succeeded: full.succeeded,
          failed: full.failed,
          cost_fen: full.cost_fen,
          status: full.status,
        });
        const done = (full.items ?? []).find(
          (i) => i.status === "succeeded" && i.output_asset_id,
        );
        if (done?.output_asset_id) setTrialAssetId(done.output_asset_id);
        // 仍在跑的批次，自动接回进度
        if (["queued", "running"].includes(full.status)) {
          unsubRef.current?.();
          unsubRef.current = subscribeBatch(full.id, {
            onProgress: (pr) => setProgress(pr),
            onItem: () => {},
            onDone: async (pr) => {
              setProgress(pr);
              await reloadBatch(full.id);
            },
            onError: (code, message) => setError(`${message}（${code}）`),
          });
        }
      })
      .catch(() => {
        /* 没有批次是正常情况 */
      });
  }, [projectId, reloadBatch]);

  // 离开页面时关闭 SSE
  useEffect(() => {
    return () => {
      unsubRef.current?.();
    };
  }, []);

  async function handlePickFile(f: File | undefined) {
    if (!f) return;
    setFile(f);
    setError(null);
    setPreview(null);
    setBatch(null);
    setTrialAssetId(null);
    setBusy("validate");
    try {
      const result = await validateCsv(projectId, f);
      setPreview(result);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  async function handleCreate() {
    if (!file) return;
    setBusy("create");
    setError(null);
    try {
      const b = await createBatch(projectId, file);
      setBatch(b);
      setProgress({
        total: b.total,
        succeeded: b.succeeded,
        failed: b.failed,
        cost_fen: b.cost_fen,
        status: b.status,
      });
      setNotice(`已建批次，共 ${b.total} 行。先试跑一条看看效果。`);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  async function handleTrial() {
    if (!batch) return;
    setBusy("trial");
    setError(null);
    try {
      const result = await trialBatch(batch.id);
      if (result.job.status === "succeeded" && result.job.output_asset_id) {
        setTrialAssetId(result.job.output_asset_id);
        setNotice(`试跑成功，花了 ${formatFen(result.job.cost_fen)}。确认效果后可以批量。`);
      } else {
        setError(result.job.error_message || "试跑失败");
      }
      await reloadBatch(batch.id);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  async function handleConfirm() {
    if (!batch) return;
    setBusy("confirm");
    setError(null);
    try {
      const b = await confirmBatch(batch.id);
      setBatch(b);
      setNotice("批量已开始，进度会实时更新。");
      unsubRef.current?.();
      unsubRef.current = subscribeBatch(b.id, {
        onProgress: (p) => setProgress(p),
        onItem: () => {},
        onDone: async (p) => {
          setProgress(p);
          await reloadBatch(b.id);
        },
        onError: (code, message) => setError(`${message}（${code}）`),
      });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  async function handleStop() {
    if (!batch) return;
    if (!window.confirm("确定停止？已经生成成功的图会保留。")) return;
    setBusy("stop");
    try {
      const b = await cancelBatch(batch.id);
      setBatch(b);
      await reloadBatch(b.id);
      setNotice("已停止。已完成的图保留在结果里，可以导出。");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  async function handleResume() {
    if (!batch) return;
    setBusy("resume");
    try {
      const b = await resumeBatch(batch.id);
      setBatch(b);
      unsubRef.current?.();
      unsubRef.current = subscribeBatch(b.id, {
        onProgress: (p) => setProgress(p),
        onItem: () => {},
        onDone: async (p) => {
          setProgress(p);
          await reloadBatch(b.id);
        },
        onError: (code, message) => setError(`${message}（${code}）`),
      });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  async function handleRefineSelected() {
    if (!batch || selected.length === 0) return;
    const price = (selected.length * 0.3).toFixed(2);
    if (!window.confirm(`精修 ${selected.length} 张，预计花费 ¥${price}。继续吗？`)) return;
    setBusy("refine");
    setError(null);
    try {
      const resp = await refineItems(batch.id, selected);
      setNotice(`已开始精修 ${resp.created} 张，预计 ¥${(resp.estimated_cost_fen / 100).toFixed(2)}。完成后刷新查看。`);
      setSelected([]);
      // 精修是后台任务，轮询刷新
      for (let i = 0; i < 40; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        const b = await fetchBatch(batch.id);
        setBatch(b);
        const done = (b.items ?? []).filter(
          (it) => it.stage === "refined" && it.status === "succeeded",
        ).length;
        if (done >= selected.length) break;
      }
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  async function handleRetry(itemId: string) {
    if (!batch) return;
    setBusy(itemId);
    try {
      await retryItem(batch.id, itemId);
      await reloadBatch(batch.id);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  const running = batch && ["queued", "running"].includes(batch.status);
  const canBulk = Boolean(trialAssetId) && batch?.status === "draft";
  const items = batch?.items ?? [];

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-4">
        <Link href={`/projects/${projectId}`} className="w-fit text-[13px] text-teal hover:underline">
          ← 返回项目
        </Link>
        <div>
          <Eyebrow>批量生成</Eyebrow>
          <h1 className="display-tight mt-1.5 text-[30px] text-ink md:text-[36px]">
            {project?.name ?? "…"} · SKU 批量
          </h1>
          <p className="mt-2 max-w-[60ch] text-[14px] leading-relaxed text-helper">
            上传 SKU 表 → 试跑一条确认效果 → 批量生成 → 导出 ZIP。
            当前仍是文生图，图片只做归档关联；「像不像原商品」要等一致性阶段。
          </p>
        </div>
      </header>

      {error && (
        <div className="rounded-[20px] bg-blush px-5 py-4 text-[14px] text-[#8c2b25]" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <div className="rounded-[20px] bg-sky/60 px-5 py-4 text-[14px] text-teal" role="status">
          {notice}
        </div>
      )}

      {/* 01 上传 */}
      <Card className="flex flex-col gap-4">
        <Eyebrow>01 · 上传 SKU 表</Eyebrow>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant={file ? "quiet" : "rainbow"}
            onClick={() => fileRef.current?.click()}
            loading={busy === "validate"}
          >
            {file ? "换一个文件" : "选择 CSV 文件"}
          </Button>
          <span className="text-[12px] leading-relaxed text-helper">
            表头：sku_code, product_name, category, color, selling_points, image_file
            <br />
            示例表在 <code className="text-ink">backend/examples/skus.csv</code>
          </span>
          {file && <span className="text-[12px] text-teal">{file.name}</span>}
        </div>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={(e) => void handlePickFile(e.target.files?.[0])}
        />

        {preview && (
          <div className="flex flex-col gap-3 border-t border-hairline pt-4">
            <p className="text-[14px] text-ink">
              共 {preview.total} 行，
              <span className="text-teal">{preview.valid} 行可用</span>
              {preview.errors.length > 0 && (
                <span className="text-[#8c2b25]">，{preview.errors.length} 处问题</span>
              )}
              {preview.missing_images.length > 0 && (
                <span className="text-[#8a4b12]">
                  ，{preview.missing_images.length} 行缺图（会跳过）
                </span>
              )}
            </p>

            {preview.errors.length > 0 && (
              <div className="overflow-hidden rounded-[16px] border border-hairline">
                <table className="w-full text-left text-[13px]">
                  <thead className="bg-blush/50">
                    <tr>
                      <th className="px-3 py-2 text-[10px] uppercase tracking-[0.14em] text-[#8c2b25]">行</th>
                      <th className="px-3 py-2 text-[10px] uppercase tracking-[0.14em] text-[#8c2b25]">列</th>
                      <th className="px-3 py-2 text-[10px] uppercase tracking-[0.14em] text-[#8c2b25]">问题</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.errors.slice(0, 10).map((e, i) => (
                      <tr key={i} className="border-t border-hairline">
                        <td className="px-3 py-2">第 {e.row} 行</td>
                        <td className="px-3 py-2 text-helper">{e.column}</td>
                        <td className="px-3 py-2">{e.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={handleCreate} loading={busy === "create"} disabled={!preview.valid}>
                建立批次（{preview.valid} 行）
              </Button>
              <span className="text-[12px] text-helper">
                预估成本 {formatFen(preview.valid * 3)}（按 ¥0.03/张估算）
              </span>
            </div>
          </div>
        )}
      </Card>

      {/* 02 试跑 */}
      {batch && (
        <Card className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Eyebrow>02 · 试跑第一条</Eyebrow>
            <StatusTag status={batch.status} />
          </div>

          {!trialAssetId && batch.status === "draft" && (
            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={handleTrial} loading={busy === "trial"}>
                试跑这一条
              </Button>
              <span className="text-[12px] text-helper">会真实调用模型，约 ¥0.03</span>
            </div>
          )}

          {trialAssetId && (
            <div className="flex flex-wrap items-start gap-4">
              <img
                src={`/api/assets/${trialAssetId}/file`}
                alt="试跑结果"
                className="w-[200px] rounded-[16px] border border-hairline"
              />
              <div className="flex flex-col gap-2">
                <p className="text-[14px] text-ink">试跑成功。满意就确认批量。</p>
                <Button onClick={handleConfirm} loading={busy === "confirm"} disabled={!canBulk}>
                  确认批量（{batch.total} 行 · 约 {formatFen(batch.total * 3)}）
                </Button>
                <p className="text-[12px] text-helper">
                  确认后会逐条生成，可以随时停止。
                </p>
              </div>
            </div>
          )}
        </Card>
      )}

      {/* 03 进度 */}
      {batch && (
        <Card className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Eyebrow>03 · 批量进度</Eyebrow>
            <div className="flex gap-2">
              {running && (
                <Button variant="quiet" onClick={handleStop} loading={busy === "stop"}>
                  停止
                </Button>
              )}
              {batch.status === "paused" && (
                <Button variant="quiet" onClick={handleResume} loading={busy === "resume"}>
                  继续
                </Button>
              )}
            </div>
          </div>

          {progress && (
            <>
              <div className="h-2 w-full overflow-hidden rounded-full bg-hairline">
                <div
                  className="h-full rounded-full bg-teal transition-all"
                  style={{
                    width: `${progress.total ? ((progress.succeeded + progress.failed) / progress.total) * 100 : 0}%`,
                  }}
                />
              </div>
              <dl className="flex flex-wrap gap-x-8 gap-y-1 text-[13px]">
                <div className="flex gap-1.5">
                  <dt className="text-helper">总数</dt>
                  <dd className="text-ink">{progress.total}</dd>
                </div>
                <div className="flex gap-1.5">
                  <dt className="text-helper">成功</dt>
                  <dd className="text-ink">{progress.succeeded}</dd>
                </div>
                <div className="flex gap-1.5">
                  <dt className="text-helper">失败/跳过</dt>
                  <dd className="text-ink">{progress.failed}</dd>
                </div>
                <div className="flex gap-1.5">
                  <dt className="text-helper">已花费</dt>
                  <dd className="text-ink">{formatFen(progress.cost_fen)}</dd>
                </div>
              </dl>
            </>
          )}

          {items.length > 0 && (
            <div className="flex flex-col gap-2 border-t border-hairline pt-4">
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-helper">{items.length} 行结果</span>
                {batch.succeeded > 0 && (
                  <a
                    href={exportUrl(batch.id)}
                    className="rounded-[28px] border border-ink px-4 py-2 text-[13px] font-medium text-ink hover:bg-ink hover:text-canvas"
                  >
                    导出 ZIP
                  </a>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-3 rounded-[16px] bg-sky/30 px-4 py-3">
                <span className="text-[12px] text-helper">
                  已选 {selected.length} 张
                  {selected.length > 0 && `（精修约 ¥${(selected.length * 0.3).toFixed(2)}）`}
                </span>
                <Button
                  variant="quiet"
                  onClick={handleRefineSelected}
                  loading={busy === "refine"}
                  disabled={selected.length === 0 || busy === "refine"}
                >
                  精修选中的 {selected.length} 张
                </Button>
                <span className="text-[11px] text-fog">
                  精修会参考原图重绘，保留形状颜色，约 ¥0.30/张
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                {items.map((item) => {
                  const selectable = item.status === "succeeded" && item.stage !== "refined";
                  return (
                    <div
                      key={item.id}
                      className="flex flex-col gap-1.5 rounded-[18px] border border-hairline bg-canvas p-1.5"
                    >
                      {item.output_asset_id ? (
                        <div className="relative">
                          <img
                            src={`/api/assets/${item.output_asset_id}/file`}
                            alt={item.sku_code}
                            className="aspect-square w-full rounded-[14px] object-cover"
                          />
                          {selectable && (
                            <input
                              type="checkbox"
                              aria-label={`选择 ${item.sku_code}`}
                              checked={selected.includes(item.id)}
                              onChange={(e) =>
                                setSelected((prev) =>
                                  e.target.checked
                                    ? [...prev, item.id]
                                    : prev.filter((id) => id !== item.id),
                                )
                              }
                              className="absolute right-2 top-2 size-5 accent-[#08304c]"
                            />
                          )}
                          {item.stage === "refined" && (
                            <span className="absolute left-2 top-2 rounded-full bg-ink px-2 py-0.5 text-[10px] text-canvas">
                              已精修
                            </span>
                          )}
                        </div>
                      ) : (
                        <div className="flex aspect-square w-full items-center justify-center rounded-[14px] bg-hairline text-[11px] text-helper">
                          {item.error_message || "未完成"}
                        </div>
                      )}
                      <div className="flex items-center justify-between px-1">
                        <span className="truncate text-[11px] text-ink">{item.sku_code}</span>
                        <StatusTag status={item.status} />
                      </div>
                      {item.stage === "refined" && (
                        <div className="flex flex-wrap gap-1 px-1">
                          <DeltaBadge deltaE={item.delta_e} />
                          <QaBadge score={item.qa_score} />
                        </div>
                      )}
                      {["failed", "over_budget"].includes(item.status) && (
                        <button
                          type="button"
                          onClick={() => void handleRetry(item.id)}
                          className="rounded-full bg-sky px-2 py-1 text-[11px] text-teal"
                        >
                          重试这一条
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </Card>
      )}

      <footer className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-hairline pt-6 text-[12px] text-helper">
        <span>阶段 2-2 · SKU 批量</span>
        <Link href={`/projects/${projectId}`} className="text-teal hover:underline">
          回到单张生成
        </Link>
      </footer>
    </div>
  );
}
