# 🤖 AGENT-GUIDE — Hermes Agent 上手指南

> **你好，Hermes Agent！** 这里是你的"大脑"——一份经过数百次任务验证的方法论、准则和可执行工具。
>
> 请按以下顺序阅读和使用，每一份文档都回答一个核心问题。

---

## 🚀 快速启动（5 分钟上手）

### 如果你是第一次加载本仓库

```bash
# 1. 克隆仓库
git clone https://github.com/qq449176836-lang/hermes-agent-knowledge.git

# 2. 按顺序阅读（每份 3-5 分钟）
read_file CONSTITUTION.md      # 必读第一：什么能做，什么绝对不能做
read_file METHODOLOGY.md       # 必读第二：遇到问题怎么思考、怎么执行
read_file KNOWLEDGE-CRYSTALLIZATION.md  # 经验如何变成永久知识
read_file EXPERIENCE-LIFECYCLE.md       # 经验的完整生命周期

# 3. 扩展阅读（按需）
read_file SPEC-DRIVEN-DEV.md           # 功能开发时读
read_file MULTI-AGENT-COORDINATION.md  # 多 Agent 协作时读
read_file EVOLUTION-ENGINE.md          # 想理解自我进化机制时读
read_file OPERATIONS.md                # 遇到具体运维问题查阅
```

---

## 📖 8 份文档详解

| # | 文档 | 回答的核心问题 | 什么时候读 |
|:--:|------|------|------|
| 0 | **AGENT-GUIDE.md** ← 你在这 | 我应该从哪里开始？ | 首次加载 |
| 1 | **CONSTITUTION.md** | 什么是我绝对不能做的？ | 每次会话自动加载 |
| 2 | **METHODOLOGY.md** | 遇到问题怎么思考？ | 需要解决问题时 |
| 3 | **KNOWLEDGE-CRYSTALLIZATION.md** | 经验怎么变成永久知识？ | 沉淀经验时 |
| 4 | **EXPERIENCE-LIFECYCLE.md** | 经验从产生到消费的完整循环？ | 管理知识体系时 |
| 5 | **SPEC-DRIVEN-DEV.md** | 如何从需求到代码不偏离？ | 功能开发时 |
| 6 | **MULTI-AGENT-COORDINATION.md** | 多 Agent 如何协作？ | 委派子 Agent 时 |
| 7 | **EVOLUTION-ENGINE.md** | 如何像生物一样进化？ | 理解引擎机制时 |
| 8 | **OPERATIONS.md** | 实际环境有哪些坑？ | 遇到具体 bug 时 |

---

## 🛠️ 工具速查

本仓库的 `tools/` 目录包含 15 个可执行脚本，按方法论文档对应：

| 你需要... | 使用工具 | 命令 |
|----------|------|------|
| 检查代码是否有敏感信息 | `secret-scanner.py` | `python tools/constitution/secret-scanner.py .` |
| 自动脱敏敏感信息 | `secret-scanner.py --fix` | `python tools/constitution/secret-scanner.py . --fix` |
| 安装 Git 提交保护 | `pre-commit-hook.sh` | `bash tools/constitution/pre-commit-hook.sh --install` |
| 诊断飞书为什么连不上 | `feishu-check.sh` | `bash tools/operations/feishu-check.sh` |
| 清理 Flask 残留进程 | `flask-cleanup.ps1` | `powershell -File tools/operations/flask-cleanup.ps1 -Port 5000` |
| 清理残留锁文件 | `lockfile-check.sh` | `bash tools/operations/lockfile-check.sh --clean` |
| 系统健康检查 | `health-check.sh` | `bash tools/operations/health-check.sh` |
| 执行会话启动检查点 | `session-checklist/SKILL.md` | `skill_view(name='session-checklist')` |
| 蒸馏经验 | `distiller.py` | `python tools/crystallization/distiller.py --mode narrative --input exp.json` |
| 管理知识衰减 | `decay-manager.py` | `python tools/crystallization/decay-manager.py --target all --dry-run` |
| 压缩冗余上下文 | `squeezer.py` | `python tools/crystallization/context-squeezer/squeezer.py --mode auto input.txt` |
| 爬取 GitHub Trending | `explorer.py` | `python tools/evolution/explorer.py --source github --top 10` |
| 分析 Skill 使用频率 | `usage-stats.py` | `python tools/evolution/usage-stats.py` |
| 扫描规格中的歧义 | `ambiguity-scanner.py` | `python tools/spec-driven/ambiguity-scanner.py spec.md` |
| 审核子 Agent 产出 | `review-engine.py` | `python tools/coordination/review-engine.py '{"task":"...","expected":"...","actual":"..."}'` |
| 委派前产前验证 | `preflight-check.py` | `python tools/coordination/preflight-check.py --paths /c/foo --files a.py,b.py` |

---

## 🧠 核心概念速记

### 五层检索法（遇到问题怎么搜）

```
L0: VikingDB 记忆库（"上次怎么解决的？"）
L1: VikingDB 知识库（"文档里怎么说的？"）
L2: 精确匹配（grep 关键字）
L3: 语义扩展（LLM 扩展关键词）
L4: 遍历 Skill 库

→ 能用 L0 就不去 L1，能搜索就不推理，能参考就不原创
```

### 棘轮循环（不要让错误重演）

```
遭遇 → 诊断 → 修复 → 记录 → 提炼 → 标准化 → 推送 → 下次自动命中
```

### E→N→P 三层蒸馏（经验如何升级）

```
Episodic（发生了什么）
    ↓
Narrative（学到了什么通用规律）
    ↓
Procedural（标准化 SKILL.md，AutoLoader 自动加载）
```

---

## ⚠️ 铁律提醒

这些规则在 CONSTITUTION.md 中详细定义，这里列最关键的三条：

1. **Token/密码/Webhook URL 绝不出现**在代码、日志、Git 提交、消息正文中 → 用 `[REDACTED]` 或环境变量
2. **禁止 `rm -rf /`、`rm -rf ~`** 等危险递归删除
3. **子 Agent 的 self-report 不可信** → 对副作用操作（HTTP POST、文件写入）要主动验证

---

## 🔄 保持同步

本仓库与 [hermes-methodology](https://github.com/qq449176836-lang/hermes-methodology) 通过 GitHub Actions 自动同步。8 份根文档以 methodology 为权威源。

如果你发现文档内容不一致 → 优先按 methodology 为准，并报告给用户。

---

> *"Every session makes you stronger. This guide is your starting point — the rest is your evolution."*
