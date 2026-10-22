import type { ButtonHTMLAttributes } from "react";

/**
 * Portrait 风格按钮
 * - rainbow：主 CTA，1.5px 彩虹渐变描边（每视图最多一个）
 * - ghost：次级动作，纯文字
 * - quiet：轻描边，用于表单内的小动作
 */
export type ButtonVariant = "rainbow" | "outline" | "ghost" | "quiet";

const BASE =
  "inline-flex items-center justify-center gap-2 text-[15px] font-medium tracking-[0.01em] transition-all duration-150 disabled:cursor-not-allowed disabled:opacity-40";

const VARIANTS: Record<ButtonVariant, string> = {
  rainbow:
    "rainbow-ring px-6 py-3 text-ink hover:-translate-y-px hover:shadow-[0_6px_18px_-10px_rgba(8,48,76,0.35)]",
  outline:
    "rounded-[28px] border border-ink px-6 py-3 text-ink hover:bg-ink hover:text-canvas",
  ghost: "px-2 py-2 text-ink hover:text-teal underline-offset-4 hover:underline",
  quiet:
    "rounded-[16px] border border-divider bg-canvas px-3 py-2 text-[13px] text-ink hover:border-ink/30",
};

export function buttonClass(variant: ButtonVariant = "rainbow", extra = ""): string {
  return `${BASE} ${VARIANTS[variant]} ${extra}`.trim();
}

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  loading?: boolean;
};

export function Button({
  variant = "rainbow",
  loading = false,
  className = "",
  children,
  disabled,
  ...rest
}: Props) {
  return (
    <button
      className={buttonClass(variant, className)}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && (
        <span
          aria-hidden="true"
          className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      )}
      {children}
    </button>
  );
}
