#!/usr/bin/env python3
"""
review-engine.py — 审核判定引擎 (Reviewer Module)

依据方法论文档: MULTI-AGENT-COORDINATION.md § 审核员判定标准（三级）

三级审核标准：
  - strict:    精确匹配（output == expected），适用于接口契约、API 定义、文件格式
  - practical: 功能等效（包含关键元素即可），适用于功能验收、业务逻辑
  - existence: 文件存在性（检查路径/文件是否存在且非空），适用于交付物检查

输入: 单条 JSON 对象或 JSON 数组
输出: {"pass": bool, "reason": str, "confidence": float} 或数组

跨部门矛盾处理:
  - 当检测到跨部门矛盾信号时，标记为 cross_dept 而非单方面判失败
  - 不归因、不建议修复方案 — 归因是调度员的活

Usage:
  echo '{"task":"...","expected":"...","actual":"...","level":"strict"}' | python3 review-engine.py
  echo '[{...}, {...}]' | python3 review-engine.py
"""

import json
import os
import re
import sys
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple, Union


# ---------------------------------------------------------------------------
# 核心判定函数
# ---------------------------------------------------------------------------

def review_strict(expected: str, actual: str) -> Tuple[bool, str, float]:
    """精确匹配：逐字符比较 expected 与 actual。

    支持：
      - 纯文本精确匹配
      - 忽略末尾换行差异（strip）
      - JSON 字符串化后精确匹配

    返回: (pass, reason, confidence)
    """
    exp = expected.strip()
    act = actual.strip()

    if exp == act:
        return True, "精确匹配: expected == actual", 1.0

    # 尝试 JSON 规范化比较
    try:
        exp_json = json.loads(exp)
        act_json = json.loads(act)
        if exp_json == act_json:
            return True, "精确匹配 (JSON 规范化后一致)", 1.0
    except (json.JSONDecodeError, TypeError):
        pass

    # 计算相似度
    similarity = SequenceMatcher(None, exp, act).ratio()
    if similarity >= 0.99:
        return False, (
            f"高相似度 ({similarity:.3f}) 但非精确匹配。"
            f"期望长度={len(exp)}, 实际长度={len(act)}"
        ), similarity
    elif similarity >= 0.95:
        return False, (
            f"相似度 {similarity:.3f}，但 strict 模式要求完全一致。"
            f"首处差异附近: exp[{min(200, len(exp))}]=... vs actual[{min(200, len(act))}]=..."
        ), similarity
    else:
        return False, (
            f"不匹配: 相似度 {similarity:.3f}。"
            f"期望长度={len(exp)}, 实际长度={len(act)}"
        ), similarity


# 常见停用词，在 practical 匹配时忽略
_PRACTICAL_STOPWORDS = {
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'shall', 'can', 'to', 'of', 'in', 'for',
    'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through', 'during',
    'this', 'that', 'these', 'those', 'it', 'its', 'and', 'but', 'or',
    'not', 'no', 'if', 'then', 'else', 'when', 'where', 'which', 'who',
}


def _tokenize_for_practical(text: str) -> List[str]:
    """从文本中提取有意义的 token。

    策略：
      1. 先按行拆分，保留每行作为一个语义单元
      2. 若只有 1 行，按标点和空格智能拆分，过滤停用词和短词
      3. 提取数字模式（如端口号）作为独立 token
    """
    text = text.strip()
    # 提取 port/digit 模式
    port_nums = re.findall(r'\b\d{2,5}\b', text)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        # 多行: 每行是一个语义单元
        elements = []
        for line in lines:
            # 每行也提取其关键 token
            tokens = re.findall(r'[A-Za-z\u4e00-\u9fff_][A-Za-z0-9\u4e00-\u9fff_]*', line.lower())
            meaningful = [t for t in tokens if len(t) >= 3 and t not in _PRACTICAL_STOPWORDS]
            if meaningful:
                elements.extend(meaningful)
            else:
                elements.append(line)
        return elements
    else:
        # 单行: 按标点拆分词组
        phrases = re.split(r'[,;:(){}[\]|、，；：]', text)
        elements = []
        for phrase in phrases:
            phrase = phrase.strip()
            if not phrase:
                continue
            # 提取有意义的词
            tokens = re.findall(r'[A-Za-z\u4e00-\u9fff_][A-Za-z0-9\u4e00-\u9fff_]*', phrase.lower())
            meaningful = [t for t in tokens if len(t) >= 3 and t not in _PRACTICAL_STOPWORDS]
            if meaningful:
                elements.extend(meaningful)
            else:
                # 短词组保留原样
                elements.append(phrase)
        # 去重保持顺序
        seen = set()
        unique = []
        for e in elements:
            if e not in seen:
                seen.add(e)
                unique.append(e)
        return unique


