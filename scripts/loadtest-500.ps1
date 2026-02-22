param(
    [int]$Port = 18180,
    [int]$TotalRequests = 1000,
    [int]$Concurrency = 500,
    [int]$Workers = 4
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$env:ENGINE_VERSION = "v2"
$env:STRICT_REQUIRED_FIELDS = "true"
$env:ALLOW_UNAUTHENTICATED_API = "true"
$env:STRICT_EXTERNAL_DATA = "false"
$env:ROUTING_PROVIDER = "fixture"

# PowerShell native command passing strips JSON quotes unless doubled.
$payload = '{""message"":""Plan a short trip""}'

python -m tools.loadtest_http `
  --spawn-app `
  --spawn-port $Port `
  --spawn-workers $Workers `
  --base-url "http://127.0.0.1:$Port" `
  --total-requests $TotalRequests `
  --concurrency $Concurrency `
  --target-concurrency 500 `
  --target-success-rate 0.99 `
  --target-p95-ms 3000 `
  --request-payload $payload
