#!/bin/bash
# =============================================================================
# lockfile-check.sh — 锁文件检测与清理
# =============================================================================
# 配套文档: OPERATIONS.md § 锁文件管理
# 用途: 检测 Hermes 系统中的残留锁文件，可选自动清理
# 用法: bash lockfile-check.sh [--clean]
# 环境: Windows Git Bash / MSYS
# 症状匹配:
#   - Gateway 启动后立即退出 → gateway.lock + gateway.pid
#   - 飞书连不上 → token-locks/*.lock
#   - Cron 不执行 → cron/.tick.lock
# =============================================================================

set -euo pipefail

# --- 颜色定义 ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

PASS="${GREEN}✓${NC}"
FAIL="${RED}✗${NC}"
WARN="${YELLOW}⚠${NC}"
INFO="${CYAN}→${NC}"

# --- 参数解析 ---
CLEAN_MODE=false
if [[ "${1:-}" == "--clean" ]]; then
    CLEAN_MODE=true
fi

# --- 路径解析 ---
HERMES_HOME="${HERMES_HOME:-${APPDATA}/cn.org.hermesagent.desktop}"

# --- 定义锁文件清单 ---
declare -A LOCK_FILES=(
    ["gateway-runtime/gateway.lock"]="Gateway 主锁 — Gateway 启动后立即退出的常见原因"
    ["gateway-runtime/gateway.pid"]="Gateway PID 文件 — 与 gateway.lock 配套"
    ["auth.lock"]="认证锁 — 飞书认证失败/卡住的原因之一"
    ["kanban.db.init.lock"]="看板数据库初始化锁"
    ["cron/.tick.lock"]="Cron 节拍锁 — Cron 不执行的头号嫌疑"
    ["skills/.usage.json.lock"]="Skills 使用统计锁"
)

# --- 工具函数 ---
print_header() {
    echo -e "${BOLD}${BLUE}════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${BLUE}  锁文件检测与清理 — OPERATIONS.md 配套脚本${NC}"
    echo -e "${BOLD}${BLUE}════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${INFO} Hermes Home: ${HERMES_HOME}"
    if $CLEAN_MODE; then
        echo -e "${WARN} 模式: 自动清理 (--clean)"
    else
        echo -e "${INFO} 模式: 仅检测 (加 --clean 自动清理)"
    fi
    echo ""
}

check_lock() {
    local rel_path="$1"
    local description="$2"
    local full_path="${HERMES_HOME}/${rel_path}"
    
    if [ -f "$full_path" ]; then
        local size
        size=$(stat -c%s "$full_path" 2>/dev/null || echo "?")
        local mtime
        mtime=$(stat -c%y "$full_path" 2>/dev/null | cut -d. -f1 || echo "未知")
        
        echo -e "  ${FAIL} ${rel_path}  (${size} bytes, ${mtime})"
        echo -e "      ${description}"
        
        if $CLEAN_MODE; then
            rm -f "$full_path"
            if [ ! -f "$full_path" ]; then
                echo -e "      ${PASS} 已清理"
            else
                echo -e "      ${FAIL} 清理失败"
            fi
        fi
        return 1
    else
        echo -e "  ${PASS} ${rel_path} — 无残留"
        return 0
    fi
}

