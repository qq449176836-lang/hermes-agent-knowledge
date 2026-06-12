#!/bin/bash
# =============================================================================
# feishu-check.sh — 飞书 7 检查点自检
# =============================================================================
# 配套文档: OPERATIONS.md § 飞书集成 → 不对话排查（7 检查点）
# 用途: 针对飞书机器人不响应的情况，自动执行 7 项排查自检
# 用法: bash feishu-check.sh
# 环境: Windows Git Bash / MSYS, 依赖 curl, yq, netcat
# =============================================================================

set -euo pipefail

# --- 颜色定义 ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

PASS="${GREEN}✓${NC}"
FAIL="${RED}✗${NC}"
WARN="${YELLOW}⚠${NC}"
INFO="${CYAN}→${NC}"

# --- 路径解析 ---
# Windows 兼容: 使用 $APPDATA 获取 Hermes 配置目录
HERMES_HOME="${HERMES_HOME:-${APPDATA}/cn.org.hermesagent.desktop}"
CONFIG_YAML="${HERMES_HOME}/config.yaml"
ENV_FILE="${HERMES_HOME}/.env"
LOG_DIR="${HERMES_HOME}/logs"

# --- 计数器 ---
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

# --- 工具函数 ---
print_header() {
    echo -e "${BOLD}${BLUE}════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${BLUE}  飞书 7 检查点自检 — OPERATIONS.md 配套脚本${NC}"
    echo -e "${BOLD}${BLUE}════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_checkpoint() {
    local num="$1"
    local title="$2"
    echo -e "${BOLD}检查点 ${num}: ${title}${NC}"
}

result_pass() {
    echo -e "  ${PASS} $1"
    PASS_COUNT=$((PASS_COUNT + 1))
}

