#!/usr/bin/env bash
# Stop ReportLens Lite started by start.sh. A run in progress is marked failed at the next start and can be re-run.
set -uo pipefail
LOGS="$(cd "$(dirname "$0")" && pwd)/logs"
for name in backend frontend; do
  f="$LOGS/$name.pid"
  if [ -f "$f" ] && kill -0 "$(cat "$f")" 2>/dev/null; then
    pid="$(cat "$f")"
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid"     # the whole session start.sh created
    for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
    kill -0 "$pid" 2>/dev/null && kill -KILL -- "-$pid" 2>/dev/null
    echo "stopped $name (pid $pid)"
  else
    echo "$name was not running"
  fi
  rm -f "$f"
done
