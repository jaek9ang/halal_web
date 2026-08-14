#!/usr/bin/env bash
#
# 백엔드 실행 (macOS / Linux).
#   ./scripts/run_backend.sh            # 기본 포트 8000
#   PORT=8080 ./scripts/run_backend.sh
#
# 운영 PMF 공유폴더는 Windows 전용이므로, 여기서는 환경변수로 로컬 경로를 주입한다.
# 이미 설정된 값은 덮어쓰지 않는다.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
PORT="${PORT:-8000}"

if [ ! -x "$PYTHON" ]; then
    echo ".venv가 없습니다. 먼저 실행하세요:" >&2
    echo "  python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt" >&2
    exit 1
fi

RUNTIME_DIR="$PROJECT_ROOT/.local_runtime"
mkdir -p "$RUNTIME_DIR/pmf_source" "$RUNTIME_DIR/원재료"

export PMF_SOURCE_DIR="${PMF_SOURCE_DIR:-$RUNTIME_DIR/pmf_source}"
export HALAL_DOC_ROOT="${HALAL_DOC_ROOT:-$RUNTIME_DIR/원재료}"
export HALAL_RAW_MATERIAL_ROOT="${HALAL_RAW_MATERIAL_ROOT:-$RUNTIME_DIR/원재료}"

cd "$BACKEND_DIR"

echo
echo "할랄인증관리 백엔드 실행"
echo "PMF_SOURCE_DIR: $PMF_SOURCE_DIR"
echo "주소: http://127.0.0.1:$PORT  (API 문서: /docs)"
echo

# 기동 전 import 사전검사 — 실패하면 uvicorn 로그에 묻히지 않고 여기서 멈춘다.
"$PYTHON" -c "import importlib; importlib.import_module('app.main'); print('app.main import OK')"

exec "$PYTHON" -m uvicorn app.main:app --reload --host 127.0.0.1 --port "$PORT"