check_token_locks() {
    local token_locks_dir="${HERMES_HOME}/gateway-runtime/token-locks"
    
    echo -e "${BOLD}Token 锁文件 (token-locks/):${NC}"
    
    if [ ! -d "$token_locks_dir" ]; then
        echo -e "  ${PASS} token-locks/ 目录不存在"
        return 0
    fi
    
    local lock_files
    lock_files=$(find "$token_locks_dir" -maxdepth 1 -name "*.lock" -type f 2>/dev/null)
    
    if [ -z "$lock_files" ]; then
        echo -e "  ${PASS} 无 .lock 文件"
        return 0
    fi
    
    local count=0
    while IFS= read -r f; do
        local fname=$(basename "$f")
        local size=$(stat -c%s "$f" 2>/dev/null || echo "?")
        echo -e "  ${FAIL} ${fname}  (${size} bytes)"
        count=$((count + 1))
    done <<< "$lock_files"
    
    if $CLEAN_MODE; then
        rm -f "${token_locks_dir}/"*.lock
        local remaining
        remaining=$(find "$token_locks_dir" -name "*.lock" -type f 2>/dev/null | wc -l)
        if [ "$remaining" -eq 0 ]; then
            echo -e "  ${PASS} 已清理全部 $count 个 token 锁文件"
        else
            echo -e "  ${FAIL} 清理后仍有 $remaining 个残留"
        fi
    else
        echo -e "  ${INFO} 共 $count 个 token 锁文件 (加 --clean 自动清理)"
    fi
    
    return $count
}

get_orphan_info() {
    local rel_path="$1"
    local full_path="${HERMES_HOME}/${rel_path}"
    
    if [ ! -f "$full_path" ]; then
        return 1
    fi
    
    # 检查是否有对应进程存活
    if [[ "$rel_path" == *".pid" ]]; then
        local pid
        pid=$(cat "$full_path" 2>/dev/null)
        if [ -n "$pid" ]; then
            if tasklist 2>/dev/null | grep -qi "$pid"; then
                echo -e "      ${WARN} PID $pid 进程仍存活（非孤儿锁）"
            else
                echo -e "      ${INFO} PID $pid 进程已不存在（孤儿锁）"
            fi
        fi
    fi
}

print_summary() {
    echo ""
    echo -e "${BOLD}${BLUE}────────────────────────────────────────────────────────${NC}"
    
    # 最终统计
    local total_locks=0
    for rel_path in "${!LOCK_FILES[@]}"; do
        if [ -f "${HERMES_HOME}/${rel_path}" ]; then
            total_locks=$((total_locks + 1))
        fi
    done
    
    # token locks
    local token_locks_dir="${HERMES_HOME}/gateway-runtime/token-locks"
    local token_count=0
    if [ -d "$token_locks_dir" ]; then
        token_count=$(find "$token_locks_dir" -maxdepth 1 -name "*.lock" -type f 2>/dev/null | wc -l)
    fi
    total_locks=$((total_locks + token_count))
    
    if [ "$total_locks" -eq 0 ]; then
        echo -e "${BOLD}${GREEN}  结果: 所有锁文件正常，无残留 ✓${NC}"
    elif $CLEAN_MODE; then
        echo -e "${BOLD}${YELLOW}  结果: 已尝试清理 $total_locks 个锁文件${NC}"
    else
        echo -e "${BOLD}${RED}  结果: 发现 $total_locks 个残留锁文件${NC}"
        echo -e "${INFO}  运行 'bash $0 --clean' 自动清理"
    fi
    echo -e "${BOLD}${BLUE}────────────────────────────────────────────────────────${NC}"
}

# --- 主流程 ---
main() {
    print_header
    
    echo -e "${BOLD}核心锁文件:${NC}"
    echo ""
    
    local lock_found=0
    for rel_path in "${!LOCK_FILES[@]}"; do
        if ! check_lock "$rel_path" "${LOCK_FILES[$rel_path]}"; then
            lock_found=$((lock_found + 1))
            if ! $CLEAN_MODE; then
                get_orphan_info "$rel_path"
            fi
        fi
        echo ""
    done
    
    check_token_locks
    
    if $CLEAN_MODE; then
        echo ""
        echo -e "${INFO} 清理完成。如果问题仍然存在："
        echo -e "  1. 确保 Hermes 完全停止后再清理"
        echo -e "  2. 清理后等待 3-5 秒再重启 Hermes"
        echo -e "  3. 检查 OPERATIONS.md § 锁文件管理"
    fi
    
    print_summary
}

main "$@"
