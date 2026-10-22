import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-center">
      <p className="text-lg font-medium text-ink">这个页面不存在</p>
      <p className="text-sm text-smoke">可能是项目被删掉了，或者地址不对。</p>
      <Link href="/" className="mt-2 text-sm text-accent hover:underline">
        回到项目列表
      </Link>
    </div>
  );
}
