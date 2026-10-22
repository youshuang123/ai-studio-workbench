"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button, buttonClass } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Divider } from "@/components/ui/Divider";
import { EmptyState } from "@/components/ui/EmptyState";
import { ProjectCardSkeleton } from "@/components/ui/Skeleton";
import { createProject, fetchHealth, fetchProjects } from "@/features/api/client";
import type { Health, ProjectListItem } from "@/features/api/types";
import { errorMessage } from "@/lib/api/client";
import { formatTime } from "@/lib/utils/format";

export default function HomePage() {
  const [projects, setProjects] = useState<ProjectListItem[] | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    try {
      const [list, h] = await Promise.all([fetchProjects(), fetchHealth()]);
      setProjects(list.items);
      setHealth(h);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
      setProjects([]);
    }
  }, []);

  useEffect(() => {
    // 首次加载数据。setState 发生在 await 之后（不是同步级联渲染），
    // 规则无法区分 await 前后的 setState，故此处显式关闭该检查。
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function handleCreate() {
    const trimmed = name.trim();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    try {
      await createProject(trimmed);
      setName("");
      setCreating(false);
      await load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink md:text-[28px]">
            创作工作台
          </h1>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-smoke">
            上传商品图，生成电商主图。AI 出初稿，你负责判断和修改。
          </p>
        </div>
        <Button onClick={() => setCreating((v) => !v)}>
          {creating ? "取消" : "新建项目"}
        </Button>
      </header>

      {health && !health.t2i_configured && (
        <div className="rounded-xl border border-warn/30 bg-warn-soft px-4 py-3 text-sm text-warn">
          还没配置模型 Key，能建项目和传图，但点生成会提示未配置。填好后重启后端即可。
        </div>
      )}

      {creating && (
        <Card className="flex flex-col gap-3 md:flex-row md:items-end">
          <label className="flex flex-1 flex-col gap-1">
            <span className="text-xs text-smoke">项目名称</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              placeholder="例如：秋冬保温杯上新"
              maxLength={100}
              className="rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </label>
          <Button onClick={handleCreate} loading={submitting} disabled={!name.trim()}>
            创建
          </Button>
        </Card>
      )}

      <Divider />

      {error && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger">
          <span>{error}</span>
          <Button variant="secondary" onClick={() => void load()}>
            重试
          </Button>
        </div>
      )}

      <section className="flex flex-col gap-4">
        <h2 className="text-sm font-medium text-smoke">我的项目</h2>

        {projects === null && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <ProjectCardSkeleton />
            <ProjectCardSkeleton />
            <ProjectCardSkeleton />
          </div>
        )}

        {projects !== null && projects.length === 0 && !error && (
          <EmptyState
            title="还没有项目"
            description="先建一个项目，再把商品图传上来。"
            action={<Button onClick={() => setCreating(true)}>创建第一个项目</Button>}
          />
        )}

        {projects !== null && projects.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((p) => (
              <Link key={p.id} href={`/projects/${p.id}`} className="block">
                <Card className="h-full transition-colors hover:border-accent/40">
                  <p className="truncate text-base font-medium text-ink">{p.name}</p>
                  <p className="mt-2 text-xs text-smoke">
                    {p.asset_count} 个素材 · {p.job_count} 个任务
                  </p>
                  <p className="mt-4 text-xs text-smoke">{formatTime(p.created_at)}</p>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </section>

      <footer className="pt-2 text-xs text-smoke">
        阶段 2-1 · 电商线最小闭环（单张主图端到端）。当前版本：{" "}
        {health?.version ?? "—"}
        {" · "}
        <Link href="/" className={buttonClass("ghost", "px-0 py-0 text-xs")}>
          刷新
        </Link>
      </footer>
    </div>
  );
}
