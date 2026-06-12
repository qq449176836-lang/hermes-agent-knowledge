#!/usr/bin/env python3
"""
usage-stats.py — Skill 使用频率统计与自适应升级/降级

对应方法论文档：EVOLUTION-ENGINE.md
  - 模块 2: AutoLoader — 频率自适应机制
  - "高频使用（30 天内 >=5 次）→ 提升到 Always-On"
  - "低频使用（连续 2 月 0 次）→ 降级为 On-Demand"
  - "引擎自身标记为 Critical，永不降级（自举防止退化）"

读取 hermes-home/usage.json，统计每个 Skill 的 30/60/90 天调用次数，
按频率规则生成升级/降级/归档建议，输出 JSON 报告。

Usage:
    python usage-stats.py [--hermes-home PATH] [--apply] [--json]

Options:
    --hermes-home PATH    Hermes 根目录 (默认: ~/.hermes)
    --apply               自动应用升级/降级到 usage.json 和 auto-load.json
    --json                仅输出 JSON（无人类可读摘要）
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CRITICAL_PRIORITY = "critical"
LEVEL_ALWAYS_ON = "always_on"
LEVEL_CONTEXT_RULES = "context_rules"
LEVEL_ON_DEMAND = "on_demand"

# Thresholds (from EVOLUTION-ENGINE.md)
UPGRADE_THRESHOLD_30D = 5       # 30天内 >=5次 → Always-On
DOWNGRADE_MONTHS_IDLE = 2       # 连续2月0次 → On-Demand
ARCHIVE_MONTHS_IDLE = 6         # 6月0次 → 归档建议

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resolve_hermes_home(hermes_home: Optional[str] = None) -> Path:
    """Resolve HERMES_HOME: explicit path > env var > ~/.hermes default."""
    if hermes_home:
        return Path(os.path.expanduser(hermes_home))
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(os.path.expanduser(env))
    return Path.home() / ".hermes"


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    """Load JSON file, return None if missing or invalid."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_json(path: Path, data: Dict[str, Any]) -> bool:
    """Atomically save JSON (write to temp then rename)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
        return True
    except OSError:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return False


def parse_iso_date(s: Optional[str]) -> Optional[datetime]:
    """Parse ISO-8601 datetime string, return None on failure/None."""
    if not s:
        return None
    try:
        # Handle 'Z' suffix and timezone offsets
        s_clean = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s_clean)
    except (ValueError, TypeError):
        return None


def _ensure_tz_aware(dt: datetime, ref: datetime) -> datetime:
    """If dt is naive, assume it's in the same timezone as ref."""
    if dt.tzinfo is None and ref.tzinfo is not None:
        return dt.replace(tzinfo=ref.tzinfo)
    if dt.tzinfo is not None and ref.tzinfo is None:
        return dt.replace(tzinfo=None)
    return dt


def categorize_uses(
    uses_history: List[str], now: datetime
) -> Tuple[int, int, int]:
    """
    Count uses in last 30, 60, 90 days from `now`.
    `uses_history` is a list of ISO-8601 timestamps of each use event.
    """
    uses_30d = uses_60d = uses_90d = 0
    for ts_str in uses_history:
        ts = parse_iso_date(ts_str)
        if ts is None:
            continue
        delta = now - ts
        days = delta.total_seconds() / 86400.0
        if days <= 30:
            uses_30d += 1
        if days <= 60:
            uses_60d += 1
        if days <= 90:
            uses_90d += 1
    return uses_30d, uses_60d, uses_90d


