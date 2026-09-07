[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$Raw = & python (Join-Path $RepoRoot 'dragon\scheduler.py') --root $RepoRoot
if ($LASTEXITCODE -ne 0) { throw 'Unable to read scheduler configuration.' }
$Config = $Raw | ConvertFrom-Json
$Existing = Get-ScheduledTask -TaskName $Config.task_name -ErrorAction SilentlyContinue
if ($null -ne $Existing) {
    Unregister-ScheduledTask -TaskName $Config.task_name -Confirm:$false
    Write-Output ('Removed scheduled task: ' + $Config.task_name)
} else {
    Write-Output ('Scheduled task is not installed: ' + $Config.task_name)
}
