param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [int]$Timeout = 90
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

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

function Set-EnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value
    )

    $lines = [System.Collections.Generic.List[string]](Get-Content $Path)
    $pattern = "^\s*$([regex]::Escape($Key))\s*="
    $updated = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match $pattern) {
            $lines[$i] = "$Key=$Value"
            $updated = $true
            break
        }
    }
    if (-not $updated) {
        $lines.Add("$Key=$Value")
    }
    Set-Content -Path $Path -Value $lines -Encoding UTF8
}

Set-EnvValue -Path $envFile -Key "ENGINE_VERSION" -Value "v1"
Set-EnvValue -Path $envFile -Key "STRICT_REQUIRED_FIELDS" -Value "false"

docker compose -f $composeFile --env-file $envFile up -d --force-recreate backend
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

python -m app.deploy.preflight --env-file $envFile --base-url $BaseUrl --timeout $Timeout
exit $LASTEXITCODE

