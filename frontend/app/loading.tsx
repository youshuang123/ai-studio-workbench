export default function Loading() {
  return (
    <div className="flex flex-col gap-4">
      <div className="h-8 w-1/3 animate-pulse rounded bg-line/60" />
      <div className="h-4 w-1/2 animate-pulse rounded bg-line/60" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="h-32 animate-pulse rounded-xl bg-line/60" />
        <div className="h-32 animate-pulse rounded-xl bg-line/60" />
        <div className="h-32 animate-pulse rounded-xl bg-line/60" />
      </div>
    </div>
  );
}
