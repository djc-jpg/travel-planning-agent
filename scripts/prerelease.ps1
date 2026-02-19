param(
    [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$composeFile = "docker-compose.prerelease.yml"
$envFile = ".env.prerelease"

if (-not (Test-Path $composeFile)) {
    Write-Error "Missing $composeFile"
    exit 1
}

if (-not (Test-Path $envFile)) {
    Write-Error "Missing $envFile. Copy .env.prerelease.example to .env.prerelease first."
    exit 1
}

$baseArgs = @("compose", "-f", $composeFile, "--env-file", $envFile)

$upArgs = $baseArgs + @("up", "-d")
if (-not $SkipBuild) {
    $upArgs += "--build"
}

docker @upArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

docker @baseArgs ps
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

docker @($baseArgs + @("exec", "-T", "backend", "python", "-m", "app.deploy.preflight", "--base-url", "http://127.0.0.1:8000", "--timeout", "60"))
exit $LASTEXITCODE

