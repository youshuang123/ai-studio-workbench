"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, Eyebrow } from "@/components/ui/Card";
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
    <div className="flex flex-col gap-10">
      <header className="flex flex-col gap-5 pt-2">
        <Eyebrow>工作台</Eyebrow>
        <div className="flex flex-wrap items-end justify-between gap-6">
          <h1 className="display-tighter max-w-[18ch] text-[30px] text-ink sm:text-[38px] md:text-[46px]">
            把商品图变成
            <span className="rainbow-text"> 可交付主图</span>
          </h1>
          <Button onClick={() => setCreating((v) => !v)}>
            {creating ? "取消" : "新建项目"}
          </Button>
        </div>
        <p className="max-w-[52ch] text-[16px] leading-relaxed text-body">
          AI 负责出初稿，你负责判断和修改。每张图都会记录用了哪个模型、花了多少钱。
        </p>
      </header>

      {health && !health.t2i_configured && (
        <div className="flex items-start gap-3 rounded-[20px] bg-peach px-5 py-4">
          <span className="mt-0.5 text-[13px] font-semibold uppercase tracking-[0.14em] text-[#8a4b12]">
            待配置
          </span>
          <p className="text-[14px] leading-relaxed text-[#6b3a0e]">
            还没配置模型 Key。建项目和传图都能用，点生成会提示未配置。填好后重启后端即可。
          </p>
        </div>
      )}

      {creating && (
        <Card className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="flex flex-1 flex-col gap-1.5">
            <Eyebrow>项目名称</Eyebrow>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              placeholder="例如：秋冬保温杯上新"
              maxLength={100}
              className="rounded-[16px] border border-divider bg-canvas px-4 py-3 text-[15px] text-ink outline-none placeholder:text-fog focus:border-ink"
            />
          </label>
          <Button onClick={handleCreate} loading={submitting} disabled={!name.trim()}>
            创建
          </Button>
        </Card>
      )}

      {error && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[20px] bg-blush px-5 py-4 text-[14px] text-[#8c2b25]">
          <span>{error}</span>
          <Button variant="quiet" onClick={() => void load()}>
            重试
          </Button>
        </div>
      )}

      <section className="flex flex-col gap-5">
        <div className="flex items-baseline justify-between">
          <h2 className="text-[19px] font-medium tracking-[-0.01em] text-ink">我的项目</h2>
          {projects !== null && projects.length > 0 && (
            <span className="text-[13px] text-helper">{projects.length} 个</span>
          )}
        </div>

        {projects === null && (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            <ProjectCardSkeleton />
            <ProjectCardSkeleton />
            <ProjectCardSkeleton />
          </div>
        )}

        {projects !== null && projects.length === 0 && !error && (
          <EmptyState
            title="还没有项目"
            description="先建一个项目，再把商品图传上来。第一张图大约 10 秒。"
            action={
              <Button variant="outline" onClick={() => setCreating(true)}>
                创建第一个项目
              </Button>
            }
          />
        )}

        {projects !== null && projects.length > 0 && (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((p) => (
              <Link key={p.id} href={`/projects/${p.id}`} className="group block">
                <Card className="h-full transition-transform duration-200 group-hover:-translate-y-0.5">
                  <div className="flex h-full flex-col gap-3">
                    <div className="flex items-start justify-between gap-3">
                      <p className="min-w-0 truncate text-[17px] font-medium tracking-[-0.01em] text-ink">
                        {p.name}
                      </p>
                      <span className="mt-0.5 shrink-0 text-[12px] text-helper">
                        {p.job_count > 0 ? `${p.job_count} 次生成` : "未生成"}
                      </span>
                    </div>
                    <div className="mt-auto flex items-center gap-2 text-[12px] text-helper">
                      <span className="rounded-full bg-sky px-2.5 py-1 text-teal">
                        {p.asset_count} 个素材
                      </span>
                      <span>{formatTime(p.created_at)}</span>
                    </div>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </section>

      <footer className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-hairline pt-6 text-[12px] text-helper">
        <span>阶段 2-1 · 电商线最小闭环</span>
        <span>版本 {health?.version ?? "—"}</span>
        {health && (
          <span>
            模型 {health.t2i_model} · 单价 ¥{(health.unit_price_fen / 100).toFixed(2)}/张
          </span>
        )}
      </footer>
    </div>
  );
}