result_fail() {
    echo -e "  ${FAIL} $1"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

result_warn() {
    echo -e "  ${WARN} $1"
    WARN_COUNT=$((WARN_COUNT + 1))
}

result_info() {
    echo -e "  ${INFO} $1"
}

print_summary() {
    echo ""
    echo -e "${BOLD}${BLUE}────────────────────────────────────────────────────────${NC}"
    echo -e "${BOLD}  检查结果: ${PASS} ${PASS_COUNT} 通过  ${FAIL} ${FAIL_COUNT} 失败  ${WARN} ${WARN_COUNT} 警告${NC}"
    echo -e "${BOLD}${BLUE}────────────────────────────────────────────────────────${NC}"
    if [ "$FAIL_COUNT" -gt 0 ]; then
        echo -e "${RED}存在不通过项，请根据上述提示排查。${NC}"
        echo -e "${RED}详见 OPERATIONS.md § 飞书集成 → 不对话排查（7 检查点）${NC}"
    else
        echo -e "${GREEN}所有检查点通过！如仍有问题，请检查网络和日志。${NC}"
    fi
}

# --- 辅助: 查找 yq 工具 ---
find_yq() {
    if command -v yq &>/dev/null; then
        echo "yq"
    elif command -v yq.exe &>/dev/null; then
        echo "yq.exe"
    else
        echo ""
    fi
}

# --- 检查点 1: 应用类型 ---
check_app_type() {
    print_checkpoint "1" "应用类型（应为「企业自建应用」）"
    
    # 尝试从 config.yaml 读取 app_id
    local app_id=""
    if [ -f "$CONFIG_YAML" ]; then
        app_id=$(grep -E '^\s*app_id\s*:' "$CONFIG_YAML" 2>/dev/null | head -1 | sed 's/.*:\s*//' | xargs)
    fi
    
    if [ -z "$app_id" ] || [ "$app_id" = "your_app_id_here" ] || [ "$app_id" = "placeholder" ]; then
        result_fail "config.yaml 中未找到有效的 feishu app_id"
        result_info "请确认 app_id 不为占位符，且应用类型为「企业自建应用」"
        return
    fi
    
    result_info "app_id: ${app_id:0:8}... (已配置)"
    
    # 尝试用 API 检查（需要 tenant_access_token）
    local token=""
    local app_secret=""
    if [ -f "$CONFIG_YAML" ]; then
        app_secret=$(grep -E '^\s*app_secret\s*:' "$CONFIG_YAML" 2>/dev/null | head -1 | sed 's/.*:\s*//' | xargs)
    fi
    
    if [ -n "$app_secret" ] && [ "$app_secret" != "your_app_secret_here" ] && [ "$app_secret" != "placeholder" ]; then
        # 获取 tenant_access_token
        local token_resp
        token_resp=$(curl -s --connect-timeout 5 --max-time 10 \
            -X POST "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal" \
            -H "Content-Type: application/json; charset=utf-8" \
            -d "{\"app_id\":\"$app_id\",\"app_secret\":\"$app_secret\"}" 2>/dev/null) || true
        
        if echo "$token_resp" | grep -q '"code":0'; then
            result_pass "飞书 API 连接正常，应用凭证有效"
            
            # 尝试获取应用信息（非标准 API，仅做基本信息检查）
            # 无法通过 API 直接判断应用类型，提示手动检查
            result_info "无法通过 API 自动判断应用类型，请在飞书开放平台确认："
            result_info "  → 管理后台 → 应用 → 应用类型 =「企业自建应用」"
            result_info "  注意:「应用商店应用」不可用于自定义机器人"
        else
            local err_msg=$(echo "$token_resp" | grep -o '"msg":"[^"]*"' | head -1 | cut -d'"' -f4)
            result_warn "获取 tenant_access_token 失败: ${err_msg:-未知错误}"
            result_info "请手动在飞书开放平台确认应用类型"
        fi
    else
        result_warn "app_secret 未配置，无法验证 API 连接"
        result_info "请手动在飞书开放平台确认应用类型为「企业自建应用」"
    fi
}

# --- 检查点 2: 权限 ---
check_permissions() {
    print_checkpoint "2" "权限范围（im:message / im:message:send_as_bot）"
    
    local app_id=""
    local app_secret=""
    if [ -f "$CONFIG_YAML" ]; then
        app_id=$(grep -E '^\s*app_id\s*:' "$CONFIG_YAML" 2>/dev/null | head -1 | sed 's/.*:\s*//' | xargs)
        app_secret=$(grep -E '^\s*app_secret\s*:' "$CONFIG_YAML" 2>/dev/null | head -1 | sed 's/.*:\s*//' | xargs)
    fi
    
    local required_perms=("im:message" "im:message:send_as_bot")
    local missing_perms=()
    
    if [ -n "$app_id" ] && [ -n "$app_secret" ] && [ "$app_secret" != "placeholder" ]; then
        # 获取 tenant_access_token
        local token_resp
        token_resp=$(curl -s --connect-timeout 5 --max-time 10 \
            -X POST "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal" \
            -H "Content-Type: application/json; charset=utf-8" \
            -d "{\"app_id\":\"$app_id\",\"app_secret\":\"$app_secret\"}" 2>/dev/null) || true
        
        local token=$(echo "$token_resp" | grep -o '"tenant_access_token":"[^"]*"' | cut -d'"' -f4)
        
        if [ -n "$token" ]; then
            # 检查已授权的权限
            local scopes_resp
            scopes_resp=$(curl -s --connect-timeout 5 --max-time 10 \
                -X GET "https://open.feishu.cn/open-apis/auth/v3/app_access_token" \
                -H "Authorization: Bearer $token" 2>/dev/null) || true
            
            # 备用：尝试从 config.yaml 的 scopes 字段读取
            if [ -f "$CONFIG_YAML" ]; then
                local configured_scopes
                configured_scopes=$(grep -E '^\s*scopes?\s*:' -A 10 "$CONFIG_YAML" 2>/dev/null | grep -oP 'im:[a-z_:]+' | sort -u) || true
                
                for perm in "${required_perms[@]}"; do
                    if echo "$configured_scopes" | grep -q "$perm"; then
                        result_pass "$perm — 已在 config.yaml 中配置"
                    else
                        result_fail "$perm — 未在 config.yaml 中找到"
                        missing_perms+=("$perm")
                    fi
                done
            else
                result_warn "config.yaml 不存在，无法验证权限配置"
                result_info "需要的权限: ${required_perms[*]}"
                return
            fi
        else
            result_warn "无法获取 access token，跳过权限 API 验证"
            result_info "需要的权限: ${required_perms[*]}"
            result_info "开通权限后需要在飞书开放平台「发版」才能生效"
            return
        fi
    else
        result_warn "app_id/app_secret 未完整配置，无法验证权限"
        result_info "需要的权限: ${required_perms[*]}"
        result_info "开通权限后需要在飞书开放平台「发版」才能生效"
        return
    fi
    
    if [ ${#missing_perms[@]} -gt 0 ]; then
        result_info "请在飞书开放平台 → 权限管理 中添加缺失权限，然后「发版」"
    fi
    
    result_info "重要提醒: 权限变更后必须点击「发版」才能生效"
}

# --- 检查点 3: 事件订阅 URL ---
check_event_subscription() {
    print_checkpoint "3" "事件订阅 URL 可访问性"
    
    local callback_url=""
    if [ -f "$CONFIG_YAML" ]; then
        callback_url=$(grep -E '^\s*(callback_url|webhook_url|event_url)\s*:' "$CONFIG_YAML" 2>/dev/null | head -1 | sed 's/.*:\s*//' | xargs)
    fi
    
    if [ -z "$callback_url" ]; then
        result_fail "config.yaml 中未找到事件订阅 URL (callback_url/webhook_url/event_url)"
        result_info "请填入 Hermes 启动后控制台打印的回调地址"
        return
    fi
    
    result_info "回调 URL: $callback_url"
    
    # 尝试访问（仅检查端口可达性）
    local host=""
    local port=""
    if echo "$callback_url" | grep -q '://'; then
        host=$(echo "$callback_url" | sed 's|.*://||' | cut -d: -f1 | cut -d/ -f1)
        port=$(echo "$callback_url" | sed 's|.*://||' | cut -d: -f2 | cut -d/ -f1)
    fi
    [ -z "$port" ] && port="443"
    
    if [ -n "$host" ]; then
        if timeout 3 bash -c "echo >/dev/tcp/$host/$port" 2>/dev/null; then
            result_pass "回调地址 $host:$port 端口可达"
        else
            result_fail "回调地址 $host:$port 端口不可达"
            result_info "请确认 Hermes Gateway 正在运行且端口正确"
        fi
    else
        result_warn "无法解析回调 URL，请手动验证"
    fi
}

# --- 检查点 4: config.yaml 完整性 ---
check_config_integrity() {
    print_checkpoint "4" "config.yaml 飞书段完整性"
    
    if [ ! -f "$CONFIG_YAML" ]; then
        result_fail "config.yaml 不存在: $CONFIG_YAML"
        return
    fi
    
    local checks=(
        "app_id:App ID"
        "app_secret:App Secret"
    )
    
    local all_ok=true
    for check in "${checks[@]}"; do
        local key="${check%%:*}"
        local label="${check##*:}"
        local value
        value=$(grep -E "^\s*${key}\s*:" "$CONFIG_YAML" 2>/dev/null | head -1 | sed 's/.*:\s*//' | xargs) || true
        
        if [ -z "$value" ]; then
            result_fail "$label 缺失 — config.yaml 中没有 $key 字段"
            all_ok=false
        elif [ "$value" = "your_${key}_here" ] || [ "$value" = "placeholder" ]; then
            result_fail "$label 为占位符 — 请填入真实值"
            all_ok=false
        else
            result_pass "$label 已配置"
        fi
    done
    
    # 检查可选但重要的字段
    local verify_token
    verify_token=$(grep -E '^\s*verification_token\s*:' "$CONFIG_YAML" 2>/dev/null | head -1 | sed 's/.*:\s*//' | xargs) || true
    if [ -n "$verify_token" ] && [ "$verify_token" != "placeholder" ]; then
        result_pass "Verification Token 已配置"
    else
        result_warn "Verification Token 未配置（事件订阅需要）"
    fi
    
    if $all_ok; then
        result_pass "config.yaml 飞书段配置完整"
    fi
}

# --- 检查点 5: .env 白名单 ---
check_env_whitelist() {
    print_checkpoint "5" "FEISHU_ALLOWED_USERS 白名单"
    
    if [ ! -f "$ENV_FILE" ]; then
        result_fail ".env 文件不存在: $ENV_FILE"
        result_info "请创建 .env 并设置 FEISHU_ALLOWED_USERS"
        return
    fi
    
    local allowed_users
    allowed_users=$(grep -E '^FEISHU_ALLOWED_USERS\s*=' "$ENV_FILE" 2>/dev/null | sed 's/.*=\s*//' | xargs) || true
    
    if [ -z "$allowed_users" ]; then
        result_fail "FEISHU_ALLOWED_USERS 未设置或为空"
        result_info "任何人发消息都不会被响应！请添加用户 ID"
        result_info "格式: FEISHU_ALLOWED_USERS=ou_xxx,ou_yyy (逗号分隔)"
    else
        local user_count
        user_count=$(echo "$allowed_users" | tr ',' '\n' | grep -c '.' 2>/dev/null) || user_count=1
        result_pass "FEISHU_ALLOWED_USERS 已配置 ($user_count 个用户)"
        result_info "用户列表: ${allowed_users:0:80}..."
    fi
}

# --- 检查点 6: 应用发布状态 ---
check_app_publish() {
    print_checkpoint "6" "应用发布状态"
    
    local app_id=""
    local app_secret=""
    if [ -f "$CONFIG_YAML" ]; then
        app_id=$(grep -E '^\s*app_id\s*:' "$CONFIG_YAML" 2>/dev/null | head -1 | sed 's/.*:\s*//' | xargs)
        app_secret=$(grep -E '^\s*app_secret\s*:' "$CONFIG_YAML" 2>/dev/null | head -1 | sed 's/.*:\s*//' | xargs)
    fi
    
    if [ -z "$app_id" ] || [ -z "$app_secret" ] || [ "$app_secret" = "placeholder" ]; then
        result_warn "凭证未配置，无法通过 API 检查发布状态"
        result_info "请在飞书开放平台 → 应用 → 发布管理中确认"
        result_info "「开发中」状态只有管理员能对话，需发布后才能全员使用"
        return
    fi
    
    # 获取 token
    local token_resp
    token_resp=$(curl -s --connect-timeout 5 --max-time 10 \
        -X POST "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal" \
        -H "Content-Type: application/json; charset=utf-8" \
        -d "{\"app_id\":\"$app_id\",\"app_secret\":\"$app_secret\"}" 2>/dev/null) || true
    
    local token=$(echo "$token_resp" | grep -o '"tenant_access_token":"[^"]*"' | cut -d'"' -f4)
    
    if [ -z "$token" ]; then
        result_warn "无法获取 access token，跳过发布状态检查"
        return
    fi
    
    # 尝试获取应用信息
    local app_info
    app_info=$(curl -s --connect-timeout 5 --max-time 10 \
        -X GET "https://open.feishu.cn/open-apis/application/v6/applications/$app_id" \
        -H "Authorization: Bearer $token" 2>/dev/null) || true
    
    if echo "$app_info" | grep -q '"app_status"'; then
        local app_status
        app_status=$(echo "$app_info" | grep -o '"app_status":[0-9]*' | cut -d: -f2)
        
        case "$app_status" in
            0)
                result_fail "应用状态: 未知"
                ;;
            1)
                result_warn "应用状态: 开发中 — 仅管理员可用"
                result_info "请在飞书开放平台发布应用"
                ;;
            2)
                result_pass "应用状态: 已发布"
                ;;
            3)
                result_warn "应用状态: 审核中"
                ;;
            4)
                result_pass "应用状态: 已上线"
                ;;
            *)
                result_warn "应用状态码: $app_status (请手动确认)"
                ;;
        esac
    else
        result_info "无法获取应用发布状态（API 可能无权限）"
        result_info "请手动在飞书开放平台确认: 应用 → 发布管理"
    fi
}

