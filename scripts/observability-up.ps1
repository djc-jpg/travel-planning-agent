param(
    [string]$ComposeFile = "docker-compose.yml",
    [string]$ObserveFile = "docker-compose.observability.yml"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

docker compose -f $ComposeFile -f $ObserveFile up -d --build
if ($LASTEXITCODE -ne 0) {
    throw "docker compose up failed with exit code $LASTEXITCODE"
}
Write-Host "Observability stack started:"
Write-Host "- Prometheus: http://localhost:9090"
Write-Host "- Grafana: http://localhost:3001"
