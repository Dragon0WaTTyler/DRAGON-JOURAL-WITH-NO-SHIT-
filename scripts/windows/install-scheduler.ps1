[CmdletBinding()]
param(
    [switch]$AllowBeforeCutover
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$Raw = & python (Join-Path $RepoRoot 'dragon\scheduler.py') --root $RepoRoot
if ($LASTEXITCODE -ne 0) { throw 'Unable to read scheduler configuration.' }
$Config = $Raw | ConvertFrom-Json
if (-not $Config.enabled -and -not $AllowBeforeCutover) {
    throw 'V5 scheduler is disabled in config/local-automation.yaml. Complete cutover or pass -AllowBeforeCutover for an explicit trial.'
}

$Arguments = '"' + $Config.watchdog + '"'
$Action = New-ScheduledTaskAction -Execute $Config.python -Argument $Arguments -WorkingDirectory $Config.working_directory
$At = [datetime]::ParseExact($Config.start_time, 'HH:mm', $null)
$Trigger = New-ScheduledTaskTrigger -Daily -At $At
$Trigger.Repetition.Interval = 'PT' + $Config.interval_minutes + 'M'
$Trigger.Repetition.Duration = 'P1D'
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 23)
Register-ScheduledTask -TaskName $Config.task_name -Action $Action -Trigger $Trigger -Settings $Settings -Description 'Single DRAGON V5 watchdog/orchestrator entry' -Force | Out-Null
Write-Output ('Installed one scheduled task: ' + $Config.task_name)
