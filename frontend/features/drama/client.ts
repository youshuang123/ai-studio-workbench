import { apiFetch } from "@/lib/api/client";

import type { Drama, DramaCharacter, DramaListItem, Shot } from "./types";

export function listDramas(projectId: string) {
  return apiFetch<{ items: DramaListItem[]; total: number }>(
    `/api/projects/${projectId}/dramas`,
  );
}

export function createDrama(
  projectId: string,
  input: { title: string; script_text: string; style: string },
) {
  return apiFetch<Drama>(`/api/projects/${projectId}/dramas`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function fetchDrama(dramaId: string) {
  return apiFetch<Drama>(`/api/dramas/${dramaId}`);
}

export function makeStoryboard(dramaId: string, scriptText?: string) {
  return apiFetch<Drama>(`/api/dramas/${dramaId}/storyboard`, {
    method: "POST",
    body: JSON.stringify(scriptText ? { script_text: scriptText } : {}),
  });
}

export function updateShot(dramaId: string, shotId: string, patch: Partial<Shot>) {
  return apiFetch<Shot>(`/api/dramas/${dramaId}/shots/${shotId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function addShot(dramaId: string, input: Partial<Shot>) {
  return apiFetch<Shot>(`/api/dramas/${dramaId}/shots`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function deleteShot(dramaId: string, shotId: string) {
  return apiFetch<{ deleted: string }>(`/api/dramas/${dramaId}/shots/${shotId}`, {
    method: "DELETE",
  });
}

export function reorderShots(dramaId: string, shotIds: string[]) {
  return apiFetch<{ ok: boolean }>(`/api/dramas/${dramaId}/shots/reorder`, {
    method: "POST",
    body: JSON.stringify({ shot_ids: shotIds }),
  });
}

export function addCharacter(
  dramaId: string,
  input: { name: string; appearance: string; costume: string; personality: string },
) {
  return apiFetch<DramaCharacter>(`/api/dramas/${dramaId}/characters`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function makeCharacterRef(dramaId: string, charId: string) {
  return apiFetch<DramaCharacter & { job_status: string; cost_fen: number }>(
    `/api/dramas/${dramaId}/characters/${charId}/ref`,
    { method: "POST" },
  );
}

export function makeKeyframes(dramaId: string, shotIds?: string[]) {
  return apiFetch<{ created: number; estimated_cost_fen: number }>(
    `/api/dramas/${dramaId}/keyframes`,
    { method: "POST", body: JSON.stringify(shotIds ? { shot_ids: shotIds } : {}) },
  );
}

export function regenKeyframe(dramaId: string, shotId: string) {
  return apiFetch<{ created: number }>(`/api/dramas/${dramaId}/shots/${shotId}/keyframe`, {
    method: "POST",
  });
}

export function composeVideo(dramaId: string) {
  return apiFetch<{
    ok: boolean;
    video_path: string;
    duration_sec: number | null;
    size: [number, number] | null;
    bytes: number;
  }>(`/api/dramas/${dramaId}/compose`, { method: "POST" });
}

export const dramaVideoUrl = (dramaId: string) => `/api/dramas/${dramaId}/video`;
export const dramaExportUrl = (dramaId: string) => `/api/dramas/${dramaId}/export`;
