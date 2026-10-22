import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // 阶段 4 部署用；本地 `next start` 会提示 mode 不匹配，属预期
  output: "standalone",
  // 关闭 Next.js 自动生成 AGENTS.md，避免污染仓库规则文件
  agentRules: false,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
