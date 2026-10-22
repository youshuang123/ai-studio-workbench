#!/usr/bin/env bash
# 重启恢复检查钩子（本项目专用，由 verify.sh 调用）。
# 契约（手册第十节）：
#   1) 退出码 0=通过，非 0=不通过；
#   2) 用临时 DATABASE_URL / DATA_DIR，不碰真实数据；
#   3) 清空模型 Key，不调真实模型；
#   4) 起服务 → 写数据 → 杀进程 → 再起 → 读回比对；
#   5) 端口被占不得杀别人的进程，直接非 0 退出；
#   6) 无论成败都停掉自己起的进程、删临时目录。
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/backend/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
PORT="${RESTART_CHECK_PORT:-8977}"
TMP="$(mktemp -d)"
export DATABASE_URL="sqlite:///$TMP/restart.db"
export DATA_DIR="$TMP/data"
export MODEL_T2I_API_KEY=""
BASE="http://127.0.0.1:$PORT"

start() {
  ( cd "$ROOT/backend" && exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" ) \
    >>"$TMP/server.log" 2>&1 &
  echo $! > "$TMP/pid"
  disown
}
stop() {
  [ -f "$TMP/pid" ] || return 0
  PID="$(cat "$TMP/pid")"
  kill "$PID" 2>/dev/null
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "$PID" 2>/dev/null || break
    sleep 0.3
  done
  kill -9 "$PID" 2>/dev/null
  rm -f "$TMP/pid"
}
wait_up() {
  for _ in $(seq 1 60); do
    curl -s -o /dev/null "$BASE/api/health" && return 0
    sleep 0.25
  done
  return 1
}
cleanup() { stop; rm -rf "$TMP"; }
trap cleanup EXIT

if curl -s -o /dev/null "$BASE/api/health"; then
  echo "端口 $PORT 已被占用，无法检查（不会杀别人的进程）。"
  exit 2
fi

# 准备一张真实 PNG 用于上传
"$PY" - "$TMP/seed.png" <<'PYEOF'
import sys
from PIL import Image
Image.new("RGB", (32, 32), (10, 120, 200)).save(sys.argv[1], format="PNG")
PYEOF
[ -f "$TMP/seed.png" ] || { echo "准备测试图片失败。"; exit 1; }

start
wait_up || { echo "服务首次启动失败："; cat "$TMP/server.log"; exit 1; }
echo "第一次启动：服务已就绪"

MARK="restart-check-$(date +%s)"
PROJECT_ID="$(
  curl -s -X POST "$BASE/api/projects" -H 'Content-Type: application/json' \
    -d "{\"name\":\"$MARK\"}" |
    "$PY" -c 'import sys,json; print(json.load(sys.stdin).get("id",""))'
)"
[ -n "$PROJECT_ID" ] || { echo "创建项目失败。"; cat "$TMP/server.log"; exit 1; }

ASSET_ID="$(
  curl -s -X POST "$BASE/api/projects/$PROJECT_ID/assets" \
    -F "file=@$TMP/seed.png;type=image/png;filename=seed.png" |
    "$PY" -c 'import sys,json; print(json.load(sys.stdin).get("id",""))'
)"
[ -n "$ASSET_ID" ] || { echo "上传资产失败。"; cat "$TMP/server.log"; exit 1; }
echo "第一次启动：已写入项目 id=$PROJECT_ID 资产 id=$ASSET_ID"

stop
echo "服务已停止。"

start
wait_up || { echo "服务第二次启动失败："; cat "$TMP/server.log"; exit 1; }

GOT_NAME="$(
  curl -s "$BASE/api/projects/$PROJECT_ID" |
    "$PY" -c 'import sys,json; print(json.load(sys.stdin).get("name",""))'
)"
HTTP_FILE="$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/assets/$ASSET_ID/file")"

if [ "$GOT_NAME" = "$MARK" ] && [ "$HTTP_FILE" = "200" ]; then
  echo "第二次启动：读回同一条项目记录，资产文件可访问（HTTP ${HTTP_FILE}）。重启恢复通过。"
  exit 0
fi
echo "第二次启动：读回失败（项目名得到：${GOT_NAME}，资产 HTTP ${HTTP_FILE}）。重启恢复不通过。"
exit 1
