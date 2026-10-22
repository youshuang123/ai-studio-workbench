"use client";

import { formatFen } from "@/lib/utils/format";

// ΔE 对浅色/白色商品不可靠（实测：两张米白杯子算到 34.6）。
// 因此界面只把它当"参考值"，用中性色，不做红/绿判断；真正的颜色判断看 QA 的 color_consistency。
const LEVEL_TEXT: Record<string, { text: string; cls: string }> = {
  same: { text: "主色接近", cls: "bg-hairline text-helper" },
  slight: { text: "主色略偏", cls: "bg-hairline text-helper" },
  different: { text: "主色差异大", cls: "bg-hairline text-helper" },
  unknown: { text: "无法判断", cls: "bg-hairline text-helper" },
};

export function deltaLevel(deltaE: number | null | undefined): string {
  if (deltaE === null || deltaE === undefined) return "unknown";
  if (deltaE <= 3) return "same";
  if (deltaE <= 6) return "slight";
  return "different";
}

export function DeltaBadge({ deltaE }: { deltaE: number | null | undefined }) {
  const level = deltaLevel(deltaE);
  const meta = LEVEL_TEXT[level];
  return (
    <span
      className={`chip ${meta.cls}`}
      title="主色差仅供参考：浅色/白色商品受背景影响大，颜色请以质检的「颜色一致」为准"
    >
      ΔE {deltaE === null || deltaE === undefined ? "—" : deltaE.toFixed(1)} · {meta.text}（参考）
    </span>
  );
}

export function QaBadge({
  score,
  max = 12,
}: {
  score: number | null | undefined;
  max?: number;
}) {
  if (score === null || score === undefined) {
    return <span className="chip bg-hairline text-helper">质检 —</span>;
  }
  const avg = score / max;
  const cls =
    avg >= 0.83 ? "bg-mint text-ink" : avg >= 0.6 ? "bg-peach text-[#8a4b12]" : "bg-blush text-[#8c2b25]";
  const label = avg >= 0.83 ? "通过" : avg >= 0.6 ? "需注意" : "不合格";
  return (
    <span className={`chip ${cls}`}>
      QA {score}/{max} · {label}
    </span>
  );
}

export type QaDetail = {
  follows_description?: number;
  no_text_or_watermark?: number;
  product_complete?: number;
  background_clean?: number;
  total?: number;
  max_total?: number;
  color_consistency?: number | null;
  issues?: string[];
  verdict?: string;
  ok?: boolean;
  error?: string;
  message?: string;
};

const DIM_LABELS: Record<string, string> = {
  follows_description: "符合描述",
  no_text_or_watermark: "无文字水印",
  product_complete: "商品完整",
  background_clean: "背景干净",
  color_consistency: "颜色一致",
};

export function parseQaDetail(raw: string | null | undefined): QaDetail | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as QaDetail;
  } catch {
    return null;
  }
}

export function QaDetailList({ detail }: { detail: QaDetail | null }) {
  if (!detail) return null;
  if (detail.ok === false) {
    return (
      <p className="text-[12px] text-[#8a4b12]">
        质检没跑成功（{detail.error}）：{detail.message}
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap gap-x-5 gap-y-1">
        {Object.entries(DIM_LABELS).map(([key, label]) => {
          const value = detail[key as keyof QaDetail];
          if (value === null || value === undefined) return null;
          return (
            <span key={key} className="text-[12px] text-helper">
              {label} <span className="font-medium text-ink">{value}/3</span>
            </span>
          );
        })}
      </div>
      {detail.issues && detail.issues.length > 0 && (
        <ul className="list-inside list-disc text-[12px] text-[#8a4b12]">
          {detail.issues.map((issue, i) => (
            <li key={i}>{issue}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function RefinePrice({ count }: { count: number }) {
  return <span>{formatFen(count * 30)}</span>;
}
