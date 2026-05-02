#!/usr/bin/env bash
# Start the SkillPool web console in the background and open the browser.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="$SCRIPT_DIR/state"
PID_FILE="$STATE_DIR/web-console.pid"
STDOUT_LOG="$STATE_DIR/web-console.out.log"
STDERR_LOG="$STATE_DIR/web-console.err.log"

HOST="127.0.0.1"
PORT=8765
URL="http://${HOST}:${PORT}/"

# ── helpers ──────────────────────────────────────────────────────────────────

health_check() {
    # Returns 0 if the server responds with HTTP 200, 1 otherwise.
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 "$URL" 2>/dev/null || true)
    [[ "$code" == "200" ]]
}

is_managed() {
    # Returns 0 if the PID file exists, the process is alive, and its
    # command line matches "skillpool" + "serve".
    [[ -f "$PID_FILE" ]] || return 1
    local pid
    pid=$(cat "$PID_FILE" 2>/dev/null | tr -d '[:space:]')
    [[ -n "$pid" ]] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    # On Linux, check /proc/<pid>/cmdline; on macOS fall back to ps.
    if [[ -r "/proc/$pid/cmdline" ]]; then
        tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q "skillpool.*serve"
    else
        ps -p "$pid" -o command= 2>/dev/null | grep -q "skillpool.*serve"
    fi
}

open_browser() {
    # Cross-platform browser opener.
    if command -v xdg-open &>/dev/null; then
        xdg-open "$URL" &>/dev/null &
    elif command -v open &>/dev/null; then
        open "$URL"
    else
        echo "Open manually: $URL"
    fi
}

# ── main ─────────────────────────────────────────────────────────────────────

mkdir -p "$STATE_DIR"

# Clean stale PID file if process is no longer managed.
if [[ -f "$PID_FILE" ]] && ! is_managed; then
    rm -f "$PID_FILE"
fi

if is_managed; then
    echo "SkillPool console is already running (PID $(cat "$PID_FILE" | tr -d '[:space:]'))."
    open_browser
    exit 0
fi

echo "Starting SkillPool console on $URL ..."

nohup python3 -m skillpool_app.cli serve \
    --host "$HOST" --port "$PORT" \
    >>"$STDOUT_LOG" 2>>"$STDERR_LOG" &
child_pid=$!

echo "$child_pid" > "$PID_FILE"

# Wait up to 10 seconds for the server to become healthy.
attempts=20
for (( i=0; i<attempts; i++ )); do
    if health_check; then
        echo "SkillPool console ready (PID $child_pid): $URL"
        open_browser
        exit 0
    fi
    sleep 0.5
done

# If we get here the server didn't come up — kill and clean up.
kill "$child_pid" 2>/dev/null || true
rm -f "$PID_FILE"
echo "ERROR: SkillPool console did not start at $URL." >&2
echo "Check logs: $STDOUT_LOG and $STDERR_LOG" >&2
exit 1
