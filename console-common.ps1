$script:Port = 8765
$script:HostName = "127.0.0.1"
$script:Url = "http://{0}:{1}/" -f $script:HostName, $script:Port
$script:Python = "python"
$script:StateDir = Join-Path $Root "state"
$script:PidPath = Join-Path $script:StateDir "web-console.pid"
$script:StdoutLog = Join-Path $script:StateDir "web-console.out.log"
$script:StderrLog = Join-Path $script:StateDir "web-console.err.log"

function Ensure-SkillPoolStateDir {
    if (-not (Test-Path $script:StateDir)) {
        New-Item -ItemType Directory -Path $script:StateDir | Out-Null
    }
}

function Test-SkillPoolConsole {
    try {
        $response = Invoke-WebRequest -Uri $script:Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

function Wait-SkillPoolConsoleHealth {
    param(
        [Parameter(Mandatory = $true)]
        [bool]$ExpectedOnline,
        [int]$Attempts = 20,
        [int]$DelayMs = 500
    )

    for ($i = 0; $i -lt $Attempts; $i++) {
        if ((Test-SkillPoolConsole) -eq $ExpectedOnline) {
            return $true
        }
        Start-Sleep -Milliseconds $DelayMs
    }

    return $false
}

function Remove-StaleSkillPoolPidFile {
    if (Test-Path $script:PidPath) {
        Remove-Item -LiteralPath $script:PidPath -Force
    }
}

function Get-ManagedSkillPoolProcessInfo {
    Ensure-SkillPoolStateDir

    if (-not (Test-Path $script:PidPath)) {
        return @{
            HasPidFile = $false
            IsValid = $false
            Pid = $null
            Reason = "pid file missing"
            CommandLine = $null
        }
    }

    $raw = (Get-Content -LiteralPath $script:PidPath -Raw -ErrorAction SilentlyContinue).Trim()
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return @{
            HasPidFile = $true
            IsValid = $false
            Pid = $null
            Reason = "pid file empty"
            CommandLine = $null
        }
    }

    $pidValue = 0
    if (-not [int]::TryParse($raw, [ref]$pidValue)) {
        return @{
            HasPidFile = $true
            IsValid = $false
            Pid = $null
            Reason = "pid file invalid"
            CommandLine = $null
        }
    }

    $process = Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $pidValue) -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return @{
            HasPidFile = $true
            IsValid = $false
            Pid = $pidValue
            Reason = "process not found"
            CommandLine = $null
        }
    }

    $commandLine = [string]$process.CommandLine
    $matchesSkillPool = $commandLine -match "skillpool\.py" -and $commandLine -match "(^|\s)serve($|\s)"
    if (-not $matchesSkillPool) {
        return @{
            HasPidFile = $true
            IsValid = $false
            Pid = $pidValue
            Reason = "pid does not belong to skillpool.py serve"
            CommandLine = $commandLine
        }
    }

    return @{
        HasPidFile = $true
        IsValid = $true
        Pid = $pidValue
        Reason = "ok"
        CommandLine = $commandLine
    }
}

function Get-SkillPoolConsoleSnapshot {
    $processInfo = Get-ManagedSkillPoolProcessInfo
    $online = Test-SkillPoolConsole

    $management = "stopped"
    $message = "SkillPool console is stopped."
    if ($processInfo.IsValid) {
        $management = "managed"
        $message = "SkillPool console is running and managed by state/web-console.pid."
    }
    elseif ($online) {
        $management = "unmanaged"
        $message = "SkillPool console responds on HTTP, but the PID file is missing or stale."
    }
    elseif ($processInfo.HasPidFile) {
        $management = "stale"
        $message = "PID file exists but does not point to a live skillpool.py serve process."
    }

    return @{
        Status = if ($online) { "running" } else { "stopped" }
        Management = $management
        Pid = $processInfo.Pid
        CommandLine = $processInfo.CommandLine
        Reason = $processInfo.Reason
        Url = $script:Url
        PidPath = $script:PidPath
        StdoutLog = $script:StdoutLog
        StderrLog = $script:StderrLog
        Message = $message
        IsManaged = $processInfo.IsValid
        HasPidFile = $processInfo.HasPidFile
        IsOnline = $online
    }
}
