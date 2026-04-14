param(
  [int]$Port = 8000,
  [switch]$Reload
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
  Write-Error "Python venv not found at $pythonPath. Create venv and install requirements first."
}

function Test-PortFree {
  param([int]$CheckPort)

  $listener = $null
  try {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $CheckPort)
    $listener.Start()
    return $true
  } catch {
    return $false
  } finally {
    if ($listener) {
      $listener.Stop()
    }
  }
}

$selectedPort = $Port
if (-not (Test-PortFree -CheckPort $selectedPort)) {
  if ($Port -eq 8000 -and (Test-PortFree -CheckPort 8001)) {
    Write-Warning "Port 8000 is busy. Falling back to 8001."
    $selectedPort = 8001
  } else {
    Write-Error "Port $Port is not available."
  }
}

$args = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$selectedPort")
if ($Reload.IsPresent) {
  $args += "--reload"
}

Write-Host "Starting API: http://127.0.0.1:$selectedPort/api/v1/health" -ForegroundColor Cyan
Write-Host "Using interpreter: $pythonPath" -ForegroundColor DarkCyan
if ($selectedPort -ne 8000) {
  Write-Host "Update FE env: VITE_API_BASE_URL=http://127.0.0.1:$selectedPort/api/v1" -ForegroundColor Yellow
}

& $pythonPath @args
