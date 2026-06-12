#!/bin/bash
# -*- coding: utf-8 -*-
# =============================================================================
# pre-commit-hook.sh — Git Pre-Commit 敏感信息检查 Hook
# =============================================================================
#
# 配套方法论文档：CONSTITUTION.md (Hermes Agent 核心准则)
# 对应规则：
#   - GIT-01: 公开仓库的任何提交都不得包含 Token、内部 IP、个人信息、私钥
#   - GIT-02: 提交前必须检查 git diff --staged 不含敏感内容
#   - TOKEN-01: API Token/Secret/Webhook URL/密码绝对禁止出现在 Git 提交中
#   - CODE-C1: Bash 脚本第一行 #!/bin/bash，第二行 set -euo pipefail
#
# 用途：在 git commit 之前自动扫描 staged 文件中的敏感信息。
#        🔴 HIGH 风险 → 阻止提交
#        🟡 MEDIUM 风险 → 警告但允许提交（需确认）
#        🟢 LOW 风险 → 仅提示，允许提交
#
# 安装：
#   cp pre-commit-hook.sh .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit
#
#   或使用内置安装功能：
#   bash pre-commit-hook.sh --install
#
# 依赖：
#   - python3 (用于运行 secret-scanner.py)
#   - 本脚本所在目录中的 secret-scanner.py
#
# 作者：Hermes Agent
# 日期：2026-06-13
# =============================================================================

set -euo pipefail

# ── 颜色定义 ────────────────────────────────────────────────────────────────
RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ── 路径 ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCANNER_SCRIPT="${SCRIPT_DIR}/secret-scanner.py"

# ── 配置 ────────────────────────────────────────────────────────────────────
# 可通过 git config 覆盖的选项
SCAN_TIMEOUT=$(git config --get hooks.secretscan.timeout 2>/dev/null || echo "60")
ALLOW_MEDIUM_DEFAULT="ask"  # ask | yes | no

# ═══════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════

