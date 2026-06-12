#!/usr/bin/env python3
"""
decay-manager.py — 知识衰减管理

对应方法论文档：KNOWLEDGE-CRYSTALLIZATION.md
  - "知识衰减与清理" 章节
  - Memory（一次性事实）: 60天未被引用 → 过期候选
  - Skill（技能）: 连续2月0次 → 降级为 on-demand；连续6月 → 归档
  - Narrative（叙事知识）: 已蒸馏为 Procedural → 降权，不再检索
  - 棘轮保证: Skill 永不自动删除，只能降级到 on-demand

扫描 Hermes 知识库，输出衰减报告，支持 --dry-run（默认）和 --apply 两种模式。

Usage:
    python decay-manager.py [--hermes-home PATH] [--target all|memory|skill|narrative]
                            [--apply] [--json]

Options:
    --hermes-home PATH    Hermes 根目录 (默认: ~/.hermes)
    --target TEXT         扫描目标: all (默认), memory, skill, narrative
    --apply               实际执行衰减操作（默认 --dry-run）
    --dry-run             仅扫描输出报告，不修改任何文件（默认）
    --json                仅输出 JSON
"""

import argparse
import json
import os
import sys
import yaml
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Constants (aligned with KNOWLEDGE-CRYSTALLIZATION.md decay table)
# ---------------------------------------------------------------------------

MEMORY_EXPIRY_DAYS = 60           # 60天未被引用 → 过期
SKILL_DOWNGRADE_MONTHS = 2        # 连续2月0次 → 降级
SKILL_ARCHIVE_MONTHS = 6          # 连续6月0次 → 归档
NARRATIVE_DISTILLED_WEIGHT_DROP = 0.3  # 已升P的降权系数

CRITICAL_PRIORITY = "critical"
LEVEL_ALWAYS_ON = "always_on"
LEVEL_ON_DEMAND = "on_demand"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resolve_hermes_home(hermes_home: Optional[str] = None) -> Path:
    if hermes_home:
        return Path(os.path.expanduser(hermes_home))
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(os.path.expanduser(env))
    return Path.home() / ".hermes"


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_json(path: Path, data: Dict[str, Any]) -> bool:
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


