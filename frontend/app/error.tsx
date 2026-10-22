"use client";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-danger/30 bg-danger-soft px-6 py-12 text-center">
      <p className="text-base font-medium text-danger">页面出错了</p>
      <p className="text-sm text-danger/80">
        可以刷新重试；如果反复出现，把这一步的操作告诉我。
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
      >
        重新加载
      </button>
      {error.digest && <p className="text-xs text-danger/60">编号：{error.digest}</p>}
    </div>
  );
}
