$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Root "console-common.ps1")

Ensure-SkillPoolStateDir
$snapshot = Get-SkillPoolConsoleSnapshot

if ($snapshot.IsManaged) {
    Stop-Process -Id $snapshot.Pid -Force
    $stopped = Wait-SkillPoolConsoleHealth -ExpectedOnline $false -Attempts 20 -DelayMs 300
    Remove-StaleSkillPoolPidFile
    if (-not $stopped) {
        throw "SkillPool console process stopped, but HTTP health check still responds on $($snapshot.Url)"
    }

    Write-Output "SkillPool console stopped: $($snapshot.Url)"
    exit 0
}

if ($snapshot.HasPidFile) {
    Remove-StaleSkillPoolPidFile
    if ($snapshot.IsOnline) {
        Write-Output "SkillPool console is online but not managed by state/web-console.pid. Refusing to stop an unknown process."
        exit 1
    }

    Write-Output "SkillPool console was already stopped. Cleaned stale PID file."
    exit 0
}

if ($snapshot.IsOnline) {
    Write-Output "SkillPool console is online but not managed by state/web-console.pid. Refusing to stop an unknown process."
    exit 1
}

Write-Output "SkillPool console is already stopped."
