#!/usr/bin/env python3
"""
preflight-check.py — 产前验证脚本 (Pre-flight Verification)

依据方法论文档: MULTI-AGENT-COORDINATION.md § 产前验证（Phase 2.5）

在委派部门之前强制执行 4 项检查：
  1. 路径可及性 — 绝对路径是否存在/可写
  2. 依赖文件就绪 — 初始文件是否已就位
  3. 跨部门路径一致性 — 多个子 Agent 引用同一文件的路径是否一致
  4. 预检清单 — 自定义检查项

输出结构化报告，标注 PASS/FAIL/WARN。
失败项给出修复建议。

Usage:
  echo '{"work_dir":"...","deps":["..."],"cross_refs":{...},"checklist":[...]}' | python3 preflight-check.py
  python3 preflight-check.py --input check_config.json
"""

import json
import os
import sys
import argparse
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 颜色 (ANSI, 终端输出用)
# ---------------------------------------------------------------------------

class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


# ---------------------------------------------------------------------------
# 检查项 1: 路径可及性
# ---------------------------------------------------------------------------

def check_path_accessibility(work_dir: str) -> Dict[str, Any]:
    """检查绝对路径是否存在、可读、可写。

    Args:
        work_dir: 工作目录的绝对路径

    Returns:
        {"pass": ..., "status": "PASS|FAIL|WARN", "checks": [...], "suggestion": ...}
    """
    checks = []
    all_pass = True

    # 检查路径是否为绝对路径
    is_absolute = os.path.isabs(work_dir)
    if is_absolute:
        checks.append({
            "item": f"绝对路径: {work_dir}",
            "result": "PASS",
            "message": "是绝对路径"
        })
    else:
        checks.append({
            "item": f"绝对路径: {work_dir}",
            "result": "FAIL",
            "message": f"不是绝对路径，请使用如 /home/user/project 或 C:\\Users\\..."
        })
        all_pass = False

    # 检查是否存在
    exists = os.path.exists(work_dir)
    if exists:
        checks.append({
            "item": f"路径存在性: {work_dir}",
            "result": "PASS",
            "message": "路径存在"
        })
    else:
        checks.append({
            "item": f"路径存在性: {work_dir}",
            "result": "FAIL",
            "message": "路径不存在",
        })
        all_pass = False

    # 检查是否为目录
    if exists:
        is_dir = os.path.isdir(work_dir)
        if is_dir:
            checks.append({
                "item": f"目录类型: {work_dir}",
                "result": "PASS",
                "message": "确认为目录"
            })
        else:
            checks.append({
                "item": f"目录类型: {work_dir}",
                "result": "FAIL",
                "message": "路径存在但不是目录"
            })
            all_pass = False

    # 检查可读性
    if exists:
        readable = os.access(work_dir, os.R_OK)
        if readable:
            checks.append({
                "item": f"可读: {work_dir}",
                "result": "PASS",
                "message": "目录可读"
            })
        else:
            checks.append({
                "item": f"可读: {work_dir}",
                "result": "FAIL",
                "message": "目录不可读"
            })
            all_pass = False

    # 检查可写性
    if exists:
        writable = os.access(work_dir, os.W_OK)
        if writable:
            checks.append({
                "item": f"可写: {work_dir}",
                "result": "PASS",
                "message": "目录可写"
            })
        else:
            checks.append({
                "item": f"可写: {work_dir}",
                "result": "WARN",
                "message": "目录不可写 — 子 Agent 可能无法创建文件"
            })
            # 可写失败不算 all_pass 失败，因为可能是只读部署策略

    # 生成修复建议
    suggestions = []
    if not is_absolute:
        suggestions.append("将 work_dir 改为绝对路径，如 /home/user/project 或 C:\\Users\\...")
    if not exists:
        suggestions.append(f"创建目录: mkdir -p {work_dir}")
    if exists and not os.path.isdir(work_dir):
        suggestions.append(f"路径不是目录，请确认 {work_dir} 是否为正确的目录路径")
    if exists and not os.access(work_dir, os.R_OK):
        suggestions.append(f"修改权限: chmod +r {work_dir}")

    return {
        "check": "路径可及性",
        "pass": all_pass,
        "status": "PASS" if all_pass else "FAIL",
        "details": checks,
        "suggestion": "; ".join(suggestions) if suggestions else None,
    }


