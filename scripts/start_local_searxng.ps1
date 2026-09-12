param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$deployment = Join-Path $repoRoot 'infra/searxng'

# The SearXNG secret is process-local and never written to the repository or
# emitted by this script.  A fresh value is safe when Compose recreates the
# container; an existing container keeps its already configured value.
$bytes = New-Object byte[] 48
[System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$env:SEARXNG_SECRET = [Convert]::ToBase64String($bytes)
try {
    docker compose --project-directory $deployment -f (Join-Path $deployment 'compose.yaml') up -d --wait
}
finally {
    Remove-Item Env:SEARXNG_SECRET -ErrorAction SilentlyContinue
}
