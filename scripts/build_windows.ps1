# 打包成 Windows 免安装目录（onedir，比 onefile 少被杀软误报）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "==> 安装依赖" -ForegroundColor Cyan
uv sync --extra dev

Write-Host "==> 安装 PyInstaller" -ForegroundColor Cyan
uv pip install pyinstaller

Write-Host "==> 清理旧产物" -ForegroundColor Cyan
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

Write-Host "==> 打包" -ForegroundColor Cyan
uv run pyinstaller `
    --noconfirm `
    --windowed `
    --name SubDrop `
    --add-data "assets;assets" `
    --icon "assets/icon.ico" `
    --collect-submodules subdrop `
    src/subdrop/__main__.py

Write-Host "==> 完成：dist\SubDrop\SubDrop.exe" -ForegroundColor Green
Write-Host "提示：把 ffmpeg.exe / ffprobe.exe 放进 dist\SubDrop\ 即可离线使用（也可依赖系统 PATH）"
