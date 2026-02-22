param(
    [string]$Db = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Db)) {
    python -m app.persistence.drill
} else {
    python -m app.persistence.drill --db $Db
}
