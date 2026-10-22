export type ShotJob = {
  id: string;
  status: string;
  stage: string;
  output_asset_id: string | null;
  cost_fen: number;
  qa_score: number | null;
  error_code: string;
  error_message: string;
};

export type Shot = {
  id: string;
  scene_id: string | null;
  index: number;
  shot_size: string;
  camera: string;
  action: string;
  dialogue: string;
  duration_sec: number;
  continuity: string;
  mood: string;
  character_ids: string[];
  job_id: string | null;
  job: ShotJob | null;
};

export type DramaScene = {
  id: string;
  index: number;
  title: string;
  location: string;
  time_of_day: string;
  summary: string;
};

export type DramaCharacter = {
  id: string;
  name: string;
  appearance: string;
  costume: string;
  personality: string;
  ref_asset_id: string | null;
};

export type Drama = {
  id: string;
  project_id: string;
  title: string;
  script_text: string;
  style: string;
  status: string;
  video_path: string;
  created_at: string | null;
  scenes: DramaScene[];
  shots: Shot[];
  characters: DramaCharacter[];
  llm_attempts?: number;
};

export type DramaListItem = {
  id: string;
  title: string;
  style: string;
  status: string;
  created_at: string | null;
};

export const SHOT_SIZES = ["远景", "全景", "中景", "近景", "特写"];
export const CAMERAS = ["平视", "俯拍", "仰拍", "过肩", "侧拍"];
export const STYLES = ["都市", "悬疑", "古装", "校园", "甜宠", "科幻"];