# ---------------------------------------------------------------------------
# 检查项 2: 依赖文件就绪
# ---------------------------------------------------------------------------

def check_dependency_files(work_dir: str, deps: List[str]) -> Dict[str, Any]:
    """检查依赖文件是否已就位。

    Args:
        work_dir: 工作目录
        deps:     依赖文件列表（相对/绝对路径）

    Returns:
        {"pass": ..., "status": ..., "details": [...], "suggestion": ...}
    """
    details = []
    all_pass = True
    missing = []

    if not deps:
        return {
            "check": "依赖文件就绪",
            "pass": True,
            "status": "PASS",
            "details": [{"item": "无依赖文件", "result": "PASS", "message": "依赖列表为空"}],
            "suggestion": None,
        }

    for dep_path in deps:
        # 如果是相对路径，拼接到 work_dir
        full_path = dep_path if os.path.isabs(dep_path) else os.path.join(work_dir, dep_path)
        exists = os.path.exists(full_path)

        if exists:
            is_file = os.path.isfile(full_path)
            if is_file:
                try:
                    size = os.path.getsize(full_path)
                    if size > 0:
                        details.append({
                            "item": dep_path,
                            "resolved": full_path,
                            "result": "PASS",
                            "message": f"文件存在 ({size} bytes)"
                        })
                    else:
                        details.append({
                            "item": dep_path,
                            "resolved": full_path,
                            "result": "WARN",
                            "message": "文件存在但为空 (0 bytes)"
                        })
                except OSError:
                    details.append({
                        "item": dep_path,
                        "resolved": full_path,
                        "result": "WARN",
                        "message": "文件存在但大小不可读"
                    })
            else:
                details.append({
                    "item": dep_path,
                    "resolved": full_path,
                    "result": "PASS",
                    "message": "目录存在"
                })
        else:
            details.append({
                "item": dep_path,
                "resolved": full_path,
                "result": "FAIL",
                "message": "文件不存在"
            })
            missing.append(dep_path)
            all_pass = False

    suggestions = []
    if missing:
        suggestions.append(f"缺失文件: {', '.join(missing)}")
        suggestions.append("检查文件路径是否正确，或者先运行生成这些文件的步骤")

    return {
        "check": "依赖文件就绪",
        "pass": all_pass,
        "status": "PASS" if all_pass else "FAIL",
        "details": details,
        "suggestion": "; ".join(suggestions) if suggestions else None,
    }


# ---------------------------------------------------------------------------
# 检查项 3: 跨部门路径一致性
# ---------------------------------------------------------------------------

