$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Root "console-common.ps1")

Ensure-SkillPoolStateDir
$snapshot = Get-SkillPoolConsoleSnapshot

Write-Output ("status: {0}" -f $snapshot.Status)
Write-Output ("management: {0}" -f $snapshot.Management)
Write-Output ("pid: {0}" -f $(if ($snapshot.Pid) { $snapshot.Pid } else { "-" }))
Write-Output ("url: {0}" -f $snapshot.Url)
Write-Output ("pid_file: {0}" -f $snapshot.PidPath)
Write-Output ("stdout_log: {0}" -f $snapshot.StdoutLog)
Write-Output ("stderr_log: {0}" -f $snapshot.StderrLog)
if ($snapshot.CommandLine) {
    Write-Output ("command: {0}" -f $snapshot.CommandLine)
}
Write-Output ("message: {0}" -f $snapshot.Message)
