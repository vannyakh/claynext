# Claynext Studio — Unified Build Script
# Builds native Rust engine crates and synchronizes Python dependencies.
$ErrorActionPreference = "Stop"

Write-Host "==> [1/3] Setting up build environment..." -ForegroundColor Cyan
$env:CARGO_INCREMENTAL = "0"

Write-Host "==> [2/3] Building native Rust engine and backends..." -ForegroundColor Cyan
cargo build --workspace --release

Write-Host "==> [3/3] Synchronizing Python environment..." -ForegroundColor Cyan
uv sync

Write-Host "==> Build completed successfully!" -ForegroundColor Green
