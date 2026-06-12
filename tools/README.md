# 🛠️ Hermes Agent Knowledge — 配套工具集

> 与 hermes-agent-knowledge 方法论文档配套的可执行脚本和工具
> 每份文档对应一组工具，实现方法论中描述的核心机制

---

## 📋 工具索引

### 🔴 CONSTITUTION（行为边界）

| 工具 | 类型 | 用途 |
|------|------|------|
| [`secret-scanner.py`](constitution/secret-scanner.py) | Python | 敏感信息扫描（Token/Key/密码），支持 --fix 自动脱敏 |
| [`pre-commit-hook.sh`](constitution/pre-commit-hook.sh) | Bash | Git pre-commit hook，自动调用 scanner 阻止敏感信息提交 |

**用法示例：**
```bash
# 扫描当前目录
python tools/constitution/secret-scanner.py .

# 自动脱敏
python tools/constitution/secret-scanner.py . --fix

# 安装 pre-commit hook
bash tools/constitution/pre-commit-hook.sh --install
```

---

### 🟡 OPERATIONS（运维实操）

| 工具 | 类型 | 用途 |
|------|------|------|
| [`feishu-check.sh`](operations/feishu-check.sh) | Bash | 飞书 7 检查点自检（权限→发布→access_key） |
| [`flask-cleanup.ps1`](operations/flask-cleanup.ps1) | PowerShell | Windows Flask 多进程残留清理 |
| [`lockfile-check.sh`](operations/lockfile-check.sh) | Bash | 锁文件检测与清理（7 类锁 + --clean） |
| [`health-check.sh`](operations/health-check.sh) | Bash | 系统健康检查（Gateway/端口/Cron/磁盘/日志） |

**用法示例：**
```bash
# 飞书自检
bash tools/operations/feishu-check.sh

# 清理 Flask 5000 端口
powershell -File tools/operations/flask-cleanup.ps1 -Port 5000

# 检测并清理残留锁
bash tools/operations/lockfile-check.sh --clean

# 系统健康快照
bash tools/operations/health-check.sh
```

---

### 🧬 EVOLUTION-ENGINE（进化引擎）

| 工具 | 类型 | 用途 |
|------|------|------|
| [`explorer.py`](evolution/explorer.py) | Python | 信息源爬虫（GitHub/HN）+ 价值评分 |
| [`usage-stats.py`](evolution/usage-stats.py) | Python | Skill 使用频率统计 + 自动升降级建议 |

**用法示例：**
```bash
# 采集 GitHub Trending 前 10
python tools/evolution/explorer.py --source github --top 10

# 只看推荐项（>=8 分）
python tools/evolution/explorer.py --source all --filter recommend --json

# 分析 Skill 使用频率
python tools/evolution/usage-stats.py

# 自动升/降级
python tools/evolution/usage-stats.py --apply
```

---

### 💎 KNOWLEDGE-CRYSTALLIZATION（知识结晶）

| 工具 | 类型 | 用途 |
|------|------|------|
| [`distiller.py`](crystallization/distiller.py) | Python | E→N→P 三层蒸馏引擎 |
| [`decay-manager.py`](crystallization/decay-manager.py) | Python | 知识衰减管理（过期/降级/归档） |

**用法示例：**
```bash
# 从 Episodic 蒸馏为 Narrative
python tools/crystallization/distiller.py --mode narrative --input exp.json

# 检测同主题聚类
python tools/crystallization/distiller.py --mode detect --input exp.json

# 查看衰减候选（不执行）
python tools/crystallization/decay-manager.py --target all --dry-run

# 执行衰减清理
python tools/crystallization/decay-manager.py --target skill --apply
```

---

### 📐 SPEC-DRIVEN-DEV（规约驱动开发）

| 工具 | 类型 | 用途 |
|------|------|------|
| [`ambiguity-scanner.py`](spec-driven/ambiguity-scanner.py) | Python | 10 维歧义扫描（🔴BLOCKER/🟡IMPORTANT/🟢SUGGESTION） |

**用法示例：**
```bash
# 扫描 spec.md
python tools/spec-driven/ambiguity-scanner.py spec.md

# JSON 输出
python tools/spec-driven/ambiguity-scanner.py spec.md --json
```

---

### 🤝 MULTI-AGENT-COORDINATION（多 Agent 协同）

| 工具 | 类型 | 用途 |
|------|------|------|
| [`review-engine.py`](coordination/review-engine.py) | Python | 三级审核判定引擎（strict/practical/existence） |
| [`preflight-check.py`](coordination/preflight-check.py) | Python | 产前验证（路径/文件/一致性/清单） |

**用法示例：**
```bash
# 单条审核
python tools/coordination/review-engine.py '{"task":"...","expected":"...","actual":"...","level":"strict"}'

# 产前验证
python tools/coordination/preflight-check.py --paths /c/foo/bar --files file1.py,file2.py
```

---

## 📊 统计

| 方法论文档 | 配套工具数 | 脚本语言 |
|-----------|-----------|---------|
| CONSTITUTION | 2 | Python + Bash |
| OPERATIONS | 4 | Bash + PowerShell |
| EVOLUTION-ENGINE | 2 | Python |
| KNOWLEDGE-CRYSTALLIZATION | 2 | Python |
| SPEC-DRIVEN-DEV | 1 | Python |
| MULTI-AGENT-COORDINATION | 2 | Python |
| **总计** | **13** | |

---

*工具持续完善中，欢迎贡献。每个工具的详细用法见各文件头部的 docstring。*
