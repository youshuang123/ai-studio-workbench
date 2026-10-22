"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, Eyebrow } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { createDrama, listDramas } from "@/features/drama/client";
import { STYLES } from "@/features/drama/types";
import type { DramaListItem } from "@/features/drama/types";
import { fetchProject } from "@/features/api/client";
import type { ProjectDetail } from "@/features/api/types";
import { errorMessage } from "@/lib/api/client";
import { formatTime } from "@/lib/utils/format";

const inputClass =
  "rounded-[16px] border border-divider bg-canvas px-4 py-2.5 text-[14px] text-ink outline-none placeholder:text-fog focus:border-ink";

export default function DramasPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const projectId = Array.isArray(params?.id) ? params.id[0] : (params?.id ?? "");

  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [items, setItems] = useState<DramaListItem[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [style, setStyle] = useState("都市");
  const [script, setScript] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [list, p] = await Promise.all([listDramas(projectId), fetchProject(projectId)]);
      setItems(list.items);
      setProject(p);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
      setItems([]);
    }
  }, [projectId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function handleCreate() {
    if (!script.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const drama = await createDrama(projectId, {
        title: title.trim() || "未命名短剧",
        script_text: script.trim(),
        style,
      });
      router.push(`/projects/${projectId}/dramas/${drama.id}`);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-3">
        <Link href={`/projects/${projectId}`} className="w-fit text-[13px] text-teal hover:underline">
          ← 返回项目
        </Link>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <Eyebrow>短剧</Eyebrow>
            <h1 className="display-tight mt-1.5 text-[30px] text-ink md:text-[36px]">
              {project?.name ?? "…"} · 短剧
            </h1>
            <p className="mt-2 max-w-[60ch] text-[14px] leading-relaxed text-helper">
              粘一段剧本 → 生成分镜表 → 逐镜头出关键帧 → 合成轻动效视频。
              先出便宜草稿，挑中的再精修。
            </p>
          </div>
          <Button onClick={() => setCreating((v) => !v)}>
            {creating ? "取消" : "新建短剧"}
          </Button>
        </div>
      </header>

      {error && (
        <div className="rounded-[20px] bg-blush px-5 py-4 text-[14px] text-[#8c2b25]" role="alert">
          {error}
        </div>
      )}

      {creating && (
        <Card className="flex flex-col gap-4">
          <Eyebrow>新建短剧</Eyebrow>
          <div className="grid gap-3 sm:grid-cols-[1fr_160px]">
            <label className="flex flex-col gap-1.5">
              <span className="text-[12px] text-helper">标题</span>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="例如：雨夜退稿"
                maxLength={120}
                className={inputClass}
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-[12px] text-helper">风格</span>
              <select
                value={style}
                onChange={(e) => setStyle(e.target.value)}
                className={inputClass}
              >
                {STYLES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] text-helper">
              剧本 <span className="text-[#8c2b25]">*</span>（纯文本，≤8000 字）
            </span>
            <textarea
              value={script}
              onChange={(e) => setScript(e.target.value)}
              rows={10}
              maxLength={8000}
              placeholder={"例：\n林小满站在公司楼下的雨里，手里攥着一份被退回的方案。\n她抬头看了一眼 28 楼的灯，还是亮的。\n电话响起，是母亲：这么晚还不回来？"}
              className={`resize-y ${inputClass}`}
            />
            <span className="text-[11px] text-fog">{script.length} / 8000</span>
          </label>
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={handleCreate} loading={busy} disabled={!script.trim()}>
              创建并进入
            </Button>
            <span className="text-[12px] text-helper">
              创建后不会自动调模型；你在下一步点「生成分镜表」
            </span>
          </div>
        </Card>
      )}

      <section className="flex flex-col gap-4">
        <h2 className="text-[19px] font-medium tracking-[-0.01em] text-ink">我的短剧</h2>

        {items === null && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-28 animate-pulse rounded-[24px] bg-hairline" />
            ))}
          </div>
        )}

        {items !== null && items.length === 0 && !error && (
          <EmptyState
            title="还没有短剧"
            description="粘一段 200 字的剧本，就能拆出 8 个镜头。"
            action={<Button variant="outline" onClick={() => setCreating(true)}>创建第一个短剧</Button>}
          />
        )}

        {items !== null && items.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((d) => (
              <Link key={d.id} href={`/projects/${projectId}/dramas/${d.id}`} className="group block">
                <Card className="h-full transition-transform group-hover:-translate-y-0.5">
                  <p className="truncate text-[17px] font-medium text-ink">{d.title}</p>
                  <div className="mt-3 flex items-center gap-2 text-[12px] text-helper">
                    <span className="rounded-full bg-sky px-2.5 py-1 text-teal">{d.style}</span>
                    <span>{formatTime(d.created_at)}</span>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
