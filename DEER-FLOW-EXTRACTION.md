# DEER-FLOW EXTRACTION — DeerFlow 精华提炼

> **源项目**：bytedance/deer-flow v2.0 (⭐71.2k, Super Agent Harness)  
> **提炼日期**：2026-06-14  
> **提炼原则**：不安装重体量框架，提取可迁移的架构设计模式注入现有体系

---

## 提炼概览

DeerFlow 是字节跳动开源的 Super Agent Harness，基于 LangGraph + LangChain，拥有 Skills / Sub-Agents / Sandbox / Memory / Context Engineering / IM Channels 六大子系统。

经分析确认：其与 Hermes + Roundtable 体系高度重叠，**不应安装**。但以下 5 个设计模式可直接注入现有体系，产生实质性提升。

| 精华 # | 模式 | 迁移目标 | 预期收益 |
|--------|------|----------|----------|
| 1 | 渐进式 Skill 加载 | Skill 系统 | 减少 60%+ 无效 token 注入 |
| 2 | 子 Agent 结构化回传 | Roundtable 协同协议 | Worker→Host 通信可程序化合并 |
| 3 | 嵌入式 Python SDK | Hermes API 层 | 进程内访问 + CI 验证一致性 |
| 4 | 写入时去重 | Memory / OpenViking | 防止相同偏好无限累积 |
| 5 | 工具调用恢复 | Gateway 健壮性 | provider 中断后自动修复对话历史 |

---

## 精华 1：渐进式 Skill 加载

### DeerFlow 做法

```
Skills 加载策略：
  基础加载 → 只注入 Skill 元数据（名称/描述/触发词）
  按需加载 → 任务需要时，才加载完整 SKILL.md
  显式激活 → /skill-name 命令 = 单回合注入完整内容

文件结构：
  /mnt/skills/public/
  ├── research/SKILL.md
  ├── report-generation/SKILL.md
  └── slide-creation/SKILL.md
  /mnt/skills/custom/
  └── your-custom-skill/SKILL.md
```

### 当前差距

Hermes 在每次会话启动时**全量注入**所有 Skill 内容到系统提示。24 个 Skill 的完整 SKILL.md 文件一次性加载，大量 token 消耗在"可能用不上"的 Skill 上。

### 迁移方案

```yaml
# Skill 加载策略（三层）
skill_loading:
  # Layer 0: 始终注入（不可降级）
  always_load:
    - think-before-coding    # 编码铁律
    - viking-realtime-recall # 召回铁律
    - viking-realtime-sync   # 同步铁律
  
  # Layer 1: 元数据注入（名称 + 描述 + 触发词，~50 tokens/skill）
  metadata_only:
    - context-squeezer
    - session-checklist
    - feishu-alert
    - github-repo-management
    # ... 其余 Skill
  
  # Layer 2: 按需加载（触发后注入完整内容）
  on_demand:
    trigger_by: 关键词匹配 | 显式 /skill-name | delegate 角色匹配
```

### 预期效果

```
当前（24 Skill 全量注入）：
  系统提示 ~48,000+ tokens（.skills_prompt_snapshot.json 显示 48KB）

渐进式（3 always + 21 metadata）：
  系统提示 ~8,000 tokens（含铁律 + 元数据）
  
→ 节省 ~40,000 tokens / 会话
→ 按 DeepSeek V3 定价 ≈ ¥0.011 / 会话
→ 日 50 会话 ≈ ¥0.54 / 天 ≈ ¥16 / 月
```

### 实现要点

1. **Skill 元数据提取** → 每个 SKILL.md 前 5 行自动解析为 name/description/trigger_words
2. **触发匹配** → 用户输入 + 当前上下文关键词与 trigger_words 做交集
3. **铁律 Skill 不可降级** → 标记为 `always_load: true` 的 Skill 绕过渐进策略
4. **降级不降权** → on_demand Skill 仍保留在 Skill 列表中，只是内容不预注入

---

## 精华 2：子 Agent 结构化回传

### DeerFlow 做法

