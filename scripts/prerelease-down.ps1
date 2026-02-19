Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$composeFile = "docker-compose.prerelease.yml"
$envFile = ".env.prerelease"

if (-not (Test-Path $composeFile)) {
    Write-Error "Missing $composeFile"
    exit 1
}

$args = @("compose", "-f", $composeFile)
if (Test-Path $envFile) {
    $args += @("--env-file", $envFile)
}
$args += @("down")

docker @args
exit $LASTEXITCODE

