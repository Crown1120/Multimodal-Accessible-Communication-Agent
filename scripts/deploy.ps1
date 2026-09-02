# Bridge 部署脚本（Docker Compose）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "构建并启动 Bridge 容器..." -ForegroundColor Cyan
Set-Location $root

# 检查 .env 文件
if (-not (Test-Path ".env")) {
    Write-Host "未找到 .env 文件，从模板创建..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "请编辑 .env 填入 API Key 后重新运行" -ForegroundColor Yellow
}

docker compose up -d --build

Write-Host ""
Write-Host "Bridge 部署完成" -ForegroundColor Green
Write-Host "前端: http://localhost:5173" -ForegroundColor Green
Write-Host "后端: http://localhost:8000/api/health" -ForegroundColor Green
Write-Host "日志: docker compose logs -f" -ForegroundColor Cyan