```
Lead Agent 分解任务 → 并行 fan-out 到 N 个子 Agent
    ↓
每个子 Agent 返回结构化 result（不是自由文本）
    ↓
Lead Agent 程序化合并（不是 LLM 再理解一次）

Sub-agent result schema:
  {
    "status": "success" | "failed" | "partial",
    "output": { ... 结构化数据 ... },
    "artifacts": ["/mnt/user-data/outputs/report.md"],
    "summary": "一句话摘要",
    "token_usage": { "input": 1234, "output": 567 }
  }
```

### 当前差距

Roundtable v1.0 Worker→Host 通信是**自由文本摘要**。Host 需要 LLM 重新解析每个 Worker 的返回才能判断下一步，"合并多个 Worker 结果"也是一次额外 LLM 调用。

### 迁移方案

```json
// Roundtable v2.0: Worker Result Schema
{
  "worker_id": "dev-01",
  "task_id": "task-42",
  "status": "pass" | "fail" | "blocked",
  
  // ✅ 结构化输出（Host 可程序化消费）
  "deliverables": [
    {
      "type": "code",
      "path": "/outputs/server.py",
      "checksum": "sha256:abc123",
      "description": "Flask 后端主文件"
    }
  ],
  
  // ⚠️ 失败信息（调度员可直接用）
  "failure": {
    "type": "interface_mismatch" | "missing_dependency" | "logic_error" | "timeout",
    "detail": "端口 5000 已被占用",
    "evidence": "netstat 输出显示 PID 1234"
  },
  
  // 📊 元数据
  "metrics": {
    "token_used": 12345,
    "cost_estimated": 0.0034,
    "duration_seconds": 45.2
  },
  
  // 自由文本兜底（仅在无法结构化时使用）
  "narrative": "已完成 Flask 后端编写..."
}
```

### 预期效果

```
当前 Host 消耗：
  合并 3 个 Worker 结果 → 1 次 LLM 调用 (~5,000 tokens)

结构化后：
  Host 程序化合并 → 0 次 LLM 调用
  只在 ambiguous / 冲突时用 LLM 裁决

→ 每次 multi-worker 任务节省 ~5,000 tokens
→ 复杂任务（5+ Worker）节省 ~20,000 tokens
```

---

## 精华 3：嵌入式 Python SDK

### DeerFlow 做法

```python
from deerflow.client import DeerFlowClient

client = DeerFlowClient()

# 聊天
response = client.chat("Analyze this paper", thread_id="my-thread")

# 流式（LangGraph SSE 协议）
for event in client.stream("hello"):
    if event.type == "messages-tuple":
        print(event.data["content"])

# 管理 API
models = client.list_models()
skills = client.list_skills()
client.update_skill("web-search", enabled=True)
```

核心设计：**SDK 返回 Schema 与 HTTP Gateway API 完全对齐，CI 自动验证一致性。**

### 迁移方案

```python
# Hermes Python SDK 设计
from hermes.client import HermesClient

client = HermesClient(endpoint="http://127.0.0.1:1933")  # OpenViking 端点

# 记忆操作（对齐 viking_* 工具）
memories = client.memory.search("多Agent协同", limit=5)
client.memory.remember("新的偏好", category="preference")

# 知识库操作
knowledge = client.knowledge.search("棘轮循环", limit=5)

# 会话管理
client.session.recall(thread_id="xxx", query="上次说的端口问题")

# Gateway 健康检查
health = client.health()  # {"status": "ok", "version": "0.3.24"}
```

### 预期收益

- **分布式 Worker 可直接导入 SDK**，不依赖 Hermes 工具链
- **CI 可验证** SDK 与 Gateway Schema 的一致性
- **离机开发** → 在笔记本上写 Worker 脚本，import hermes SDK 连服务器

---

## 精华 4：写入时去重

### DeerFlow 做法

> "Memory updates now skip duplicate fact entries at apply time, so repeated preferences and context do not accumulate endlessly across sessions."

核心逻辑：写入记忆前，检查是否与已有记忆**语义重复**→ 跳过而非追加。

