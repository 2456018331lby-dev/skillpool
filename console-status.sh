#!/usr/bin/env bash
# Show the current status of the SkillPool web console.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="$SCRIPT_DIR/state"
PID_FILE="$STATE_DIR/web-console.pid"
STDOUT_LOG="$STATE_DIR/web-console.out.log"
STDERR_LOG="$STATE_DIR/web-console.err.log"

HOST="127.0.0.1"
PORT=8765
URL="http://${HOST}:${PORT}/"

mkdir -p "$STATE_DIR"

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

# ── gather state ─────────────────────────────────────────────────────────────

online=false
health_check && online=true

managed=false
pid=""
command_line=""
pid_file_exists=false
reason=""

if [[ -f "$PID_FILE" ]]; then
    pid_file_exists=true
    pid=$(cat "$PID_FILE" 2>/dev/null | tr -d '[:space:]')
fi

if is_managed; then
    managed=true
    reason="ok"
    if [[ -r "/proc/$pid/cmdline" ]]; then
        command_line=$(tr '\0' ' ' < "/proc/$pid/cmdline")
    else
        command_line=$(ps -p "$pid" -o command= 2>/dev/null || echo "")
    fi
elif [[ "$pid_file_exists" == "true" && -z "$pid" ]]; then
    reason="pid file empty"
elif [[ "$pid_file_exists" == "true" ]] && ! kill -0 "$pid" 2>/dev/null; then
    reason="process not found"
elif [[ "$pid_file_exists" == "true" ]]; then
    reason="pid does not belong to skillpool serve"
fi

# ── determine overall status ─────────────────────────────────────────────────

status="stopped"
management="stopped"
message="SkillPool console is stopped."

if [[ "$managed" == "true" ]]; then
    status="running"
    management="managed"
    message="SkillPool console is running and managed by state/web-console.pid."
elif [[ "$online" == "true" ]]; then
    status="running"
    management="unmanaged"
    message="SkillPool console responds on HTTP, but the PID file is missing or stale."
elif [[ "$pid_file_exists" == "true" ]]; then
    management="stale"
    message="PID file exists but does not point to a live skillpool serve process."
fi

# ── output ───────────────────────────────────────────────────────────────────

echo "status: $status"
echo "management: $management"
echo "pid: ${pid:--}"
echo "url: $URL"
echo "pid_file: $PID_FILE"
echo "stdout_log: $STDOUT_LOG"
echo "stderr_log: $STDERR_LOG"
if [[ -n "$command_line" ]]; then
    echo "command: $command_line"
fi
echo "message: $message"
