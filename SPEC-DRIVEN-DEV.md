# SPEC-DRIVEN DEV — 规约驱动开发管道

> **"先定宪法，再写法律；先写规格，再写代码。"**
>
> 7 阶段不可逆管道 + 10 维歧义扫描 + 跨产物一致性分析 + 棘轮闭环记忆蒸馏。

---

## 核心理念

传统开发中，需求存在于聊天记录里、存在于开发者的脑子里，唯独不存在于可以被工具读取和验证的结构化文档中。SDD 的核心假设：**规格是第一公民，代码是规格的可执行产物。**

```
Constitution ──→ Specify ──→ Clarify ──→ Plan ──→ Tasks ──→ Analyze ──→ Implement
     ↑                                                                       │
     └─────────────── 棘轮闭环记忆蒸馏 ←─────────── 经验累积 ────────────────┘
```

七阶段不可逆流动。每个阶段的输出是下一阶段的刚性输入。不允许跳过，不允许回溯绕过。

---

## 阶段 0：Constitution — 宪章加载

**目标：建立项目的不可变约束边界。**

自动搜索并加载 `.hermes-constitution.md`（项目级 → 父目录 → 全局）。宪章中的不可变原则作为后续所有阶段的硬约束——Plan/Implement 阶段强制遵守，禁止事项在任何提案中自动排除。

---

## 阶段 1：Specify — 规格定义

**目标：将用户需求转化为结构化的功能规格文档。**

产出 `specs/<feature>/spec.md`，包含用户故事、IN-SCOPE/OUT-OF-SCOPE、数据模型、功能需求、非功能需求等。不确定的条目标记 `[NEEDS-CLARIFICATION]`。

### 需求质量 Checklist（质量门）

> 规格的本质是"英语单元测试"——每一条需求陈述应当像单元测试一样可验证、无歧义。

**三条硬规则**：
1. 禁止 Verify/Test/Confirm 开头（那是测试用例，不是需求质量检查）
2. ≥80% 条目必须有 `[Spec §X.Y]` 追溯引用
3. 每条标注质量维度：`[Completeness]` `[Clarity]` `[Consistency]` `[Measurability]` `[Coverage]`

**门禁**：所有条目 ✅ 方可进入下一阶段。

---

## 阶段 2：Clarify — 10 维歧义扫描

**目标：系统性地识别并消除规格中的所有歧义。**

这是管道中最关键的阶段——对规格执行 10 个维度的歧义扫描：

| # | 维度 | 核心检查 |
|---|------|---------|
| 1 | **功能范围** | 边界在哪？有无"等等"模糊表述？ |
| 2 | **数据模型** | 字段类型精度？必填/可选？唯一性约束？ |
| 3 | **UX/界面行为** | 各种状态下的 UI 行为？交互反馈形式？ |
| 4 | **非功能需求** | QPS/延迟/P99 量化？可用性目标？ |
| 5 | **集成与依赖** | 外部服务契约？降级策略？循环依赖？ |
| 6 | **边界条件** | 上下界？空输入？并发冲突？时区？ |
| 7 | **约束与假设** | 假设经过验证？资源限制量化？ |
| 8 | **安全与权限** | 认证/授权模型？数据脱敏？审计日志？ |
| 9 | **错误处理** | 异常码？重试策略？超时？事务边界？ |
| 10 | **可观测性** | 日志级别？指标埋点？告警条件？ |

### 三层分流交互策略

```
🔴 BLOCKER → 逐题交互，即时回写（解决一个再问下一个）
🟡 IMPORTANT → 汇总后一次性呈现
🟢 NICE-TO-HAVE → 合并为 checkbox 清单，一键确认
```

**门禁**：无 BLOCKER 级别歧义剩余方可进入 Plan。

---

## 阶段 3：Plan — 技术方案

**目标：基于澄清后的规格，制定可执行的技术方案。**

产出 `plan.md`，包含架构概览、技术选型及理由、组件设计、接口定义、数据流、风险缓解。每项技术选型必须有明确理由。集成 `experience-retrieval` 检索历史类似方案的经验（如"上次 Z 模块的接口设计被要求返工"→ 本次优先对齐）。

