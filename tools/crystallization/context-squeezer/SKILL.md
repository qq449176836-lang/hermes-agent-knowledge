---
name: context-squeezer
description: "SmartCrusher + CCR 上下文压缩 — 按内容类型智能压缩工具输出，支持可逆检索。减少 40-80% Token，关键信息不丢失。"
---

# 🗜️ Context Squeezer — 智能上下文压缩器

灵感来源：[Headroom](https://github.com/chopratejas/headroom)（SmartCrusher + CCR 设计模式）

## 核心理念

> 不是盲目砍内容，而是**先判断类型 → 选对压缩策略 → 保留关键信号 → 缓存原始数据**。

## 三步工作流

```
工具输出（可能数千行）
  │
  ├─ Step 1: 内容路由 — 判断类型
  │
  ├─ Step 2: 分层压缩 — 保留关键、浓缩冗余、丢弃无用
  │
  └─ Step 3: CCR 缓存 — 原始内容本地存档，嵌入检索标记
```

---

## 使用规则

### 触发条件

**满足以下任一条件时，先压缩再使用：**

| 条件 | 阈值 |
|------|------|
| 工具输出行数 | > 50 行 |
| 工具输出字符数 | > 2000 字符 |
| JSON 数组长度 | > 10 个条目 |
| 文件内容（read_file） | > 200 行 |
| 终端输出 | > 100 行 |

**不需要压缩的场景：**
- 错误 / 异常输出 → 直接保留，不压缩（错误信息不能丢）
- 用户明确要求查看完整内容
- 短内容（低于阈值）

### 执行方式

```bash
# 自动检测类型（推荐）
echo "$TOOL_OUTPUT" | python3 ~/.hermes/skills/context-squeezer/squeezer.py --type auto

# 指定类型
echo "$TOOL_OUTPUT" | python3 ~/.hermes/skills/context-squeezer/squeezer.py --type <TYPE>

# TYPE 可选: auto, browser, search, terminal, code, json

# 内容太大时先写文件
cat > /tmp/squeezer_input.txt << 'SQEOF'
<Tool Output Here>
SQEOF
python3 ~/.hermes/skills/context-squeezer/squeezer.py --type auto < /tmp/squeezer_input.txt

# --no-ccr 禁用缓存（调试用）
python3 ~/.hermes/skills/context-squeezer/squeezer.py --type json --no-ccr < data.json

---

## 五种内容类型 & 压缩策略

### 1. browser_snapshot（HTML/DOM 快照）

**策略：** 只保留可交互元素（带 `@ref` 标记的），折叠纯展示内容。

```
原始: 1500 行 DOM 树
压缩后: ~200 行（仅含 @e1 @e2 ... 的交互节点 + 页面标题/URL）
节省: 85%
```

**提取规则：**
- 保留所有 `@ref` 标记的行（可点击/可输入元素）
- 保留页面标题、URL、关键 heading
- 折叠连续的纯文本节点为 "… N 个文本节点已折叠 …"
- 保留所有错误/异常信息

### 2. search_files（grep/搜索 结果）

**策略：** 按文件分组，统计每文件命中数，只保留唯一匹配行。

```
原始: 500 行匹配结果
压缩后: 
  - 文件 A: 45 次匹配 (3 种不同内容)
  - 文件 B: 12 次匹配 (2 种不同内容)
  - ...
  + 每种内容的第一个匹配行
节省: 70-90%
```

**提取规则：**
- 按文件路径分组
- 每文件统计总命中数
- 去重：相同文本的匹配只保留一次 + "…×N…"
- 每文件最多展示 5 条不同的匹配行
- 保留所有错误行

### 3. terminal_output（命令执行结果）

**策略：** 保留头部（含命令）+ 尾部（最新输出）+ 错误行，中间用采样代替。

```
原始: 800 行日志
压缩后: 
  [HEAD — 前 15 行]
  … 755 行中间内容（5 行采样 + 3 行错误）已折叠 …
  [TAIL — 后 15 行]
节省: 60-80%
```

**提取规则：**
- HEAD: 前 15 行（含命令本身）
- TAIL: 后 15 行（最新输出）
- 中间按 20 行间隔采样 1 行
- ⚠️ 错误行（含 Error/Exception/Traceback/Failed）无条件全保留
- ⚠️ WARNING 行无条件全保留

### 4. read_file（代码文件）

**策略：** 保留 import / 签名 / 注释，普通函数体折叠。

```
原始: 300 行 Python 代码
压缩后:
  - 完整保留: import、class 定义、函数签名、docstring
  - 折叠: 函数体内非关键逻辑 → "… 42 行实现代码已折叠 …"
  - 完整保留: 装饰器、类型注解、错误处理
节省: 30-50%
```

**提取规则：**
- 完整保留: import/from 语句、class/def 签名、docstring、装饰器
- 折叠函数体: 保留第一行和最后一行，中间替换为折叠标记
- 完整保留: try/except、raise、assert 行
- 完整保留: 所有注释

### 5. json（JSON / 结构化数据）

**策略：** Headroom SmartCrusher 风格 — 提取常量字段，采样代表性条目，保留异常。

```
原始: 200 个 JSON 对象
压缩后:
  [常量字段] id, type, version → 所有条目共享，提取一次
  [头部采样] 前 3 个条目
  [高方差采样] 5 个差异最大的条目
  [异常条目] 2 个偏离平均值 > 2σ 的条目
  … 190 个条目已折叠（CCR: hash=abc123）…
节省: 80-95%
```

**提取规则：**
- 字段分析: 找出所有条目中值相同的字段 → 提取为常量，所有条目不再显示
- 采样: 保留前 3 个（结构参考）+ 按方差采样 5 个（代表多样性）
- 异常保留: 任何字段偏离均值 > 2 个标准差的条目，完整保留
- 错误/空值条目: 完整保留

---

## CCR：可逆压缩（Compress-Cache-Retrieve）

### 原理

压缩后原始内容不丢弃，存入本地缓存。LLM 需要时可取回。

```
压缩: 1000 行 → 50 行 + [CCR: hash=a1b2c3]
缓存: ~/.hermes/squeezer-cache/a1b2c3.json
检索: read_file ~/.hermes/squeezer-cache/a1b2c3.json → 取回完整 1000 行
```

### 缓存位置

```
~/.hermes/squeezer-cache/
├── a1b2c3d4.json    # hash = 内容 MD5 前 8 位
├── e5f6g7h8.json
└── .cleanup.log     # 清理记录
```

- 缓存 TTL: 1 小时（过期自动清理）
- 最大条目: 50 个（超出时 LRU 淘汰）

### 检索方式

当压缩后的内容不够用时，直接读取缓存：

```bash
# 方式 1: 直接读取
cat ~/.hermes/squeezer-cache/a1b2c3d4.json

# 方式 2: 搜索缓存
grep "关键词" ~/.hermes/squeezer-cache/*.json

# 方式 3: BM25 搜索（如果安装了 Python）
python3 ~/.hermes/skills/context-squeezer/squeezer.py --retrieve a1b2c3 --query "关键词"
```

---

## 压缩决策树

```
工具输出了大量内容？
├─ 包含 Error / Exception / Traceback？
│   └─ 不压缩！错误信息不能丢
├─ 先用 --type auto 自动检测 →
│   ├─ 检测为 browser → 类型 1: 只保留 @ref 节点
│   ├─ 检测为 search  → 类型 2: 按文件分组去重
│   ├─ 检测为 code    → 类型 4: 保留签名 + 折叠函数体
│   ├─ 检测为 json    → 类型 5: 常量提取 + 采样 + 异常保留
│   └─ 检测为 terminal/text → 类型 3: HEAD + TAIL + 错误行
├─ 短内容（< 阈值）？
│   └─ 不压缩，直接使用
└─ 不确定？
    └─ 类型 3（通用 HEAD+TAIL 策略），最安全
```

---

## 使用示例

### 示例 1: 压缩 browser_snapshot

```bash
# 原始: 1567 行 DOM 树
# 执行压缩
python3 ~/.hermes/skills/context-squeezer/squeezer.py --type browser < snapshot.txt

# 输出: ~200 行交互节点 + [CCR: hash=a1b2c3d4]
# 节省: 87%
```

### 示例 2: 压缩 JSON 工具输出

```bash
# 原始: 200 个对象的数组，3000 行
python3 ~/.hermes/skills/context-squeezer/squeezer.py --type json < output.json

# 输出:
#   [常量字段] id, type, version
#   [采样 8 条] + [异常 2 条]
#   [CCR: hash=e5f6g7h8]
# 节省: 92%
```

### 示例 3: 需要完整数据时检索

```bash
# LLM 发现压缩版不够，检索原始数据
cat ~/.hermes/squeezer-cache/e5f6g7h8.json

# 或搜索特定内容
python3 ~/.hermes/skills/context-squeezer/squeezer.py --retrieve e5f6g7 --query "error"
```

---

## 与 Hermes 现有机制协同

| Hermes 机制 | Squeezer 作用 |
|-------------|---------------|
| Memory 系统 | 不冲突 — 压缩的是工具输出，不影响记忆存储 |
| Context Compaction | 互补 — Squeezer 是实时压缩，Compaction 是历史摘要 |
| Skill 系统 | Squeezer 本身就是一个 Skill，可被其他 Skill 引用 |
| Evolution Engine | 压缩模式可被 TOIN 学习（哪些字段常被 retrieve → 调整保留策略） |

---

## 快速开始

```bash
# 1. 确保脚本存在
ls ~/.hermes/skills/context-squeezer/squeezer.py

# 2. 测试压缩
echo '[{"id":1,"name":"test","status":"ok"},{"id":2,"name":"prod","status":"ok"},{"id":3,"name":"dev","status":"error"}]' | \
  python3 ~/.hermes/skills/context-squeezer/squeezer.py --type json

# 3. 查看缓存
ls ~/.hermes/squeezer-cache/

# 4. 清理过期缓存
python3 ~/.hermes/skills/context-squeezer/squeezer.py --cleanup
```
