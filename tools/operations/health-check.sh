#!/bin/bash
# =============================================================================
# health-check.sh — Hermes 系统健康检查
# =============================================================================
# 配套文档: OPERATIONS.md § 日常维护 → 健康检查
# 用途: 一键检查 Hermes 系统的运行状态
# 检查项:
#   1. Gateway 进程状态 (tasklist)
#   2. 端口监听状态 (netstat)
#   3. Cron 任务数量与状态
#   4. 磁盘剩余空间
#   5. 最近错误日志摘要
# 用法: bash health-check.sh
# 环境: Windows Git Bash / MSYS
# =============================================================================

set -euo pipefail

# --- 颜色定义 ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

PASS="${GREEN}✓${NC}"
FAIL="${RED}✗${NC}"
WARN="${YELLOW}⚠${NC}"
INFO="${CYAN}→${NC}"
DOT="${MAGENTA}•${NC}"

# --- 路径解析 ---
HERMES_HOME="${HERMES_HOME:-${APPDATA}/cn.org.hermesagent.desktop}"
LOG_DIR="${HERMES_HOME}/logs"
GATEWAY_LOG="${LOG_DIR}/gateway.log"
AGENT_LOG="${LOG_DIR}/agent.log"
CRON_DIR="${HERMES_HOME}/cron"

# --- 路径转 Windows 格式（用于 tasklist） ---
winpath() {
    echo "$1" | sed 's|/|\\|g' | sed 's|^\\c\\|C:\\|'
}

# --- 工具函数 ---
print_header() {
    echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${BLUE}  Hermes 系统健康检查${NC}"
    echo -e "${BOLD}${BLUE}  $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${INFO} Hermes Home: ${HERMES_HOME}"
    echo ""
}

section_header() {
    echo ""
    echo -e "${BOLD}${MAGENTA}── $1 ──${NC}"
    echo ""
}

# --- 检查 1: Gateway 进程状态 ---
check_gateway_process() {
    section_header "1. Gateway 进程状态"
    
    local gateway_found=false
    local hermes_found=false
    local python_found=false
    
    # 用 tasklist 检查（Windows）
    local tasklist_out
    tasklist_out=$(tasklist 2>/dev/null || true)
    
    # 查找 gateway 相关进程
    if echo "$tasklist_out" | grep -qi "gateway"; then
        gateway_found=true
        echo -e "${PASS} Gateway 进程: 运行中"
        echo "$tasklist_out" | grep -i "gateway" | while read -r line; do
            echo -e "  ${DOT} $line"
        done
    else
        echo -e "${FAIL} Gateway 进程: 未运行"
    fi
    
    # 查找 hermes 相关进程
    if echo "$tasklist_out" | grep -qi "hermes"; then
        hermes_found=true
        echo -e "${PASS} Hermes 进程: 运行中"
        echo "$tasklist_out" | grep -i "hermes" | while read -r line; do
            echo -e "  ${DOT} $line"
        done
    else
        echo -e "${WARN} Hermes 进程: 未检测到"
    fi
    
    # 查找 Python 进程（Flask 通常是 Python）
    if echo "$tasklist_out" | grep -qi "python"; then
        python_found=true
        local py_count
        py_count=$(echo "$tasklist_out" | grep -ci "python")
        echo -e "${INFO} Python 进程: $py_count 个运行中"
        
        # 显示 Python 进程的内存占用
        echo "$tasklist_out" | grep -i "python" | while read -r line; do
            local mem_kb=$(echo "$line" | awk '{print $(NF-1)}' | sed 's/,//g')
            local pid=$(echo "$line" | awk '{print $2}')
            echo -e "  ${DOT} PID=$pid  Memory=$(echo "scale=1; $mem_kb/1024" | bc 2>/dev/null || echo "?")MB"
        done
    else
        echo -e "${INFO} Python 进程: 未检测到"
    fi
    
    if ! $gateway_found && ! $hermes_found && ! $python_found; then
        echo -e "${FAIL} 所有 Hermes 相关进程均未运行"
    fi
}

# --- 检查 2: 端口监听状态 ---
check_port_status() {
    section_header "2. 端口监听状态"
    
    local ports_to_check=("5000:Flask/API" "5001:Gateway" "8080:Web UI")
    local any_listening=false
    
    for port_def in "${ports_to_check[@]}"; do
        local port="${port_def%%:*}"
        local label="${port_def##*:}"
        
        local netstat_out
        netstat_out=$(netstat -ano 2>/dev/null | grep ":$port " || true)
        
        if [ -n "$netstat_out" ]; then
            any_listening=true
            local listening
            listening=$(echo "$netstat_out" | grep "LISTENING" || true)
            
            if [ -n "$listening" ]; then
                echo -e "${PASS} 端口 $port ($label): LISTENING"
                echo "$listening" | while read -r line; do
                    local pid=$(echo "$line" | awk '{print $NF}')
                    echo -e "  ${DOT} $line → PID=$pid"
                done
            else
                echo -e "${WARN} 端口 $port ($label): 已占用但非 LISTENING 状态"
                echo "$netstat_out" | while read -r line; do
                    echo -e "  ${DOT} $line"
                done
            fi
        else
            echo -e "${WARN} 端口 $port ($label): 未监听"
        fi
    done
    
    if ! $any_listening; then
        echo -e "${FAIL} 所有预期端口均未监听，Hermes 可能未正常启动"
    fi
}

