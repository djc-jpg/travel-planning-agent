param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [int]$Timeout = 90,
    [switch]$SkipBuild
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

function Wait-BackendHealthy {
    param(
        [string]$Url,
        [int]$WaitSeconds
    )

    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri "$Url/health" -UseBasicParsing -TimeoutSec 5
            if ($resp.StatusCode -eq 200) {
                return
            }
        } catch {
            Start-Sleep -Seconds 2
            continue
        }
        Start-Sleep -Seconds 2
    }
    throw "Backend did not become healthy within $WaitSeconds seconds"
}

function Run-Phase {
    param(
        [string]$Name,
        [string]$EngineVersion,
        [string]$StrictRequiredFields
    )

    Write-Host ""
    Write-Host "=== Phase: $Name (ENGINE_VERSION=$EngineVersion, STRICT_REQUIRED_FIELDS=$StrictRequiredFields) ==="

    Set-EnvValue -Path $envFile -Key "ENGINE_VERSION" -Value $EngineVersion
    Set-EnvValue -Path $envFile -Key "STRICT_REQUIRED_FIELDS" -Value $StrictRequiredFields

    $baseArgs = @("compose", "-f", $composeFile, "--env-file", $envFile)
    $upArgs = $baseArgs + @("up", "-d", "--force-recreate", "backend")
    if (-not $SkipBuild) {
        $upArgs += "--build"
    }

    docker @upArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose up failed in phase $Name"
    }

    Wait-BackendHealthy -Url $BaseUrl -WaitSeconds $Timeout

    python -m app.deploy.preflight --env-file $envFile --base-url $BaseUrl --timeout $Timeout
    if ($LASTEXITCODE -ne 0) {
        throw "preflight failed in phase $Name"
    }

    python -m app.deploy.rollout_drill --env-file $envFile --base-url $BaseUrl --expect-engine $EngineVersion --expect-strict $StrictRequiredFields --timeout $Timeout
    if ($LASTEXITCODE -ne 0) {
        throw "rollout drill failed in phase $Name"
    }
}

try {
    Run-Phase -Name "baseline_v1" -EngineVersion "v1" -StrictRequiredFields "false"
    Run-Phase -Name "canary_v2_soft" -EngineVersion "v2" -StrictRequiredFields "false"
    Run-Phase -Name "canary_v2_strict" -EngineVersion "v2" -StrictRequiredFields "true"
    Run-Phase -Name "rollback_v1" -EngineVersion "v1" -StrictRequiredFields "false"
}
catch {
    Write-Error $_
    exit 1
}

Write-Host ""
Write-Host "Rollout + rollback drill completed."
exit 0

