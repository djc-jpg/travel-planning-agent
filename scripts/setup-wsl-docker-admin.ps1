param(
    [string]$Distro = "Ubuntu"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).
    IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Please run this script in an elevated PowerShell (Run as Administrator)."
    exit 1
}

Write-Host "Enabling WSL optional features..."
dism /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart | Out-Host
dism /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart | Out-Host

Write-Host "Installing WSL distro: $Distro"
wsl --install -d $Distro | Out-Host

Write-Host "Installing Docker Desktop..."
winget install --id Docker.DockerDesktop -e --accept-package-agreements --accept-source-agreements --silent | Out-Host

Write-Host ""
Write-Host "Post-checks:"
cmd /u /c "wsl --status > %TEMP%\wsl_status_post.txt 2>&1"
Get-Content "$env:TEMP\wsl_status_post.txt" -Encoding Unicode | Out-Host

$dockerBin = "C:\Program Files\Docker\Docker\resources\bin"
if (Test-Path $dockerBin) {
    $env:Path += ";$dockerBin"
}
try {
    docker --version | Out-Host
} catch {
    Write-Host "docker command not ready yet. You may need to reboot and launch Docker Desktop once."
}

