#!/bin/bash

set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8011}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

check_port() {
  local port="$1"
  local name="$2"

  if command -v lsof >/dev/null 2>&1; then
    if lsof -i :"$port" >/dev/null 2>&1; then
      echo "Port $port is already in use. Stop the existing process before starting $name."
      lsof -i :"$port"
      exit 1
    fi
    return
  fi

  if command -v ss >/dev/null 2>&1; then
    if ss -ltn "( sport = :$port )" | tail -n +2 | grep -q .; then
      echo "Port $port is already in use. Stop the existing process before starting $name."
      ss -ltn "( sport = :$port )"
      exit 1
    fi
    return
  fi

  if command -v netstat >/dev/null 2>&1; then
    if netstat -an 2>/dev/null | grep -E "[\.:]$port[[:space:]]" | grep -qi listen; then
      echo "Port $port is already in use. Stop the existing process before starting $name."
      netstat -an 2>/dev/null | grep -E "[\.:]$port[[:space:]]"
      exit 1
    fi
  fi
}

resolve_python() {
  if command -v python3.11 >/dev/null 2>&1; then
    echo "python3.11"
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    local version
    version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    if [ "$version" = "3.11" ]; then
      echo "python3"
      return
    fi
  fi

  if command -v python >/dev/null 2>&1; then
    local version
    version="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    if [ "$version" = "3.11" ]; then
      echo "python"
      return
    fi
  fi

  if command -v py >/dev/null 2>&1; then
    if py -3.11 -c "import sys" >/dev/null 2>&1; then
      echo "py -3.11"
      return
    fi
  fi

  echo ""
}

check_port "$BACKEND_PORT" "backend"
check_port "$FRONTEND_PORT" "frontend"

PYTHON_CMD="$(resolve_python)"
if [ -z "$PYTHON_CMD" ]; then
  echo "Python 3.11 is required for local backend development."
  exit 1
fi

echo "Using Python command: $PYTHON_CMD"
echo "Starting backend on http://$BACKEND_HOST:$BACKEND_PORT"
cd "$PROJECT_ROOT/backend"
$PYTHON_CMD -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" &
BACKEND_PID=$!

cleanup() {
  if kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

echo "Starting frontend on http://127.0.0.1:$FRONTEND_PORT"
cd "$PROJECT_ROOT/frontend"
npm start
