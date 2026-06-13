---
name: session-checklist
description: "会话启动检查——确保三层检索和棘轮循环每轮执行"
---

# ✅ Session Checklist — 方法论执行检查点

> 每次会话开始时自动加载，确保核心方法论不沦为纸上文档。

---

## 任务前（三层检索）

接到新任务时，**在动手之前**必须走完三层：

```
□ Layer 1: 精确匹配
  → search_files 搜索项目已有代码/文档
  → 检查 Memory 中是否有同类问题记录
  → 检查 ~/.hermes/skills/ 是否有直接匹配的 Skill

□ Layer 2: 语义扩展
  → 将关键词做语义扩展（同义词、相关领域）
  → 扩大搜索范围到 knowledge 文档

□ Layer 3: Skill 库对比
  → 遍历可能相关的 Skill
  → 即使不完全匹配，核心思路可能可迁移

❌ 禁止：跳过检索直接写代码
✅ 目标：能用现成方案就不造轮子
```

---

## 任务后（棘轮循环）

任务完成时，必须走完整闭环，**不半途而废**：

```
□ 1. 记录 → 写经验卡片（Context/Action/Result/Learning 四要素）
   位置: <skill-dir>/EXPERIENCE.md 或 ~/.hermes/knowledge-base/

□ 2. 提炼 → 从具体案例提取通用模式
   格式: "模式：XXX" — 能直接回答"这类问题的一般解法是什么"

□ 3. 标准化 → 更新文档或创建 Skill
   ≥3 次同类经验 → 升华为 SKILL.md

□ 4. 推送 → 上传到 heyuan 仓库
   路径: skills/<name>/

❌ 禁止：修完就停（遭遇→诊断→修复→...停！）
✅ 目标：每次经验都变成永久可复用的知识
```

---

## 快速自检

每个回复前问自己：

1. 这次操作前我搜索过了吗？
2. 上次同类任务的经验卡片写了吗？
3. 新产出的代码/脚本推送了吗？

---

## 知识文档索引

会话中遇到对应问题时，主动加载：

| 文档 | 当需要... |
|------|----------|
| CONSTITUTION.md | 判断什么能做/不能做 |
| METHODOLOGY.md | 不知道怎么拆解任务 |
| KNOWLEDGE-CRYSTALLIZATION.md | 决定经验存哪里、怎么存 |
| EXPERIENCE-LIFECYCLE.md | 理解经验的完整生命周期 |
| OPERATIONS.md | 操作类踩坑参考 |
