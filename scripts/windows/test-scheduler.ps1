[CmdletBinding()]
param(
    [string]$EvidencePath
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$Raw = & python (Join-Path $RepoRoot 'dragon\scheduler.py') --root $RepoRoot
if ($LASTEXITCODE -ne 0) { throw 'Unable to read scheduler configuration.' }
$Config = $Raw | ConvertFrom-Json
$Task = Get-ScheduledTask -TaskName $Config.task_name -ErrorAction Stop
$Matching = @(Get-ScheduledTask | Where-Object {
    $Candidate = $_
    @($Candidate.Actions | Where-Object {
        $_.Execute -eq $Config.python -and $_.Arguments -like ('*' + $Config.watchdog + '*')
    }).Count -gt 0
})
$EnabledMatching = @($Matching | Where-Object { $_.State -ne 'Disabled' })
if ($EnabledMatching.Count -ne 1) { throw ('Expected exactly one enabled DRAGON task; found ' + $EnabledMatching.Count + '.') }
if ($Task.Actions.Count -ne 1) { throw 'DRAGON scheduler must have exactly one action.' }
if ($Task.Actions[0].Execute -ne $Config.python) { throw 'Scheduled Python executable does not match configuration.' }
if ($Task.Actions[0].Arguments -notlike ('*' + $Config.watchdog + '*')) { throw 'Scheduled action does not invoke the DRAGON watchdog.' }
if ($Task.Triggers.Count -ne 1) { throw 'DRAGON scheduler must have exactly one trigger.' }
$ActualStart = ([datetime]$Task.Triggers[0].StartBoundary).ToString('HH:mm')
if ($ActualStart -ne $Config.start_time) { throw ('Scheduled start time mismatch: ' + $ActualStart) }
$ExpectedInterval = 'PT' + [string]$Config.interval_minutes + 'M'
if ([string]$Task.Triggers[0].Repetition.Interval -ne $ExpectedInterval) { throw 'Scheduled watchdog interval does not match configuration.' }
if ([string]$Task.Settings.MultipleInstances -ne 'IgnoreNew') { throw 'Scheduled task must ignore overlapping instances.' }
if (-not $Task.Settings.StartWhenAvailable) { throw 'Scheduled task must start when the machine becomes available.' }

if ([string]::IsNullOrWhiteSpace($EvidencePath)) {
    $EvidencePath = Join-Path $RepoRoot 'acceptance\machine\scheduler\inventory.json'
}
$EvidencePath = [System.IO.Path]::GetFullPath($EvidencePath)
$EvidenceDirectory = Split-Path -Parent $EvidencePath
New-Item -ItemType Directory -Path $EvidenceDirectory -Force | Out-Null
$Evidence = [ordered]@{
    schema_version = 5
    status = 'PASS'
    observed_at = [datetimeoffset]::Now.ToString('o')
    runtime_fingerprint = $Config.runtime_fingerprint
    source_git_revision = $Config.source_git_revision
    task_name = $Config.task_name
    matching_enabled_tasks = $EnabledMatching.Count
    action_count = $Task.Actions.Count
    trigger_count = $Task.Triggers.Count
    start_time = $ActualStart
    interval_minutes = $Config.interval_minutes
    multiple_instances = [string]$Task.Settings.MultipleInstances
    start_when_available = [bool]$Task.Settings.StartWhenAvailable
    watchdog = $Config.watchdog
}
$Temporary = Join-Path $EvidenceDirectory ('.inventory.' + [guid]::NewGuid().ToString('N') + '.tmp')
try {
    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Temporary, (($Evidence | ConvertTo-Json -Depth 6) + [Environment]::NewLine), $Utf8NoBom)
    Move-Item -LiteralPath $Temporary -Destination $EvidencePath -Force
} finally {
    Remove-Item -LiteralPath $Temporary -Force -ErrorAction SilentlyContinue
}
Write-Output ('Scheduler configuration PASS: ' + $Config.task_name)
Write-Output ('Machine evidence: ' + $EvidencePath)
