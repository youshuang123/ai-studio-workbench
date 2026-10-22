export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded-[20px] bg-hairline ${className}`.trim()}
    />
  );
}

export function ProjectCardSkeleton() {
  return (
    <div className="rounded-[24px] border border-hairline bg-canvas p-3">
      <Skeleton className="aspect-[4/3] w-full" />
      <Skeleton className="mt-4 h-4 w-2/3" />
      <Skeleton className="mt-2 h-3 w-1/3" />
    </div>
  );
}