---

## 阶段 4：Tasks — 任务拆解

**目标：将技术方案拆解为可独立执行和验证的原子任务。**

产出 `tasks.md`，每个任务 2-4 小时内可完成，有可独立验证的产出，状态可二值判定。任务间依赖形成 DAG（有向无环图）。可选：同步到 GitHub/GitLab Issue。

---

## 阶段 5：Analyze — 跨产物一致性分析（质量门）

**目标：在编码前进行跨产物一致性分析，发现不一致则阻塞实施。**

### 六大检测维度

| 维度 | 检测内容 | 严重度 |
|------|---------|--------|
| 重复 (Duplication) | 同一需求多处冗余定义 | MEDIUM |
| 歧义 (Ambiguity) | Clarify 阶段应消除但残留的模糊表述 | HIGH |
| 欠规范 (Underspecification) | tasks 缺关联 spec；plan 未覆盖 IN-SCOPE | HIGH |
| 宪章违规 (Constitution Violation) | plan/tasks 违反宪章约束 | **CRITICAL** |
| 覆盖缺口 (Coverage Gap) | spec IN-SCOPE 在 tasks 中找不到对应 | HIGH |
| 不一致 (Inconsistency) | plan 技术选型与宪章冲突 | **CRITICAL** |

**只读原则**：Analyze 不修改任何文件，所有发现写入 `analyze.md`。

**门禁**：CRITICAL = 0 方可进入 Implement。

---

## 阶段 6：Implement — 编码实施

**目标：按任务拓扑序逐个实施，每个任务完成后立即验证。**

### 实施前 Checklist 门禁（7 项全通过方可启动）

| # | 检查项 | 来源 |
|---|--------|------|
| 1 | 需求质量 Checklist | §1.4 checklist.md 全部 ✅ |
| 2 | 无 BLOCKER 歧义 | clarify.md 🔴=0 |
| 3 | 宪章合规 | plan.md 全部通过 |
| 4 | 产物追溯链完整 | 每个任务有关联 spec 条目 |
| 5 | Analyze 门禁通过 | analyze.md CRITICAL=0 |
| 6 | 任务依赖合法 DAG | 无循环依赖 |
| 7 | Checklist 追溯覆盖 | ≥80% 条目有 [Spec §X.Y] |

### 刚性追溯

实现代码中标注对应 spec 条目：

```python
# @spec: spec.md §3.2 - 用户头像上传
# @task: T4 - 实现头像上传 API
async def upload_avatar(user_id: str, file: UploadFile):
    ...
```

---

## 棘轮闭环：经验蒸馏

每次管道执行完成后，经验被不可逆地推送到三层记忆系统：

```
Episodic (发生了什么) → 存入 Session Transcript
     │  提取关键教训
     ▼
Narrative (学到了什么) → 存入 Memory + Tags
     │  检测 >=3 次重复模式
     ▼
Procedural (怎么做) → 更新 SKILL.md
```

### 检索集成

| 管道阶段 | 检索哪层记忆 | 目的 |
|---------|------------|------|
| Specify | Episodic | 类似功能的历史规格 |
| Clarify | Narrative | 同类功能的历史歧义 |
| Plan | Narrative + Procedural | 相似技术方案和经验教训 |
| Analyze | Narrative | 历史一致性问题和违规模式 |
| Implement | Episodic | 类似功能的实现参考 |

---

## 常见反模式

| 反模式 | 后果 |
|--------|------|
| 跳过 Constitution | 后续大幅返工 |
| Clarify 走过场 | 隐式假设在 Implement 才暴露 |
| BLOCKER 批量轰炸用户 | 用户注意力崩溃，回复质量下降 |
| Plan 和 Implement 脱节 | 设计很好但编码偏离 |
| 棘轮逆行 | 相同错误在下一次重复 |
| 跳过 Analyze | spec/plan/tasks 不一致到编码才暴露 |

---

> *"每一次跳过规格的借口，都是下一次返工的理由。"*
