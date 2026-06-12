#!/usr/bin/env python3
"""
Knowledge Distillation Engine
==============================
Companion script for: KNOWLEDGE-CRYSTALLIZATION.md + EXPERIENCE-LIFECYCLE.md

Purpose:
    Implements the E → N → P distillation pipeline:
      - Episodic layer: raw experience records with five required elements
                        (timestamp, symptom, root_cause, fix, tags).
      - Narrative layer: structured stories with four elements
                         (Context, Action, Result, Learning).

    Quality gates enforce that all required elements are present at each
    layer before distillation can proceed. A same-topic detector flags
    when ≥3 episodic records share a common tag, prompting Narrative
    consolidation.

Modes:
    --mode episodic   → Validate episodic input (5 elements) and emit it.
    --mode narrative  → Distill one or more episodic records into Narrative format.
    --mode detect     → Scan records for same-topic clusters (≥3) and suggest
                        which episodic records should be distilled together.

Usage:
    # Validate a single episodic record
    python distiller.py --mode episodic --input '{"timestamp":"...","symptom":"...",...}'

    # Distill a batch of episodic records to Narrative
    python distiller.py --mode narrative --input episodes.json

    # Detect same-topic clusters in a collection
    python distiller.py --mode detect --input episodes.json --min-cluster 3
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class EpisodicRecord:
    """Raw experience captured at the Episodic (E) layer.

    Five required elements:
        timestamp   — ISO-8601 datetime when the experience occurred.
        symptom     — Observable problem or situation description.
        root_cause  — Identified underlying cause.
        fix         — Action taken to resolve or handle the situation.
        tags        — List of topical labels for clustering / retrieval.
    """

    timestamp: str
    symptom: str
    root_cause: str
    fix: str
    tags: List[str]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Tuple[Optional["EpisodicRecord"], List[str]]:
        """Parse and validate a dict into an EpisodicRecord.

        Returns (record, errors).  If errors is non-empty, record is None.
        """
        required = {
            "timestamp": str,
            "symptom": str,
            "root_cause": str,
            "fix": str,
            "tags": list,
        }
        errors: List[str] = []

        for field_name, expected_type in required.items():
            if field_name not in data:
                errors.append(f"Missing required field: '{field_name}'")
                continue
            value = data[field_name]
            if not isinstance(value, expected_type):
                errors.append(
                    f"Field '{field_name}' expected {expected_type.__name__}, "
                    f"got {type(value).__name__}"
                )
                continue
            if expected_type is str and not value.strip():
                errors.append(f"Field '{field_name}' is empty")

        # Additional tag validation
        if "tags" in data:
            tags = data["tags"]
            if not isinstance(tags, list) or len(tags) == 0:
                errors.append("Field 'tags' must be a non-empty list")
            elif not all(isinstance(t, str) and t.strip() for t in tags):
                errors.append("All tags must be non-empty strings")

        # Timestamp format check (best effort)
        if "timestamp" in data and isinstance(data["timestamp"], str):
            try:
                datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                errors.append("Field 'timestamp' is not a valid ISO-8601 datetime")

        if errors:
            return None, errors

        return cls(
            timestamp=data["timestamp"],
            symptom=data["symptom"].strip(),
            root_cause=data["root_cause"].strip(),
            fix=data["fix"].strip(),
            tags=[t.strip() for t in data["tags"]],
        ), []


@dataclass
class NarrativeRecord:
    """Structured story at the Narrative (N) layer.

    Four required elements:
        context  — Background / situation that led to the experience.
        action   — What was done in response.
        result   — Outcome of the action.
        learning — Key takeaway or principle extracted.
    """

    context: str
    action: str
    result: str
    learning: str
    source_tags: List[str] = field(default_factory=list)
    distilled_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "context": self.context,
            "action": self.action,
            "result": self.result,
            "learning": self.learning,
            "source_tags": self.source_tags,
            "distilled_at": self.distilled_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Tuple[Optional["NarrativeRecord"], List[str]]:
        """Parse and validate a dict into a NarrativeRecord.

        Returns (record, errors). All four CARL elements must be present.
        """
        required = ["context", "action", "result", "learning"]
        errors: List[str] = []

        for field_name in required:
            if field_name not in data:
                errors.append(f"Missing required Narrative field: '{field_name}'")
            elif not isinstance(data[field_name], str) or not data[field_name].strip():
                errors.append(f"Narrative field '{field_name}' is empty or not a string")

        if errors:
            return None, errors

        return cls(
            context=data["context"].strip(),
            action=data["action"].strip(),
            result=data["result"].strip(),
            learning=data["learning"].strip(),
            source_tags=data.get("source_tags", []),
            distilled_at=data.get("distilled_at", datetime.now().isoformat()),
        ), []


# ---------------------------------------------------------------------------
# Distillation Logic: Episodic → Narrative
# ---------------------------------------------------------------------------

def distill_episodic_to_narrative(episodes: List[EpisodicRecord]) -> NarrativeRecord:
    """Distill one or more EpisodicRecords into a single NarrativeRecord.

    Heuristic mapping:
        Context   ← combined symptoms + timestamps
        Action    ← combined fixes
        Result    ← synthesized from symptoms → fix relationship
        Learning  ← synthesized from root_cause patterns

    When multiple episodes are provided, the distillation merges common
    themes.  When a single episode is provided, each element maps directly.
    """
    now_iso = datetime.now().isoformat()

    if len(episodes) == 1:
        ep = episodes[0]
        return NarrativeRecord(
            context=f"On {ep.timestamp}, the following was observed: {ep.symptom}",
            action=ep.fix,
            result=f"After applying the fix for root cause '{ep.root_cause}', the symptom was resolved.",
            learning=f"Root cause '{ep.root_cause}' should be monitored. Prevention: address {ep.root_cause} proactively.",
            source_tags=ep.tags,
            distilled_at=now_iso,
        )
    else:
        # Multi-episode merge
        all_tags: List[str] = []
        symptoms: List[str] = []
        fixes: List[str] = []
        root_causes: List[str] = []

        for ep in episodes:
            all_tags.extend(ep.tags)
            symptoms.append(f"- [{ep.timestamp}] {ep.symptom}")
            fixes.append(f"- {ep.fix}")
            if ep.root_cause not in root_causes:
                root_causes.append(ep.root_cause)

        unique_tags = sorted(set(all_tags))
        context_lines = [
            f"Over {len(episodes)} related episodes, the following symptoms recurred:"
        ] + symptoms

        action_lines = ["The following fixes were applied:"] + fixes

        rc_str = ", ".join(root_causes)
        result_lines = [
            f"Addressing root causes ({rc_str}) resolved the recurring symptoms.",
        ]

        learning_lines = [
            f"Pattern identified across {len(episodes)} episodes: root causes {rc_str} "
            f"manifest through similar symptoms. Establish systematic monitoring for these patterns.",
        ]

        return NarrativeRecord(
            context="\n".join(context_lines),
            action="\n".join(action_lines),
            result="\n".join(result_lines),
            learning="\n".join(learning_lines),
            source_tags=unique_tags,
            distilled_at=now_iso,
        )


# ---------------------------------------------------------------------------
# Same-Topic Detection
# ---------------------------------------------------------------------------

def detect_topic_clusters(
    episodes: List[EpisodicRecord],
    min_cluster: int = 3,
) -> Dict[str, List[int]]:
    """Detect groups of episodes sharing the same tag.

    Returns a dict mapping tag → list of episode indices (0-based).
    Only clusters with >= min_cluster episodes are returned.
    """
    tag_to_indices: Dict[str, List[int]] = defaultdict(list)
    for i, ep in enumerate(episodes):
        for tag in ep.tags:
            tag_to_indices[tag].append(i)

    # Filter to clusters meeting the minimum size
    clusters: Dict[str, List[int]] = {}
    for tag, indices in tag_to_indices.items():
        if len(indices) >= min_cluster:
            clusters[tag] = sorted(indices)

    return clusters


# ---------------------------------------------------------------------------
# Quality Gates
# ---------------------------------------------------------------------------

def validate_episodic_input(data: Dict[str, Any]) -> Tuple[Optional[EpisodicRecord], List[str]]:
    """Quality gate for Episodic layer: all five elements required."""
    return EpisodicRecord.from_dict(data)


def validate_narrative_input(data: Dict[str, Any]) -> Tuple[Optional[NarrativeRecord], List[str]]:
    """Quality gate for Narrative layer: all four CARL elements required."""
    return NarrativeRecord.from_dict(data)


# ---------------------------------------------------------------------------
# Mode Handlers
# ---------------------------------------------------------------------------

def handle_episodic_mode(args: argparse.Namespace) -> int:
    """Validate episodic input and output it in canonical form."""
    try:
        data = json.loads(args.input) if args.input.startswith("{") else _load_json_file(args.input)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"[ERROR] Cannot parse input: {e}", file=sys.stderr)
        return 1

    # If input is a list, validate each element
    if isinstance(data, list):
        all_passed = True
        for i, item in enumerate(data):
            record, errors = validate_episodic_input(item)
            if errors:
                all_passed = False
                print(f"[FAIL] Record {i}: {'; '.join(errors)}", file=sys.stderr)
            else:
                assert record is not None
                print(f"[PASS] Record {i}: {record.symptom[:60]}...")
        return 0 if all_passed else 1

    record, errors = validate_episodic_input(data)
    if errors:
        print(f"[FAIL] {'; '.join(errors)}", file=sys.stderr)
        return 1

    assert record is not None
    output = {
        "timestamp": record.timestamp,
        "symptom": record.symptom,
        "root_cause": record.root_cause,
        "fix": record.fix,
        "tags": record.tags,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


def handle_narrative_mode(args: argparse.Namespace) -> int:
    """Distill episodic records into a Narrative record.

    Accepts a single episodic record or a JSON array of them.
    """
    try:
        data = json.loads(args.input) if args.input.startswith("[") or args.input.startswith("{") else _load_json_file(args.input)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"[ERROR] Cannot parse input: {e}", file=sys.stderr)
        return 1

    # Normalize to list
    items = data if isinstance(data, list) else [data]

    episodes: List[EpisodicRecord] = []
    all_errors: List[str] = []
    for i, item in enumerate(items):
        record, errors = validate_episodic_input(item)
        if errors:
            all_errors.append(f"Record {i}: {'; '.join(errors)}")
        else:
            assert record is not None
            episodes.append(record)

    if all_errors:
        print(f"[FAIL] Quality gate failed:\n" + "\n".join(all_errors), file=sys.stderr)
        return 1

    if not episodes:
        print("[FAIL] No valid episodic records to distill.", file=sys.stderr)
        return 1

    narrative = distill_episodic_to_narrative(episodes)

    # Validate the output narrative
    out_data = narrative.to_dict()
    _, n_errors = validate_narrative_input(out_data)
    if n_errors:
        print(f"[FAIL] Distilled narrative failed quality gate: {'; '.join(n_errors)}", file=sys.stderr)
        return 1

    print(json.dumps(out_data, indent=2, ensure_ascii=False))
    return 0


def handle_detect_mode(args: argparse.Namespace) -> int:
    """Scan episodic records for same-topic clusters."""
    try:
        data = _load_json_file(args.input)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"[ERROR] Cannot parse input: {e}", file=sys.stderr)
        return 1

    if not isinstance(data, list):
        print("[ERROR] Detect mode requires a JSON array of episodic records.", file=sys.stderr)
        return 1

    episodes: List[EpisodicRecord] = []
    for i, item in enumerate(data):
        record, errors = validate_episodic_input(item)
        if errors:
            print(f"[WARN] Skipping record {i}: {'; '.join(errors)}", file=sys.stderr)
            continue
        assert record is not None
        episodes.append(record)

    min_cluster = getattr(args, "min_cluster", 3)
    clusters = detect_topic_clusters(episodes, min_cluster=min_cluster)

    if not clusters:
        print(json.dumps({
            "message": f"No topic clusters found with >= {min_cluster} episodes.",
            "clusters": {},
            "total_episodes": len(episodes),
        }, indent=2))
        return 0

    output_clusters: Dict[str, Any] = {}
    for tag, indices in clusters.items():
        output_clusters[tag] = {
            "count": len(indices),
            "episode_indices": indices,
            "suggestion": (
                f"These {len(indices)} episodes share tag '{tag}'. "
                f"Consider distilling them into a Narrative record."
            ),
        }

    result = {
        "message": f"Found {len(clusters)} topic cluster(s) with >= {min_cluster} episodes.",
        "clusters": output_clusters,
        "total_episodes": len(episodes),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json_file(path: str) -> Any:
    """Load JSON from a file path."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Construct the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Knowledge Distillation Engine — E→N→P pipeline for experience crystallization.",
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["episodic", "narrative", "detect"],
        required=True,
        help="Operating mode: validate episodic, distill to narrative, or detect topic clusters.",
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input: JSON string (for single records) or path to a JSON file.",
    )
    parser.add_argument(
        "--min-cluster",
        type=int,
        default=3,
        help="Minimum episodes per topic cluster for detect mode (default: 3).",
    )
    return parser


def main() -> None:
    """Entry point: dispatch to the requested mode handler."""
    parser = build_parser()
    args = parser.parse_args()

    handlers = {
        "episodic": handle_episodic_mode,
        "narrative": handle_narrative_mode,
        "detect": handle_detect_mode,
    }

    exit_code = handlers[args.mode](args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
