# Claynext Studio — Fast Development Runner
# Launches studio in fast dev mode (no splash screen, debug engine).
param(
    [switch]$Studio = $false,
    [switch]$NoSplash = $true
)

$ErrorActionPreference = "Stop"

Write-Host "==> Ensuring Rust engine binary is ready..." -ForegroundColor Cyan
$env:CARGO_INCREMENTAL = "0"
cargo build --bin claynext-engine

$argsList = @()
if ($Studio) { $argsList += "--studio" }
if ($NoSplash) { $argsList += "--no-splash" }

Write-Host "==> Launching Claynext Studio..." -ForegroundColor Green
uv run main.py @argsList
