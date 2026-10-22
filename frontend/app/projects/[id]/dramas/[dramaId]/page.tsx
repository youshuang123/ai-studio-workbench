"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, Eyebrow } from "@/components/ui/Card";
import { StatusTag } from "@/components/ui/StatusTag";
import {
  addCharacter,
  addShot,
  composeVideo,
  deleteShot,
  dramaExportUrl,
  dramaVideoUrl,
  fetchDrama,
  makeCharacterRef,
  makeKeyframes,
  makeStoryboard,
  regenKeyframe,
  reorderShots,
  updateShot,
} from "@/features/drama/client";
import { CAMERAS, SHOT_SIZES } from "@/features/drama/types";
import type { Drama, Shot } from "@/features/drama/types";
import { errorMessage } from "@/lib/api/client";
import { formatFen } from "@/lib/utils/format";

const inputClass =
  "w-full rounded-[12px] border border-divider bg-canvas px-2.5 py-1.5 text-[13px] text-ink outline-none focus:border-ink";

export default function DramaDetailPage() {
  const params = useParams<{ id: string; dramaId: string }>();
  const projectId = Array.isArray(params?.id) ? params.id[0] : (params?.id ?? "");
  const dramaId = Array.isArray(params?.dramaId)
    ? params.dramaId[0]
    : (params?.dramaId ?? "");

  const [drama, setDrama] = useState<Drama | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [charName, setCharName] = useState("");
  const [charLook, setCharLook] = useState("");
  const [charCostume, setCharCostume] = useState("");

  const load = useCallback(async () => {
    try {
      const d = await fetchDrama(dramaId);
      setDrama(d);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [dramaId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const shots = useMemo(() => drama?.shots ?? [], [drama]);
  const totalSec = useMemo(
    () => shots.reduce((acc, s) => acc + (s.duration_sec || 0), 0),
    [shots],
  );
  const withFrame = shots.filter((s) => s.job?.output_asset_id).length;
  const totalCost = shots.reduce((acc, s) => acc + (s.job?.cost_fen ?? 0), 0);

  async function run(key: string, fn: () => Promise<unknown>, msg?: string) {
    setBusy(key);
    setError(null);
    setNotice(null);
    try {
      await fn();
      await load();
      if (msg) setNotice(msg);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  async function handleStoryboard() {
    if (!drama) return;
    await run("storyboard", () => makeStoryboard(drama.id), "分镜表已生成，可以逐条修改");
  }

  async function handleKeyframes() {
    if (!drama) return;
    const missing = shots.filter((s) => !s.job_id).length;
    if (missing === 0) return;
    const price = (missing * 0.03).toFixed(2);
    if (!window.confirm(`为 ${missing} 个镜头生成关键帧，预计 ¥${price}。继续吗？`)) return;
    await run(
      "keyframes",
      () => makeKeyframes(drama.id),
      `已开始生成 ${missing} 张关键帧`,
    );
    // 轮询
    for (let i = 0; i < 30; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      await load();
    }
  }

  async function handleCompose() {
    if (!drama) return;
    if (!window.confirm(`合成 ${shots.length} 个镜头，约 ${totalSec.toFixed(1)} 秒。视频合成不额外收费。继续吗？`)) return;
    await run("compose", () => composeVideo(drama.id), "视频已合成");
  }

  async function handleAddCharacter() {
    if (!drama || !charName.trim()) return;
    await run("char", () =>
      addCharacter(drama.id, {
        name: charName.trim(),
        appearance: charLook.trim(),
        costume: charCostume.trim(),
        personality: "",
      }),
    );
    setCharName("");
    setCharLook("");
    setCharCostume("");
  }

  async function saveShot(shot: Shot, patch: Partial<Shot>) {
    if (!drama) return;
    await run("save", () => updateShot(drama.id, shot.id, patch));
  }

  if (!drama) {
    return (
      <div className="flex flex-col gap-4">
        {error ? (
          <div className="rounded-[20px] bg-blush px-5 py-4 text-[14px] text-[#8c2b25]">{error}</div>
        ) : (
          <>
            <div className="h-4 w-24 animate-pulse rounded bg-hairline" />
            <div className="h-8 w-1/3 animate-pulse rounded bg-hairline" />
            <div className="h-64 animate-pulse rounded-[24px] bg-hairline" />
          </>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-3">
        <Link
          href={`/projects/${projectId}/dramas`}
          className="w-fit text-[13px] text-teal hover:underline"
        >
          ← 返回短剧列表
        </Link>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <Eyebrow>短剧 · {drama.style}</Eyebrow>
            <h1 className="display-tight mt-1.5 text-[30px] text-ink md:text-[36px]">
              {drama.title}
            </h1>
            <p className="mt-2 text-[13px] text-helper">
              {shots.length} 个镜头 · 约 {totalSec.toFixed(1)} 秒 · 关键帧 {withFrame}/
              {shots.length} · 已花 {formatFen(totalCost)}
            </p>
          </div>
          <StatusTag status={drama.status === "video_ready" ? "succeeded" : drama.status} />
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

      {/* 01 剧本 */}
      <Card className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Eyebrow>01 · 剧本</Eyebrow>
          <Button onClick={handleStoryboard} loading={busy === "storyboard"}>
            {shots.length ? "重新生成分镜表" : "生成分镜表"}
          </Button>
        </div>
        <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-[16px] bg-sky/30 p-4 text-[13px] leading-relaxed text-body">
          {drama.script_text}
        </pre>
        {drama.llm_attempts && (
          <p className="text-[11px] text-fog">分镜表生成用了 {drama.llm_attempts} 次尝试</p>
        )}
      </Card>

      {/* 02 分镜表 */}
      {shots.length > 0 && (
        <Card className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Eyebrow>02 · 分镜表（可逐条修改）</Eyebrow>
            <div className="flex gap-2">
              <Button
                variant="quiet"
                onClick={() =>
                  run("add", () => addShot(drama.id, { action: "（待补充镜头）" }))
                }
              >
                加一个镜头
              </Button>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-left text-[13px]">
              <thead className="bg-sky/40">
                <tr>
                  {["#", "景别", "机位", "动作", "台词", "秒", "情绪", ""].map((h) => (
                    <th
                      key={h}
                      className="px-2 py-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-helper"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shots.map((shot, i) => (
                  <tr key={shot.id} className="border-t border-hairline align-top">
                    <td className="px-2 py-2 text-helper">{shot.index}</td>
                    <td className="w-[90px] px-2 py-2">
                      <select
                        value={shot.shot_size}
                        onChange={(e) => void saveShot(shot, { shot_size: e.target.value })}
                        className={inputClass}
                      >
                        {SHOT_SIZES.map((s) => (
                          <option key={s}>{s}</option>
                        ))}
                      </select>
                    </td>
                    <td className="w-[90px] px-2 py-2">
                      <select
                        value={shot.camera}
                        onChange={(e) => void saveShot(shot, { camera: e.target.value })}
                        className={inputClass}
                      >
                        {CAMERAS.map((c) => (
                          <option key={c}>{c}</option>
                        ))}
                      </select>
                    </td>
                    <td className="px-2 py-2">
                      <textarea
                        defaultValue={shot.action}
                        onBlur={(e) =>
                          e.target.value !== shot.action &&
                          void saveShot(shot, { action: e.target.value })
                        }
                        rows={2}
                        className={`resize-y ${inputClass}`}
                      />
                    </td>
                    <td className="px-2 py-2">
                      <textarea
                        defaultValue={shot.dialogue}
                        onBlur={(e) =>
                          e.target.value !== shot.dialogue &&
                          void saveShot(shot, { dialogue: e.target.value })
                        }
                        rows={2}
                        className={`resize-y ${inputClass}`}
                      />
                    </td>
                    <td className="w-[64px] px-2 py-2">
                      <input
                        type="number"
                        min={2}
                        max={8}
                        step={0.5}
                        defaultValue={shot.duration_sec}
                        onBlur={(e) =>
                          Number(e.target.value) !== shot.duration_sec &&
                          void saveShot(shot, { duration_sec: Number(e.target.value) })
                        }
                        className={inputClass}
                      />
                    </td>
                    <td className="w-[80px] px-2 py-2">
                      <input
                        defaultValue={shot.mood}
                        onBlur={(e) =>
                          e.target.value !== shot.mood &&
                          void saveShot(shot, { mood: e.target.value })
                        }
                        className={inputClass}
                      />
                    </td>
                    <td className="w-[110px] px-2 py-2">
                      <div className="flex flex-col gap-1">
                        <button
                          type="button"
                          onClick={() => {
                            if (i === 0) return;
                            const ids = shots.map((s) => s.id);
                            [ids[i - 1], ids[i]] = [ids[i], ids[i - 1]];
                            void run("reorder", () => reorderShots(drama.id, ids));
                          }}
                          className="rounded-full bg-sky px-2 py-1 text-[11px] text-teal disabled:opacity-40"
                          disabled={i === 0}
                        >
                          上移
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            if (!window.confirm(`删除第 ${shot.index} 镜？`)) return;
                            void run("del", () => deleteShot(drama.id, shot.id));
                          }}
                          className="rounded-full bg-hairline px-2 py-1 text-[11px] text-[#8c2b25]"
                        >
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-fog">
            改动作/台词/时长会让该镜头已有 keyframe 失效，需要重新生成。改景别/机位不影响。
          </p>
        </Card>
      )}

      {/* 03 角色 */}
      <Card className="flex flex-col gap-3">
        <Eyebrow>03 · 角色（可选）</Eyebrow>
        <div className="flex flex-wrap items-end gap-2">
          <input
            value={charName}
            onChange={(e) => setCharName(e.target.value)}
            placeholder="角色名"
            className={`w-[120px] ${inputClass}`}
          />
          <input
            value={charLook}
            onChange={(e) => setCharLook(e.target.value)}
            placeholder="外貌（25 岁女性，齐肩黑发）"
            className={`w-[220px] ${inputClass}`}
          />
          <input
            value={charCostume}
            onChange={(e) => setCharCostume(e.target.value)}
            placeholder="服装（米色针织衫）"
            className={`w-[180px] ${inputClass}`}
          />
          <Button variant="quiet" onClick={handleAddCharacter} loading={busy === "char"}>
            添加
          </Button>
        </div>

        {drama.characters.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {drama.characters.map((c) => (
              <div key={c.id} className="flex gap-3 rounded-[18px] border border-hairline p-3">
                {c.ref_asset_id ? (
                  <img
                    src={`/api/assets/${c.ref_asset_id}/file`}
                    alt={c.name}
                    className="size-16 shrink-0 rounded-[12px] object-cover"
                  />
                ) : (
                  <div className="flex size-16 shrink-0 items-center justify-center rounded-[12px] bg-hairline text-[11px] text-helper">
                    无参考图
                  </div>
                )}
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <p className="truncate text-[14px] font-medium text-ink">{c.name}</p>
                  <p className="line-clamp-2 text-[11px] text-helper">
                    {c.appearance} {c.costume}
                  </p>
                  <button
                    type="button"
                    onClick={() =>
                      run("ref", () => makeCharacterRef(drama.id, c.id), "参考图已生成（¥0.03）")
                    }
                    className="w-fit rounded-full bg-sky px-2 py-1 text-[11px] text-teal"
                  >
                    {c.ref_asset_id ? "重生成参考图" : "生成参考图"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* 04 关键帧 */}
      {shots.length > 0 && (
        <Card className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Eyebrow>04 · 关键帧</Eyebrow>
            <div className="flex items-center gap-3">
              <span className="text-[12px] text-helper">
                {withFrame}/{shots.length} 已生成
              </span>
              <Button
                onClick={handleKeyframes}
                loading={busy === "keyframes"}
                disabled={shots.every((s) => s.job_id)}
              >
                生成缺失的关键帧（≈¥{(shots.filter((s) => !s.job_id).length * 0.03).toFixed(2)}）
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {shots.map((shot) => {
              const assetId = shot.job?.output_asset_id;
              return (
                <div
                  key={shot.id}
                  className="flex flex-col gap-1.5 rounded-[18px] border border-hairline bg-canvas p-1.5"
                >
                  {assetId ? (
                    <img
                      src={`/api/assets/${assetId}/file`}
                      alt={`第 ${shot.index} 镜`}
                      className="aspect-square w-full rounded-[14px] object-cover"
                    />
                  ) : (
                    <div className="flex aspect-square w-full flex-col items-center justify-center gap-1 rounded-[14px] bg-hairline text-[11px] text-helper">
                      <span>第 {shot.index} 镜</span>
                      <span>{shot.job?.error_message || "未生成"}</span>
                    </div>
                  )}
                  <div className="flex items-center justify-between px-1">
                    <span className="text-[11px] text-ink">
                      {shot.index}. {shot.shot_size}
                    </span>
                    <StatusTag status={shot.job?.status ?? "idle"} />
                  </div>
                  <div className="flex items-center justify-between px-1 pb-1">
                    <button
                      type="button"
                      onClick={() =>
                        run("regen", () => regenKeyframe(drama.id, shot.id), "已重新生成该镜头")
                      }
                      className="rounded-full bg-sky px-2 py-1 text-[11px] text-teal"
                    >
                      重生成
                    </button>
                    {shot.job?.cost_fen ? (
                      <span className="text-[10px] text-fog">{formatFen(shot.job.cost_fen)}</span>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* 05 成片 */}
      {shots.length > 0 && (
        <Card className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Eyebrow>05 · 成片（轻动效）</Eyebrow>
            <div className="flex items-center gap-2">
              <Button
                onClick={handleCompose}
                loading={busy === "compose"}
                disabled={withFrame !== shots.length}
              >
                合成视频（约 {totalSec.toFixed(0)} 秒）
              </Button>
              {drama.video_path && (
                <a
                  href={dramaExportUrl(drama.id)}
                  className="rounded-[28px] border border-ink px-4 py-2 text-[13px] font-medium text-ink hover:bg-ink hover:text-canvas"
                >
                  导出 ZIP
                </a>
              )}
            </div>
          </div>

          {withFrame !== shots.length && (
            <p className="text-[12px] text-[#8a4b12]">
              还有 {shots.length - withFrame} 个镜头没有关键帧，补齐后才能合成。
            </p>
          )}

          {drama.video_path ? (
            <video
              controls
              src={dramaVideoUrl(drama.id)}
              className="w-full max-w-[560px] rounded-[18px] border border-hairline"
            />
          ) : (
            <div className="flex h-40 items-center justify-center rounded-[18px] border border-dashed border-divider bg-sky/30 text-[13px] text-helper">
              还没有成片
            </div>
          )}
          <p className="text-[11px] text-fog">
            当前是「关键帧 + 推拉/转场」的轻动效，不是生成式视频；输出无声。
          </p>
        </Card>
      )}

      <footer className="flex items-center gap-4 border-t border-hairline pt-6 text-[12px] text-helper">
        <span>阶段 2-4 · 短剧线</span>
        <Link href={`/projects/${projectId}/dramas`} className="text-teal hover:underline">
          返回短剧列表
        </Link>
      </footer>
    </div>
  );
}
