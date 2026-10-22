"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
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
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-ink">1. 商品图</h3>
        <span className="text-xs text-smoke">png / jpg / webp，≤10MB</span>
      </div>

      {asset ? (
        <div className="flex items-center gap-3 rounded-xl border border-line bg-surface p-3">
          <img
            src={asset.url}
            alt="商品图预览"
            className="size-16 shrink-0 rounded-lg border border-line object-cover"
          />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm text-ink">{asset.filename}</p>
            <p className="mt-1 text-xs text-smoke">
              {asset.width}×{asset.height} · {formatBytes(asset.bytes)}
            </p>
          </div>
          <Button variant="secondary" onClick={() => inputRef.current?.click()}>
            换一张
          </Button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          className="flex min-h-32 flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-line bg-surface px-4 py-8 text-sm text-smoke hover:border-accent/50 disabled:opacity-60"
        >
          <span className="font-medium text-ink">
            {busy ? "正在上传…" : "点击上传商品图"}
          </span>
          <span className="text-xs">建议正面清晰、纯色背景</span>
        </button>
      )}

      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={(e) => void handleFile(e.target.files?.[0])}
      />

      {error && <p className="text-sm text-danger">{error}</p>}
    </div>
  );
}
