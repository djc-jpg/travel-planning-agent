param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 18310,
    [int]$Requests = 20,
    [string]$EnvFile = ".env.prerelease"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

python -m app.deploy.slo_drill `
  --host $BindHost `
  --port $Port `
  --requests $Requests `
  --profile realtime `
  --env-file $EnvFile `
  --output "eval/reports/slo_realtime_latest.json"
