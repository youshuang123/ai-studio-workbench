"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchJob } from "@/features/api/client";

export type JobStage = "preparing" | "calling" | "";

export type JobDoneEvent = {
  job_id: string;
  asset_id: string;
  cost_fen: number;
  elapsed_ms: number | null;
};

export type JobErrorEvent = { code: string; message: string };

export type JobPhase =
  | { kind: "idle" }
  | { kind: "status"; stage: JobStage }
  | { kind: "done"; data: JobDoneEvent }
  | { kind: "error"; error: JobErrorEvent }
  | { kind: "cancelled"; message: string }
  | { kind: "disconnected"; message: string };

type Snapshot = { jobId: string | null; phase: JobPhase };

const MAX_RECONNECT = 2;

/**
 * 订阅任务进度。
 *
 * 关键规则（前端手册 §10.2）：
 * - 服务端自定义 `error` 事件与「连接断开」同名，靠是否带 data 区分；
 * - 连接关闭但没收到 done/error/cancelled → 不算成功 → 先按任务 ID 回查后端真实状态；
 * - 回查说还在跑才重连，最多 2 次，仍失败显示 disconnected（可手动刷新）。
 */
export function useJobEvents(jobId: string | null, onSettled?: () => void) {
  const [snapshot, setSnapshot] = useState<Snapshot>({ jobId: null, phase: { kind: "idle" } });
  const [reconnectKey, setReconnectKey] = useState(0);
  const settledRef = useRef(onSettled);
  const reconnectRef = useRef(0);
  const sourceRef = useRef<EventSource | null>(null);
  const closedRef = useRef(false);

  useEffect(() => {
    settledRef.current = onSettled;
  }, [onSettled]);

  const setPhase = useCallback((id: string, phase: JobPhase) => {
    setSnapshot({ jobId: id, phase });
  }, []);

  /** 用户主动「停止等待」：只关连接，任务在后端继续 */
  const stopWaiting = useCallback(() => {
    closedRef.current = true;
    sourceRef.current?.close();
    sourceRef.current = null;
    if (jobId) {
      setPhase(jobId, {
        kind: "disconnected",
        message: "已停止等待。任务仍在后台生成，刷新页面可以查看结果。",
      });
    }
  }, [jobId, setPhase]);

  useEffect(() => {
    if (!jobId) return;

    closedRef.current = false;
    const es = new EventSource(`/api/jobs/${jobId}/events`);
    sourceRef.current = es;

    const close = () => {
      if (!closedRef.current) {
        closedRef.current = true;
        es.close();
        sourceRef.current = null;
      }
    };

    const settle = () => {
      close();
      settledRef.current?.();
    };

    /** 断线后回查后端真实状态（不把「连接关闭」当成成功） */
    const reconcile = async () => {
      try {
        const job = await fetchJob(jobId);
        const elapsed = job.elapsed_ms ?? null;

        if (job.status === "succeeded" && job.output_asset_id) {
          setPhase(jobId, {
            kind: "done",
            data: {
              job_id: jobId,
              asset_id: job.output_asset_id,
              cost_fen: job.cost_fen,
              elapsed_ms: elapsed,
            },
          });
          settle();
          return;
        }
        if (job.status === "cancelled") {
          setPhase(jobId, {
            kind: "cancelled",
            message: job.error_message || "任务已取消",
          });
          settle();
          return;
        }
        if (job.status === "failed" || job.status === "over_budget") {
          setPhase(jobId, {
            kind: "error",
            error: {
              code: job.error_code || "JOB_FAILED",
              message: job.error_message || "生成失败，可重试",
            },
          });
          settle();
          return;
        }

        // 仍在排队/运行 → 允许有限次重连
        if (reconnectRef.current < MAX_RECONNECT) {
          reconnectRef.current += 1;
          setReconnectKey((k) => k + 1);
          return;
        }
        setPhase(jobId, {
          kind: "disconnected",
          message: "连接中断，任务可能仍在后台生成。刷新页面可查看最新状态。",
        });
        settle();
      } catch {
        if (reconnectRef.current < MAX_RECONNECT) {
          reconnectRef.current += 1;
          setReconnectKey((k) => k + 1);
          return;
        }
        setPhase(jobId, {
          kind: "disconnected",
          message: "连不上服务，请确认后端已启动。任务可能仍在后台生成。",
        });
        settle();
      }
    };

    es.addEventListener("status", (event) => {
      if (closedRef.current) return;
      try {
        const data = JSON.parse((event as MessageEvent).data) as { stage: JobStage };
        setPhase(jobId, { kind: "status", stage: data.stage ?? "" });
      } catch {
        // 忽略无法解析的事件
      }
    });

    es.addEventListener("done", (event) => {
      if (closedRef.current) return;
      try {
        const data = JSON.parse((event as MessageEvent).data) as JobDoneEvent;
        setPhase(jobId, { kind: "done", data });
      } catch {
        setPhase(jobId, {
          kind: "error",
          error: { code: "SSE_BAD_EVENT", message: "结果解析失败，请刷新" },
        });
      } finally {
        settle();
      }
    });

    es.addEventListener("cancelled", (event) => {
      if (closedRef.current) return;
      let message = "任务已取消";
      try {
        const data = JSON.parse((event as MessageEvent).data) as { message?: string };
        if (data.message) message = data.message;
      } catch {
        // 用默认文案
      }
      setPhase(jobId, { kind: "cancelled", message });
      settle();
    });

    es.addEventListener("error", (event) => {
      if (closedRef.current) return;
      const messageEvent = event as MessageEvent;

      // 带 data = 服务端主动发的 error 事件
      if (messageEvent.data) {
        try {
          const payload = JSON.parse(messageEvent.data) as { error: JobErrorEvent };
          setPhase(jobId, { kind: "error", error: payload.error });
        } catch {
          setPhase(jobId, {
            kind: "error",
            error: { code: "SSE_BAD_EVENT", message: "进度信息解析失败，请刷新" },
          });
        }
        settle();
        return;
      }

      // 不带 data = 连接断开，回查后端，不猜结果
      close();
      void reconcile();
    });

    return () => {
      close();
    };
  }, [jobId, reconnectKey, setPhase]);

  // jobId 变了但 effect 还没跑完：先显示"准备中"，避免闪回上一次的结果
  const current: JobPhase =
    snapshot.jobId === jobId
      ? snapshot.phase
      : jobId
        ? { kind: "status", stage: "preparing" }
        : { kind: "idle" };

  return {
    phase: current,
    stopWaiting,
    isWorking:
      Boolean(jobId) && (current.kind === "idle" || current.kind === "status"),
  };
}