### 当前差距

Hermes 的 `memory` 工具和 OpenViking 的 `viking_remember` 都是**无条件追加**。相同偏好被多次写入时，memory 和 VikingDB 记忆库会无限累积冗余条目。实际案例：`"🔴 铁律：每次回复前必须viking_search()"` 如果被多次 viking_remember，会有 N 份副本。

### 迁移方案

```python
# Memory 写入逻辑增强
async def memory_add_with_dedup(content: str, target: str):
    # 1. 语义搜索已有记忆（找最近 10 条同类型）
    existing = await viking_search(
        query=content[:100],
        scope=f"viking://user/default/{target}/memories/",
        limit=10
    )
    
    # 2. 相似度检查（阈值 0.85）
    if existing and existing[0].score > 0.85:
        # 3. 更新已有记忆的时间戳，跳过新增
        touch(existing[0].uri)
        return {"status": "deduplicated", "existing_uri": existing[0].uri}
    
    # 4. 无重复 → 正常写入
    return await viking_remember(content)
```

### 预期效果

- Memory 条目数从线性增长 → 对数增长
- 防止相同铁律/偏好/约定出现 3-5 份副本
- VikingDB 记忆库存储成本降低 30-50%

---

## 精华 5：工具调用恢复

### DeerFlow 做法

> "When a provider or middleware interrupts a tool-call loop, DeerFlow now strips provider-level raw tool-call metadata on forced-stop assistant messages and injects placeholder tool results for dangling calls before the next model invocation."

核心逻辑：
1. 检测到 provider 中断了工具调用循环
2. 剥离 assistant 消息中的原始 tool-call 元数据
3. 为悬空的 tool_call_id 注入占位 tool 结果
4. 修复后的消息历史 → 下一次模型调用不会因 malformed history 报错

### 迁移到 Hermes Gateway

```python
# Gateway 消息历史修复器
async def recover_interrupted_tool_calls(messages: list) -> list:
    """
    当 provider 中断了 tool-call 循环，修复消息历史。
    
    场景：assistant 发出了 3 个 tool_call，provider 在第 2 个完成后中断。
    第 3 个 tool_call 没有对应的 tool_result → OpenAI 兼容模型会报 malformed history。
    """
    fixed = []
    pending_tool_ids = set()
    
    for msg in messages:
        if msg.role == "assistant" and msg.tool_calls:
            for tc in msg.tool_calls:
                pending_tool_ids.add(tc.id)
            # 剥离原始 tool-call 元数据
            fixed.append(strip_raw_metadata(msg))
        
        elif msg.role == "tool" and msg.tool_call_id in pending_tool_ids:
            pending_tool_ids.remove(msg.tool_call_id)
        
        fixed.append(msg)
    
    # 为悬空的 tool_call 注入占位结果
    for dangling_id in pending_tool_ids:
        fixed.append({
            "role": "tool",
            "tool_call_id": dangling_id,
            "content": "[Tool call interrupted — results unavailable]"
        })
    
    return fixed
```

### 预期效果

- DeepSeek V4 等严格校验 tool_call_id 序列的模型不再因中断报错
- 长任务（10+ 工具调用）稳定性提升
- 减少因 "malformed history" 导致的会话重建

---

## 实施路线图

```
阶段 1（本周）：精华 1 + 4
  ├── Skill 元数据提取脚本
  ├── 渐进式加载配置
  └── Memory 写入去重逻辑

阶段 2（下周）：精华 2 + 5
  ├── Roundtable Worker Result Schema
  ├── Host 程序化合并逻辑
  └── Gateway 工具调用恢复

阶段 3（2周内）：精华 3
  └── Hermes Python SDK（hermes-client pip package）
```

---

## 关键设计原则

> 提炼而非照搬。只取设计模式，不搬代码。每个注入点必须：
> 1. **适配**现有架构（不引入新依赖）
> 2. **可验证**（有明确的成功标准）
> 3. **可回滚**（改动独立，不影响其他模块）

---

> *"好的框架不是拿来装的，是拿来读的。"*
