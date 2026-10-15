# Claynext Studio — Packaging & Distribution Script
# Packages the PySide6 application with compiled Rust engine binaries.
$ErrorActionPreference = "Stop"

Write-Host "==> Compiling native Rust binaries for distribution..." -ForegroundColor Cyan
$env:CARGO_INCREMENTAL = "0"
cargo build --workspace --release

Write-Host "==> Building Python wheel package..." -ForegroundColor Cyan
uv build --wheel

Write-Host "==> Package build completed in dist/!" -ForegroundColor Green
