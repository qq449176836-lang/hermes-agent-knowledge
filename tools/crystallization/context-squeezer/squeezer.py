#!/usr/bin/env python3
"""
Context Squeezer — SmartCrusher + CCR 压缩引擎
灵感: Headroom (chopratejas/headroom)

用法:
    # 压缩
    python3 squeezer.py --type json < input.json
    python3 squeezer.py --type browser < snapshot.txt
    python3 squeezer.py --type search < grep_results.txt
    python3 squeezer.py --type terminal < output.txt
    python3 squeezer.py --type code < source.py
    python3 squeezer.py --type auto < any.txt          # 自动检测类型

    # 检索
    python3 squeezer.py --retrieve hash1234
    python3 squeezer.py --retrieve hash1234 --query "关键词"

    # 维护
    python3 squeezer.py --cleanup
    python3 squeezer.py --stats
"""

import sys
import os
import json
import hashlib
import re
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# ==== 配置 ====
CACHE_DIR = Path.home() / ".hermes" / "squeezer-cache"
CACHE_TTL_SECONDS = 3600  # 1 小时
MAX_CACHE_ENTRIES = 50
CLEANUP_LOG = CACHE_DIR / ".cleanup.log"

# 行数阈值
MIN_LINES = 50
MIN_CHARS = 2000

# ==== CCR 缓存 ====

def ensure_cache_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

def content_hash(data: str) -> str:
    return hashlib.md5(data.encode("utf-8")).hexdigest()[:8]

def cache_original(data: str) -> str:
    """缓存原始内容，返回 hash"""
    ensure_cache_dir()
    h = content_hash(data)
    path = CACHE_DIR / f"{h}.json"
    entry = {
        "hash": h,
        "timestamp": time.time(),
        "size_chars": len(data),
        "content": data,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False)
    return h

def retrieve_cache(hash_key: str, query: str = None) -> str | None:
    """检索缓存"""
    path = CACHE_DIR / f"{hash_key}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        entry = json.load(f)
    content = entry.get("content", "")
    if query and content:
        # 简易 BM25 风格：找包含所有查询词的行
        terms = query.lower().split()
        lines = content.split("\n")
        scored = []
        for i, line in enumerate(lines):
            low = line.lower()
            score = sum(1 for t in terms if t in low)
            if score > 0:
                # 给连续匹配加分
                if i > 0 and any(t in lines[i-1].lower() for t in terms):
                    score += 1
                if i < len(lines)-1 and any(t in lines[i+1].lower() for t in terms):
                    score += 1
                scored.append((score, i, line))
        scored.sort(key=lambda x: -x[0])
        if scored:
            return "\n".join(f"[L{i+1}] {line}" for _, i, line in scored[:20])
        return f"[未找到匹配 '{query}' 的内容]"
    return content

def cleanup_cache():
    """清理过期和超量缓存"""
    ensure_cache_dir()
    now = time.time()
    entries = []
    for f in CACHE_DIR.glob("*.json"):
        if f.name == ".cleanup.log":
            continue
        try:
            with open(f, "r", encoding="utf-8") as fp:
                e = json.load(fp)
            entries.append((f, e.get("timestamp", 0), e.get("size_chars", 0)))
        except Exception:
            entries.append((f, 0, 0))

    removed = 0
    # 按时间排序
    entries.sort(key=lambda x: x[1])

    for f, ts, size in entries:
        # 过期
        if now - ts > CACHE_TTL_SECONDS:
            f.unlink(missing_ok=True)
            removed += 1

    # 超量淘汰 (LRU)
    remaining = sorted(
        [(f, ts) for f, ts, _ in entries if f.exists()],
        key=lambda x: x[1]
    )
    while len(remaining) > MAX_CACHE_ENTRIES:
        f, _ = remaining.pop(0)
        f.unlink(missing_ok=True)
        removed += 1

    # 写清理日志
    with open(CLEANUP_LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()}: 清理 {removed} 条目\n")
    return removed


# ==== 内容类型检测 ====

