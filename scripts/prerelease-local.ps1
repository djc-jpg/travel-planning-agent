param(
    [int]$Port = 8016,
    [int]$Timeout = 90,
    [switch]$StrictRedis
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not (Test-Path (Join-Path $projectRoot ".env.prerelease"))) {
    Write-Error "Missing .env.prerelease. Copy .env.prerelease.example to .env.prerelease first."
    exit 1
}

Set-Location $projectRoot

if (-not $StrictRedis) {
    # Local prerelease mode allows memory fallback when Redis is unavailable.
    $env:ALLOW_INMEMORY_BACKEND = "true"
}

python -m app.deploy.preflight --env-file .env.prerelease --skip-smoke
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$job = Start-Job -ScriptBlock {
    param($port, $root, $allowInMemory)
    Set-Location $root
    if ($allowInMemory) {
        $env:ALLOW_INMEMORY_BACKEND = "true"
    }
    python -c "from dotenv import load_dotenv; load_dotenv('.env.prerelease'); import uvicorn; uvicorn.run('app.api.main:app', host='127.0.0.1', port=$port, log_level='warning')"
} -ArgumentList $Port, $projectRoot, (-not $StrictRedis)

try {
    Start-Sleep -Seconds 5
    python -m app.deploy.preflight --env-file .env.prerelease --base-url "http://127.0.0.1:$Port" --timeout $Timeout
    exit $LASTEXITCODE
}
finally {
    Stop-Job $job -ErrorAction SilentlyContinue | Out-Null
    Remove-Job $job -Force -ErrorAction SilentlyContinue
}
