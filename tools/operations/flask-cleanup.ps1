# =============================================================================
# flask-cleanup.ps1 — Windows Flask 进程清理
# =============================================================================
# 配套文档: OPERATIONS.md § Flask 服务管理（Windows）
# 用途: 检测并清理占用指定端口的旧 Flask/Python 进程，防止多进程残留
# 用法: powershell -ExecutionPolicy Bypass -File flask-cleanup.ps1 [-Port 5000]
# 环境: Windows PowerShell 5.1+
# 教训: 代码更新后 API 返回旧数据，往往是端口上有多个残留进程
# =============================================================================

param(
    [int]$Port = 5000,
    [switch]$Force = $false,
    [switch]$Quiet = $false
)

# --- 颜色输出 ---
function Write-Pass { 
    param([string]$Msg)
    Write-Host "  [✓] $Msg" -ForegroundColor Green 
}
function Write-Fail { 
    param([string]$Msg)
    Write-Host "  [✗] $Msg" -ForegroundColor Red 
}
function Write-Warn { 
    param([string]$Msg)
    Write-Host "  [⚠] $Msg" -ForegroundColor Yellow 
}
function Write-Info { 
    param([string]$Msg)
    Write-Host "  [→] $Msg" -ForegroundColor Cyan 
}
function Write-Header {
    param([string]$Msg)
    Write-Host ""
    Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Blue
    Write-Host "  $Msg" -ForegroundColor Blue
    Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Blue
    Write-Host ""
}

# --- 主流程 ---
Write-Header "Flask 进程清理 — 端口 $Port"

# 步骤 1: 检测端口占用
Write-Info "检测端口 $Port 占用情况..."
$netstatOutput = netstat -ano 2>$null | Select-String ":$Port\s+"

if (-not $netstatOutput) {
    Write-Pass "端口 $Port 当前无占用，无需清理"
    
    # 额外检查：查找所有 Python 进程供参考
    Write-Info "查找系统中所有 Python 进程..."
    $pythonProcs = Get-Process -Name "python*" -ErrorAction SilentlyContinue
    if ($pythonProcs) {
        Write-Info "发现 $($pythonProcs.Count) 个 Python 进程（未占用端口 $Port）："
        foreach ($proc in $pythonProcs) {
            Write-Info "  PID=$($proc.Id)  Name=$($proc.ProcessName)  Memory=$([math]::Round($proc.WorkingSet64/1MB, 1))MB"
        }
    } else {
        Write-Pass "无 Python 进程运行"
    }
    return
}

# 步骤 2: 解析占用 PID
Write-Info "发现端口 $Port 占用:"
$pids = @{}
foreach ($line in $netstatOutput) {
    $parts = -split $line.Line
    $pid = $parts[-1]
    if ($pid -match '^\d+$') {
        $state = $parts[-2]
        $localAddr = $parts[1]
        $pids[$pid] = @{
            State = $state
            LocalAddress = $localAddr
            PID = $pid
        }
        $stateLabel = if ($state -eq "LISTENING") { "LISTENING" } else { $state }
        Write-Info "  PID=$pid  State=$stateLabel  Addr=$localAddr"
    }
}

if ($pids.Count -eq 0) {
    Write-Warn "无法解析任何 PID，请手动检查 netstat 输出"
    return
}

# 步骤 3: 显示进程详情
Write-Info "获取进程详细信息..."
$distinctPids = $pids.Keys | Sort-Object -Unique

foreach ($pid in $distinctPids) {
    try {
        $proc = Get-Process -Id $pid -ErrorAction Stop
        Write-Info "  PID=$pid → $($proc.ProcessName) (启动时间: $($proc.StartTime), 内存: $([math]::Round($proc.WorkingSet64/1MB, 1))MB)"
    } catch {
        Write-Warn "  PID=$pid → 进程不存在或已退出"
    }
}

# 步骤 4: 确认并终止
$listeningPids = ($pids.GetEnumerator() | Where-Object { $_.Value.State -eq "LISTENING" } | ForEach-Object { $_.Key })
$otherPids = ($pids.GetEnumerator() | Where-Object { $_.Value.State -ne "LISTENING" } | ForEach-Object { $_.Key })

if ($Force) {
    Write-Warn "强制模式: 跳过确认，直接终止所有占用进程"
} else {
    Write-Host ""
    Write-Host "即将终止以下进程: LISTENING($($listeningPids.Count)) + 其他($($otherPids.Count))" -ForegroundColor Yellow
    if (-not $Quiet) {
        $confirm = Read-Host "确认终止? (y/N)"
        if ($confirm -ne 'y' -and $confirm -ne 'Y') {
            Write-Warn "用户取消操作"
            return
        }
    }
}

# 执行终止
$killed = 0
$allPids = $listeningPids + $otherPids | Sort-Object -Unique

foreach ($pid in $allPids) {
    try {
        Stop-Process -Id $pid -Force -ErrorAction Stop
        Write-Pass "已终止 PID=$pid"
        $killed++
    } catch {
        Write-Fail "终止 PID=$pid 失败: $_"
    }
}

Write-Info "已终止 $killed/$($allPids.Count) 个进程"

# 步骤 5: 等待并验证
Start-Sleep -Seconds 2

Write-Info "验证端口 $Port 是否清空..."
$verifyOutput = netstat -ano 2>$null | Select-String ":$Port\s+.*LISTENING"

if (-not $verifyOutput) {
    Write-Pass "端口 $Port 已清空 ✓"
} else {
    Write-Fail "端口 $Port 仍有进程 LISTENING:"
    Write-Fail $verifyOutput
    Write-Info "尝试更激进的方式:"
    Write-Info "  Get-Process | Where-Object {`$_.MainWindowTitle -like '*python*'} | Stop-Process -Force"
    
    # 查找所有 Python 进程并询问
    $pythonProcs = Get-Process -Name "python*" -ErrorAction SilentlyContinue
    if ($pythonProcs) {
        Write-Warn "系统仍有 $($pythonProcs.Count) 个 Python 进程"
        if (-not $Quiet) {
            $killAll = Read-Host "终止所有 Python 进程? (y/N)"
            if ($killAll -eq 'y' -or $killAll -eq 'Y') {
                foreach ($proc in $pythonProcs) {
                    try {
                        Stop-Process -Id $proc.Id -Force -ErrorAction Stop
                        Write-Pass "已终止 PID=$($proc.Id) ($($proc.ProcessName))"
                    } catch {
                        Write-Fail "终止 PID=$($proc.Id) 失败: $_"
                    }
                }
            }
        }
    }
    
    # 最终验证
    Start-Sleep -Seconds 1
    $finalCheck = netstat -ano 2>$null | Select-String ":$Port\s+.*LISTENING"
    if (-not $finalCheck) {
        Write-Pass "端口 $Port 最终已清空 ✓"
    } else {
        Write-Fail "端口 $Port 仍然被占用，可能需要重启机器或检查是否有服务自动重启"
        Write-Fail $finalCheck
    }
}

# 步骤 6: 后续建议
Write-Host ""
Write-Info "如要重新启动 Flask 服务，建议:"
Write-Info "  python -B server.py    # -B 禁止 .pyc 缓存"
Write-Info ""
Write-Info "详见 OPERATIONS.md § Flask 服务管理（Windows）"
