"use client";

import { useEffect, useRef, useState } from "react";

export type JobStage = "preparing" | "calling" | "";

export type JobDoneEvent = {
  job_id: string;
  asset_id: string;
  cost_fen: number;
  elapsed_ms: number | null;
};

export type JobErrorEvent = { code: string; message: string };

type State = {
  jobId: string | null;
  stage: JobStage;
  done: JobDoneEvent | null;
  error: JobErrorEvent | null;
};

const IDLE: State = { jobId: null, stage: "", done: null, error: null };

export function useJobEvents(jobId: string | null, onSettled?: () => void) {
  const [state, setState] = useState<State>(IDLE);
  const settledRef = useRef(onSettled);

  useEffect(() => {
    settledRef.current = onSettled;
  }, [onSettled]);

  useEffect(() => {
    if (!jobId) return;

    const es = new EventSource(`/api/jobs/${jobId}/events`);
    let closed = false;
    const close = () => {
      if (!closed) {
        closed = true;
        es.close();
      }
    };

    es.addEventListener("status", (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data) as { stage: JobStage };
        setState({ jobId, stage: data.stage ?? "", done: null, error: null });
      } catch {
        // 忽略无法解析的事件
      }
    });

    es.addEventListener("done", (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data) as JobDoneEvent;
        setState({ jobId, stage: "calling", done: data, error: null });
      } catch {
        setState({
          jobId,
          stage: "",
          done: null,
          error: { code: "SSE_BAD_EVENT", message: "结果解析失败，请刷新" },
        });
      } finally {
        close();
        settledRef.current?.();
      }
    });

    // 服务端的自定义 error 事件与连接错误都叫 "error"，靠 data 是否存在区分
    es.addEventListener("error", (event) => {
      const messageEvent = event as MessageEvent;
      if (messageEvent.data) {
        try {
          const payload = JSON.parse(messageEvent.data) as { error: JobErrorEvent };
          setState({ jobId, stage: "", done: null, error: payload.error });
        } catch {
          setState({
            jobId,
            stage: "",
            done: null,
            error: { code: "SSE_BAD_EVENT", message: "进度信息解析失败，请刷新" },
          });
        }
        close();
        settledRef.current?.();
        return;
      }
      setState({
        jobId,
        stage: "",
        done: null,
        error: { code: "SSE_DISCONNECTED", message: "进度连接断开，请刷新页面查看结果" },
      });
      close();
      settledRef.current?.();
    });

    return () => {
      close();
    };
  }, [jobId]);

  // 派生初始状态：jobId 变了但 effect 还没跑，界面上仍应显示"准备中"
  const current: State =
    state.jobId === jobId
      ? state
      : { jobId, stage: jobId ? "preparing" : "", done: null, error: null };

  return {
    stage: current.stage,
    done: current.done,
    error: current.error,
    isWorking: Boolean(jobId) && !current.done && !current.error,
  };
}
