import type { ReactNode } from "react";

/** 相纸卡：24px 圆角 + 1px 发丝边 + 极轻阴影（DESIGN.md Photo Profile Card） */
export function Card({
  children,
  className = "",
  padded = true,
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <div
      className={`rounded-[24px] border border-hairline bg-canvas shadow-[var(--shadow-subtle)] ${
        padded ? "p-5" : ""
      } ${className}`.trim()}
    >
      {children}
    </div>
  );
}

export function CardTitle({ children }: { children: ReactNode }) {
  return (
    <h3 className="text-[15px] font-medium tracking-[0.01em] text-ink">{children}</h3>
  );
}

/** 小节眉标：10-11px、大写、0.14em 字距（DESIGN.md Eyebrow Label） */
export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-helper">
      {children}
    </span>
  );
}