# --- 检查点 7: access_key 同步延迟 ---
check_access_key_sync() {
    print_checkpoint "7" "access_key 同步延迟检测"
    
    # 检查 token-locks 目录
    local token_locks_dir="${HERMES_HOME}/gateway-runtime/token-locks"
    
    if [ -d "$token_locks_dir" ]; then
        local lock_count
        lock_count=$(find "$token_locks_dir" -name "*.lock" -type f 2>/dev/null | wc -l)
        
        if [ "$lock_count" -gt 0 ]; then
            result_warn "发现 $lock_count 个 token 锁文件（可能导致同步延迟）"
            result_info "建议清理: rm -f \"${token_locks_dir}/\"*.lock"
        else
            result_pass "token-locks 目录干净，无残留锁文件"
        fi
    else
        result_info "token-locks 目录不存在（可能未初始化）"
    fi
    
    # 检查日志中是否有 access_key 相关错误
    local gateway_log="${LOG_DIR}/gateway.log"
    if [ -f "$gateway_log" ]; then
        local recent_key_errors
        recent_key_errors=$(tail -100 "$gateway_log" 2>/dev/null | grep -ci "access.key\|token.*expired\|invalid.token\|unauthorized" || echo "0")
        
        if [ "$recent_key_errors" -gt 0 ]; then
            result_warn "最近日志中发现 $recent_key_errors 条 access_key/token 相关错误"
            result_info "刚重启后 1-2 分钟内 access_key 可能尚不可用，请等待"
        else
            result_pass "最近日志中无 access_key 相关错误"
        fi
    else
        result_info "gateway.log 不存在，跳过日志检查"
    fi
    
    result_info "提示: 刚重启 1-2 分钟内 access_key 短暂不可用属正常现象"
}

# --- 主流程 ---
main() {
    print_header
    
    check_app_type
    echo ""
    
    check_permissions
    echo ""
    
    check_event_subscription
    echo ""
    
    check_config_integrity
    echo ""
    
    check_env_whitelist
    echo ""
    
    check_app_publish
    echo ""
    
    check_access_key_sync
    echo ""
    
    print_summary
}

main "$@"
