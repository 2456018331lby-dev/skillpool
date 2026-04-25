$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Root "console-common.ps1")

Ensure-SkillPoolStateDir
$snapshot = Get-SkillPoolConsoleSnapshot

if (-not $snapshot.IsOnline -and $snapshot.HasPidFile -and -not $snapshot.IsManaged) {
    Remove-StaleSkillPoolPidFile
}

if (-not (Test-SkillPoolConsole)) {
    $process = Start-Process `
        -FilePath $script:Python `
        -ArgumentList @("skillpool.py", "serve", "--host", $script:HostName, "--port", "$script:Port") `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -RedirectStandardOutput $script:StdoutLog `
        -RedirectStandardError $script:StderrLog `
        -PassThru

    Set-Content -Path $script:PidPath -Value $process.Id -Encoding ASCII

    $started = Wait-SkillPoolConsoleHealth -ExpectedOnline $true -Attempts 20 -DelayMs 500
    if (-not $started) {
        try {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
        catch {
        }
        Remove-StaleSkillPoolPidFile
        throw "SkillPool console did not start at $($script:Url). Check logs: $($script:StdoutLog) and $($script:StderrLog)"
    }
}
elseif (-not $snapshot.IsManaged -and $snapshot.HasPidFile) {
    Remove-StaleSkillPoolPidFile
}

Start-Process $script:Url | Out-Null
Write-Output "SkillPool console ready: $($script:Url)"
Write-Output "PID file: $($script:PidPath)"
