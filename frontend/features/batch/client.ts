import { apiFetch } from "@/lib/api/client";

import type { Batch, BatchProgress, ValidateResult } from "./types";

function csvForm(file: File): FormData {
  const form = new FormData();
  form.append("file", file);
  return form;
}

export function validateCsv(projectId: string, file: File) {
  return apiFetch<ValidateResult>(`/api/projects/${projectId}/batches/validate`, {
    method: "POST",
    body: csvForm(file),
  });
}

export function createBatch(projectId: string, file: File, name?: string) {
  const form = csvForm(file);
  if (name) form.append("name", name);
  return apiFetch<Batch & { created_jobs: number }>(
    `/api/projects/${projectId}/batches`,
    { method: "POST", body: form },
  );
}

export function listBatches(projectId: string) {
  return apiFetch<{ items: Batch[]; total: number }>(`/api/projects/${projectId}/batches`);
}

export function fetchBatch(batchId: string) {
  return apiFetch<Batch>(`/api/batches/${batchId}`);
}

export function trialBatch(batchId: string) {
  return apiFetch<{ job: { id: string; status: string; cost_fen: number; output_asset_id: string | null; error_message: string }; batch: Batch }>(
    `/api/batches/${batchId}/trial`,
    { method: "POST" },
  );
}

export function confirmBatch(batchId: string) {
  return apiFetch<Batch>(`/api/batches/${batchId}/confirm`, { method: "POST" });
}

export function resumeBatch(batchId: string) {
  return apiFetch<Batch>(`/api/batches/${batchId}/resume`, { method: "POST" });
}

export function cancelBatch(batchId: string) {
  return apiFetch<Batch>(`/api/batches/${batchId}/cancel`, { method: "POST" });
}

export function retryItem(batchId: string, itemId: string) {
  return apiFetch<{ item: { id: string; status: string } }>(
    `/api/batches/${batchId}/items/${itemId}/retry`,
    { method: "POST" },
  );
}

export const exportUrl = (batchId: string) => `/api/batches/${batchId}/export`;

/** 批次 SSE；done 之后调用 onDone。 */
export function subscribeBatch(
  batchId: string,
  handlers: {
    onProgress: (p: BatchProgress) => void;
    onItem: (item: { id: string; sku_code: string; status: string; cost_fen: number }) => void;
    onDone: (p: BatchProgress & { status: string }) => void;
    onError: (code: string, message: string) => void;
  },
): () => void {
  const es = new EventSource(`/api/batches/${batchId}/events`);
  let closed = false;
  const close = () => {
    if (!closed) {
      closed = true;
      es.close();
    }
  };

  es.addEventListener("progress", (e) => {
    if (closed) return;
    try {
      handlers.onProgress(JSON.parse((e as MessageEvent).data) as BatchProgress);
    } catch {
      /* 忽略解析失败 */
    }
  });

  es.addEventListener("item", (e) => {
    if (closed) return;
    try {
      handlers.onItem(JSON.parse((e as MessageEvent).data));
    } catch {
      /* 忽略 */
    }
  });

  es.addEventListener("done", (e) => {
    if (closed) return;
    try {
      handlers.onDone(JSON.parse((e as MessageEvent).data));
    } finally {
      close();
    }
  });

  es.addEventListener("error", (e) => {
    if (closed) return;
    const me = e as MessageEvent;
    if (me.data) {
      try {
        const payload = JSON.parse(me.data) as { error: { code: string; message: string } };
        handlers.onError(payload.error.code, payload.error.message);
      } catch {
        handlers.onError("SSE_BAD_EVENT", "进度信息解析失败，请刷新");
      }
    } else {
      handlers.onError("SSE_DISCONNECTED", "进度连接中断，刷新页面可查看最新状态");
    }
    close();
  });

  return close;
}
