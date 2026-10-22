import type { Metadata } from "next";

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
      <body>
        <div className="mx-auto w-full max-w-6xl px-4 py-6 md:px-6 md:py-8">
          {children}
        </div>
      </body>
    </html>
  );
}
