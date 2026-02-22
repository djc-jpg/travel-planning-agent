param(
    [string]$ComposeFile = "docker-compose.yml",
    [string]$ObserveFile = "docker-compose.observability.yml"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

docker compose -f $ComposeFile -f $ObserveFile down
if ($LASTEXITCODE -ne 0) {
    throw "docker compose down failed with exit code $LASTEXITCODE"
}
Write-Host "Observability stack stopped."