def months_since_last_use(
    last_used: Optional[str], now: datetime
) -> Optional[float]:
    """Return approximate months since last use (30.44-day months)."""
    ts = parse_iso_date(last_used)
    if ts is None:
        return None
    delta = now - ts
    return delta.total_seconds() / (86400.0 * 30.44)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def analyze_usage(
    hermes_home: Path, now: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Analyze usage.json and produce a full statistics + recommendation report.

    Returns a dict with:
      - generated_at, window_days, now
      - skills: per-skill stats with recommendations
      - summary: aggregated counts
    """
    if now is None:
        now = datetime.now().astimezone()

    usage_path = hermes_home / "usage.json"
    usage = load_json(usage_path)

    if usage is None:
        return {
            "error": "usage.json not found",
            "path": str(usage_path),
            "generated_at": now.isoformat(),
        }

    skills = usage.get("skills", {})
    report: Dict[str, Any] = {
        "generated_at": now.isoformat(),
        "source": str(usage_path),
        "source_window_days": usage.get("window_days", 30),
        "total_skills": len(skills),
        "skills": {},
        "summary": {
            "upgrade_candidates": [],
            "downgrade_candidates": [],
            "archive_candidates": [],
            "critical_skipped": [],
        },
    }

    for skill_name, skill_data in skills.items():
        priority = skill_data.get("priority", "")
        current_level = skill_data.get("current_level", LEVEL_ON_DEMAND)
        total_uses = skill_data.get("total_uses", 0)
        last_used = skill_data.get("last_used")
        first_used = skill_data.get("first_used")

        # Uses in windows (from usage_history if present, else estimate from total)
        usage_history = skill_data.get("usage_history", [])
        if usage_history:
            uses_30d, uses_60d, uses_90d = categorize_uses(usage_history, now)
        else:
            # Fallback: use uses_last_30d + zero for wider windows
            uses_30d = skill_data.get("uses_last_30d", 0)
            uses_60d = 0
            uses_90d = 0

        months_idle = months_since_last_use(last_used, now)

        # Determine recommendation
        recommendation = "keep"  # default
        reason = ""

        if priority == CRITICAL_PRIORITY:
            # Critical skills: never downgrade/archive (自举防止退化)
            recommendation = "keep_critical"
            reason = "引擎核心技能，永不降级（自举保证）"
            report["summary"]["critical_skipped"].append(skill_name)
        elif uses_30d >= UPGRADE_THRESHOLD_30D:
            if current_level != LEVEL_ALWAYS_ON:
                recommendation = "upgrade"
                reason = f"30天内使用 {uses_30d} 次（>= {UPGRADE_THRESHOLD_30D}），建议升级到 Always-On"
            else:
                recommendation = "keep"
                reason = "高频使用，已处于 Always-On"
        elif months_idle is not None and months_idle >= ARCHIVE_MONTHS_IDLE:
            recommendation = "archive"
            reason = f"连续 {months_idle:.1f} 月未使用（>= {ARCHIVE_MONTHS_IDLE}），建议归档"
        elif months_idle is not None and months_idle >= DOWNGRADE_MONTHS_IDLE:
            if current_level not in (LEVEL_ON_DEMAND,):
                recommendation = "downgrade"
                reason = f"连续 {months_idle:.1f} 月未使用（>= {DOWNGRADE_MONTHS_IDLE}），建议降级到 On-Demand"
            else:
                recommendation = "keep"
                reason = "低使用，已处于 On-Demand"
        else:
            recommendation = "keep"
            reason = "使用频率正常，维持当前层级"

        skill_report = {
            "total_uses": total_uses,
            "uses_last_30d": uses_30d,
            "uses_last_60d": uses_60d,
            "uses_last_90d": uses_90d,
            "first_used": first_used,
            "last_used": last_used,
            "months_idle": round(months_idle, 2) if months_idle is not None else None,
            "current_level": current_level,
            "priority": priority,
            "recommendation": recommendation,
            "reason": reason,
        }

        report["skills"][skill_name] = skill_report

        if recommendation == "upgrade":
            report["summary"]["upgrade_candidates"].append(skill_name)
        elif recommendation == "downgrade":
            report["summary"]["downgrade_candidates"].append(skill_name)
        elif recommendation == "archive":
            report["summary"]["archive_candidates"].append(skill_name)

    return report


def apply_changes(
    hermes_home: Path, report: Dict[str, Any], now: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Apply upgrade/downgrade recommendations to usage.json and auto-load.json.

    Returns a dict of changes made.
    """
    if now is None:
        now = datetime.now().astimezone()

    changes: Dict[str, Any] = {
        "applied_at": now.isoformat(),
        "upgrades": [],
        "downgrades": [],
        "archives": [],
        "errors": [],
    }

    # --- Update usage.json ---
    usage_path = hermes_home / "usage.json"
    usage = load_json(usage_path)
    if usage is None:
        changes["errors"].append(f"usage.json not found at {usage_path}")
        return changes

    for skill_name, skill_report in report.get("skills", {}).items():
        rec = skill_report["recommendation"]
        new_level = None

        if rec == "upgrade":
            new_level = LEVEL_ALWAYS_ON
        elif rec == "downgrade":
            new_level = LEVEL_ON_DEMAND
        elif rec == "archive":
            new_level = LEVEL_ON_DEMAND  # 归档实际降级为 on_demand + 标记

        if new_level is None:
            continue

        old_level = skill_report["current_level"]
        if old_level == new_level:
            continue  # no change needed

        # Update in usage.json
        if skill_name in usage.get("skills", {}):
            usage["skills"][skill_name]["current_level"] = new_level
            usage["skills"][skill_name]["last_level_change"] = now.isoformat()

        if rec == "upgrade":
            changes["upgrades"].append(
                {"skill": skill_name, "from": old_level, "to": new_level}
            )
        elif rec == "downgrade":
            changes["downgrades"].append(
                {"skill": skill_name, "from": old_level, "to": new_level}
            )
        elif rec == "archive":
            changes["archives"].append(
                {"skill": skill_name, "from": old_level, "to": new_level}
            )

    usage["last_maintenance"] = now.isoformat()
    if not save_json(usage_path, usage):
        changes["errors"].append("Failed to save usage.json")

    # --- Update auto-load.json ---
    auto_load_path = hermes_home / "auto-load.json"
    auto_load = load_json(auto_load_path)

    if auto_load is None:
        changes["errors"].append(
            f"auto-load.json not found at {auto_load_path} — "
            "usage.json updated but auto-load.json left unchanged"
        )
        return changes

    # Move upgraded skills into always_on
    for upg in changes["upgrades"]:
        skill_name = upg["skill"]
        # Add to always_on if not already there
        always_on = auto_load.get("always_on", [])
        if not any(s.get("skill") == skill_name for s in always_on):
            always_on.append(
                {
                    "skill": skill_name,
                    "reason": f"AutoLoader 频率自适应: 30天内高频使用, 由 {upg['from']} 升级",
                    "priority": "high",
                }
            )
            auto_load["always_on"] = always_on
        # Remove from other sections
        auto_load["on_demand"] = [
            s for s in auto_load.get("on_demand", []) if s != skill_name
        ]
        # Remove from context_rules
        auto_load["context_rules"] = [
            r
            for r in auto_load.get("context_rules", [])
            if r.get("skill") != skill_name
        ]

    # Move downgraded skills from always_on → on_demand
    for dng in changes["downgrades"]:
        skill_name = dng["skill"]
        auto_load["always_on"] = [
            s
            for s in auto_load.get("always_on", [])
            if s.get("skill") != skill_name
        ]
        on_demand = auto_load.get("on_demand", [])
        if skill_name not in on_demand:
            on_demand.append(skill_name)
            auto_load["on_demand"] = on_demand
        # Also remove from context_rules
        auto_load["context_rules"] = [
            r
            for r in auto_load.get("context_rules", [])
            if r.get("skill") != skill_name
        ]

    # Move archived skills similarly (on_demand + note)
    for arc in changes["archives"]:
        skill_name = arc["skill"]
        auto_load["always_on"] = [
            s
            for s in auto_load.get("always_on", [])
            if s.get("skill") != skill_name
        ]
        auto_load["context_rules"] = [
            r
            for r in auto_load.get("context_rules", [])
            if r.get("skill") != skill_name
        ]
        on_demand = auto_load.get("on_demand", [])
        if skill_name not in on_demand:
            on_demand.append(skill_name)
            auto_load["on_demand"] = on_demand

    auto_load["stats"] = auto_load.get("stats", {})
    auto_load["stats"]["last_updated"] = now.isoformat()

    if not save_json(auto_load_path, auto_load):
        changes["errors"].append("Failed to save auto-load.json")

    return changes


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Skill 使用频率统计（EVOLUTION-ENGINE 频率自适应）"
    )
    parser.add_argument(
        "--hermes-home",
        default=None,
        help="Hermes 根目录 (默认: ~/.hermes)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="自动应用升级/降级到 usage.json 和 auto-load.json",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_only",
        help="仅输出 JSON（无人类可读摘要）",
    )
    args = parser.parse_args()

    hermes_home = resolve_hermes_home(args.hermes_home)
    now = datetime.now().astimezone()

    # Analyze
    report = analyze_usage(hermes_home, now)

    if "error" in report:
        print(json.dumps(report, indent=2, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    # Apply if requested
    changes = None
    if args.apply:
        changes = apply_changes(hermes_home, report, now)
        report["applied_changes"] = changes

    # Output
    if args.json_only:
        output = report
        if changes:
            output["applied_changes"] = changes
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        _print_human_report(report)


def _print_human_report(report: Dict[str, Any]) -> None:
    """Print a human-readable summary of the usage statistics."""
    print("=" * 60)
    print("  EVOLUTION ENGINE — Skill 使用频率统计")
    print(f"  生成时间: {report['generated_at']}")
    print(f"  数据源:   {report.get('source', 'N/A')}")
    print(f"  Skill 总数: {report.get('total_skills', 0)}")
    print("=" * 60)

    summary = report.get("summary", {})
    upgrades = summary.get("upgrade_candidates", [])
    downgrades = summary.get("downgrade_candidates", [])
    archives = summary.get("archive_candidates", [])
    critical_skipped = summary.get("critical_skipped", [])

    if critical_skipped:
        print(f"\n🔒 Critical (永不降级): {', '.join(critical_skipped)}")

    if upgrades:
        print(f"\n⬆️  升级候选 (→ Always-On): {len(upgrades)}")
        for name in upgrades:
            skill = report["skills"].get(name, {})
            print(f"     • {name}: {skill.get('reason', '')}")

    if downgrades:
        print(f"\n⬇️  降级候选 (→ On-Demand): {len(downgrades)}")
        for name in downgrades:
            skill = report["skills"].get(name, {})
            print(f"     • {name}: {skill.get('reason', '')}")

    if archives:
        print(f"\n📦 归档候选: {len(archives)}")
        for name in archives:
            skill = report["skills"].get(name, {})
            print(f"     • {name}: {skill.get('reason', '')}")

    if not upgrades and not downgrades and not archives:
        print("\n✅ 所有技能状态正常，无需调整。")

    # Per-skill detail table
    print("\n" + "-" * 60)
    print(f"{'Skill':<28} {'30d':>4} {'60d':>4} {'90d':>4} {'Idle(M)':>7} {'Level':>14} {'Rec':>12}")
    print("-" * 60)
    for name, skill in report.get("skills", {}).items():
        rec_icon = {"upgrade": "⬆", "downgrade": "⬇", "archive": "📦", "keep": "✓", "keep_critical": "🔒"}.get(
            skill["recommendation"], "?"
        )
        idle = f"{skill['months_idle']:.1f}" if skill.get("months_idle") is not None else "N/A"
        print(
            f"{name:<28} "
            f"{skill['uses_last_30d']:>4} "
            f"{skill['uses_last_60d']:>4} "
            f"{skill['uses_last_90d']:>4} "
            f"{idle:>7} "
            f"{skill['current_level']:>14} "
            f"{rec_icon} {skill['recommendation']}"
        )

    # Applied changes
    if "applied_changes" in report:
        ac = report["applied_changes"]
        print("\n" + "=" * 60)
        print("  APPLIED CHANGES")
        print(f"  Applied at: {ac.get('applied_at', 'N/A')}")
        if ac.get("upgrades"):
            print(f"  ⬆ Upgrades: {ac['upgrades']}")
        if ac.get("downgrades"):
            print(f"  ⬇ Downgrades: {ac['downgrades']}")
        if ac.get("archives"):
            print(f"  📦 Archives: {ac['archives']}")
        if ac.get("errors"):
            print(f"  ❌ Errors: {ac['errors']}")

    print()


if __name__ == "__main__":
    main()
