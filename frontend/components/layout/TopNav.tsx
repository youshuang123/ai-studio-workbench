import Link from "next/link";

/** 浮动药丸导航：56px 高、28px 圆角、六层轻阴影（DESIGN.md Floating Pill Nav） */
export function TopNav() {
  return (
    <header className="sticky top-4 z-30 mx-auto w-full max-w-[1200px] px-4">
      <nav
        aria-label="主导航"
        className="flex h-14 items-center justify-between gap-3 rounded-[28px] border border-hairline bg-canvas px-4 shadow-[var(--shadow-nav)]"
      >
        <Link href="/" className="flex items-center gap-2.5">
          <span aria-hidden="true" className="rainbow-square size-3 shrink-0" />
          <span className="text-[17px] font-semibold tracking-[-0.02em] text-ink">
            AI Studio
          </span>
        </Link>

        <span className="hidden items-center gap-2 rounded-full bg-sky px-3 py-1.5 text-[12px] text-teal sm:flex">
          <span className="text-[10px] font-semibold uppercase tracking-[0.14em]">
            阶段 2-1
          </span>
          <span className="text-ink">单张主图端到端</span>
        </span>

        <Link
          href="/"
          className="rounded-full px-3 py-2 text-[13px] font-medium text-ink hover:text-teal"
        >
          项目列表
        </Link>
      </nav>
    </header>
  );
}
