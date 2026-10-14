#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv-mac/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  printf '找不到项目虚拟环境：%s\n' "$PYTHON_BIN" >&2
  printf '请先在仓库根目录创建并安装环境，再运行此脚本。\n' >&2
  exit 1
fi

cd "$ROOT_DIR"
export OPENIMPACT_LLM_PROVIDER="${OPENIMPACT_LLM_PROVIDER:-rule}"
exec "$PYTHON_BIN" -m uvicorn openimpact.api:app --host 127.0.0.1 --port 8000 "$@"