def review_practical(expected: str, actual: str) -> Tuple[bool, str, float]:
    """功能等效判定：检查 actual 是否包含 expected 的关键元素。

    策略：
      1. Tokenize expected — 提取有意义的词/短语
      2. 对每个 token 做模糊匹配（子串 + 单词边界可选）
      3. 阈值: >= 75% 的关键元素匹配
      4. 额外检查: 整体字符串相似度作为辅助信号

    返回: (pass, reason, confidence)
    """
    exp_norm = expected.strip()
    act_norm = actual.strip()
    act_lower = act_norm.lower()

    # 完全匹配直接通过
    if exp_norm == act_norm:
        return True, "精确匹配 (等同于 strict pass)", 1.0

    # 提取关键元素
    exp_elements = _tokenize_for_practical(exp_norm)

    if not exp_elements:
        return True, "expected 无有效关键元素，默认通过", 0.5

    # 检查每个关键元素是否在 actual 中出现
    matched = 0
    missing = []
    for elem in exp_elements:
        elem_lower = elem.lower() if isinstance(elem, str) else str(elem).lower()
        if elem_lower in act_lower:
            matched += 1
        else:
            missing.append(elem)

    token_ratio = matched / len(exp_elements)

    # 整体字符串相似度辅助
    overall_similarity = SequenceMatcher(None, exp_norm.lower(), act_lower).ratio()

    # 综合得分: token匹配占 70%, 整体相似度占 30%
    combined_score = token_ratio * 0.7 + overall_similarity * 0.3
    threshold = 0.75

    if token_ratio >= threshold or combined_score >= threshold:
        if token_ratio == 1.0:
            return True, "所有关键元素存在 — 功能等效", 0.95
        elif token_ratio >= threshold:
            return True, (
                f"关键元素匹配率 {token_ratio:.0%} ({matched}/{len(exp_elements)}), "
                f"缺失: {missing[:3]}"
            ), token_ratio
        else:
            return True, (
                f"综合得分 {combined_score:.0%} (token={token_ratio:.0%}, "
                f"相似度={overall_similarity:.0%}) — 判定为功能等效"
            ), combined_score
    else:
        return False, (
            f"关键元素匹配率 {token_ratio:.0%} ({matched}/{len(exp_elements)}) < 阈值, "
            f"综合得分 {combined_score:.0%}。缺失: {missing[:5]}"
        ), combined_score


def review_existence(expected: str, actual: str) -> Tuple[bool, str, float]:
    """文件存在性检查：验证路径/文件是否存在且非空。

    expected 和 actual 都可为：
      - 单个路径字符串
      - JSON 数组字符串
      - 逗号分隔路径列表

    返回: (pass, reason, confidence)
    """
    paths = _parse_paths(expected, actual)

    if not paths:
        return False, "未提供有效路径", 0.0

    results = []
    all_pass = True

    for p in paths:
        exists = os.path.exists(p)
        is_file = os.path.isfile(p)
        is_dir = os.path.isdir(p)
        is_nonempty = False

        if is_file:
            try:
                is_nonempty = os.path.getsize(p) > 0
            except OSError:
                is_nonempty = False

        if exists and (is_dir or is_nonempty):
            detail = f"✓ {p} (文件, {os.path.getsize(p) if is_file else '目录'} bytes)" if is_file else f"✓ {p} (目录存在)"
            results.append({"path": p, "pass": True, "detail": detail})
        elif exists and not is_nonempty:
            results.append({"path": p, "pass": False, "detail": f"✗ {p} (文件存在但为空)"})
            all_pass = False
        else:
            results.append({"path": p, "pass": False, "detail": f"✗ {p} (不存在)"})
            all_pass = False

    passed = sum(1 for r in results if r["pass"])
    confidence = passed / len(results) if results else 0.0

    if all_pass:
        return True, f"全部 {len(paths)} 个路径存在且非空", 1.0
    else:
        failed = [r["path"] for r in results if not r["pass"]]
        return False, f"{passed}/{len(paths)} 路径通过, 失败: {failed}", confidence


def _parse_paths(expected: str, actual: str) -> List[str]:
    """从 expected 和 actual 中提取路径列表。"""
    paths: List[str] = []

    for source in [expected, actual]:
        if not source:
            continue
        s = source.strip()
        # 尝试 JSON 数组
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                paths.extend(str(p) for p in parsed)
                continue
            elif isinstance(parsed, str):
                paths.append(parsed)
                continue
        except (json.JSONDecodeError, TypeError):
            pass
        # 逗号分隔
        if ',' in s:
            paths.extend(p.strip() for p in s.split(',') if p.strip())
        else:
            paths.append(s)

    # 去重保持顺序
    seen = set()
    unique = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


