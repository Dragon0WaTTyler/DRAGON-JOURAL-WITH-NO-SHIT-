[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$Raw = & python (Join-Path $RepoRoot 'dragon\scheduler.py') --root $RepoRoot
if ($LASTEXITCODE -ne 0) { throw 'Unable to read scheduler configuration.' }
$Config = $Raw | ConvertFrom-Json
$Task = Get-ScheduledTask -TaskName $Config.task_name -ErrorAction Stop
if ($Task.Actions.Count -ne 1) { throw 'DRAGON scheduler must have exactly one action.' }
if ($Task.Actions[0].Execute -ne $Config.python) { throw 'Scheduled Python executable does not match configuration.' }
if ($Task.Actions[0].Arguments -notlike ('*' + $Config.watchdog + '*')) { throw 'Scheduled action does not invoke the DRAGON watchdog.' }
Write-Output ('Scheduler configuration PASS: ' + $Config.task_name)
