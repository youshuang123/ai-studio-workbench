export type Asset = {
  id: string;
  project_id: string;
  kind: "upload" | "output" | string;
  filename: string;
  mime: string;
  bytes: number;
  width: number;
  height: number;
  created_at: string | null;
  url: string;
};

export type ProjectListItem = {
  id: string;
  name: string;
  asset_count: number;
  job_count: number;
  created_at: string | null;
};

export type JobBrief = {
  id: string;
  status: string;
  product_name: string;
  output_asset_id: string | null;
  cost_fen: number;
  error_code: string;
  error_message: string;
  created_at: string | null;
};

export type ProjectDetail = {
  id: string;
  name: string;
  description: string;
  created_at: string | null;
  assets: Asset[];
  recent_jobs: JobBrief[];
};

export type GenerationJob = {
  id: string;
  project_id: string;
  status: string;
  product_name: string;
  output_asset_id: string | null;
  cost_fen: number;
  unit_price_fen: number;
  elapsed_ms: number | null;
  error_code: string;
  error_message: string;
  created_at: string | null;
};

export type Usage = {
  total_fen: number;
  images: number;
  by_model: { model: string; images: number; cost_fen: number }[];
};

export type Health = {
  status: string;
  version: string;
  t2i_configured: boolean;
  t2i_model: string;
  unit_price_fen: number;
  task_budget_fen: number;
};
