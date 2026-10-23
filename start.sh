#!/usr/bin/env bash
# 一键启动（后端 8000 + 前端 3001）
# 用法：./start.sh          启动
#      ./start.sh status   看状态
#      ./stop.sh           停止
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3001}"
LOG_DIR="$ROOT/.logs"
mkdir -p "$LOG_DIR"

is_up() { curl -s -o /dev/null --max-time 2 "$1"; }

if [ "${1:-}" = "status" ]; then
  if is_up "http://127.0.0.1:$BACKEND_PORT/api/health"; then
    echo "后端  :$BACKEND_PORT  运行中"
  else
    echo "后端  :$BACKEND_PORT  未运行"
  fi
  if is_up "http://127.0.0.1:$FRONTEND_PORT/"; then
    echo "前端  :$FRONTEND_PORT  运行中"
  else
    echo "前端  :$FRONTEND_PORT  未运行"
  fi
  exit 0
fi

# ── 后端 ──
if is_up "http://127.0.0.1:$BACKEND_PORT/api/health"; then
  echo "后端已在 :$BACKEND_PORT 运行"
else
  echo "启动后端 :$BACKEND_PORT …"
  ( cd "$ROOT/backend" && nohup ./.venv/bin/python -m uvicorn app.main:app \
      --host 127.0.0.1 --port "$BACKEND_PORT" > "$LOG_DIR/backend.log" 2>&1 & )
  for _ in $(seq 1 40); do
    is_up "http://127.0.0.1:$BACKEND_PORT/api/health" && break
    sleep 0.5
  done
  if is_up "http://127.0.0.1:$BACKEND_PORT/api/health"; then
    echo "后端 OK"
  else
    echo "后端启动失败，日志：$LOG_DIR/backend.log"
    tail -20 "$LOG_DIR/backend.log"
    exit 1
  fi
fi

# ── 前端 ──
if is_up "http://127.0.0.1:$FRONTEND_PORT/"; then
  echo "前端已在 :$FRONTEND_PORT 运行"
else
  if [ ! -f "$ROOT/frontend/.next/BUILD_ID" ]; then
    echo "前端还没有生产构建，先跑一次 npm run build …"
    ( cd "$ROOT/frontend" && npm run build > "$LOG_DIR/frontend-build.log" 2>&1 ) || {
      echo "构建失败，日志：$LOG_DIR/frontend-build.log"
      tail -20 "$LOG_DIR/frontend-build.log"
      exit 1
    }
  fi
  echo "启动前端 :$FRONTEND_PORT …"
  ( cd "$ROOT/frontend" && nohup ./node_modules/.bin/next start --port "$FRONTEND_PORT" \
      > "$LOG_DIR/frontend.log" 2>&1 & )
  for _ in $(seq 1 40); do
    is_up "http://127.0.0.1:$FRONTEND_PORT/" && break
    sleep 0.5
  done
  if is_up "http://127.0.0.1:$FRONTEND_PORT/"; then
    echo "前端 OK"
  else
    echo "前端启动失败，日志：$LOG_DIR/frontend.log"
    tail -20 "$LOG_DIR/frontend.log"
    exit 1
  fi
fi

echo
echo "打开：http://127.0.0.1:$FRONTEND_PORT"
echo "API ：http://127.0.0.1:$BACKEND_PORT/api/health"