# ---------------------------------------------------------------------------
# 跨部门矛盾检测
# ---------------------------------------------------------------------------

def detect_cross_dept_conflict(
    task: str, expected: str, actual: str
) -> Optional[Dict[str, Any]]:
    """检测跨部门矛盾信号。

    信号:
      - expected 提到某路径/文件存在，actual 显示不存在
      - expected 说"已交付"，actual 为空
      - expected 和 actual 引用不同的路径名

    返回: cross_dept 信息 dict，无矛盾则 None
    """
    signals = []

    # 信号1: expected 含路径但 actual 为空
    path_pattern = re.findall(r'(?:/[\w./-]+|\\\\[\w\\]+|[A-Z]:\\[\w\\]+)', expected)
    if path_pattern and (not actual or not actual.strip()):
        signals.append(f"expected 包含路径 {path_pattern[:3]}，但 actual 为空")

    # 信号2: expected 和 actual 引用不同路径
    exp_paths = set(re.findall(r'(?:/[\w./-]+|\\\\[\w\\]+|[A-Z]:\\[\w\\]+)', expected))
    act_paths = set(re.findall(r'(?:/[\w./-]+|\\\\[\w\\]+|[A-Z]:\\[\w\\]+)', actual))
    if exp_paths and act_paths and not exp_paths.intersection(act_paths):
        signals.append(f"路径不一致: expected={exp_paths}, actual={act_paths}")

    # 信号3: 关键词 "找不到" / "不存在" / "not found"
    if re.search(r'找不[到着]|不存在|not\s*found|no\s*such\s*file', actual, re.IGNORECASE):
        signals.append("actual 包含 '找不到/不存在' 信号，疑似跨部门矛盾")

    if signals:
        return {
            "cross_dept": True,
            "signals": signals,
            "note": "矛盾归因由调度员处理，此处仅标记不选边站"
        }
    return None


# ---------------------------------------------------------------------------
# 主审核入口
# ---------------------------------------------------------------------------

def review(task: str, expected: str, actual: str, level: str) -> Dict[str, Any]:
    """执行单条审核。

    Args:
        task:       任务描述
        expected:   期望结果
        actual:     实际结果
        level:      strict | practical | existence

    Returns:
        {"pass": bool, "reason": str, "confidence": float, ...}
    """
    level = level.lower().strip()

    if level not in ("strict", "practical", "existence"):
        return {
            "pass": False,
            "reason": f"未知审核等级: '{level}'，可选: strict, practical, existence",
            "confidence": 0.0,
        }

    # 执行对应级别审核
    if level == "strict":
        passed, reason, confidence = review_strict(expected, actual)
    elif level == "practical":
        passed, reason, confidence = review_practical(expected, actual)
    else:  # existence
        passed, reason, confidence = review_existence(expected, actual)

    result: Dict[str, Any] = {
        "pass": passed,
        "reason": reason,
        "confidence": round(confidence, 4),
        "level": level,
    }

    # 跨部门矛盾检测 (on fail)
    if not passed:
        cross_dept = detect_cross_dept_conflict(task, expected, actual)
        if cross_dept:
            result["cross_dept"] = cross_dept

    return result


# ---------------------------------------------------------------------------
# 批量审核
# ---------------------------------------------------------------------------

def review_batch(items: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """批量审核。

    Args:
        items: [{"task":..., "expected":..., "actual":..., "level":...}, ...]

    Returns:
        [{"pass":..., "reason":..., "confidence":..., ...}, ...]
    """
    return [review(
        task=item.get("task", ""),
        expected=item.get("expected", ""),
        actual=item.get("actual", ""),
        level=item.get("level", "practical"),
    ) for item in items]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """从 stdin 读取 JSON 输入，输出审核结果到 stdout。"""
    try:
        raw = sys.stdin.read()
    except KeyboardInterrupt:
        sys.exit(1)

    if not raw.strip():
        print(json.dumps({"error": "无输入"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"JSON 解析失败: {e}"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    # 批量 vs 单条
    if isinstance(data, list):
        results = review_batch(data)
    elif isinstance(data, dict):
        # 允许顶层的 "items" 键
        if "items" in data and isinstance(data["items"], list):
            results = review_batch(data["items"])
        else:
            results = review(
                task=data.get("task", ""),
                expected=data.get("expected", ""),
                actual=data.get("actual", ""),
                level=data.get("level", "practical"),
            )
    else:
        print(json.dumps({"error": "输入必须是 JSON 对象或数组"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
