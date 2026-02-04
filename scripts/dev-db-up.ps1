<#
PowerShell helper to start local Postgres via docker compose on Windows.
Usage: .\scripts\dev-db-up.ps1
#>

param()

function Fail-Msg($msg) {
    Write-Host $msg -ForegroundColor Red
    exit 1
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail-Msg "Docker is not installed or not in PATH.\nPlease install Docker Desktop (WSL2) and ensure it's running."
}

Write-Host "Starting Postgres service via docker compose..."
docker compose up -d db

Write-Host "Done. Check 'docker ps' to confirm the container is running."

Write-Host "Run the following in PowerShell to continue:"
Write-Host "$env:DATABASE_URL = 'postgresql://postgres:postgres@localhost:5432/accountinox'"
Write-Host "npx prisma migrate dev --name init  # or 'npx prisma db push'"
Write-Host "npx prisma generate"
Write-Host "npm run build"
