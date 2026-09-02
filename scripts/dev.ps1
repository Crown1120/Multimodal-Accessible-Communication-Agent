# Bridge 开发脚本（Windows PowerShell）
# 启动后端与前端开发服务

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "启动后端..." -ForegroundColor Cyan
Start-Process -FilePath "python" -ArgumentList "-m","uvicorn","app.main:app","--reload","--port","8000" -WorkingDirectory "$root\backend"

Write-Host "启动前端..." -ForegroundColor Cyan
Start-Process -FilePath "npm.cmd" -ArgumentList "run","dev" -WorkingDirectory "$root\frontend"

Write-Host "后端: http://localhost:8000/api/health" -ForegroundColor Green
Write-Host "前端: http://localhost:5173" -ForegroundColor Green
