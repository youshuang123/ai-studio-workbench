import type { Metadata } from "next";

import { TopNav } from "@/components/layout/TopNav";

import "./globals.css";

export const metadata: Metadata = {
  title: "AI Studio 工作台",
  description: "电商主图与短剧分镜的批量创作工作台",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen bg-canvas">
        <TopNav />
        <main className="mx-auto w-full max-w-[1200px] px-4 pb-16 pt-8 md:px-6 md:pt-10">
          {children}
        </main>
      </body>
    </html>
  );
}