# --- 检查 3: Cron 任务状态 ---
check_cron_status() {
    section_header "3. Cron 任务状态"
    
    if [ ! -d "$CRON_DIR" ]; then
        echo -e "${WARN} Cron 目录不存在: $CRON_DIR"
        return
    fi
    
    # 统计 cron 文件
    local cron_files
    cron_files=$(find "$CRON_DIR" -maxdepth 1 -type f ! -name ".*" 2>/dev/null || true)
    local cron_count
    cron_count=$(echo "$cron_files" | grep -c '.' 2>/dev/null || echo "0")
    
    # 统计锁文件
    local tick_lock="${CRON_DIR}/.tick.lock"
    local tick_lock_exists=false
    if [ -f "$tick_lock" ]; then
        tick_lock_exists=true
    fi
    
    # 统计日志文件
    local cron_log_count=0
    if [ -d "$CRON_DIR" ]; then
        cron_log_count=$(find "$CRON_DIR" -name "*.log" -type f 2>/dev/null | wc -l)
    fi
    
    echo -e "${INFO} Cron 目录: $CRON_DIR"
    echo -e "${INFO} Cron 任务文件: $cron_count 个"
    
    if [ "$cron_count" -gt 0 ];then
        echo "$cron_files" | while read -r f; do
            local fname=$(basename "$f")
            local fsize=$(stat -c%s "$f" 2>/dev/null || echo "?")
            echo -e "  ${DOT} $fname (${fsize} bytes)"
        done
    else
        echo -e "${WARN} 无 Cron 任务配置"
    fi
    
    # Cron tick 锁检查
    if $tick_lock_exists; then
        local lock_age
        lock_age=$(($(date +%s) - $(stat -c%Y "$tick_lock" 2>/dev/null || echo "$(date +%s)")))
        if [ "$lock_age" -gt 300 ]; then
            echo -e "${FAIL} .tick.lock 存在且超过 5 分钟未更新 (${lock_age}s) — Cron 可能卡死"
            echo -e "  ${INFO} 建议删除锁文件: rm -f \"$tick_lock\""
        else
            echo -e "${PASS} .tick.lock 活跃 (${lock_age}s 前更新) — Cron 正常运行"
        fi
    else
        echo -e "${WARN} .tick.lock 不存在 — Cron 可能未运行或刚启动"
    fi
    
    echo -e "${INFO} Cron 日志文件: $cron_log_count 个"
}

# --- 检查 4: 磁盘剩余空间 ---
check_disk_space() {
    section_header "4. 磁盘剩余空间"
    
    # Windows 下获取磁盘信息
    local drives
    if command -v wmic &>/dev/null; then
        drives=$(wmic logicaldisk get size,freespace,caption 2>/dev/null | tail -n +2 | grep -v '^$' || true)
    fi
    
    if [ -n "$drives" ]; then
        echo "$drives" | while read -r line; do
            local drive letter free size
            read -r drive free size <<< "$line"
            
            if [ -n "$free" ] && [ -n "$size" ] && [ "$size" != "0" ]; then
                local free_gb=$(echo "scale=1; $free/1073741824" | bc 2>/dev/null || echo "?")
                local total_gb=$(echo "scale=1; $size/1073741824" | bc 2>/dev/null || echo "?")
                local pct_used=$(echo "scale=0; ($size-$free)*100/$size" | bc 2>/dev/null || echo "?")
                
                local color="${GREEN}"
                if [ "$pct_used" != "?" ] && [ "$pct_used" -gt 90 ]; then
                    color="${RED}"
                elif [ "$pct_used" != "?" ] && [ "$pct_used" -gt 75 ]; then
                    color="${YELLOW}"
                fi
                
                echo -e "  ${DOT} ${drive}: ${free_gb}GB 可用 / ${total_gb}GB 总计 (${color}${pct_used}%${NC} 已用)"
            fi
        done
    else
        # 备用: 用 df
        echo -e "${INFO} 磁盘使用 (df -h):"
        df -h 2>/dev/null | grep -E '^/|^[A-Z]:' | while read -r line; do
            echo -e "  ${DOT} $line"
        done
    fi
    
    # Hermes 目录大小
    if [ -d "$HERMES_HOME" ]; then
        local hermes_size
        hermes_size=$(du -sh "$HERMES_HOME" 2>/dev/null | awk '{print $1}' || echo "?")
        echo -e "${INFO} Hermes 数据目录大小: ${hermes_size}"
    fi
    
    # 日志目录大小
    if [ -d "$LOG_DIR" ]; then
        local log_size
        log_size=$(du -sh "$LOG_DIR" 2>/dev/null | awk '{print $1}' || echo "?")
        local log_files
        log_files=$(find "$LOG_DIR" -name "*.log" -type f 2>/dev/null | wc -l)
        echo -e "${INFO} 日志目录大小: ${log_size} (${log_files} 个日志文件)"
    fi
}