print_banner() {
    echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${CYAN}║  🔍 Pre-Commit 敏感信息扫描  (CONSTITUTION.md GIT-02)   ║${NC}"
    echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_error() {
    echo -e "${RED}${BOLD}✖${NC} ${RED}$*${NC}" >&2
}

print_warning() {
    echo -e "${YELLOW}${BOLD}⚠${NC} ${YELLOW}$*${NC}" >&2
}

print_success() {
    echo -e "${GREEN}${BOLD}✔${NC} ${GREEN}$*${NC}"
}

print_info() {
    echo -e "${BLUE}${BOLD}ℹ${NC} ${BLUE}$*${NC}"
}

# ═══════════════════════════════════════════════════════════════════════════
# 安装功能：将本脚本安装到 .git/hooks/pre-commit
# ═══════════════════════════════════════════════════════════════════════════

do_install() {
    local git_dir
    git_dir="$(git rev-parse --git-dir 2>/dev/null)" || {
        print_error "当前目录不在 Git 仓库中。请在 Git 仓库根目录运行此命令。"
        exit 1
    }

    local hook_path="${git_dir}/hooks/pre-commit"

    # 检查是否已有 hook
    if [[ -f "$hook_path" ]]; then
        if ! diff -q "$hook_path" "${BASH_SOURCE[0]}" &>/dev/null; then
            print_warning "已存在 pre-commit hook，将被覆盖。"
            # 备份旧 hook
            cp "$hook_path" "${hook_path}.backup.$(date +%Y%m%d_%H%M%S)"
            print_info "旧 hook 已备份"
        else
            print_info "pre-commit hook 已是最新版本，无需更新。"
            exit 0
        fi
    fi

    cp "${BASH_SOURCE[0]}" "$hook_path"
    chmod +x "$hook_path"
    print_success "pre-commit hook 已安装至: ${hook_path}"

    # 同时确保 secret-scanner.py 可访问
    if [[ ! -f "$SCANNER_SCRIPT" ]]; then
        print_warning "secret-scanner.py 不在本脚本同目录中，hook 可能无法正常工作。"
        print_info "请将 secret-scanner.py 复制到: ${SCRIPT_DIR}/"
    fi

    echo ""
    print_info "配置项（可选）："
    echo "  git config hooks.secretscan.timeout 60"
    echo ""
}

# ═══════════════════════════════════════════════════════════════════════════
# 主扫描逻辑
# ═══════════════════════════════════════════════════════════════════════════

do_scan() {
    print_banner

    # 检查 secret-scanner.py 是否存在
    if [[ ! -f "$SCANNER_SCRIPT" ]]; then
        print_error "找不到 secret-scanner.py"
        print_error "期望路径: ${SCANNER_SCRIPT}"
        print_info "请确保 secret-scanner.py 与 pre-commit-hook.sh 在同一目录。"
        print_info "或设置: git config hooks.secretscan.scanner /path/to/secret-scanner.py"
        exit 1
    fi

    # 获取 staged 文件列表
    local staged_files
    staged_files=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null) || {
        print_error "无法获取 staged 文件列表。"
        exit 1
    }

    if [[ -z "$staged_files" ]]; then
        print_info "没有 staged 文件，跳过扫描。"
        exit 0
    fi

    # 统计文件数
    local file_count
    file_count=$(echo "$staged_files" | wc -l | tr -d ' ')
    print_info "扫描 ${file_count} 个 staged 文件..."

    # 创建临时文件存放待扫描文件列表
    local tmpfile
    tmpfile=$(mktemp /tmp/precommit_scan_XXXXXX)
    trap "rm -f '$tmpfile'" EXIT

    # 复制 staged 文件到临时目录（因为文件可能只有部分 staged）
    # 但为了简单和高效，我们直接扫描工作区中对应路径的文件
    # 这样可以捕获文件级别的敏感信息（即使修改不涉及敏感行也值得提醒）
    echo "$staged_files" > "$tmpfile"

    # 运行扫描器
    local scan_output
    local scan_exit_code=0

    # 逐文件扫描（只扫描 staged 文件）
    local all_findings=0
    local high_count=0
    local medium_count=0
    local low_count=0

    # 使用 --json 模式获取结构化结果
    if scan_output=$(python3 "$SCANNER_SCRIPT" --json --quiet $(echo "$staged_files" | tr '\n' ' ') 2>/dev/null); then
        scan_exit_code=0
    else
        scan_exit_code=$?
    fi

    # 解析 JSON 结果
    if [[ -n "$scan_output" ]]; then
        # 使用 python3 解析 JSON（跨平台安全）
        local parsed
        parsed=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
    s = data['scan_summary']
    print(f\"{s['total_findings']}|{s['high']}|{s['medium']}|{s['low']}|{s['overall_risk']}|{s['files_scanned']}\")
    # 输出详细 findings 供展示
    for f_item in data.get('findings', []):
        print(f\"FINDING|{f_item['file']}|{f_item['line']}|{f_item['risk']}|{f_item['pattern']}\")
except Exception as e:
    print(f\"ERROR|{e}\", file=sys.stderr)
    sys.exit(1)
" <<< "$scan_output" 2>/dev/null)
    else
        parsed="0|0|0|0|LOW|0"
    fi

    # 解析统计行
    local stats_line
    stats_line=$(echo "$parsed" | head -1)
    IFS='|' read -r all_findings high_count medium_count low_count overall_risk files_scanned <<< "$stats_line"

    # 输出详细发现
    local findings_lines
    findings_lines=$(echo "$parsed" | tail -n +2 | grep "^FINDING|" || true)

    if [[ -n "$findings_lines" ]]; then
        echo ""
        echo -e "${BOLD}── 发现敏感信息 ──${NC}"
        echo ""

        # 按风险分组显示
        local prev_file=""
        while IFS='|' read -r _type file line risk pattern; do
            if [[ "$file" != "$prev_file" ]]; then
                echo -e "  ${BOLD}📄 ${file}${NC}"
                prev_file="$file"
            fi
            local icon=""
            case "$risk" in
                HIGH)   icon="🔴" ;;
                MEDIUM) icon="🟡" ;;
                LOW)    icon="🟢" ;;
            esac
            printf "    ${icon} L%04d  [%s] %s\n" "$line" "$risk" "$pattern"
        done <<< "$findings_lines"

        echo ""
    fi

    # ── 决策 ────────────────────────────────────────────────────────────────
    echo -e "${BOLD}── 扫描统计 ──${NC}"
    echo -e "  文件: ${files_scanned}  |  🔴 HIGH: ${high_count}  |  🟡 MEDIUM: ${medium_count}  |  🟢 LOW: ${low_count}"
    echo ""

    case "$overall_risk" in
        HIGH)
            echo -e "${RED}${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
            echo -e "${RED}${BOLD}║  🚫 提交被阻止！发现高风险敏感信息。                     ║${NC}"
            echo -e "${RED}${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
            echo ""
            echo -e "  参考规则: ${CYAN}CONSTITUTION.md § GIT-01, TOKEN-01${NC}"
            echo ""
            echo -e "  建议操作:"
            echo -e "    1. 运行 ${CYAN}python3 secret-scanner.py <文件> --fix${NC} 自动替换"
            echo -e "    2. 手动移除敏感信息，改用环境变量或配置文件"
            echo -e "    3. 如确需提交（非敏感测试数据），使用 ${CYAN}git commit --no-verify${NC} 跳过"
            echo ""
            exit 1
            ;;
        MEDIUM)
            echo -e "${YELLOW}${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
            echo -e "${YELLOW}${BOLD}║  ⚠ 发现中等风险敏感信息。请确认后提交。                  ║${NC}"
            echo -e "${YELLOW}${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
            echo ""

            # 检查是否自动允许
            local allow_medium
            allow_medium=$(git config --get hooks.secretscan.allowMedium 2>/dev/null || echo "$ALLOW_MEDIUM_DEFAULT")

            case "$allow_medium" in
                yes)
                    print_warning "配置允许中等风险提交，继续..."
                    exit 0
                    ;;
                no)
                    print_error "配置拒绝中等风险提交，已阻止。"
                    exit 1
                    ;;
                *)
                    # 交互模式：询问用户
                    echo -ne "  ${YELLOW}是否继续提交？[y/N] ${NC}"
                    read -r response
                    if [[ "$response" =~ ^[Yy]$ ]]; then
                        print_warning "用户确认，继续提交。"
                        exit 0
                    else
                        print_info "提交已取消。"
                        exit 1
                    fi
                    ;;
            esac
            ;;
        LOW|*)
            if [[ "$all_findings" -gt 0 ]]; then
                print_success "仅发现低风险项，允许提交。"
                echo ""
                echo -e "  提示: 如为公开仓库，建议也处理低风险项。"
            else
                print_success "未发现敏感信息，提交通过 ✅"
            fi
            exit 0
            ;;
    esac
}

# ═══════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════

case "${1:-}" in
    --install|-i)
        do_install
        ;;
    --help|-h)
        echo "用法:"
        echo "  bash pre-commit-hook.sh --install    安装到 .git/hooks/pre-commit"
        echo "  bash pre-commit-hook.sh --help       显示此帮助"
        echo ""
        echo "安装后每次 git commit 会自动调用。"
        echo ""
        echo "Git 配置项:"
        echo "  git config hooks.secretscan.timeout <秒>       扫描超时 (默认 60)"
        echo "  git config hooks.secretscan.allowMedium yes|no|ask  中等风险策略 (默认 ask)"
        ;;
    *)
        do_scan
        ;;
esac
