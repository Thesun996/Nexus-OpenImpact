#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

if ! command -v npm >/dev/null 2>&1; then
  printf '未找到 npm；请先安装 Node.js 20.19 或更高版本。\n' >&2
  exit 1
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  printf '前端依赖尚未安装，请先执行：cd %s && npm install\n' "$FRONTEND_DIR" >&2
  exit 1
fi

cd "$FRONTEND_DIR"
export OPENIMPACT_API_TARGET="${OPENIMPACT_API_TARGET:-http://127.0.0.1:8000}"
exec npm run dev -- --host 127.0.0.1 --port "${OPENIMPACT_FRONTEND_PORT:-5173}" "$@"