def check_cross_dept_consistency(
    cross_refs: Dict[str, List[str]]
) -> Dict[str, Any]:
    """检查多个子 Agent 引用同一逻辑文件时路径是否一致。

    输入格式:
      {
        "config.json": [
          "dev: /project/config.json",
          "ops: /project/config/config.json",
          "test: /project/config.json"
        ]
      }

    规则:
      - 所有路径标准化后应完全相同
      - 标准化: os.path.normpath, 去末尾 /
      - 不一致时标记 WARN 或 FAIL

    Returns:
        {"pass": ..., "status": ..., "details": [...], "suggestion": ...}
    """
    if not cross_refs:
        return {
            "check": "跨部门路径一致性",
            "pass": True,
            "status": "PASS",
            "details": [{"item": "无跨部门引用", "result": "PASS", "message": "未提供跨部门引用信息"}],
            "suggestion": None,
        }

    details = []
    all_consistent = True
    all_absolute = True
    conflicts = []

    for logical_name, agent_paths in cross_refs.items():
        # agent_paths: ["agent_name: /some/path", ...]
        parsed = []
        for entry in agent_paths:
            if ':' in entry:
                agent, path = entry.split(':', 1)
                agent = agent.strip()
                path = path.strip()
            else:
                agent = "unknown"
                path = entry.strip()
            normalized = os.path.normpath(path).rstrip('/').rstrip('\\')
            parsed.append({"agent": agent, "raw": path, "normalized": normalized})
            if not os.path.isabs(normalized):
                all_absolute = False

        # 检查所有 normalized 路径是否一致
        unique_paths = list(set(p["normalized"] for p in parsed))
        if len(unique_paths) == 1:
            details.append({
                "item": logical_name,
                "result": "PASS",
                "message": f"路径一致: {unique_paths[0]}",
                "agents": [p["agent"] for p in parsed],
            })
        else:
            all_consistent = False
            conflict_detail = {
                "logical_file": logical_name,
                "variants": {},
            }
            for p in parsed:
                conflict_detail["variants"].setdefault(p["normalized"], []).append(p["agent"])
            conflicts.append(conflict_detail)

            detail_msg = f"路径不一致 — 变体: {list(conflict_detail['variants'].keys())[:5]}"
            details.append({
                "item": logical_name,
                "result": "FAIL",
                "message": detail_msg,
                "agents": {norm: agents for norm, agents in conflict_detail["variants"].items()},
            })

    suggestions = []
    if conflicts:
        for c in conflicts:
            variants = list(c["variants"].keys())
            suggested = variants[0]  # 建议选第一个
            affected = []
            for v, agents in c["variants"].items():
                if v != suggested:
                    affected.extend(agents)
            suggestions.append(
                f"{c['logical_file']}: 统一使用 '{suggested}'，"
                f"受影响: {', '.join(affected)}"
            )
    if not all_absolute:
        suggestions.append("部分路径不是绝对路径，建议全部使用绝对路径避免歧义")

    return {
        "check": "跨部门路径一致性",
        "pass": all_consistent,
        "status": "PASS" if all_consistent else "FAIL",
        "details": details,
        "suggestion": "; ".join(suggestions) if suggestions else None,
    }


# ---------------------------------------------------------------------------
# 检查项 4: 预检清单
# ---------------------------------------------------------------------------

