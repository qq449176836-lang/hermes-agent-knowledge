#!/usr/bin/env python3
"""
10-Dimension Ambiguity Scanner
===============================
Companion script for: SPEC-DRIVEN-DEV.md — Clarify Phase

Purpose:
    Scans a specification file (spec.md or similar) for ambiguities across
    10 structured dimensions that commonly cause downstream implementation
    drift.  Each finding is classified into one of three severity levels:

        🔴 BLOCKER   — Must be resolved before implementation starts.
        🟡 IMPORTANT — Should be resolved early in the implementation phase.
        🟢 SUGGESTION — Nice-to-have clarification that reduces risk.

The 10 Dimensions:
     1. Input/Output format undefined
     2. Boundary conditions missing
     3. Error handling undefined
     4. Concurrency / race conditions unconsidered
     5. Security / permissions unspecified
     6. Performance constraints unspecified
     7. Compatibility requirements missing
     8. Dependency versions unlocked
     9. Rollback / undo strategy unstated
    10. Acceptance criteria not quantified

Usage:
    python ambiguity-scanner.py --spec path/to/spec.md
    python ambiguity-scanner.py --spec spec.md --output report.json
    python ambiguity-scanner.py --spec spec.md --format text
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    """Classification tier for each finding."""

    BLOCKER = "blocker"      # 🔴 Must resolve before implementation
    IMPORTANT = "important"  # 🟡 Should resolve early
    SUGGESTION = "suggestion"  # 🟢 Nice-to-have


SEVERITY_EMOJI: Dict[Severity, str] = {
    Severity.BLOCKER: "🔴",
    Severity.IMPORTANT: "🟡",
    Severity.SUGGESTION: "🟢",
}


@dataclass
class Finding:
    """A single ambiguity finding from one of the 10 dimensions."""

    dimension: int
    dimension_name: str
    severity: Severity
    description: str
    evidence: str  # Relevant snippet or regex match from the spec
    recommendation: str


# ---------------------------------------------------------------------------
# Dimension Checkers
# ---------------------------------------------------------------------------

# Tuple of (dimension_number, dimension_name, severity, checker_function)
# Each checker receives the full spec text and returns a list of Findings.

def _check_io_format(spec: str) -> List[Finding]:
    """Dimension 1: Input/Output format undefined."""
    findings: List[Finding] = []
    dim = 1
    name = "Input/Output Format Undefined"

    # Heuristic: check for common I/O markers
    has_input_section = bool(re.search(
        r'(?i)(input|request|payload|parameter|argument|stdin)',
        spec
    ))
    has_output_section = bool(re.search(
        r'(?i)(output|response|result|return|stdout)',
        spec
    ))

    # Check for format specifications (JSON schema, proto, type defs, etc.)
    has_type_def = bool(re.search(
        r'(?i)(json\s*schema|protobuf|typescript\s*interface|openapi|graphql\s*schema|'
        r'`[a-z_]+\s*:\s*[A-Z][a-z]+`|format:\s*(json|yaml|xml|csv|binary))',
        spec
    ))

    if not has_input_section:
        findings.append(Finding(
            dimension=dim, dimension_name=name,
            severity=Severity.BLOCKER,
            description="No input format or parameter specification found.",
            evidence="Spec does not define what inputs the component accepts.",
            recommendation="Define input format: data types, constraints, required/optional fields, and examples.",
        ))

    if not has_output_section:
        findings.append(Finding(
            dimension=dim, dimension_name=name,
            severity=Severity.BLOCKER,
            description="No output format or response specification found.",
            evidence="Spec does not define what the component returns.",
            recommendation="Define output format: structure, status codes, error format, and success examples.",
        ))

    if has_input_section and has_output_section and not has_type_def:
        findings.append(Finding(
            dimension=dim, dimension_name=name,
            severity=Severity.IMPORTANT,
            description="I/O mentioned but no concrete format/type definitions (JSON Schema, proto, TS interface, etc.).",
            evidence="Input/output sections exist but lack formal type/format definitions.",
            recommendation="Add concrete type definitions: JSON Schema, Protobuf, TypeScript interfaces, or equivalent.",
        ))

    return findings


def _check_boundary_conditions(spec: str) -> List[Finding]:
    """Dimension 2: Boundary conditions missing."""
    findings: List[Finding] = []
    dim = 2
    name = "Boundary Conditions Missing"

    boundary_keywords = [
        r'\bmin(imum)?\b', r'\bmax(imum)?\b', r'\blimit\b',
        r'\bempty\b', r'\bnull\b', r'\bnil\b', r'\bzero\b',
        r'\bnegative\b', r'\boverflow\b', r'\bedge\s*case\b',
        r'\b>[\s=]', r'\b<[\s=]', r'\brange\b',
    ]
    found_any = any(re.search(kw, spec, re.IGNORECASE) for kw in boundary_keywords)

    # Look for "what happens when" patterns
    what_if = bool(re.search(r'(?i)what\s+(happens|if|about)|edge\s*case', spec))

    if not found_any and not what_if:
        findings.append(Finding(
            dimension=dim, dimension_name=name,
            severity=Severity.BLOCKER,
            description="No boundary conditions specified (min/max, empty input, null values, overflow).",
            evidence="Spec lacks discussion of edge cases, limits, or boundary behavior.",
            recommendation="Define behavior for: empty/null input, max-size payloads, zero values, negative numbers, and overflow scenarios.",
        ))
    elif found_any and not what_if:
        findings.append(Finding(
            dimension=dim, dimension_name=name,
            severity=Severity.IMPORTANT,
            description="Boundary terms appear but explicit edge-case handling is not described.",
            evidence="Limits mentioned but no 'what happens when' scenarios defined.",
            recommendation="Add explicit 'What happens when ...' sections for each boundary condition.",
        ))

    return findings


def _check_error_handling(spec: str) -> List[Finding]:
    """Dimension 3: Error handling undefined."""
    findings: List[Finding] = []
    dim = 3
    name = "Error Handling Undefined"

    has_error_section = bool(re.search(
        r'(?i)(error\s*(handling|codes?|response|format|message)|'
        r'exception|failure\s*mode|fault\s*tolerance|graceful\s*degradation)',
        spec
    ))

    has_retry = bool(re.search(
        r'(?i)(retry|backoff|circuit\s*breaker|timeout|fallback)',
        spec
    ))

    if not has_error_section:
        findings.append(Finding(
            dimension=dim, dimension_name=name,
            severity=Severity.BLOCKER,
            description="No error handling strategy defined.",
            evidence="Spec does not describe how errors, exceptions, or failures are handled.",
            recommendation="Define: error codes/categories, error response format, logging strategy, and user-facing messages.",
        ))
    else:
        if not has_retry:
            findings.append(Finding(
                dimension=dim, dimension_name=name,
                severity=Severity.IMPORTANT,
                description="Error handling mentioned but no retry/backoff/timeout strategy.",
                evidence="Error section exists but lacks resilience patterns (retry, backoff, circuit breaker).",
                recommendation="Specify retry policies, timeout values, and circuit breaker thresholds.",
            ))

    return findings


def _check_concurrency(spec: str) -> List[Finding]:
    """Dimension 4: Concurrency / race conditions unconsidered."""
    findings: List[Finding] = []
    dim = 4
    name = "Concurrency / Race Conditions Unconsidered"

    has_concurrency = bool(re.search(
        r'(?i)(concurrent|concurrency|race\s*condition|thread\s*safe|'
        r'mutex|lock|atomic|idempotent|parallel|serializ(e|ation)|'
        r'optimistic\s*lock|pessimistic\s*lock)',
        spec
    ))

    # Indicators that concurrency is likely relevant
    has_state_change = bool(re.search(
        r'(?i)(create|update|delete|write|modify|mutate|state\s*change|'
        r'transition|workflow)',
        spec
    ))

    if has_state_change and not has_concurrency:
        findings.append(Finding(
            dimension=dim, dimension_name=name,
            severity=Severity.BLOCKER,
            description="State-changing operations defined without concurrency considerations.",
            evidence="Spec describes mutations (create/update/delete) but does not address race conditions.",
            recommendation="Define: idempotency keys, optimistic locking (version/etag), or transactional guarantees.",
        ))
    elif not has_concurrency:
        findings.append(Finding(
            dimension=dim, dimension_name=name,
            severity=Severity.IMPORTANT,
            description="No concurrency model or thread-safety guarantees specified.",
            evidence="Spec lacks any discussion of concurrent access patterns.",
            recommendation="Clarify: expected concurrency level, thread-safety requirements, and synchronization approach.",
        ))

    return findings


def _check_security(spec: str) -> List[Finding]:
    """Dimension 5: Security / permissions unspecified."""
    findings: List[Finding] = []
    dim = 5
    name = "Security / Permissions Unspecified"

    has_auth = bool(re.search(
        r'(?i)(auth(entication|orization)?|oauth|jwt|api\s*key|token|'
        r'permission|role|access\s*control|rbac|acl|login|session)',
        spec
    ))

    has_data_protection = bool(re.search(
        r'(?i)(encrypt(ion)?|hash|salt|pii|gdpr|data\s*protection|'
        r'sanitiz(e|ation)|xss|sql\s*injection|csrf|input\s*valid)',
        spec
    ))

    if not has_auth:
        findings.append(Finding(
            dimension=dim, dimension_name=name,
            severity=Severity.BLOCKER,
            description="Authentication and authorization model not defined.",
            evidence="Spec does not describe who can access what or how identities are verified.",
            recommendation="Define: auth mechanism (OAuth, JWT, API key), permission model, and role hierarchy.",
        ))

    if not has_data_protection:
        findings.append(Finding(
            dimension=dim, dimension_name=name,
            severity=Severity.IMPORTANT,
            description="Data protection measures not specified.",
            evidence="Spec does not address encryption, input sanitization, or sensitive data handling.",
            recommendation="Specify: encryption at rest/in transit, input validation strategy, PII handling policy.",
        ))

    return findings


def _check_performance(spec: str) -> List[Finding]:
    """Dimension 6: Performance constraints unspecified."""
    findings: List[Finding] = []
    dim = 6
    name = "Performance Constraints Unspecified"

    has_latency = bool(re.search(
        r'(?i)(latency|p99|p95|p50|millisecond|ms|response\s*time|<[\s=]\s*\d+\s*(m?s|sec))',
        spec
    ))

    has_throughput = bool(re.search(
        r'(?i)(throughput|rps|rpm|qps|requests?\s*per\s*second|tps|concurrent\s*users)',
        spec
    ))

    has_resource = bool(re.search(
        r'(?i)(cpu|memory|ram|storage|disk|bandwidth)\s*(limit|budget|constraint|usage)',
        spec
    ))

    if not (has_latency or has_throughput or has_resource):
        findings.append(Finding(
            dimension=dim, dimension_name=name,
            severity=Severity.IMPORTANT,
            description="No performance targets specified (latency, throughput, or resource limits).",
            evidence="Spec lacks any measurable performance constraints.",
            recommendation="Define: p95/p99 latency targets, throughput requirements (RPS), and resource budgets.",
        ))
    else:
        if not has_latency:
            findings.append(Finding(
                dimension=dim, dimension_name=name,
                severity=Severity.SUGGESTION,
                description="Performance mentioned but no latency SLA defined.",
                evidence="Throughput or resource limits mentioned but latency targets missing.",
                recommendation="Add p95/p99 latency targets (e.g., 'p95 < 200ms').",
            ))
        if not has_throughput:
            findings.append(Finding(
                dimension=dim, dimension_name=name,
                severity=Severity.SUGGESTION,
                description="Performance mentioned but no throughput target defined.",
                evidence="Latency or resource limits mentioned but throughput targets missing.",
                recommendation="Add throughput requirements (e.g., 'supports 1000 RPS').",
            ))

    return findings


def _check_compatibility(spec: str) -> List[Finding]:
    """Dimension 7: Compatibility requirements missing."""
    findings: List[Finding] = []
    dim = 7
    name = "Compatibility Requirements Missing"

    has_backward = bool(re.search(
        r'(?i)(backward\s*compat|breaking\s*change|migration|deprecat|version\s*compat)',
        spec
    ))

    has_platform = bool(re.search(
        r'(?i)(browser|os|operating\s*system|platform|windows|linux|macos|'
        r'android|ios|mobile|desktop)\s*(support|compat|requirement|target)',
        spec
    ))

    if not has_backward:
        findings.append(Finding(
            dimension=dim, dimension_name=name,
            severity=Severity.IMPORTANT,
            description="Backward compatibility and migration strategy not defined.",
            evidence="Spec does not address compatibility with previous versions or breaking changes.",
            recommendation="Define: backward compatibility policy, deprecation timeline, migration guide requirements.",
        ))

    if not has_platform:
        findings.append(Finding(
            dimension=dim, dimension_name=name,
            severity=Severity.SUGGESTION,
            description="Platform/browser/OS compatibility targets not specified.",
            evidence="Spec does not list supported platforms or environments.",
            recommendation="Enumerate: supported OS versions, browsers, runtime environments, and their minimum versions.",
        ))

    return findings


def _check_dependencies(spec: str) -> List[Finding]:
    """Dimension 8: Dependency versions unlocked."""
    findings: List[Finding] = []
    dim = 8
    name = "Dependency Versions Unlocked"

    has_deps = bool(re.search(
        r'(?i)(dependenc|library|package|module|framework|import|require)',
        spec
    ))

    has_pinned = bool(re.search(
        r'(?i)(==|@[\d.]+|version\s*[:=]\s*[\d.]+|locked|pinned|'
        r'exact\s*version|semver|~>|>=|<=)',
        spec
    ))

    if has_deps and not has_pinned:
        findings.append(Finding(
            dimension=dim, dimension_name=name,
            severity=Severity.IMPORTANT,
            description="Dependencies mentioned but versions are not pinned or ranged.",
            evidence="Spec references dependencies without version constraints.",
            recommendation="Pin dependency versions or specify semver ranges (e.g., '>=1.2,<2.0').",
        ))
    elif not has_deps:
        findings.append(Finding(
            dimension=dim, dimension_name=name,
            severity=Severity.SUGGESTION,
            description="No dependency inventory found in spec.",
            evidence="Spec does not enumerate external dependencies.",
            recommendation="List all external dependencies with minimum required versions.",
        ))

    return findings


def _check_rollback(spec: str) -> List[Finding]:
    """Dimension 9: Rollback / undo strategy unstated."""
    findings: List[Finding] = []
    dim = 9
    name = "Rollback / Undo Strategy Unstated"

    has_rollback = bool(re.search(
        r'(?i)(rollback|undo|revert|reversal|compensat|saga|'
        r'roll\s*forward|backup|restore|snapshot|recovery|disaster)',
        spec
    ))

    # Indicators that state is mutated (rollback likely needed)
    has_mutation = bool(re.search(
        r'(?i)(create|update|delete|write|modify|mutate|deploy|migrate|'
        r'schema\s*change|data\s*migration)',
        spec
    ))

    if has_mutation and not has_rollback:
        findings.append(Finding(
            dimension=dim, dimension_name=name,
            severity=Severity.IMPORTANT,
            description="State-changing operations defined without rollback or undo strategy.",
            evidence="Spec describes mutations/deployments/migrations but no recovery plan.",
            recommendation="Define: rollback procedures, data backup/restore strategy, and deployment revert process.",
        ))
    elif not has_rollback:
        findings.append(Finding(
            dimension=dim, dimension_name=name,
            severity=Severity.SUGGESTION,
            description="No rollback or recovery strategy mentioned.",
            evidence="Spec lacks disaster recovery or rollback plans.",
            recommendation="Consider adding: rollback procedures, recovery time objective (RTO), recovery point objective (RPO).",
        ))

    return findings


def _check_acceptance_criteria(spec: str) -> List[Finding]:
    """Dimension 10: Acceptance criteria not quantified."""
    findings: List[Finding] = []
    dim = 10
    name = "Acceptance Criteria Not Quantified"

    has_criteria = bool(re.search(
        r'(?i)(acceptance\s*criteria|definition\s*of\s*done|done\s*when|'
        r'given\s*[-–—]\s*when\s*[-–—]\s*then|gherkin|bdd|test\s*case)',
        spec
    ))

    has_quantified = bool(re.search(
        r'(?i)(\d+%\s*(of|success|coverage|accuracy|precision|recall)|'
        r'metric|kpi|sla|threshold|measurable|quantif)',
        spec
    ))

    if not has_criteria:
        findings.append(Finding(
            dimension=dim, dimension_name=name,
            severity=Severity.BLOCKER,
            description="No acceptance criteria or Definition of Done specified.",
            evidence="Spec does not define when the implementation is considered complete/correct.",
            recommendation="Define: acceptance criteria using Given-When-Then format, measurable success metrics, and test scenarios.",
        ))
    elif has_criteria and not has_quantified:
        findings.append(Finding(
            dimension=dim, dimension_name=name,
            severity=Severity.IMPORTANT,
            description="Acceptance criteria exist but lack quantifiable metrics.",
            evidence="Criteria are qualitative without measurable thresholds.",
            recommendation="Quantify criteria: add specific thresholds (e.g., '95% accuracy', '<200ms p95 latency').",
        ))

    return findings


# Registry of all dimension checkers in order
DIMENSION_CHECKERS: List[tuple] = [
    (1, "Input/Output Format Undefined", Severity.BLOCKER, _check_io_format),
    (2, "Boundary Conditions Missing", Severity.BLOCKER, _check_boundary_conditions),
    (3, "Error Handling Undefined", Severity.BLOCKER, _check_error_handling),
    (4, "Concurrency / Race Conditions Unconsidered", Severity.BLOCKER, _check_concurrency),
    (5, "Security / Permissions Unspecified", Severity.BLOCKER, _check_security),
    (6, "Performance Constraints Unspecified", Severity.IMPORTANT, _check_performance),
    (7, "Compatibility Requirements Missing", Severity.IMPORTANT, _check_compatibility),
    (8, "Dependency Versions Unlocked", Severity.IMPORTANT, _check_dependencies),
    (9, "Rollback / Undo Strategy Unstated", Severity.IMPORTANT, _check_rollback),
    (10, "Acceptance Criteria Not Quantified", Severity.BLOCKER, _check_acceptance_criteria),
]


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def scan_spec(spec_text: str) -> List[Finding]:
    """Run all 10 dimension checkers against the spec text.

    Returns a flat list of all Findings found.
    """
    all_findings: List[Finding] = []
    for dim_num, dim_name, default_severity, checker_fn in DIMENSION_CHECKERS:
        findings = checker_fn(spec_text)
        all_findings.extend(findings)
    return all_findings


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def build_report(findings: List[Finding], spec_path: str) -> Dict[str, Any]:
    """Build a structured report dict from findings."""
    blockers = [f for f in findings if f.severity == Severity.BLOCKER]
    importants = [f for f in findings if f.severity == Severity.IMPORTANT]
    suggestions = [f for f in findings if f.severity == Severity.SUGGESTION]

    def _serialize(f: Finding) -> Dict[str, Any]:
        return {
            "dimension": f.dimension,
            "dimension_name": f.dimension_name,
            "severity": f.severity.value,
            "description": f.description,
            "evidence": f.evidence,
            "recommendation": f.recommendation,
        }

    return {
        "spec_file": spec_path,
        "summary": {
            "total_findings": len(findings),
            "blockers": len(blockers),
            "important": len(importants),
            "suggestions": len(suggestions),
            "verdict": (
                "BLOCKED" if blockers else
                "CAUTION" if importants else
                "CLEAR"
            ),
        },
        "findings": {
            "blocker": [_serialize(f) for f in blockers],
            "important": [_serialize(f) for f in importants],
            "suggestion": [_serialize(f) for f in suggestions],
        },
    }


def format_text_report(report: Dict[str, Any]) -> str:
    """Format a report as a human-readable plain-text block."""
    lines: List[str] = []
    summary = report["summary"]

    lines.append("=" * 64)
    lines.append("  10-DIMENSION AMBIGUITY SCAN REPORT")
    lines.append("=" * 64)
    lines.append(f"  Spec file : {report['spec_file']}")
    lines.append(f"  Findings  : {summary['total_findings']} total")
    lines.append(f"              🔴 BLOCKER    : {summary['blockers']}")
    lines.append(f"              🟡 IMPORTANT  : {summary['important']}")
    lines.append(f"              🟢 SUGGESTION : {summary['suggestions']}")
    lines.append(f"  Verdict   : {summary['verdict']}")
    lines.append("=" * 64)

    for tier_key, tier_label in [
        ("blocker", "🔴 BLOCKERS"),
        ("important", "🟡 IMPORTANT"),
        ("suggestion", "🟢 SUGGESTIONS"),
    ]:
        entries = report["findings"].get(tier_key, [])
        if not entries:
            continue
        lines.append(f"\n{tier_label} ({len(entries)}):")
        lines.append("-" * 48)
        for i, f in enumerate(entries, 1):
            lines.append(f"\n  [{i}] Dim {f['dimension']}: {f['dimension_name']}")
            lines.append(f"      {f['description']}")
            lines.append(f"      💡 {f['recommendation']}")

    lines.append("\n" + "=" * 64)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Construct the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="10-Dimension Ambiguity Scanner — scan specs for missing clarity (SPEC-DRIVEN-DEV Clarify phase).",
    )
    parser.add_argument(
        "--spec", "-s",
        required=True,
        help="Path to the specification file (e.g., spec.md).",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Optional path to write the JSON report (prints to stdout if omitted).",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["json", "text"],
        default="text",
        help="Output format (default: text).",
    )
    return parser


def main() -> None:
    """Entry point: load spec, scan, and produce report."""
    parser = build_parser()
    args = parser.parse_args()

    spec_path = Path(args.spec)
    if not spec_path.is_file():
        print(f"[ERROR] Spec file not found: {args.spec}", file=sys.stderr)
        sys.exit(1)

    spec_text = spec_path.read_text(encoding="utf-8")
    findings = scan_spec(spec_text)
    report = build_report(findings, str(spec_path.resolve()))

    if args.format == "json":
        output = json.dumps(report, indent=2, ensure_ascii=False)
    else:
        output = format_text_report(report)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"[INFO] Report written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
