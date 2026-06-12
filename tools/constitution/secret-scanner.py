#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
secret-scanner.py — 敏感信息扫描工具
======================================

配套方法论文档：CONSTITUTION.md (Hermes Agent 核心准则)
对应规则：
  - TOKEN-01: API Token/Secret/Webhook URL 禁止出现在 Git 提交中
  - TOKEN-02: 展示时用 [REDACTED] 或环境变量占位符替换
  - TOKEN-04: 脚本中 Token 一律通过文件读取或环境变量注入，禁止硬编码
  - TOKEN-05: 飞书 Webhook URL 只存储于文件，不拼接到命令行
  - GIT-02: 提交前必须检查 staged 内容不含敏感信息

用途：扫描指定文件/目录中的敏感信息（Token、密钥、Webhook URL 等），
      支持自动修复（--fix），输出扫描统计与风险等级。
      可作为 Git pre-commit hook 或 CI 流水线中的安全检查环节使用。

用法：
  python3 secret-scanner.py <路径> [--fix] [--verbose] [--quiet] [--json]

作者：Hermes Agent
日期：2026-06-13
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple


# ============================================================================
# 风险等级定义
# ============================================================================

class RiskLevel(Enum):
    """敏感信息风险等级，对应 CONSTITUTION.md 的三层规则体系。"""
    HIGH = "HIGH"       # 🔴 铁律级别 — 必须阻止
    MEDIUM = "MEDIUM"   # 🟡 约定级别 — 警告但允许
    LOW = "LOW"         # 🟢 建议级别 — 仅提示


# ============================================================================
# 命中记录
# ============================================================================

@dataclass
class Finding:
    """单条敏感信息命中记录。"""
    file_path: str
    line_number: int
    line_content: str
    pattern_name: str
    risk_level: RiskLevel
    matched_value: str       # 实际匹配到的值（用于 --fix 替换）
    suggestion: str = ""


# ============================================================================
# 扫描规则定义
# 参考 CONSTITUTION.md § TOKEN-01 ~ TOKEN-05, GIT-01 ~ GIT-02
# ============================================================================

