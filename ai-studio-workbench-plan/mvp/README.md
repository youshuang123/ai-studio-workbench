# AI Studio MVP Skeleton (v0.2)

这是 PRD v0.2 对应的 **Step 5 骨架**：API-only、便宜优先、预算守卫、两条工作流。

> 当前是**可运行的骨架 + 离线 mock**，不是生产系统。真实供应商需要在 `studio/providers/http.py` 基础上接适配器。

## 能跑通什么

1. **电商素材工作流**：SKU CSV → 主图/场景图 → QA → manifest/report。
2. **短剧工作流**：剧本 → 分镜 JSON → 角色一致性包 → 关键帧 → 轻动效 HTML 预览。
3. **模型网关**：多供应商路由、单价上限、运行预算、缓存、重试、用量记录。
4. **成本测算**：¥0.10/张、¥1/min 目标校验。

## 快速开始

```sh
cd out/ai-studio-workbench-plan/mvp

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 可选：复制配置（不复制也能跑，内置 mock 默认配置）
cp config.example.yaml config.yaml

# 一条命令跑通两条工作流（离线 mock，不花钱）
.venv/bin/python -m studio demo
```

输出在 `data/runs/<run_id>/`：

```text
data/runs/ecom-.../
├── assets/           # SVG 占位图（mock）
├── manifest.json     # 资产、QA、成本、参数
└── report.md         # 人读报告

data/runs/drama-.../
├── assets/           # 关键帧 SVG
├── preview.html      # 关键帧 + CSS 轻动效预览
├── preview.json      # 镜头/时长/运动参数
├── manifest.json
└── report.md
```

## 常用命令

```sh
# 两条工作流 demo
.venv/bin/python -m studio demo

# 只跑电商
.venv/bin/python -m studio ecommerce --skus examples/skus.csv

# 只跑短剧
.venv/bin/python -m studio drama --script examples/script.md

# 成本测算
.venv/bin/python -m studio cost

# 查看某次运行摘要
.venv/bin/python -m studio inspect data/runs/<run_id>

# 限制单次运行预算
.venv/bin/python -m studio demo --max-cost 1.00
```

## 目录

```text
studio/
  config.py        # YAML + env 配置
  models.py        # Request/Result/ReferencePack/QAReport/Usage
  store.py         # 文件存储：runs/assets/cache/usage/logs
  gateway.py       # 路由、预算守卫、缓存、重试、计费
  consistency.py   # SKU/角色参考包与 prompt 构建
  qa.py            # 离线启发式 QA（生产替换为 VLM/API）
  light_motion.py  # 关键帧 + CSS 轻动效 HTML
  cost.py          # 成本公式
  providers/
    base.py        # Provider 接口 + 计价
    mock.py        # 离线 SVG/JSON provider
    http.py        # 通用 HTTP provider 模板
  workflows/
    ecommerce.py
    short_drama.py
  cli.py
examples/
  skus.csv
  script.md
tests/
```

## 接真实 API

1. 在 `config.yaml` 加一个 `type: http` 的 provider：

```yaml
providers:
  vendor_a:
    type: http
    base_url: https://api.vendor-a.example
    endpoint: /v1/images/generate
    api_key_env: VENDOR_A_API_KEY
    response_type: image_url
    timeout_seconds: 120
    models:
      image.cheap:
        unit: image
        price: 0.06
        tasks: [image.generate, image.edit]
```

2. 把 `routing.image.generate.standard` 改成 `[vendor_a/image.cheap]`。
3. 在 `.env` 填 `VENDOR_A_API_KEY`。
4. 如果供应商的请求/响应字段不同，继承 `HTTPProvider` 并覆盖 `build_payload` / `parse_response`，或在 `providers/` 下新增适配器。

> 真实项目至少接 2 家 T2I、1 家 LLM、1 家 VLM、1 家 TTS；视频 P1 再接 2 家。

## 成本守卫

`Gateway` 在调用前做两层检查：

- **单价上限**：标准图 > ¥0.10/张、标准视频 > ¥1/min 的供应商会被跳过；
- **运行总预算**：`budget.max_cost_per_run` 用尽后停止，保留已完成结果。

缓存命中时成本记 0；所有调用写入 `data/usage.jsonl`。

## 测试

```sh
.venv/bin/python -m pytest -q
```

覆盖：预算拦截、缓存命中、电商批量、短剧分镜/预览、成本公式。

## 当前边界

- Mock provider 只生成 SVG/JSON/HTML，不调用真实模型。
- 轻动效是 HTML 预览，不是 MP4；生产替换为 FFmpeg/时间线渲染。
- QA 是启发式，不是真实 VLM 审核。
- 一致性包是参考图 + prompt + seed；真实供应商是否支持 LoRA/多图参考，需要按 API 能力接入。
- 未实现：登录/租户/数据库/队列/真实计费/审核台；这些是 PRD 的 P0/P1 生产化工作。

## 下一步

1. 接 2 家真实 T2I API，跑 100 张金标图，校准 ¥0.10/张。
2. 接 1 家 LLM API，替换 mock 分镜。
3. 接 1 家 VLM API，替换启发式 QA。
4. 用 FFmpeg 替换 HTML 轻动效，输出 1080p MP4。
5. 加 SQLite/Postgres + 任务队列，支持断点续跑和多租户。
