#!/usr/bin/env bash
# 停止前后端（只停本项目占用的端口）
set -u
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3001}"

stop_port() {
  local port="$1" name="$2"
  local pids
  pids="$(lsof -ti :"$port" 2>/dev/null || true)"
  if [ -z "$pids" ]; then
    echo "$name :$port 未运行"
    return 0
  fi
  echo "停止 $name :$port （PID: $pids）"
  # shellcheck disable=SC2086
  kill $pids 2>/dev/null || true
  for _ in $(seq 1 20); do
    lsof -ti :"$port" >/dev/null 2>&1 || break
    sleep 0.3
  done
  pids="$(lsof -ti :"$port" 2>/dev/null || true)"
  [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
  echo "$name 已停止"
}

stop_port "$FRONTEND_PORT" "前端"
stop_port "$BACKEND_PORT" "后端"
