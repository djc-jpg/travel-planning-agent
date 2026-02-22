param(
    [string]$Host = "127.0.0.1",
    [int]$BasePort = 18200
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

python -m app.deploy.dependency_fault_drill --host $Host --base-port $BasePort
