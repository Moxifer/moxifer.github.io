param(
  [Parameter(Mandatory = $true)]
  [string]$Bucket,

  [string]$Key = "search-index.json"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$indexPath = Join-Path $repoRoot "search-index.json"

if (-not (Test-Path -LiteralPath $indexPath)) {
  throw "Missing search index file: $indexPath"
}

Push-Location $repoRoot
try {
  npx wrangler r2 object put "$Bucket/$Key" --file "$indexPath"
}
finally {
  Pop-Location
}