def detect_type(text: str) -> str:
    """自动检测内容类型"""
    if not text.strip():
        return "empty"

    # browser_snapshot 特征: @ref 交互元素 + 方括号数字元素
    ref_markers = len(re.findall(r'@e\d+', text))
    bracket_refs = len(re.findall(r'\[\d+\]', text))
    if ref_markers > 1 or (ref_markers > 0 and bracket_refs > 2):
        return "browser"

    # JSON 特征
    stripped = text.strip()
    if (stripped.startswith("[") and stripped.endswith("]")) or \
       (stripped.startswith("{") and stripped.endswith("}")):
        return "json"

    # search_files 特征: 文件路径:行号: 模式
    search_patterns = len(re.findall(r'^[^\s:]+\.\w+:\d+:', text, re.MULTILINE))
    if search_patterns > 2:
        return "search"

    # 代码特征: 包含函数/类定义或 import
    code_indicators = len(re.findall(
        r'\b(def |class |import |from \w+ import|function |const |let |var |public class)',
        text
    ))
    if code_indicators > 1:
        return "code"

    # 终端输出特征: 大量短行 + 可能含路径
    lines = text.split("\n")
    avg_len = sum(len(l) for l in lines) / max(len(lines), 1)
    if len(lines) > 20 and avg_len < 150:
        return "terminal"

    return "text"


# ==== 压缩策略 ====

def squeeze_browser(text: str) -> tuple[str, str]:
    """压缩 browser_snapshot: 保留交互元素"""
    lines = text.split("\n")
    kept = []
    skipped_count = 0
    consecutive_skip = 0

    for line in lines:
        # 保留交互元素
        has_ref = bool(re.search(r'@e\d+', line))
        has_bracket = bool(re.search(r'\[\d+\]', line))
        is_heading = bool(re.search(r'(heading|h[1-6]|title|Title)', line, re.IGNORECASE))
        is_error = bool(re.search(r'(error|Error|fail|Fail|exception|Exception)', line))
        is_url = bool(re.search(r'https?://', line))

        if has_ref or is_heading or is_error or is_url:
            if consecutive_skip > 0:
                kept.append(f"  … {consecutive_skip} 行非交互内容已折叠 …")
                consecutive_skip = 0
            kept.append(line)
        elif has_bracket:
            # 方括号元素可能是文本节点 — 保留但标记
            if consecutive_skip > 0:
                kept.append(f"  … {consecutive_skip} 行非交互内容已折叠 …")
                consecutive_skip = 0
            kept.append(line)
        else:
            skipped_count += 1
            consecutive_skip += 1

    if consecutive_skip > 0:
        kept.append(f"  … {consecutive_skip} 行非交互内容已折叠 …")

    result = "\n".join(kept)
    return result, f"browser | {len(lines)}→{len(kept)} 行 | 保留 {len(lines)-skipped_count} 交互元素"


def squeeze_search(text: str) -> tuple[str, str]:
    """压缩 search_files 结果: 按文件分组去重"""
    lines = text.split("\n")
    file_groups = {}  # {filepath: [(lineno, content), ...]}
    other_lines = []
    current_file = None

    for line in lines:
        # 匹配 grep 风格: path/to/file.py:123:content
        m = re.match(r'^(.+?\.\w+):(\d+):(.*)', line)
        if m:
            fpath, lineno, content = m.group(1), m.group(2), m.group(3).strip()
            if fpath not in file_groups:
                file_groups[fpath] = []
            file_groups[fpath].append((lineno, content))
        else:
            # 可能是继续行或元数据
            m2 = re.match(r'^(.+?\.\w+)-(\d+)-(.*)', line)
            if m2:
                fpath, lineno, content = m2.group(1), m2.group(2), m2.group(3).strip()
                if fpath not in file_groups:
                    file_groups[fpath] = []
                file_groups[fpath].append((lineno, content))
            else:
                other_lines.append(line)

    result = []
    total_original = len(lines)

    for fpath, matches in sorted(file_groups.items()):
        # 去重
        seen = set()
        unique_matches = []
        for lineno, content in matches:
            if content not in seen:
                seen.add(content)
                unique_matches.append((lineno, content))

        result.append(f"\n📄 {fpath} — {len(matches)} 次匹配 ({len(unique_matches)} 种)")
        for lineno, content in unique_matches[:5]:
            result.append(f"  L{lineno}: {content[:120]}")
        if len(unique_matches) > 5:
            result.append(f"  … 还有 {len(unique_matches)-5} 种不同内容 …")

    if other_lines:
        result.append(f"\n📋 其他: {len(other_lines)} 行")

    result.append("")
    result.extend(other_lines[:3])
    if len(other_lines) > 3:
        result.append(f"… 还有 {len(other_lines)-3} 行其他内容 …")

    compressed = "\n".join(result)
    return compressed, f"search | {total_original}→{len(compressed.split(chr(10)))} 行"


