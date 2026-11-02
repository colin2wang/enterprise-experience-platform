# web-run.ps1 - Start the vite dev server (hot reload) at http://localhost:5173/web/.
# /v1 API calls are proxied to 127.0.0.1:8100 - start the Python backend yourself.
# Author: Wang, Bing <colin2wang@gmail.com>

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Push-Location "$root/frontend"
pnpm run dev
Pop-Location