SCAN_RULES = [
    # ── GitHub Token ──
    {
        "name": "GitHub Personal Access Token (classic)",
        "pattern": r'ghp_[a-zA-Z0-9]{36}',
        "risk": RiskLevel.HIGH,
        "suggestion": "移除硬编码的 GitHub Token，改用 ~/.git-credentials 或 GH_TOKEN 环境变量 (TOKEN-03)",
    },
    {
        "name": "GitHub Personal Access Token (fine-grained)",
        "pattern": r'github_pat_[a-zA-Z0-9_]{22,}',
        "risk": RiskLevel.HIGH,
        "suggestion": "移除硬编码的 GitHub Token，改用 ~/.git-credentials 或 GH_TOKEN 环境变量 (TOKEN-03)",
    },
    {
        "name": "GitHub OAuth Token",
        "pattern": r'gho_[a-zA-Z0-9]{36}',
        "risk": RiskLevel.HIGH,
        "suggestion": "移除硬编码的 OAuth Token，改用环境变量注入 (TOKEN-03)",
    },

    # ── 飞书 / Lark Webhook ──
    {
        "name": "Feishu/Lark Webhook URL",
        "pattern": r'https://open\.feishu\.cn/open-apis/bot/v2/hook/[a-z0-9\-]{36,}',
        "risk": RiskLevel.HIGH,
        "suggestion": "Webhook URL 只存储于文件，通过 -d @file 注入 curl，禁止硬编码或拼接在命令行中 (TOKEN-05)",
    },
    {
        "name": "Lark (国际版) Webhook URL",
        "pattern": r'https://open\.larksuite\.com/open-apis/bot/v2/hook/[a-z0-9\-]{36,}',
        "risk": RiskLevel.HIGH,
        "suggestion": "Webhook URL 只存储于文件，通过 -d @file 注入 curl (TOKEN-05)",
    },

    # ── 通用 API Key ──
    {
        "name": "API Key 赋值",
        "pattern": r'(?i)(?:api[_-]?key|apikey)\s*[:=]\s*["\']([^"\'\s]{8,})["\']',
        "risk": RiskLevel.HIGH,
        "suggestion": "API Key 通过环境变量注入，禁止硬编码在源码中 (TOKEN-04)",
    },
    {
        "name": "API Key 变量赋值（无引号）",
        "pattern": r'(?i)(?:api[_-]?key|apikey)\s*[:=]\s*([^\s"\'#]{16,})',
        "risk": RiskLevel.HIGH,
        "suggestion": "API Key 通过环境变量注入，禁止硬编码 (TOKEN-04)",
    },

    # ── 密码 / Secret ──
    {
        "name": "密码硬编码",
        "pattern": r'(?i)(?:password|passwd|pwd)\s*[:=]\s*["\']([^"\']{3,})["\']',
        "risk": RiskLevel.HIGH,
        "suggestion": "密码从环境变量或密钥管理服务获取，禁止硬编码 (TOKEN-01)",
    },
    {
        "name": "Secret 硬编码",
        "pattern": r'(?i)(?:secret|secret_key|secretkey)\s*[:=]\s*["\']([^"\']{8,})["\']',
        "risk": RiskLevel.HIGH,
        "suggestion": "Secret 通过环境变量或 vault 注入，禁止硬编码 (TOKEN-01)",
    },

    # ── 通用 Token 模式 ──
    {
        "name": "Token 硬编码",
        "pattern": r'(?i)(?:token|access_token|auth_token|bearer)\s*[:=]\s*["\']([^"\']{12,})["\']',
        "risk": RiskLevel.MEDIUM,
        "suggestion": "Token 通过环境变量注入，禁止硬编码在源码中 (TOKEN-04)",
    },

    # ── AWS / Cloud 凭证 ──
    {
        "name": "AWS Access Key ID",
        "pattern": r'(?<![A-Z0-9])AKIA[0-9A-Z]{16}(?![A-Z0-9])',
        "risk": RiskLevel.HIGH,
        "suggestion": "AWS 凭证通过 ~/.aws/credentials 或环境变量管理，禁止硬编码",
    },
    {
        "name": "AWS Secret Access Key",
        "pattern": r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[:=]\s*["\']([^"\']{20,})["\']',
        "risk": RiskLevel.HIGH,
        "suggestion": "AWS 凭证通过 ~/.aws/credentials 或环境变量管理",
    },

    # ── 私钥 ──
    {
        "name": "RSA 私钥",
        "pattern": r'-----BEGIN\s+(?:RSA\s+)?PRIVATE KEY-----',
        "risk": RiskLevel.HIGH,
        "suggestion": "私钥不应出现在源码文件中，使用环境变量或密钥管理服务 (GIT-01)",
    },
    {
        "name": "EC 私钥",
        "pattern": r'-----BEGIN\s+EC\s+PRIVATE KEY-----',
        "risk": RiskLevel.HIGH,
        "suggestion": "私钥不应出现在源码文件中 (GIT-01)",
    },
    {
        "name": "OpenSSH 私钥",
        "pattern": r'-----BEGIN\s+OPENSSH\s+PRIVATE KEY-----',
        "risk": RiskLevel.HIGH,
        "suggestion": "SSH 私钥不应出现在源码中，应存储在 ~/.ssh/ 目录 (SYS-02)",
    },

    # ── 连接串 ──
    {
        "name": "数据库连接串（含密码）",
        "pattern": r'(?i)(?:mysql|postgres(?:ql)?|mongodb|redis)://[^:]+:[^@]+@',
        "risk": RiskLevel.HIGH,
        "suggestion": "数据库密码从环境变量注入，不要硬编码在连接串中 (SYS-05)",
    },
    {
        "name": "JDBC 连接串（含密码）",
        "pattern": r'(?i)jdbc:[a-z]+://[^:]+:[^@;/]+@',
        "risk": RiskLevel.HIGH,
        "suggestion": "数据库密码从环境变量注入 (SYS-05)",
    },

    # ── 内部 IP ──
    {
        "name": "内网 IP 地址",
        "pattern": r'\b(?:10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}\b',
        "risk": RiskLevel.LOW,
        "suggestion": "避免在公开仓库中暴露内部 IP 地址 (SYS-05)",
    },

    # ── JWT Token ──
    {
        "name": "JWT Token",
        "pattern": r'(?i)eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}',
        "risk": RiskLevel.MEDIUM,
        "suggestion": "JWT Token 不应硬编码或提交到仓库",
    },

    # ── Slack Webhook ──
    {
        "name": "Slack Webhook URL",
        "pattern": r'https://hooks\.slack\.com/services/T[a-zA-Z0-9_]+/B[a-zA-Z0-9_]+/[a-zA-Z0-9_]+',
        "risk": RiskLevel.HIGH,
        "suggestion": "Slack Webhook URL 不应硬编码，从环境变量注入",
    },

    # ── 通用 Bearer Token（字符串中） ──
    {
        "name": "Authorization Header Bearer Token",
        "pattern": r'(?i)authorization["\s:]*bearer\s+["\']?([a-zA-Z0-9_\-\.]{20,})["\']?',
        "risk": RiskLevel.MEDIUM,
        "suggestion": "Bearer Token 从环境变量注入，禁止硬编码 (TOKEN-04)",
    },
]


# ============================================================================
# 文件过滤
# ============================================================================

# 忽略的目录
IGNORED_DIRS = {
    '.git', '__pycache__', 'node_modules', '.venv', 'venv',
    '.tox', '.eggs', '*.egg-info', '.mypy_cache', '.pytest_cache',
    '.ruff_cache', 'dist', 'build', '.DS_Store',
}

# 忽略的文件扩展名（二进制等）
IGNORED_EXTENSIONS = {
    '.pyc', '.pyo', '.so', '.dll', '.exe', '.bin',
    '.jpg', '.jpeg', '.png', '.gif', '.ico', '.svg',
    '.mp3', '.mp4', '.avi', '.mov', '.wav',
    '.zip', '.tar', '.gz', '.bz2', '.7z', '.rar',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx',
    '.ttf', '.woff', '.woff2', '.eot',
    '.db', '.sqlite', '.sqlite3',
    '.min.js', '.min.css',
}


def should_skip_file(file_path: Path) -> bool:
    """根据扩展名和目录判断是否跳过文件。"""
    # 跳过隐藏文件（除了 .env* 等可能需要扫描的）
    if file_path.name.startswith('.') and not file_path.name.startswith('.env'):
        return True

    # 跳过忽略的扩展名
    if file_path.suffix.lower() in IGNORED_EXTENSIONS:
        return True

    # 跳过忽略的目录
    for part in file_path.parts[:-1]:
        if part in IGNORED_DIRS:
            return True

    # 跳过过大文件 (>10MB)
    try:
        if file_path.stat().st_size > 10 * 1024 * 1024:
            return True
    except OSError:
        return True

    return False


def collect_files(target: Path) -> List[Path]:
    """递归收集需要扫描的文件。"""
    files = []
    if target.is_file():
        if not should_skip_file(target):
            files.append(target)
    elif target.is_dir():
        for root, dirs, filenames in os.walk(target):
            # 过滤目录
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
            root_path = Path(root)
            for fname in filenames:
                fpath = root_path / fname
                if not should_skip_file(fpath):
                    files.append(fpath)
    return sorted(files)


# ============================================================================
# 扫描引擎
# ============================================================================

def scan_file(file_path: Path, fix: bool = False) -> List[Finding]:
    """扫描单个文件，返回命中列表。若 fix=True，对匹配值执行替换。"""
    findings: List[Finding] = []

    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError):
        return findings

    modified = False
    new_lines = list(lines)

    for line_idx, original_line in enumerate(lines):
        line_number = line_idx + 1
        line_stripped = original_line.rstrip('\n\r')

        for rule in SCAN_RULES:
            pattern = rule["pattern"]
            matches = list(re.finditer(pattern, line_stripped))

            for match in matches:
                # 对于有捕获组的模式，group(1) 是实际密钥值，group(0) 是完整匹配
                # 用于显示：展示完整匹配；用于修复：只替换密钥值本身
                full_match = match.group(0)
                if match.lastindex and match.lastindex >= 1:
                    secret_value = match.group(1)  # 仅密钥值
                else:
                    secret_value = full_match  # 完整匹配即为密钥

                finding = Finding(
                    file_path=str(file_path),
                    line_number=line_number,
                    line_content=line_stripped.strip(),
                    pattern_name=rule["name"],
                    risk_level=rule["risk"],
                    matched_value=full_match,
                    suggestion=rule["suggestion"],
                )
                findings.append(finding)

                # --fix: 只替换密钥值本身，保留变量名和引号结构
                if fix and secret_value:
                    new_lines[line_idx] = new_lines[line_idx].replace(
                        secret_value, "[REDACTED]", 1
                    )
                    modified = True

    # 写回修复后的文件
    if fix and modified:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
        except OSError as e:
            print(f"⚠ 无法写入修复后的文件 {file_path}: {e}", file=sys.stderr)

    return findings


