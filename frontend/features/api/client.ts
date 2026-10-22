import { apiFetch } from "@/lib/api/client";

import type {
  Asset,
  GenerationJob,
  Health,
  ProjectDetail,
  ProjectListItem,
  Usage,
} from "./types";

type ListResp = { items: ProjectListItem[]; total: number };

export function fetchHealth() {
  return apiFetch<Health>("/api/health");
}

export function fetchProjects() {
  return apiFetch<ListResp>("/api/projects");
}

export function createProject(name: string, description = "") {
  return apiFetch<{ id: string; name: string }>("/api/projects", {
    method: "POST",
    body: JSON.stringify({ name, description }),
  });
}

export function fetchProject(id: string) {
  return apiFetch<ProjectDetail>(`/api/projects/${id}`);
}

export function fetchUsage(id: string) {
  return apiFetch<Usage>(`/api/projects/${id}/usage`);
}

export function uploadAsset(projectId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<Asset>(`/api/projects/${projectId}/assets`, {
    method: "POST",
    body: form,
  });
}

export type GenerateInput = {
  source_asset_id: string;
  product_name: string;
  category?: string;
  selling_points?: string;
  color?: string;
};

export function createGeneration(projectId: string, input: GenerateInput) {
  return apiFetch<{ job_id: string; status: string }>(
    `/api/projects/${projectId}/generations`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export function fetchJob(jobId: string) {
  return apiFetch<GenerationJob>(`/api/jobs/${jobId}`);
}

export function retryJob(jobId: string) {
  return apiFetch<{ job_id: string; status: string }>(
    `/api/jobs/${jobId}/retry`,
    { method: "POST" },
  );
}

export function refineJob(jobId: string) {
  return apiFetch<{ job_id: string; status: string; stage: string }>(
    `/api/jobs/${jobId}/refine`,
    { method: "POST" },
  );
}

export function rerunQa(jobId: string) {
  return apiFetch<{ ok: boolean; qa_score?: number; error?: string; message?: string }>(
    `/api/jobs/${jobId}/qa`,
    { method: "POST" },
  );
}

export function cancelJob(jobId: string) {
  return apiFetch<{ job_id: string; status: string; cancel_requested: boolean }>(
    `/api/jobs/${jobId}/cancel`,
    { method: "POST" },
  );
}
