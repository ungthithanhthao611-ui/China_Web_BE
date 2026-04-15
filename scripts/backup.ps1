param(
  [string]$BackupRoot = "backups",
  [string]$DatabaseUrl = $env:DATABASE_URL,
  [string]$UploadDir = $env:UPLOAD_DIR
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $DatabaseUrl) {
  $envFile = Join-Path $projectRoot ".env"
  if (Test-Path -LiteralPath $envFile) {
    $databaseLine = Get-Content -LiteralPath $envFile | Where-Object { $_ -match "^DATABASE_URL=" } | Select-Object -First 1
    if ($databaseLine) {
      $DatabaseUrl = $databaseLine.Substring("DATABASE_URL=".Length).Trim()
    }
  }
}

if (-not $UploadDir) {
  $UploadDir = Join-Path $projectRoot "uploads"
} elseif (-not [System.IO.Path]::IsPathRooted($UploadDir)) {
  $UploadDir = Join-Path $projectRoot $UploadDir
}

if (-not [System.IO.Path]::IsPathRooted($BackupRoot)) {
  $BackupRoot = Join-Path $projectRoot $BackupRoot
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$targetDir = Join-Path $BackupRoot $timestamp
New-Item -ItemType Directory -Path $targetDir -Force | Out-Null

if ($DatabaseUrl -like "sqlite:///*") {
  $sqlitePath = $DatabaseUrl.Replace("sqlite:///", "")
  if (-not [System.IO.Path]::IsPathRooted($sqlitePath)) {
    $sqlitePath = Join-Path $projectRoot $sqlitePath
  }
  if (Test-Path -LiteralPath $sqlitePath) {
    Copy-Item -LiteralPath $sqlitePath -Destination (Join-Path $targetDir "database.sqlite3")
  } else {
    Write-Warning "SQLite database not found: $sqlitePath"
  }
} elseif ($DatabaseUrl -like "postgresql*") {
  $pgDump = Get-Command pg_dump -ErrorAction SilentlyContinue
  if (-not $pgDump) {
    Write-Warning "pg_dump was not found. Install PostgreSQL client tools to back up the database."
  } else {
    & $pgDump.Source $DatabaseUrl -Fc -f (Join-Path $targetDir "database.dump")
  }
} else {
  Write-Warning "Unsupported or missing DATABASE_URL. Database backup was skipped."
}

if (Test-Path -LiteralPath $UploadDir) {
  $uploadItems = Get-ChildItem -LiteralPath $UploadDir -Force
  if ($uploadItems) {
    Compress-Archive -Path (Join-Path $UploadDir "*") -DestinationPath (Join-Path $targetDir "uploads.zip") -Force
  } else {
    Write-Warning "Upload directory is empty: $UploadDir"
  }
} else {
  Write-Warning "Upload directory not found: $UploadDir"
}

Write-Host "Backup written to $targetDir"
