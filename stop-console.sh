#!/usr/bin/env bash
# Stop a running SkillPool web console managed by open-console.sh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="$SCRIPT_DIR/state"
PID_FILE="$STATE_DIR/web-console.pid"

HOST="127.0.0.1"
PORT=8765
URL="http://${HOST}:${PORT}/"

# ── helpers ──────────────────────────────────────────────────────────────────

health_check() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 "$URL" 2>/dev/null || true)
    [[ "$code" == "200" ]]
}

is_managed() {
    [[ -f "$PID_FILE" ]] || return 1
    local pid
    pid=$(cat "$PID_FILE" 2>/dev/null | tr -d '[:space:]')
    [[ -n "$pid" ]] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    if [[ -r "/proc/$pid/cmdline" ]]; then
        tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q "skillpool.*serve"
    else
        ps -p "$pid" -o command= 2>/dev/null | grep -q "skillpool.*serve"
    fi
}

# ── main ─────────────────────────────────────────────────────────────────────

mkdir -p "$STATE_DIR"

if is_managed; then
    pid=$(cat "$PID_FILE" | tr -d '[:space:]')
    echo "Stopping SkillPool console (PID $pid) ..."
    kill "$pid" 2>/dev/null || true

    # Wait up to 6 seconds for the process to exit.
    for (( i=0; i<20; i++ )); do
        if ! health_check; then
            rm -f "$PID_FILE"
            echo "SkillPool console stopped: $URL"
            exit 0
        fi
        sleep 0.3
    done

    # Force-kill if it didn't exit gracefully.
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$PID_FILE"
    echo "Warning: had to force-kill PID $pid."
    if health_check; then
        echo "ERROR: Process stopped but HTTP health check still responds on $URL" >&2
        exit 1
    fi
    echo "SkillPool console stopped: $URL"
    exit 0
fi

# No managed process — clean up stale PID file if present.
if [[ -f "$PID_FILE" ]]; then
    rm -f "$PID_FILE"
    if health_check; then
        echo "SkillPool console is online but not managed by state/web-console.pid. Refusing to stop an unknown process." >&2
        exit 1
    fi
    echo "SkillPool console was already stopped. Cleaned stale PID file."
    exit 0
fi

if health_check; then
    echo "SkillPool console is online but not managed by state/web-console.pid. Refusing to stop an unknown process." >&2
    exit 1
fi

echo "SkillPool console is already stopped."