def check_custom_checklist(
    work_dir: str, checklist: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """执行自定义预检清单。

    每项格式:
      {
        "name": "检查项名称",
        "type": "file_exists" | "command" | "env_var" | "contains",
        "target": "目标路径或命令或环境变量名",
        "expected": "期望值 (type=contains 时)",
        "required": true/false
      }

    Returns:
        {"pass": ..., "status": ..., "details": [...], "suggestion": ...}
    """
    if not checklist:
        return {
            "check": "预检清单",
            "pass": True,
            "status": "PASS",
            "details": [{"item": "无自定义检查项", "result": "PASS", "message": "清单为空"}],
            "suggestion": None,
        }

    details = []
    all_pass = True
    suggestions = []

    for item in checklist:
        name = item.get("name", "未命名检查项")
        check_type = item.get("type", "file_exists")
        target = item.get("target", "")
        expected = item.get("expected", None)
        required = item.get("required", True)

        try:
            if check_type == "file_exists":
                full_target = target if os.path.isabs(target) else os.path.join(work_dir, target)
                ok = os.path.exists(full_target)
                if ok:
                    details.append({
                        "item": name,
                        "result": "PASS",
                        "message": f"文件存在: {full_target}"
                    })
                else:
                    details.append({
                        "item": name,
                        "result": "FAIL" if required else "WARN",
                        "message": f"文件不存在: {full_target}"
                    })
                    if required:
                        all_pass = False
                        suggestions.append(f"确保文件 {target} 存在并重新运行验证")

            elif check_type == "env_var":
                ok = target in os.environ
                val = os.environ.get(target, "")
                if ok:
                    details.append({
                        "item": name,
                        "result": "PASS",
                        "message": f"环境变量 {target}={val}"
                    })
                else:
                    details.append({
                        "item": name,
                        "result": "FAIL" if required else "WARN",
                        "message": f"环境变量 {target} 未设置"
                    })
                    if required:
                        all_pass = False
                        suggestions.append(f"设置环境变量: export {target}=<值>")

            elif check_type == "contains":
                full_target = target if os.path.isabs(target) else os.path.join(work_dir, target)
                if not os.path.isfile(full_target):
                    details.append({
                        "item": name,
                        "result": "FAIL" if required else "WARN",
                        "message": f"目标文件不存在: {full_target}，无法检查内容"
                    })
                    if required:
                        all_pass = False
                        suggestions.append(f"先创建文件 {target}")
                else:
                    with open(full_target, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                    if expected and expected in content:
                        details.append({
                            "item": name,
                            "result": "PASS",
                            "message": f"在 {target} 中找到期望内容: '{expected[:80]}'"
                        })
                    else:
                        details.append({
                            "item": name,
                            "result": "FAIL" if required else "WARN",
                            "message": f"在 {target} 中未找到期望内容: '{expected[:80]}'"
                        })
                        if required:
                            all_pass = False
                            suggestions.append(f"在 {target} 中确保包含: {expected}")

            else:
                details.append({
                    "item": name,
                    "result": "WARN",
                    "message": f"未知检查类型: {check_type}，已跳过"
                })

        except Exception as e:
            details.append({
                "item": name,
                "result": "FAIL",
                "message": f"检查执行异常: {e}"
            })
            all_pass = False
            suggestions.append(f"修复 {name} 的检查配置: {e}")

    return {
        "check": "预检清单",
        "pass": all_pass,
        "status": "PASS" if all_pass else "FAIL",
        "details": details,
        "suggestion": "; ".join(suggestions) if suggestions else None,
    }


# ---------------------------------------------------------------------------
# 主入口: 执行全部 4 项产前检查
# ---------------------------------------------------------------------------

def run_preflight(config: Dict[str, Any]) -> Dict[str, Any]:
    """执行完整产前验证。

    输入 config:
      {
        "work_dir": "/absolute/path/to/project",
        "deps": ["file1.py", "config.json", ...],
        "cross_refs": {
          "logical_file_name": ["agent_a: /path/x", "agent_b: /path/y", ...]
        },
        "checklist": [
          {"name": "...", "type": "file_exists|env_var|contains", "target": "...", "expected": "...", "required": true}
        ]
      }

    返回完整报告。
    """
    work_dir = config.get("work_dir", "")
    deps = config.get("deps", [])
    cross_refs = config.get("cross_refs", {})
    checklist = config.get("checklist", [])

    results = [
        check_path_accessibility(work_dir),
        check_dependency_files(work_dir, deps),
        check_cross_dept_consistency(cross_refs),
        check_custom_checklist(work_dir, checklist),
    ]

    all_pass = all(r["pass"] for r in results)
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    warn_count = sum(1 for r in results if r["status"] == "WARN")

    return {
        "report": "产前验证报告",
        "timestamp": datetime.now().isoformat(),
        "work_dir": work_dir,
        "overall": "PASS" if all_pass else "FAIL",
        "summary": {
            "total_checks": len(results),
            "passed": sum(1 for r in results if r["status"] == "PASS"),
            "failed": fail_count,
            "warned": warn_count,
        },
        "sections": results,
        "verdict": (
            "✓ 所有产前检查通过，可以委派部门"
            if all_pass
            else f"✗ {fail_count} 项 FAIL, {warn_count} 项 WARN — 建议修复后再委派"
        ),
    }


# ---------------------------------------------------------------------------
# 格式化输出
# ---------------------------------------------------------------------------

def format_report(report: Dict[str, Any], use_color: bool = True) -> str:
    """将报告格式化为可读文本。"""
    lines = []
    c = Colors if use_color else type('NoColor', (), {
        'GREEN': '', 'RED': '', 'YELLOW': '', 'CYAN': '', 'RESET': '', 'BOLD': ''
    })()

    lines.append(f"{c.BOLD}{'='*60}{c.RESET}")
    lines.append(f"{c.BOLD}  产前验证报告 (Pre-flight Verification){c.RESET}")
    lines.append(f"{c.BOLD}{'='*60}{c.RESET}")
    lines.append(f"  时间:     {report['timestamp']}")
    lines.append(f"  工作目录: {report['work_dir']}")
    lines.append(f"  总体结果: {c.GREEN if report['overall']=='PASS' else c.RED}{report['overall']}{c.RESET}")
    lines.append(f"  通过/失败/警告: {report['summary']['passed']}/{report['summary']['failed']}/{report['summary']['warned']}")
    lines.append("")

    for i, section in enumerate(report["sections"], 1):
        icon = "✓" if section["status"] == "PASS" else ("⚠" if section["status"] == "WARN" else "✗")
        status_color = c.GREEN if section["status"] == "PASS" else (c.YELLOW if section["status"] == "WARN" else c.RED)
        lines.append(f"{c.BOLD}{i}. {section['check']}{c.RESET} {status_color}[{section['status']}]{c.RESET} {icon}")

        for detail in section.get("details", []):
            d_icon = "  ✓" if detail["result"] == "PASS" else ("  ⚠" if detail["result"] == "WARN" else "  ✗")
            d_color = c.GREEN if detail["result"] == "PASS" else (c.YELLOW if detail["result"] == "WARN" else c.RED)
            lines.append(f"    {d_color}{d_icon}{c.RESET} {detail['item']}: {detail['message']}")

        if section.get("suggestion"):
            lines.append(f"    {c.CYAN}💡 修复建议: {section['suggestion']}{c.RESET}")

        lines.append("")

    lines.append(f"{c.BOLD}{'='*60}{c.RESET}")
    lines.append(f"  {c.BOLD}结论: {report['verdict']}{c.RESET}")
    lines.append(f"{c.BOLD}{'='*60}{c.RESET}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="产前验证 (Pre-flight Check) — MULTI-AGENT-COORDINATION.md Phase 2.5",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  echo '{"work_dir":"...","deps":[...],"cross_refs":{...},"checklist":[...]}' | python3 preflight-check.py
  python3 preflight-check.py --input check_config.json
  python3 preflight-check.py --input check_config.json --json
        """,
    )
    parser.add_argument(
        "--input", "-i",
        help="JSON 配置文件路径 (不指定则从 stdin 读取)",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="输出纯 JSON 格式（默认输出可读文本）",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="禁用颜色输出",
    )
    args = parser.parse_args()

    # 读取配置
    if args.input:
        try:
            with open(args.input, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except FileNotFoundError:
            print(f"错误: 配置文件不存在: {args.input}", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"错误: JSON 解析失败: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            raw = sys.stdin.read()
        except KeyboardInterrupt:
            sys.exit(1)
        if not raw.strip():
            print("错误: 无输入。请通过 stdin 传入 JSON 配置或使用 --input", file=sys.stderr)
            sys.exit(1)
        try:
            config = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"错误: JSON 解析失败: {e}", file=sys.stderr)
            sys.exit(1)

    # 执行验证
    report = run_preflight(config)

    # 输出
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_report(report, use_color=not args.no_color))

    # 退出码
    sys.exit(0 if report["overall"] == "PASS" else 1)


if __name__ == "__main__":
    main()