def load_yaml(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return None


def parse_iso_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    # Handle datetime.date objects from YAML
    if hasattr(s, "isoformat"):
        dt = s
        if not isinstance(dt, datetime):
            from datetime import time as dt_time
            dt = datetime.combine(dt, dt_time.min)
        return dt
    try:
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


def days_since(ts: datetime, now: datetime) -> float:
    ts = _ensure_tz_aware(ts, now)
    return (now - ts).total_seconds() / 86400.0


def months_since(ts: datetime, now: datetime) -> float:
    return days_since(ts, now) / 30.44


def find_yaml_files(directory: Path) -> List[Path]:
    """Recursively find all .yaml and .yml files in directory."""
    if not directory.exists():
        return []
    files: List[Path] = []
    for pattern in ("*.yaml", "*.yml"):
        files.extend(directory.rglob(pattern))
    return sorted(files)


# ---------------------------------------------------------------------------
# Memory decay scanner
# ---------------------------------------------------------------------------

def scan_memory_decay(hermes_home: Path, now: datetime) -> List[Dict[str, Any]]:
    """
    Scan Memory entries for decay candidates.

    Memory items are stored in:
      - ~/.hermes/memories/  (if it exists)
      - ~/.hermes/knowledge-base/experiences/  (Narrative form, cross-referenced)

    Also checks memories/ directory for standalone memory files.

    Returns list of decay candidate dicts.
    """
    candidates: List[Dict[str, Any]] = []

    # --- Check memories/ directory ---
    memories_dir = hermes_home / "memories"
    memory_files: List[Path] = []
    if memories_dir.exists():
        for ext in ("*.json", "*.yaml", "*.yml", "*.md"):
            memory_files.extend(memories_dir.rglob(ext))
    memory_files = sorted(set(memory_files))

    for mf in memory_files:
        mtime = datetime.fromtimestamp(mf.stat().st_mtime)
        age_days = days_since(mtime, now)

        # Simple heuristic: check file modification time as "last referenced"
        # For JSON/YAML we try to parse a date field
        last_ref = mtime
        data: Optional[Dict] = None

        if mf.suffix in (".yaml", ".yml"):
            data = load_yaml(mf)
        elif mf.suffix == ".json":
            data = load_json(mf)

        if data and isinstance(data, dict):
            # Try to extract a date field
            date_str = data.get("last_referenced") or data.get("date") or data.get("updated_at")
            parsed = parse_iso_date(date_str)
            if parsed:
                last_ref = parsed

        age_from_ref = days_since(last_ref, now)
        expired = age_from_ref > MEMORY_EXPIRY_DAYS

        if expired:
            candidates.append({
                "type": "memory",
                "path": str(mf),
                "name": mf.stem,
                "last_referenced": last_ref.isoformat(),
                "age_days": round(age_from_ref, 1),
                "threshold_days": MEMORY_EXPIRY_DAYS,
                "action": "expire",
                "reason": f"已 {age_from_ref:.0f} 天未被引用 (阈值: {MEMORY_EXPIRY_DAYS}天)",
            })

    # --- Also check knowledge-base experiences for decay ---
    # Experiences that have been distilled to Procedural should be marked
    kb_dir = hermes_home / "knowledge-base"
    exp_dir = kb_dir / "experiences"
    if exp_dir.exists():
        idx = load_yaml(kb_dir / "index.yaml")
        for exp_file in find_yaml_files(exp_dir):
            data = load_yaml(exp_file)
            if not data or not isinstance(data, dict):
                continue

            date_str = data.get("date")
            parsed = parse_iso_date(date_str)
            if not parsed:
                continue

            age_days = days_since(parsed, now)
            # Check if this experience has been distilled (outcome references procedural)
            outcome = data.get("outcome", "")
            tags = data.get("tags", [])
            is_distilled = (
                outcome == "distilled"
                or "distilled" in tags
                or "procedural" in tags
            )

            if is_distilled and age_days > MEMORY_EXPIRY_DAYS:
                candidates.append({
                    "type": "narrative_to_procedural",
                    "path": str(exp_file),
                    "name": data.get("id", exp_file.stem),
                    "last_referenced": parsed.isoformat(),
                    "age_days": round(age_days, 1),
                    "threshold_days": MEMORY_EXPIRY_DAYS,
                    "action": "downgrade_weight",
                    "reason": f"已蒸馏为 Procedural，原始 Narrative 降权（权重×{NARRATIVE_DISTILLED_WEIGHT_DROP}）",
                    "new_weight": NARRATIVE_DISTILLED_WEIGHT_DROP,
                })

    return candidates


# ---------------------------------------------------------------------------
# Skill decay scanner
# ---------------------------------------------------------------------------

def scan_skill_decay(hermes_home: Path, now: datetime) -> List[Dict[str, Any]]:
    """
    Scan Skill usage for decay candidates.

    Reads usage.json to find skills with low/nonexistent usage.
    Classification:
      - 2+ months idle → downgrade candidate
      - 6+ months idle → archive candidate
      - Critical priority → never decay (自举保证)

    Returns list of decay candidate dicts.
    """
    candidates: List[Dict[str, Any]] = []
    usage = load_json(hermes_home / "usage.json")
    if usage is None:
        return candidates

    for skill_name, skill_data in usage.get("skills", {}).items():
        priority = skill_data.get("priority", "")
        current_level = skill_data.get("current_level", LEVEL_ON_DEMAND)
        last_used = skill_data.get("last_used")

        if priority == CRITICAL_PRIORITY:
            continue  # Never decay (棘轮保证)

        last_used_dt = parse_iso_date(last_used)
        if last_used_dt is None:
            # Never used — treat as "infinite idle" but flag with a sentinel
            m_idle = 999.0  # sentinel: never used
            reason_idle = "从未使用"
        else:
            m_idle = months_since(last_used_dt, now)
            reason_idle = f"连续 {m_idle:.1f} 月未使用"

        if m_idle >= SKILL_ARCHIVE_MONTHS:
            idle_desc = reason_idle
            candidates.append({
                "type": "skill",
                "name": skill_name,
                "last_used": last_used,
                "months_idle": round(m_idle, 1) if m_idle < 999 else None,
                "current_level": current_level,
                "action": "archive",
                "reason": f"{idle_desc} (阈值: {SKILL_ARCHIVE_MONTHS}月)，建议归档",
                "target_level": LEVEL_ON_DEMAND,
            })
        elif m_idle >= SKILL_DOWNGRADE_MONTHS:
            idle_desc = reason_idle
            if current_level not in (LEVEL_ON_DEMAND,):
                candidates.append({
                    "type": "skill",
                    "name": skill_name,
                    "last_used": last_used,
                    "months_idle": round(m_idle, 1) if m_idle < 999 else None,
                    "current_level": current_level,
                    "action": "downgrade",
                    "reason": f"{idle_desc} (阈值: {SKILL_DOWNGRADE_MONTHS}月)，建议降级为 On-Demand",
                    "target_level": LEVEL_ON_DEMAND,
                })

    return candidates


# ---------------------------------------------------------------------------
# Narrative decay scanner
# ---------------------------------------------------------------------------

def scan_narrative_decay(hermes_home: Path, now: datetime) -> List[Dict[str, Any]]:
    """
    Scan Narrative knowledge for decay.

    Narrative entries reside in:
      - ~/.hermes/knowledge-base/experiences/  (YAML experience cards)

    Decay rules from KNOWLEDGE-CRYSTALLIZATION.md:
      - 已蒸馏为 Procedural → 降权（不再作为主要检索源）
      - Experience marked with "distilled" tag or "procedural" outcome → weight drop

    Returns list of decay candidate dicts.
    """
    candidates: List[Dict[str, Any]] = []
    exp_dir = hermes_home / "knowledge-base" / "experiences"
    if not exp_dir.exists():
        return candidates

    for exp_file in find_yaml_files(exp_dir):
        data = load_yaml(exp_file)
        if not data or not isinstance(data, dict):
            continue

        exp_id = data.get("id", exp_file.stem)
        date_str = data.get("date")
        parsed = parse_iso_date(date_str)
        age_days = days_since(parsed, now) if parsed else None

        outcome = data.get("outcome", "")
        tags = data.get("tags", [])
        surprises = data.get("surprises", [])

        # Check if already distilled to Procedural
        is_distilled = (
            outcome == "distilled"
            or "distilled" in tags
            or "procedural" in tags
            or "procedural_knowledge" in tags
        )

        if is_distilled:
            current_weight = data.get("retrieval_weight", 1.0)
            new_weight = round(current_weight * NARRATIVE_DISTILLED_WEIGHT_DROP, 2)
            candidates.append({
                "type": "narrative",
                "path": str(exp_file),
                "name": exp_id,
                "date": date_str,
                "age_days": round(age_days, 1) if age_days else None,
                "outcome": outcome,
                "is_distilled": True,
                "current_weight": current_weight,
                "new_weight": new_weight,
                "action": "downgrade_weight",
                "reason": f"已蒸馏为 Procedural 知识，原始 Narrative 降权（{current_weight} → {new_weight}）",
            })

        # Check for outdated/stale narrative (no procedural conversion, very old)
        if age_days and age_days > 365 and not is_distilled:
            candidates.append({
                "type": "narrative",
                "path": str(exp_file),
                "name": exp_id,
                "date": date_str,
                "age_days": round(age_days, 1),
                "outcome": outcome,
                "is_distilled": False,
                "action": "review_suggested",
                "reason": f"超过 365 天未被蒸馏，建议人工审核是否仍有价值或应归档",
            })

    return candidates


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def scan_all(
    hermes_home: Path,
    target: str,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Run decay scan for the specified target(s)."""
    if now is None:
        now = datetime.now().astimezone()

    targets = []
    if target == "all":
        targets = ["memory", "skill", "narrative"]
    else:
        targets = [target]

    report: Dict[str, Any] = {
        "generated_at": now.isoformat(),
        "hermes_home": str(hermes_home),
        "targets_scanned": targets,
        "mode": "dry-run",
        "candidates": {
            "expire": [],     # Memory items to expire
            "downgrade": [],  # Skills/narratives to downgrade
            "archive": [],    # Skills to archive
            "downgrade_weight": [],  # Narratives to down-weight
            "review_suggested": [],  # Narratives needing human review
        },
        "summary": {
            "total_candidates": 0,
            "memory_expired": 0,
            "skill_downgrade": 0,
            "skill_archive": 0,
            "narrative_downgrade_weight": 0,
            "narrative_review_needed": 0,
        },
    }

    all_candidates: List[Dict[str, Any]] = []

    if "memory" in targets:
        mem_candidates = scan_memory_decay(hermes_home, now)
        all_candidates.extend(mem_candidates)

    if "skill" in targets:
        skill_candidates = scan_skill_decay(hermes_home, now)
        all_candidates.extend(skill_candidates)

    if "narrative" in targets:
        narrative_candidates = scan_narrative_decay(hermes_home, now)
        all_candidates.extend(narrative_candidates)

    # --- Bucket by action type ---
    for c in all_candidates:
        action = c.get("action", "unknown")
        bucket = action
        if bucket in report["candidates"]:
            report["candidates"][bucket].append(c)
        else:
            report["candidates"][bucket] = [c]

    # --- Summary ---
    report["summary"] = {
        "total_candidates": len(all_candidates),
        "memory_expired": len(report["candidates"].get("expire", [])),
        "skill_downgrade": len(report["candidates"].get("downgrade", [])),
        "skill_archive": len(report["candidates"].get("archive", [])),
        "narrative_downgrade_weight": len(report["candidates"].get("downgrade_weight", [])),
        "narrative_review_needed": len(report["candidates"].get("review_suggested", [])),
    }
    report["all_candidates"] = all_candidates

    return report


def apply_decay(
    hermes_home: Path, report: Dict[str, Any], now: datetime
) -> Dict[str, Any]:
    """
    Apply decay actions reported in the scan.

    Actions:
      - expire Memory: add `decayed: true, decayed_at: <ISO>` to memory entry
      - downgrade Skill: update usage.json level → on_demand, update auto-load.json
      - archive Skill: same as downgrade + mark archived
      - downgrade_weight Narrative: set retrieval_weight to new_weight in YAML file

    Returns a dict of applied changes.
    """
    changes: Dict[str, Any] = {
        "applied_at": now.isoformat(),
        "actions": [],
        "errors": [],
    }

    for candidate in report.get("all_candidates", []):
        action = candidate.get("action")
        ctype = candidate.get("type")
        path_str = candidate.get("path")

        try:
            if action == "expire" and ctype == "memory":
                # Mark memory entry as decayed
                if path_str:
                    mem_path = Path(path_str)
                    if mem_path.suffix in (".yaml", ".yml"):
                        data = load_yaml(mem_path)
                        if data:
                            data["decayed"] = True
                            data["decayed_at"] = now.isoformat()
                            with open(mem_path, "w", encoding="utf-8") as f:
                                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
                    elif mem_path.suffix == ".json":
                        data = load_json(mem_path)
                        if data:
                            data["decayed"] = True
                            data["decayed_at"] = now.isoformat()
                            save_json(mem_path, data)
                    changes["actions"].append({
                        "type": "memory_expire",
                        "path": path_str,
                        "status": "applied",
                    })

            elif action in ("downgrade", "archive") and ctype == "skill":
                skill_name = candidate["name"]
                target_level = candidate.get("target_level", LEVEL_ON_DEMAND)

                # Update usage.json
                usage_path = hermes_home / "usage.json"
                usage = load_json(usage_path)
                if usage and skill_name in usage.get("skills", {}):
                    old_level = usage["skills"][skill_name]["current_level"]
                    usage["skills"][skill_name]["current_level"] = target_level
                    usage["skills"][skill_name]["last_level_change"] = now.isoformat()
                    usage["skills"][skill_name]["decay_action"] = action
                    usage["last_maintenance"] = now.isoformat()
                    save_json(usage_path, usage)

                # Update auto-load.json
                al_path = hermes_home / "auto-load.json"
                al = load_json(al_path)
                if al:
                    al["always_on"] = [
                        s for s in al.get("always_on", [])
                        if s.get("skill") != skill_name
                    ]
                    al["context_rules"] = [
                        r for r in al.get("context_rules", [])
                        if r.get("skill") != skill_name
                    ]
                    on_demand = al.get("on_demand", [])
                    if skill_name not in on_demand:
                        on_demand.append(skill_name)
                        al["on_demand"] = on_demand
                    al.setdefault("stats", {})["last_updated"] = now.isoformat()
                    save_json(al_path, al)

                changes["actions"].append({
                    "type": f"skill_{action}",
                    "name": skill_name,
                    "target_level": target_level,
                    "status": "applied",
                })

            elif action == "downgrade_weight" and ctype in ("narrative", "narrative_to_procedural"):
                if path_str:
                    npath = Path(path_str)
                    data = load_yaml(npath)
                    if data:
                        old_weight = data.get("retrieval_weight", 1.0)
                        new_weight = candidate.get("new_weight", NARRATIVE_DISTILLED_WEIGHT_DROP)
                        data["retrieval_weight"] = new_weight
                        data["weight_downgraded_at"] = now.isoformat()
                        data["weight_downgrade_reason"] = "已蒸馏为 Procedural 知识"
                        with open(npath, "w", encoding="utf-8") as f:
                            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
                        changes["actions"].append({
                            "type": "narrative_weight_downgrade",
                            "path": path_str,
                            "old_weight": old_weight,
                            "new_weight": new_weight,
                            "status": "applied",
                        })

            elif action == "review_suggested":
                # No automated action — just log
                changes["actions"].append({
                    "type": "narrative_review_suggested",
                    "path": path_str,
                    "name": candidate.get("name"),
                    "status": "skipped (requires human review)",
                })

        except (OSError, yaml.YAMLError, json.JSONDecodeError) as exc:
            changes["errors"].append({
                "candidate": candidate.get("name", path_str),
                "error": str(exc),
            })

    return changes


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="知识衰减管理（KNOWLEDGE-CRYSTALLIZATION 衰减策略）"
    )
    parser.add_argument(
        "--hermes-home",
        default=None,
        help="Hermes 根目录 (默认: ~/.hermes)",
    )
    parser.add_argument(
        "--target",
        default="all",
        choices=["all", "memory", "skill", "narrative"],
        help="扫描目标 (默认: all)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="实际执行衰减操作（默认仅预览）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="仅预览，不修改文件（默认开启）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_only",
        help="仅输出 JSON",
    )
    args = parser.parse_args()

    # --apply overrides --dry-run
    if args.apply:
        args.dry_run = False

    hermes_home = resolve_hermes_home(args.hermes_home)
    now = datetime.now().astimezone()

    # Scan
    report = scan_all(hermes_home, args.target, now)

    if args.dry_run:
        report["mode"] = "dry-run"
    else:
        report["mode"] = "apply"
        applied = apply_decay(hermes_home, report, now)
        report["applied_changes"] = applied

    # Output
    if args.json_only:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    else:
        _print_human_report(report)


def _print_human_report(report: Dict[str, Any]) -> None:
    """Print human-readable decay report."""
    mode = report.get("mode", "dry-run")
    mode_label = "🔍 DRY-RUN (预览模式)" if mode == "dry-run" else "⚡ APPLY (执行模式)"

    print("=" * 60)
    print("  KNOWLEDGE CRYSTALLIZATION — 知识衰减报告")
    print(f"  生成时间: {report['generated_at']}")
    print(f"  模式:     {mode_label}")
    print(f"  扫描范围: {', '.join(report.get('targets_scanned', []))}")
    print("=" * 60)

    summary = report.get("summary", {})
    total = summary.get("total_candidates", 0)

    if total == 0:
        print("\n✅ 没有发现需要衰减的知识条目，知识库状态健康。")
        return

    print(f"\n📊 共发现 {total} 个衰减候选:\n")

    # Memory expire
    mem_exp = summary.get("memory_expired", 0)
    if mem_exp > 0:
        print(f"  🧠 Memory 过期候选: {mem_exp}")
        for c in report.get("candidates", {}).get("expire", []):
            print(f"     • {c['name']}: {c['reason']}")

    # Skill downgrade
    sk_dng = summary.get("skill_downgrade", 0)
    if sk_dng > 0:
        print(f"\n  ⚡ Skill 降级候选: {sk_dng}")
        for c in report.get("candidates", {}).get("downgrade", []):
            print(f"     • {c['name']}: {c['reason']}")

    # Skill archive
    sk_arc = summary.get("skill_archive", 0)
    if sk_arc > 0:
        print(f"\n  📦 Skill 归档候选: {sk_arc}")
        for c in report.get("candidates", {}).get("archive", []):
            print(f"     • {c['name']}: {c['reason']}")

    # Narrative weight downgrade
    nw_dng = summary.get("narrative_downgrade_weight", 0)
    if nw_dng > 0:
        print(f"\n  📖 Narrative 降权候选: {nw_dng}")
        for c in report.get("candidates", {}).get("downgrade_weight", []):
            print(f"     • {c['name']}: {c['reason']}")

    # Narrative review needed
    nr_rev = summary.get("narrative_review_needed", 0)
    if nr_rev > 0:
        print(f"\n  👁️  Narrative 人工审核建议: {nr_rev}")
        for c in report.get("candidates", {}).get("review_suggested", []):
            print(f"     • {c['name']}: {c['reason']}")

    # Applied changes
    if "applied_changes" in report:
        ac = report["applied_changes"]
        print(f"\n{'=' * 60}")
        print("  APPLIED CHANGES")
        print(f"  Applied at: {ac.get('applied_at', 'N/A')}")
        for a in ac.get("actions", []):
            status_icon = "✓" if a.get("status") == "applied" else "⚠"
            print(f"  {status_icon} [{a.get('type')}] {a.get('name', a.get('path', 'N/A'))}")
        if ac.get("errors"):
            print(f"\n  ❌ Errors:")
            for err in ac["errors"]:
                print(f"     • {err}")

    print(f"\n💡 使用 --apply 执行上述衰减操作。")


if __name__ == "__main__":
    main()
