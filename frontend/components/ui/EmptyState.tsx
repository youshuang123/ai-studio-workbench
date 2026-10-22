import type { ReactNode } from "react";

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-[24px] border border-hairline bg-sky/40 px-6 py-14 text-center">
      <p className="text-[19px] font-medium tracking-[-0.01em] text-ink">{title}</p>
      {description && (
        <p className="max-w-md text-[15px] leading-relaxed text-helper">{description}</p>
      )}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
