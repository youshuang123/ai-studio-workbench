"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Eyebrow } from "@/components/ui/Card";
import { uploadAsset } from "@/features/api/client";
import type { Asset } from "@/features/api/types";
import { errorMessage } from "@/lib/api/client";
import { formatBytes } from "@/lib/utils/format";

export function UploadBox({
  projectId,
  asset,
  onUploaded,
}: {
  projectId: string;
  asset: Asset | null;
  onUploaded: (asset: Asset) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File | undefined) {
    if (!file || busy) return;
    setError(null);
    setBusy(true);
    try {
      const uploaded = await uploadAsset(projectId, file);
      onUploaded(uploaded);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <Eyebrow>01 · 商品图</Eyebrow>
        <span className="text-[11px] text-fog">png / jpg / webp · ≤10MB</span>
      </div>

      {asset ? (
        <div className="flex items-center gap-3 rounded-[20px] border border-hairline bg-canvas p-3">
          <img
            src={asset.url}
            alt="商品图预览"
            className="size-16 shrink-0 rounded-[14px] border border-hairline object-cover"
          />
          <div className="min-w-0 flex-1">
            <p className="truncate text-[14px] text-ink">{asset.filename}</p>
            <p className="mt-0.5 text-[12px] text-helper">
              {asset.width}×{asset.height} · {formatBytes(asset.bytes)}
            </p>
          </div>
          <Button variant="quiet" onClick={() => inputRef.current?.click()}>
            换一张
          </Button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          className="flex min-h-[132px] flex-col items-center justify-center gap-2 rounded-[20px] border border-dashed border-divider bg-sky/30 px-4 py-8 text-[14px] text-helper transition-colors hover:border-ink/40 disabled:opacity-60"
        >
          <span className="font-medium text-ink">
            {busy ? "正在上传…" : "点击上传商品图"}
          </span>
          <span className="text-[12px]">建议正面清晰、纯色背景</span>
        </button>
      )}

      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={(e) => void handleFile(e.target.files?.[0])}
      />

      {error && <p className="text-[13px] text-[#8c2b25]">{error}</p>}
    </div>
  );
}
