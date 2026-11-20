# Start Claude Code on free models through FreeLLMAPI (see README.md).
# Your normal `claude` command and settings are left untouched.
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path

$key = $env:FREELLMAPI_API_KEY
$keyFile = Join-Path $here '.key'
if (-not $key -and (Test-Path $keyFile)) { $key = (Get-Content $keyFile -Raw).Trim() }
if (-not $key) {
  Write-Host "No FreeLLMAPI key found. Put it in $keyFile or set FREELLMAPI_API_KEY." -ForegroundColor Red
  Write-Host "See $here\README.md, steps 3 and 4."
  exit 1
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  Write-Host 'Node.js 20 or newer is needed: https://nodejs.org' -ForegroundColor Red
  exit 1
}

# Desktop app listens on 31415, the Docker/server install on 3001.
$candidates = if ($env:FREELLMAPI_URL) { @($env:FREELLMAPI_URL) } else { @('http://localhost:31415', 'http://localhost:3001') }
$url = $null
foreach ($c in $candidates) {
  try {
    Invoke-WebRequest -Uri "$c/v1/models" -Headers @{ Authorization = "Bearer $key" } -TimeoutSec 5 -UseBasicParsing | Out-Null
    $url = $c; break
  } catch {}
}
if (-not $url) {
  Write-Host "FreeLLMAPI is not answering at $($candidates -join ' or '). Open the FreeLLMAPI app first." -ForegroundColor Red
  exit 1
}

$env:FREELLMAPI_URL = $url
$env:FREELLMAPI_API_KEY = $key
npx -y freellmapi@0.8.2 launch @args
exit $LASTEXITCODE
