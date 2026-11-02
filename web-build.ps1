# web-build.ps1 - Build the Vue frontend into web/ for uvicorn static serving.
# Author: Wang, Bing <colin2wang@gmail.com>

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Push-Location "$root/frontend"
pnpm build
$code = $LASTEXITCODE
Pop-Location

if ($code -ne 0) { Write-Error "Frontend build failed." }
Write-Host "==> Build finished. Output: $root\web (served at /web by the backend)" -ForegroundColor Green
