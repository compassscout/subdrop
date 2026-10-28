# 打包 Windows 版本（免安装目录 + 单文件 exe）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
#
# 前置：Node.js（用于取静态 ffmpeg）、uv、Python 3.12

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "==> 准备构建环境" -ForegroundColor Cyan
uv venv .venv-build --python 3.12
$py = ".venv-build\Scripts\python.exe"
uv pip install --python $py "PySide6-Essentials>=6.6" "requests>=2.31" pyinstaller
uv pip install --python $py -e . --no-deps

if (-not (Test-Path "tools\ffmpeg.exe")) {
    Write-Host "==> 下载静态 ffmpeg（约 79MB）" -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path tools | Out-Null
    npm install ffmpeg-static --no-save --prefix .
    Copy-Item "node_modules\ffmpeg-static\ffmpeg.exe" "tools\ffmpeg.exe" -Force
}
Write-Host ("    ffmpeg: {0:N1} MB" -f ((Get-Item "tools\ffmpeg.exe").Length / 1MB))

$common = @(
    "--noconfirm", "--clean", "--windowed",
    "--icon", "assets\icon.ico",
    "--add-data", "assets;assets",
    "--add-binary", "tools\ffmpeg.exe;ffmpeg",
    "--paths", "src",
    "--exclude-module", "PySide6.QtQml",
    "--exclude-module", "PySide6.QtQuick",
    "--exclude-module", "PySide6.QtNetwork",
    "--exclude-module", "PySide6.QtWebEngineCore",
    "--exclude-module", "tkinter",
    "--exclude-module", "pytest"
)

Write-Host "==> 打包目录版" -ForegroundColor Cyan
& ".venv-build\Scripts\pyinstaller.exe" @common --name SubDrop --distpath dist --workpath build scripts\launcher.py

Write-Host "==> 打包单文件版" -ForegroundColor Cyan
& ".venv-build\Scripts\pyinstaller.exe" @common --onefile --name SubDrop --distpath dist-exe --workpath build-exe scripts\launcher.py

Write-Host "==> 压缩目录版" -ForegroundColor Cyan
Remove-Item "SubDrop-portable.zip" -ErrorAction SilentlyContinue
tar -a -c -f "SubDrop-portable.zip" -C dist SubDrop

Write-Host ""
Write-Host ("完成：dist-exe\SubDrop.exe  {0:N0} MB" -f ((Get-Item "dist-exe\SubDrop.exe").Length / 1MB)) -ForegroundColor Green
Write-Host ("      SubDrop-portable.zip  {0:N0} MB" -f ((Get-Item "SubDrop-portable.zip").Length / 1MB)) -ForegroundColor Green