# ============================================================================
# 输出格式化
# ============================================================================

def print_findings(findings: List[Finding], verbose: bool = False):
    """以人类可读格式输出扫描结果。"""
    if not findings:
        return

    # 按风险等级分组
    high = [f for f in findings if f.risk_level == RiskLevel.HIGH]
    medium = [f for f in findings if f.risk_level == RiskLevel.MEDIUM]
    low = [f for f in findings if f.risk_level == RiskLevel.LOW]

    # 按文件分组
    by_file: dict = {}
    for f in findings:
        by_file.setdefault(f.file_path, []).append(f)

    for file_path, file_findings in by_file.items():
        print(f"\n📄 {file_path}")
        for f in file_findings:
            icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}[f.risk_level.value]
            print(f"  {icon} L{f.line_number:04d} [{f.risk_level.value}] {f.pattern_name}")
            if verbose:
                preview = f.line_content[:120]
                if len(f.line_content) > 120:
                    preview += "..."
                print(f"      内容: {preview}")
                if f.suggestion:
                    print(f"      建议: {f.suggestion}")

    # 汇总
    print(f"\n{'='*60}")
    print(f"扫描统计: 🔴 HIGH={len(high)}  🟡 MEDIUM={len(medium)}  🟢 LOW={len(low)}  总计={len(findings)}")
    print(f"{'='*60}")