# --- 检查 5: 最近错误日志摘要 ---
check_error_logs() {
    section_header "5. 最近错误日志摘要"
    
    local errors_found=false
    
    for log_file in "$GATEWAY_LOG" "$AGENT_LOG"; do
        local log_name=$(basename "$log_file")
        
        if [ ! -f "$log_file" ]; then
            echo -e "${WARN} ${log_name}: 文件不存在"
            continue
        fi
        
        local log_size
        log_size=$(stat -c%s "$log_file" 2>/dev/null || echo "0")
        echo -e "${INFO} ${log_name}: $(echo "scale=1; $log_size/1024" | bc 2>/dev/null || echo "?")KB"
        
        # 查找错误关键词
        local error_patterns=("ERROR" "FATAL" "Traceback" "exception" "fail" "crash" "timeout" "refused")
        
        for pattern in "${error_patterns[@]}"; do
            local matches
            matches=$(tail -500 "$log_file" 2>/dev/null | grep -ci "$pattern" || echo "0")
            if [ "$matches" -gt 0 ]; then
                errors_found=true
                if [ "$matches" -gt 10 ]; then
                    echo -e "  ${FAIL} \"$pattern\": $matches 次 (最近 500 行)"
                else
                    echo -e "  ${WARN} \"$pattern\": $matches 次 (最近 500 行)"
                fi
            fi
        done
        
        # 显示最近 3 条错误行
        local recent_errors
        recent_errors=$(tail -500 "$log_file" 2>/dev/null | grep -iE "ERROR|FATAL|Traceback|exception" | tail -3 || true)
        if [ -n "$recent_errors" ]; then
            echo -e "  ${INFO} 最近错误行:"
            echo "$recent_errors" | while read -r err_line; do
                # 截断过长的行
                local display_line="${err_line:0:120}"
                if [ ${#err_line} -gt 120 ]; then
                    display_line="${display_line}..."
                fi
                echo -e "    ${DOT} ${display_line}"
            done
        fi
        
        echo ""
    done
    
    if ! $errors_found; then
        echo -e "${PASS} 最近日志中无严重错误"
    fi
}

# --- 检查 6: 最近一次 Gateway 启动信息 ---
check_gateway_startup() {
    section_header "6. Gateway 启动信息"
    
    if [ -f "$GATEWAY_LOG" ]; then
        # 查找最近一次启动行
        local startup_lines
        startup_lines=$(grep -i "startup\|started\|listening\|ready\|initialized" "$GATEWAY_LOG" 2>/dev/null | tail -3 || true)
        
        if [ -n "$startup_lines" ]; then
            echo "$startup_lines" | while read -r line; do
                echo -e "  ${DOT} $line"
            done
        else
            echo -e "${INFO} 未找到明确的启动标记"
        fi
        
        # 日志文件最后修改时间
        local log_mtime
        log_mtime=$(stat -c%y "$GATEWAY_LOG" 2>/dev/null | cut -d. -f1 || echo "未知")
        echo -e "${INFO} gateway.log 最后更新: ${log_mtime}"
    else
        echo -e "${WARN} gateway.log 不存在"
    fi
}

# --- 总结 ---
print_summary() {
    echo ""
    echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  健康检查完成${NC}"
    echo -e "${INFO} 如发现问题，请参考:"
    echo -e "  • OPERATIONS.md § 日常维护"
    echo -e "  • OPERATIONS.md § Flask 服务管理（Windows）"
    echo -e "  • OPERATIONS.md § 锁文件管理"
    echo -e "  • 运行 lockfile-check.sh 检查锁文件"
    echo -e "  • 运行 flask-cleanup.ps1 清理端口占用"
    echo -e "${BOLD}${BLUE}══════════════════════════════════════════════════════════════${NC}"
}

# --- 主流程 ---
main() {
    print_header
    
    check_gateway_process
    check_port_status
    check_cron_status
    check_disk_space
    check_error_logs
    check_gateway_startup
    
    print_summary
}

main "$@"
