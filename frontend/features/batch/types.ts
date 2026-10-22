export type CsvRowPreview = {
  index: number;
  sku_code: string;
  product_name: string;
  category: string;
  color: string;
  selling_points: string;
  image_file: string;
  ok: boolean;
  skipped: boolean;
  errors: { row: number; column: string; message: string }[];
};

export type ValidateResult = {
  rows: CsvRowPreview[];
  errors: { row: number; column: string; message: string }[];
  missing_images: { row: number; sku_code: string; file: string }[];
  total: number;
  valid: number;
  file_name: string;
};

export type BatchItem = {
  id: string;
  sku_code: string;
  product_name: string;
  status: string;
  cost_fen: number;
  output_asset_id: string | null;
  error_code: string;
  error_message: string;
};

export type Batch = {
  id: string;
  project_id: string;
  name: string;
  status: string;
  total: number;
  succeeded: number;
  failed: number;
  cost_fen: number;
  budget_fen: number;
  confirmed_at: string | null;
  created_at: string | null;
  finished_at: string | null;
  items?: BatchItem[];
};

export type BatchProgress = {
  total: number;
  succeeded: number;
  failed: number;
  cost_fen: number;
  status: string;
};