def squeeze_terminal(text: str) -> tuple[str, str]:
    """压缩终端输出: HEAD + TAIL + 错误行 + 采样"""
    lines = text.split("\n")
    total = len(lines)

    if total <= 60:
        return text, f"terminal | {total} 行（无需压缩）"

    head = lines[:15]
    tail = lines[-15:]
    middle = lines[15:-15]

    # 提取错误行
    error_lines = []
    for i, line in enumerate(middle):
        if re.search(r'(Error|ERROR|Exception|Traceback|Failed|FAILED|fatal|FATAL|panic|PANIC)', line):
            error_lines.append((i + 15, line))

    # 采样
    sample = []
    for i in range(0, len(middle), max(1, len(middle) // 8)):
        if i < len(middle):
            sample.append(middle[i])

    result = []
    result.extend(head)

    # 错误行优先
    if error_lines:
        result.append(f"\n{'='*40}")
        result.append(f"⚠️  错误/异常 ({len(error_lines)} 处):")
        for lineno, line in error_lines[:10]:
            result.append(f"  L{lineno+1}: {line[:200]}")
        if len(error_lines) > 10:
            result.append(f"  … 还有 {len(error_lines)-10} 处错误 …")

    if sample:
        result.append(f"\n{'='*40}")
        result.append(f"📊 中间采样 ({len(sample)}/{len(middle)} 行):")
        for line in sample:
            result.append(f"  {line[:200]}")

    result.append(f"\n{'='*40}")
    result.append(f"… {len(middle)} 行中间内容已折叠 …")
    result.extend(tail)

    compressed = "\n".join(result)
    return compressed, f"terminal | {total}→{len(compressed.split(chr(10)))} 行 | {len(error_lines)} 错误"


def squeeze_code(text: str) -> tuple[str, str]:
    """压缩代码: 保留签名 + 折叠函数体"""
    lines = text.split("\n")
    kept = []
    in_skip_block = False
    skip_start = 0
    indent_level = 0
    total = len(lines)

    for i, line in enumerate(lines):
        stripped = line.strip()

        # 永远保留的行
        is_import = bool(re.match(r'^(import |from \w+ import)', stripped))
        is_def = bool(re.match(r'^(def |class |async def )', stripped))
        is_decorator = stripped.startswith('@')
        is_error_handler = bool(re.match(r'^(try:|except |finally:|raise |assert )', stripped))
        is_comment = stripped.startswith('#') or stripped.startswith('//')
        is_blank = stripped == ''
        is_return = stripped.startswith('return ')

        if is_import or is_def or is_decorator or is_error_handler or is_comment or is_blank or is_return:
            if in_skip_block:
                skip_lines = i - skip_start
                if skip_lines > 3:
                    kept.append(f"  … {skip_lines} 行实现代码已折叠 …")
                else:
                    # 恢复被跳过的几行
                    for j in range(skip_start, i):
                        kept.append(lines[j])
                in_skip_block = False
            kept.append(line)
        else:
            if not in_skip_block:
                skip_start = i
                in_skip_block = True

    if in_skip_block:
        skip_lines = total - skip_start
        if skip_lines > 3:
            kept.append(f"  … {skip_lines} 行实现代码已折叠 …")

    compressed = "\n".join(kept)
    return compressed, f"code | {total}→{len(kept)} 行"


def squeeze_json(text: str) -> tuple[str, str]:
    """压缩 JSON: 常量提取 + 采样 + 异常保留"""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return squeeze_terminal(text)[0], "json (解析失败，降级为 terminal 策略)"

    if not isinstance(data, list) or len(data) <= 10:
        return text, f"json | {len(data)} 条目（无需压缩）"

    total = len(data)

    # 分析字段
    if len(data) > 0 and isinstance(data[0], dict):
        all_keys = set()
        for item in data:
            if isinstance(item, dict):
                all_keys.update(item.keys())

        # 找常量字段（所有条目值相同）
        constant_fields = {}
        for key in all_keys:
            values = [item.get(key) for item in data if isinstance(item, dict)]
            unique = set(str(v) for v in values)
            if len(unique) == 1:
                constant_fields[key] = values[0]

        # 找异常条目（任何字段偏离均值 > 2σ 的数值字段）
        anomaly_indices = set()
        for key in all_keys:
            nums = []
            for item in data:
                if isinstance(item, dict):
                    v = item.get(key)
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        nums.append(v)
            if len(nums) > 3:
                mean = sum(nums) / len(nums)
                variance = sum((x - mean) ** 2 for x in nums) / len(nums)
                std = variance ** 0.5
                if std > 0:
                    for idx, item in enumerate(data):
                        if isinstance(item, dict):
                            v = item.get(key)
                            if isinstance(v, (int, float)) and abs(v - mean) > 2 * std:
                                anomaly_indices.add(idx)

        # 输出
        result = []
        result.append(f"[共 {total} 个条目]")

        # 常量字段
        if constant_fields:
            result.append(f"\n📌 常量字段（所有条目共享）:")
            for k, v in constant_fields.items():
                result.append(f"  {k}: {json.dumps(v, ensure_ascii=False)}")
            result.append("")

        # 头部采样
        head_count = min(3, total)
        result.append(f"📋 头部采样 ({head_count} 条):")
        for i in range(head_count):
            item_clean = {k: v for k, v in data[i].items() if k not in constant_fields} if isinstance(data[i], dict) else data[i]
            result.append(f"  [{i}] {json.dumps(item_clean, ensure_ascii=False)[:200]}")

        # 高方差采样
        if total > head_count:
            step = max(1, (total - head_count) // 5)
            sample_indices = list(range(head_count, total, step))[:5]
            result.append(f"\n📊 分布采样 ({len(sample_indices)} 条):")
            for idx in sample_indices:
                item_clean = {k: v for k, v in data[idx].items() if k not in constant_fields} if isinstance(data[idx], dict) else data[idx]
                result.append(f"  [{idx}] {json.dumps(item_clean, ensure_ascii=False)[:200]}")

        # 异常条目
        if anomaly_indices:
            result.append(f"\n⚠️  异常条目 ({len(anomaly_indices)} 条):")
            for idx in sorted(anomaly_indices)[:5]:
                item_clean = {k: v for k, v in data[idx].items() if k not in constant_fields} if isinstance(data[idx], dict) else data[idx]
                result.append(f"  [{idx}] {json.dumps(item_clean, ensure_ascii=False)[:300]}")
    else:
        # 非字典数组
        result = []
        result.append(f"[共 {total} 个条目]")
        head_count = min(5, total)
        result.append(f"\n📋 前 {head_count} 条:")
        for i in range(head_count):
            result.append(f"  [{i}] {json.dumps(data[i], ensure_ascii=False)[:200]}")
        if total > 10:
            step = max(1, (total - head_count) // 5)
            sample_indices = list(range(head_count, total, step))[:5]
            result.append(f"\n📊 分布采样 ({len(sample_indices)} 条):")
            for idx in sample_indices:
                result.append(f"  [{idx}] {json.dumps(data[idx], ensure_ascii=False)[:200]}")

    result.append(f"\n… {total - head_count - len(anomaly_indices)} 个条目已折叠 …")

    compressed = "\n".join(result)
    return compressed, f"json | {total}→{len(compressed.split(chr(10)))} 行 | {len(constant_fields) if 'constant_fields' in dir() else 0} 常量字段"


def squeeze_auto(text: str) -> tuple[str, str]:
    """自动检测类型并压缩"""
    content_type = detect_type(text)
    squeezers = {
        "browser": squeeze_browser,
        "search": squeeze_search,
        "terminal": squeeze_terminal,
        "code": squeeze_code,
        "json": squeeze_json,
        "text": squeeze_terminal,
        "empty": lambda t: (t, "empty"),
    }
    squeezer = squeezers.get(content_type, squeeze_terminal)
    compressed, summary = squeezer(text)
    return compressed, f"auto→{content_type} | {summary}"


# ==== 主入口 ====

def main():
    parser = argparse.ArgumentParser(description="Context Squeezer — 智能上下文压缩")
    parser.add_argument("--type", "-t", choices=["browser", "search", "terminal", "code", "json", "auto"],
                        default="auto", help="内容类型 (默认: auto)")
    parser.add_argument("--retrieve", "-r", help="检索缓存 hash")
    parser.add_argument("--query", "-q", help="检索查询词 (配合 --retrieve)")
    parser.add_argument("--cleanup", action="store_true", help="清理过期缓存")
    parser.add_argument("--stats", action="store_true", help="显示缓存统计")
    parser.add_argument("--no-ccr", action="store_true", help="不缓存原始内容")
    parser.add_argument("--no-fold", action="store_true", help="不添加折叠标记")
    args = parser.parse_args()

    # 检索模式
    if args.retrieve:
        ensure_cache_dir()
        result = retrieve_cache(args.retrieve, args.query)
        if result is None:
            print(f"[错误] 缓存 {args.retrieve} 不存在", file=sys.stderr)
            sys.exit(1)
        print(result)
        return

    # 清理模式
    if args.cleanup:
        removed = cleanup_cache()
        print(f"✅ 清理完成: 删除 {removed} 个过期/超量缓存")
        return

    # 统计模式
    if args.stats:
        ensure_cache_dir()
        files = list(CACHE_DIR.glob("*.json"))
        total_size = sum(f.stat().st_size for f in files)
        print(f"缓存目录: {CACHE_DIR}")
        print(f"缓存条目: {len(files)} 个")
        print(f"总大小:   {total_size/1024:.1f} KB")
        print(f"TTL:      {CACHE_TTL_SECONDS}s ({CACHE_TTL_SECONDS/3600:.1f}h)")
        print(f"上限:     {MAX_CACHE_ENTRIES} 个")
        return

    # 压缩模式: 从 stdin 读取
    text = sys.stdin.read()

    if not text.strip():
        print("[空输入]", file=sys.stderr)
        sys.exit(0)

    # 选择压缩策略
    squeezers = {
        "browser": squeeze_browser,
        "search": squeeze_search,
        "terminal": squeeze_terminal,
        "code": squeeze_code,
        "json": squeeze_json,
        "auto": squeeze_auto,
    }
    squeezer = squeezers.get(args.type, squeeze_auto)
    compressed, summary = squeezer(text)

    # CCR 缓存
    ccr_marker = ""
    if not args.no_ccr:
        h = cache_original(text)
        compressed_lines = len(compressed.split("\n"))
        original_lines = len(text.split("\n"))
        pct = round((1 - compressed_lines / max(original_lines, 1)) * 100)
        ccr_marker = f"\n\n[CCR: {pct}% 压缩 | 原始 {original_lines} 行 | 检索: hash={h}]"

    if not args.no_fold:
        compressed += ccr_marker

    # 输出: 摘要信息到 stderr, 压缩结果到 stdout
    print(f"# {summary} | CCR: {ccr_marker.strip() if ccr_marker else 'disabled'}", file=sys.stderr)

    sys.stdout.write(compressed)


if __name__ == "__main__":
    main()
