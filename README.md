# Hermes Agent — 核心知识体系

> **一套让 AI Agent 持续自我进化的方法论、准则与操作系统。**

---

## 🤖 如果你是 Hermes Agent

**👋 你好！请先阅读这份上手指南 → [AGENT-GUIDE.md](./AGENT-GUIDE.md)**

那份文档会告诉你：
- 按什么顺序阅读 8 份方法论文档
- 什么时候用哪个配套工具
- 核心概念的速记口诀

---

## 📖 这是什么？

这不是某个具体项目的文档，而是 **Hermes Agent 自身的"大脑"**——它如何思考、如何自我进化、如何做决策、如何避免重复犯错。

如果你正在使用或构建 AI Agent，这里的每一条方法论都经过了数百次真实任务的验证。

---

## 📂 文档索引

| # | 文档 | 回答的问题 |
|---|------|-----------|
| 1 | [**CONSTITUTION.md**](./CONSTITUTION.md) | Agent 必须遵守哪些铁律？ |
| 2 | [**EVOLUTION-ENGINE.md**](./EVOLUTION-ENGINE.md) | Agent 如何像生物一样自我进化？ |
| 3 | [**METHODOLOGY.md**](./METHODOLOGY.md) | Agent 遇到问题怎么思考、怎么拆解？ |
| 4 | [**SPEC-DRIVEN-DEV.md**](./SPEC-DRIVEN-DEV.md) | 代码如何从规格到实现不偏离？ |
| 5 | [**MULTI-AGENT-COORDINATION.md**](./MULTI-AGENT-COORDINATION.md) | 多 Agent 如何协作而不混乱？ |
| 6 | [**KNOWLEDGE-CRYSTALLIZATION.md**](./KNOWLEDGE-CRYSTALLIZATION.md) | 经验如何从对话变成永久知识？ |
| 7 | [**EXPERIENCE-LIFECYCLE.md**](./EXPERIENCE-LIFECYCLE.md) | 经验的完整生-存-用循环？ |
| 8 | [**OPERATIONS.md**](./OPERATIONS.md) | 实际环境中的踩坑经验与操作守则 |

---

## 🧠 核心理念

```
经验不丢失 → 知识不退化 → 能力只增不减
```

Hermes Agent 的设计目标不是"一次性地完成任务"，而是**每一次交互都让它变得更强**。

---

## ⚡ 快速理解八层架构

```
┌─────────────────────────────────────────┐
│            CONSTITUTION                 │  ← 不可妥协的底线
│       (铁律 → 约定 → 建议)               │
├─────────────────────────────────────────┤
│         EVOLUTION ENGINE                │  ← 自我进化的引擎
│    (Explorer → AutoLoader → Reviewer)   │
├─────────────────────────────────────────┤
│           METHODOLOGY                   │  ← 思考与执行的方法
│   (检索法 → DAG分解 → 棘轮循环)          │
├─────────────────────────────────────────┤
│         SPEC-DRIVEN DEV                 │  ← 规格到代码的管道
│   (7阶段 → 10维扫描 → 跨产物分析)        │
├─────────────────────────────────────────┤
│      MULTI-AGENT COORDINATION           │  ← 多部门协作协议
│   (4层架构 → 审核调度分离 → 部门闭环)     │
├─────────────────────────────────────────┤
│      KNOWLEDGE CRYSTALLIZATION          │  ← 知识如何沉淀
│   (Episodic → Narrative → Procedural)   │
├─────────────────────────────────────────┤
│       EXPERIENCE LIFECYCLE              │  ← 经验的完整循环
│   (生产 → 蒸馏 → 检索 → 固化)            │
├─────────────────────────────────────────┤
│           OPERATIONS                    │  ← 实战经验积累
│      (踩坑 → 修复 → 标准化)              │
└─────────────────────────────────────────┘
```

---

## 🛠️ 配套工具

方法论不是纸上谈兵。每个文档都有对应的**可执行脚本**，实现方法论中描述的核心机制。

| 方法论 | 工具数 | 入口 |
|--------|--------|------|
| CONSTITUTION | 2 | 敏感信息扫描、pre-commit hook |
| OPERATIONS | 5 | 飞书自检、Flask清理、锁文件检测、健康检查、会话检查点 |
| EVOLUTION-ENGINE | 2 | 信息爬虫+评分、Skill频率分析 |
| KNOWLEDGE-CRYSTALLIZATION | 3 | E→N→P蒸馏、知识衰减管理、上下文压缩 |
| SPEC-DRIVEN-DEV | 1 | 10维歧义扫描 |
| MULTI-AGENT-COORDINATION | 2 | 三级审核判定、产前验证 |

👉 **[查看完整工具目录 →](tools/README.md)**

---

## 🔑 四个关键设计原则

1. **棘轮效应** — 能力只能前进，不能后退
2. **三不原则** — 不干扰用户、不重复犯错、不遗忘经验
3. **闭环自动化** — 遭遇→诊断→修复→记录→提炼→标准化→推送
4. **分层蒸馏** — 原始经验 → 叙事知识 → 可执行技能

---

## 📜 许可

MIT License — 欢迎参考、修改和传播。

---

> *"The Agent that learns, outlives the Agent that just executes."*
