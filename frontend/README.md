# 前端（阶段 2-1）

Next.js 16 App Router + React 19 + Tailwind CSS 4 + TypeScript strict。

## 环境要求

- Node.js 22
- 后端已在本机 `http://127.0.0.1:8000` 运行（见 `backend/README.md`）

## 启动（照着做）

```bash
cd frontend
npm install          # 首次才需要

npm run dev          # 开发模式 → http://localhost:3000
# 或验收用生产构建
npm run build && npm run start
```

后端地址由 `next.config.ts` 的 `rewrites` 把 `/api/*` 同源代理过去，浏览器端不跨域。
要换后端地址：`cp .env.example .env.local` 并改 `BACKEND_URL`。

**`.env.local` 不要提交**，里面也不放任何模型 Key（Key 只存在后端 `.env`）。

## 验证

```bash
npm run lint         # eslint
npm run typecheck    # tsc --noEmit
npm test             # vitest（19 条）
npm run build        # 生产构建
```

或从仓库根目录一次验完四项：`./verify.sh 阶段2-1`

## 页面

| 路径 | 内容 |
| --- | --- |
| `/` | 项目列表：新建、卡片（素材数/任务数）、空状态、加载骨架、失败重试 |
| `/projects/[id]` | 项目详情：上传商品图 → 填商品信息 → 生成主图 → SSE 进度 → 预览 → 下载；底部历史 |

## 约定

- 金额一律由后端以「分」传入，前端只负责格式化成 `¥0.03`
- 未知任务状态走 `stale`（"状态未知"），不当成成功也不当成失败
- 后端错误 `{"error":{"code","message"}}` 由 `lib/api/client.ts` 归一化成 `ApiError`，界面只显示 `userMessage`
- 生成进度用 SSE：`status → done | error | cancelled`；`error` 事件与连接断开同名，靠是否带 `data` 区分
- **断线不猜结果**：连接断了先 `GET /api/jobs/{id}` 回查真实状态，仍在跑才重连（最多 2 次）
- **停止等待 ≠ 取消任务**：前者只关 SSE（任务继续），后者调后端真取消
- 不可重试的错误（预算不足 / 未配 Key）不显示重试按钮
- 资产图片直接由 `GET /api/assets/{id}/file` 提供，不经 next/image 优化管线
