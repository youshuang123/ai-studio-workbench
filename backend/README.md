# 后端（阶段 2-1｜电商线最小闭环 · 单张主图端到端）

FastAPI + SQLAlchemy + SQLite。当前实现：项目、资产上传、单张主图生成（真实调用 T2I API）、预算守卫、SSE 进度、成本归集。

## 环境要求

- Python 3.12.x（本机 `/Users/youshuang/.local/bin/python3.12`）

## 启动（照着做）

```bash
cd backend
/Users/youshuang/.local/bin/python3.12 -m venv .venv   # 首次才需要
./.venv/bin/pip install -r requirements.txt            # 首次才需要
cp .env.example .env                                    # 首次才需要，然后填 Key
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

健康检查：<http://127.0.0.1:8000/api/health>

## 配置模型 Key（验收前）

编辑 `backend/.env`，把 Key 粘在 `MODEL_T2I_API_KEY=` 后面，然后重启服务。

- 不填 Key 时：接口 `/api/health` 里 `t2i_configured=false`，点生成会明确返回「未配置模型 API Key」。
- **不要**把 Key 写进代码、提交进 git、贴进对话或截图。
- 单价在 `MODEL_T2I_UNIT_PRICE`（元/张），按供应商实际账单核对。

## 验证

```bash
cd backend
MODEL_API_KEY="" ./.venv/bin/python -m pytest -q     # 41 条 mock 测试，离线可跑
```

从仓库根目录一次验完四项：

```bash
./verify.sh 阶段2-1
```

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查、Key 是否已配置、单价与预算 |
| POST | `/api/projects` | 创建项目 |
| GET | `/api/projects` | 项目列表（含资产数、任务数） |
| GET | `/api/projects/{id}` | 项目详情（含资产、最近任务） |
| GET | `/api/projects/{id}/usage` | 成本归集 |
| POST | `/api/projects/{id}/assets` | 上传商品图（multipart `file`） |
| GET | `/api/assets/{id}/file` | 读取图片 |
| GET | `/api/assets/{id}/download` | 下载原图 |
| POST | `/api/projects/{id}/generations` | 创建生成任务（202） |
| GET | `/api/jobs/{id}` | 任务详情 |
| GET | `/api/jobs/{id}/events` | **SSE**：`status → done` / `error` / `cancelled` |
| POST | `/api/jobs/{id}/retry` | 重试失败/超预算任务 |
| POST | `/api/jobs/{id}/cancel` | 取消任务：`queued` 直接取消；`running` 置 `cancel_requested`，执行器在检查点停止（已发出的请求可能已产生费用） |

错误结构统一为 `{"error": {"code": "...", "message": "..."}}`，不返回堆栈。

## 批量（阶段 2-2）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/projects/{id}/batches/validate` | 上传 CSV 只校验，返回逐行错误 |
| POST | `/api/projects/{id}/batches` | 校验并建批次（draft） |
| GET | `/api/projects/{id}/batches` | 最近 5 个批次（刷新后恢复用） |
| GET | `/api/batches/{id}` | 批次详情（含所有行） |
| POST | `/api/batches/{id}/trial` | 试跑第一条（同步等结果） |
| POST | `/api/batches/{id}/confirm` | 确认批量（必须先成功试跑） |
| POST | `/api/batches/{id}/resume` | 续跑（只跑未完成的） |
| POST | `/api/batches/{id}/cancel` | 停止，保留已完成 |
| POST | `/api/batches/{id}/items/{item_id}/retry` | 单条重试 |
| GET | `/api/batches/{id}/events` | **SSE**：progress / item / done / error |
| GET | `/api/batches/{id}/export` | 导出 ZIP（图片 + 清单 + 账单） |

CSV 表头固定：`sku_code, product_name, category, color, selling_points, image_file`
示例：`backend/examples/skus.csv`（20 行）

配置：`BATCH_CONCURRENCY`（默认 3）、`BATCH_BUDGET_CNY`（默认 10）、`BATCH_MAX_ROWS`（默认 200）

## 精修与质检（阶段 2-3）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/jobs/{id}/refine` | 精修（图生图，≈¥0.30/张）；草稿必须已成功 |
| POST | `/api/jobs/{id}/qa` | 重跑质检（VLM，≈¥0.003） |
| POST | `/api/batches/{id}/refine` | 批量精修（`{"item_ids":[...]}`，≤20 条，受 ¥5 预算约束） |

- 精修 job 通过 `stage=refined` + `refined_from` 关联草稿，**草稿永远保留**
- 精修成功后自动质检：`delta_e`（主色差，仅供参考）+ `qa_score` / `qa_detail`（VLM 五维）
- 五维：符合描述 / 无文字水印 / 商品完整 / 背景干净 / **颜色一致（传草稿图做双图对比）**
- 判定按平均分：≥2.5 pass、≥1.8 warn、否则 fail
- 配置：`MODEL_EDIT_*`、`MODEL_VLM_*`、`DELTA_E_THRESHOLD`、`BATCH_REFINE_BUDGET_CNY`

## 数据与状态

- 数据库：`backend/data/app.db`（SQLite，首次启动自动建表）
- 图片：`backend/data/assets/YYYY/MM/{uuid}.png`，同名 `.json` 存 prompt / 模型 / 成本
- 任务状态：`queued → running → succeeded | failed | over_budget | cancelled`
- 服务重启时，残留的 `running` 任务会被标记为 `failed(INTERRUPTED)`，可重试

## 已知限制（阶段 2-1 范围）

- 默认模型 FLUX.1-schnell 是**文生图**，看不到上传的商品图 → 生成结果不保证与原商品一致。一致性在 2-2 接入图生图模型后验收。
- 无登录（过渡档内部试用），接口只监听 127.0.0.1。
- 无批量、无 CSV 导入、无一致性量化、无 ZIP 导出（2-2）。
