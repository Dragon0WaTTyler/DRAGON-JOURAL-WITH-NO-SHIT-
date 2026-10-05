param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$deployment = Join-Path $repoRoot 'infra/searxng'

# Compose interpolates this required field even for `down`; the value is never
# persisted and need not match the running container's startup value.
$bytes = New-Object byte[] 48
[System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$env:SEARXNG_SECRET = [Convert]::ToBase64String($bytes)
try {
    docker compose --project-directory $deployment -f (Join-Path $deployment 'compose.yaml') down
}
finally {
    Remove-Item Env:SEARXNG_SECRET -ErrorAction SilentlyContinue
}
