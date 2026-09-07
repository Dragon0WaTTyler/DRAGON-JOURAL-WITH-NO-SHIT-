[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$Raw = & python (Join-Path $RepoRoot 'dragon\scheduler.py') --root $RepoRoot
if ($LASTEXITCODE -ne 0) { throw 'Unable to read scheduler configuration.' }
$Config = $Raw | ConvertFrom-Json
Start-ScheduledTask -TaskName $Config.task_name
Write-Output ('Started scheduled task: ' + $Config.task_name)