def overall_risk(findings: List[Finding]) -> RiskLevel:
    """计算综合风险等级：取最高级别。"""
    if not findings:
        return RiskLevel.LOW
    levels = {f.risk_level for f in findings}
    if RiskLevel.HIGH in levels:
        return RiskLevel.HIGH
    if RiskLevel.MEDIUM in levels:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def output_json(findings: List[Finding], files_scanned: int):
    """JSON 格式输出。"""
    result = {
        "scan_summary": {
            "files_scanned": files_scanned,
            "total_findings": len(findings),
            "high": sum(1 for f in findings if f.risk_level == RiskLevel.HIGH),
            "medium": sum(1 for f in findings if f.risk_level == RiskLevel.MEDIUM),
            "low": sum(1 for f in findings if f.risk_level == RiskLevel.LOW),
            "overall_risk": overall_risk(findings).value,
        },
        "findings": [
            {
                "file": f.file_path,
                "line": f.line_number,
                "pattern": f.pattern_name,
                "risk": f.risk_level.value,
                "matched": f.matched_value,
                "suggestion": f.suggestion,
            }
            for f in findings
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


# ============================================================================
# 入口
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="secret-scanner.py — 敏感信息扫描工具（CONSTITUTION.md 配套脚本）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 secret-scanner.py src/
  python3 secret-scanner.py . --fix
  python3 secret-scanner.py config.yaml --verbose
  python3 secret-scanner.py . --json --quiet
        """,
    )
    parser.add_argument(
        "target",
        nargs="+",
        help="要扫描的文件或目录路径",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="自动将匹配到的敏感值替换为 [REDACTED]",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="输出详细内容（匹配行内容和修复建议）",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="静默模式，仅输出 JSON（需配合 --json）或无输出",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出扫描结果",
    )

    args = parser.parse_args()

    # 收集文件
    all_files: List[Path] = []
    for target_str in args.target:
        target_path = Path(target_str).resolve()
        if not target_path.exists():
            print(f"⚠ 路径不存在，跳过: {target_str}", file=sys.stderr)
            continue
        all_files.extend(collect_files(target_path))

    if not all_files:
        if not args.quiet:
            print("ℹ 没有找到可扫描的文件。")
        if args.json:
            output_json([], 0)
        sys.exit(0)

    # 扫描
    all_findings: List[Finding] = []
    for file_path in all_files:
        findings = scan_file(file_path, fix=args.fix)
        all_findings.extend(findings)

    # 输出
    if args.json:
        output_json(all_findings, len(all_files))
    elif not args.quiet:
        if all_findings:
            print_findings(all_findings, verbose=args.verbose)
        else:
            print(f"✅ 已扫描 {len(all_files)} 个文件，未发现敏感信息。")

    # 退出码：HIGH → 1，MEDIUM → 2，LOW/无 → 0
    risk = overall_risk(all_findings)
    if risk == RiskLevel.HIGH:
        sys.exit(1)
    elif risk == RiskLevel.MEDIUM:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
