#!/usr/bin/env bash
# Container entry (ADR-0027): migrate, then run api and worker side by side.
# If either process exits, stop the other and exit non-zero so Docker restarts the container.
set -uo pipefail

: "${PORT:=8000}"
: "${HOST:=0.0.0.0}"
cd "${APP_DIR:-/app/backend}"

# The SQLite file and the storage root live on the volume.
db_path="${DATABASE_URL#sqlite:///}"
mkdir -p "$(dirname "$db_path")" "${STORAGE_ROOT:-./data/storage}"

echo "start: alembic upgrade head"
alembic upgrade head || { echo "start: migration failed" >&2; exit 1; }

uvicorn app.main:create_app --factory --host "$HOST" --port "$PORT" \
    --no-server-header --timeout-graceful-shutdown 20 &
api_pid=$!
python -m app.worker &
worker_pid=$!
echo "start: api pid $api_pid, worker pid $worker_pid"

stop() {
    kill -TERM "$api_pid" "$worker_pid" 2>/dev/null
    wait "$api_pid" "$worker_pid" 2>/dev/null
}
trap 'stop; exit 0' TERM INT

# Poll instead of `wait -n` so the script also runs on bash 3.2 (macOS).
while kill -0 "$api_pid" 2>/dev/null && kill -0 "$worker_pid" 2>/dev/null; do
    sleep 1
done
if kill -0 "$api_pid" 2>/dev/null; then
    wait "$worker_pid"; code=$?; who=worker
else
    wait "$api_pid"; code=$?; who=api
fi
echo "start: $who exited with $code, stopping the other" >&2
stop
exit "$((code == 0 ? 1 : code))"
