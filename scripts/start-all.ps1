# Bridge 一键启动 + 进程守护脚本
# 用法：
#   .\scripts\start-all.ps1          # 启动前后端（带崩溃自动重启）
#   .\scripts\start-all.ps1 -Stop    # 停止所有进程
#   .\scripts\start-all.ps1 -Status  # 查看运行状态

param(
    [switch]$Stop,
    [switch]$Status
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot "backend"
$FrontendDir = Join-Path $ProjectRoot "frontend"
$BackendPort = 8000
$FrontendPort = 5173
$PidFile = Join-Path $ProjectRoot ".bridge-pids.json"

function Get-RunningPids {
    if (Test-Path $PidFile) {
        $data = Get-Content $PidFile -Raw | ConvertFrom-Json
        $result = @{}
        foreach ($key in $data.PSObject.Properties.Name) {
            $pid = $data.$key
            if ($pid -and (Get-Process -Id $pid -ErrorAction SilentlyContinue)) {
                $result[$key] = $pid
            }
        }
        return $result
    }
    return @{}
}

function Save-Pids($pids) {
    $pids | ConvertTo-Json | Set-Content $PidFile -Encoding UTF8
}

function Stop-All {
    $pids = Get-RunningPids
    foreach ($key in $pids.Keys) {
        $pid = $pids[$key]
        Write-Host "Stopping $key (PID $pid)..." -ForegroundColor Yellow
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    }
    # 清理端口占用
    foreach ($port in @($BackendPort, $FrontendPort)) {
        Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | ForEach-Object {
            Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
    if (Test-Path $PidFile) { Remove-Item $PidFile -Force }
    Write-Host "All processes stopped." -ForegroundColor Green
}

function Show-Status {
    $pids = Get-RunningPids
    $backendUp = $null -ne (Get-NetTCPConnection -LocalPort $BackendPort -ErrorAction SilentlyContinue)
    $frontendUp = $null -ne (Get-NetTCPConnection -LocalPort $FrontendPort -ErrorAction SilentlyContinue)
    Write-Host "=== Bridge Service Status ===" -ForegroundColor Cyan
    Write-Host "Backend  (port $BackendPort): $(if ($backendUp) {'UP'} else {'DOWN'})"
    Write-Host "Frontend (port $FrontendPort): $(if ($frontendUp) {'UP'} else {'DOWN'})"
    if ($pids.Count -gt 0) {
        Write-Host "Watched PIDs: $($pids | ConvertTo-Json -Compress)"
    }
}

if ($Stop) { Stop-All; exit 0 }
if ($Status) { Show-Status; exit 0 }

# 检查是否已在运行
$existing = Get-RunningPids
if ($existing.Count -gt 0) {
    Write-Host "Bridge is already running. Use -Stop to stop first, or -Status to check." -ForegroundColor Yellow
    Show-Status
    exit 0
}

Write-Host "=== Starting Bridge Services ===" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"

# 确保日志目录存在
$logDir = Join-Path $BackendDir "logs"
if (!(Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

# 启动后端（隐藏窗口，重定向日志）
$backendLog = Join-Path $logDir "run_8000.log"
$backendErr = Join-Path $logDir "run_8000_err.log"
$pythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"
if (!(Test-Path $pythonExe)) {
    Write-Host "ERROR: Python venv not found at $pythonExe" -ForegroundColor Red
    Write-Host "Please run: cd backend && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

$backendProc = Start-Process -FilePath $pythonExe `
    -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","$BackendPort" `
    -WorkingDirectory $BackendDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $backendLog `
    -RedirectStandardError $backendErr `
    -PassThru
Write-Host "Backend  started (PID $($backendProc.Id), log: $backendLog)" -ForegroundColor Green

# 启动前端
$frontendLog = Join-Path $FrontendDir "vite-dev.log"
$frontendErr = Join-Path $FrontendDir "vite-dev-err.log"
$frontendProc = Start-Process -FilePath "npm.cmd" `
    -ArgumentList "run","dev" `
    -WorkingDirectory $FrontendDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $frontendLog `
    -RedirectStandardError $frontendErr `
    -PassThru
Write-Host "Frontend started (PID $($frontendProc.Id), log: $frontendLog)" -ForegroundColor Green

# 保存 PID
Save-Pids @{ backend = $backendProc.Id; frontend = $frontendProc.Id }

# 等待服务就绪
Write-Host "Waiting for services to be ready..." -ForegroundColor Cyan
$ready = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 1
    $backendOk = $null -ne (Get-NetTCPConnection -LocalPort $BackendPort -ErrorAction SilentlyContinue)
    $frontendOk = $null -ne (Get-NetTCPConnection -LocalPort $FrontendPort -ErrorAction SilentlyContinue)
    if ($backendOk -and $frontendOk) {
        $ready = $true
        break
    }
    Write-Host "  [$($i+1)/20] backend=$(if ($backendOk) {'UP'} else {'...'}) frontend=$(if ($frontendOk) {'UP'} else {'...'})"
}

if ($ready) {
    Write-Host ""
    Write-Host "=== Bridge is Ready! ===" -ForegroundColor Green
    Write-Host "  Frontend: http://localhost:$FrontendPort"
    Write-Host "  Backend:  http://127.0.0.1:$BackendPort/api/health"
    Write-Host ""
    Write-Host "To stop:  .\scripts\start-all.ps1 -Stop"
    Write-Host "To check: .\scripts\start-all.ps1 -Status"
    Write-Host ""
    Write-Host "Process watcher: if a process crashes, run this script again to restart." -ForegroundColor Yellow
} else {
    Write-Host "WARNING: Services may not be fully ready. Check logs:" -ForegroundColor Yellow
    Write-Host "  $backendLog"
    Write-Host "  $frontendLog"
}
