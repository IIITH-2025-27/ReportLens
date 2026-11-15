#!/usr/bin/env bash
# Start ReportLens Lite (API on :8001, page on :5174) in the background, detached from the terminal that started
# it, so closing that terminal (or the editor) does not stop it. Logs and process ids go to web_lite/logs/.
#   ./start.sh            start (does nothing if it is already running)
#   ./stop.sh             stop
# Python: $PYTHON if set, else the first virtualenv found (web/backend, web_lite/backend, ../chart-claim verifier).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
LOGS="$HERE/logs"
mkdir -p "$LOGS"

alive() { [ -f "$LOGS/$1.pid" ] && kill -0 "$(cat "$LOGS/$1.pid")" 2>/dev/null; }

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in "$ROOT/web/backend/.venv/bin/python" "$HERE/backend/.venv/bin/python" \
           "$ROOT/../chart-claim verifier/.venv/bin/python"; do
    [ -x "$c" ] && PY="$c" && break
  done
fi
PY="${PY:-python3}"

# setsid: its own session, so it outlives whatever started this script. `exec` keeps one process id throughout:
# the one written to the .pid file is the server itself and leads its session, so stop.sh can stop it.
DETACH=(perl -MPOSIX -e 'POSIX::setsid(); exec @ARGV or die "exec: $!"' --)

if alive backend; then
  echo "API already running (pid $(cat "$LOGS/backend.pid"))"
else
  (cd "$HERE/backend" && PYTHONPATH="$ROOT" "$PY" -m alembic upgrade head >>"$LOGS/backend.log" 2>&1)
  (cd "$HERE/backend" && PYTHONPATH="$ROOT" HF_DEACTIVATE_ASYNC_LOAD=1 \
    exec "${DETACH[@]}" "$PY" -m uvicorn app.main:app --port 8001 </dev/null >>"$LOGS/backend.log" 2>&1) &
  echo $! >"$LOGS/backend.pid"
  echo "API starting (pid $(cat "$LOGS/backend.pid")), log: web_lite/logs/backend.log"
fi

if alive frontend; then
  echo "Page already running (pid $(cat "$LOGS/frontend.pid"))"
else
  (cd "$HERE/frontend" && exec "${DETACH[@]}" ./node_modules/.bin/vite --port 5174 --strictPort \
    </dev/null >>"$LOGS/frontend.log" 2>&1) &
  echo $! >"$LOGS/frontend.pid"
  echo "Page starting (pid $(cat "$LOGS/frontend.pid")), log: web_lite/logs/frontend.log"
fi

for _ in $(seq 1 60); do
  if curl -fs http://localhost:8001/api/health >/dev/null && curl -fs http://localhost:5174 >/dev/null; then
    echo "Ready: http://localhost:5174   (models: $(curl -fs http://localhost:8001/api/health))"
    exit 0
  fi
  sleep 1
done
echo "Not answering after 60 s; see web_lite/logs/backend.log and frontend.log" >&2
exit 1
