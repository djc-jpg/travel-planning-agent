param(
    [string]$Host = "127.0.0.1",
    [int]$Port = 18300,
    [int]$Requests = 20,
    [ValidateSet("auto", "realtime", "degraded")]
    [string]$Profile = "degraded"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

python -m app.deploy.slo_drill `
  --host $Host `
  --port $Port `
  --requests $Requests `
  --profile $Profile
