# TOOL-CALL RECOVERY — 工具调用恢复模式

> **来源**：DeerFlow 精华提炼 #5  
> **核心机制**：provider 中断 tool-call 循环时，自动修复消息历史，防止 malformed history 错误  

---

## 问题场景

当 Agent 发出多个 tool_call，provider 在第 N 个完成后中断（stop reason ≠ tool_calls）。导致：

```
assistant: 发出 tool_call_1, tool_call_2, tool_call_3
    ↓
tool_result_1 ✅
tool_result_2 ✅
    ↓  ← provider 在此中断（连续 token 限制 / 网络波动 / API 限流）
tool_result_3 ❌  ← 缺失
    ↓
下一次 model 调用 → 严格校验 tool_call_id 序列 → malformed history 错误
```

OpenAI 兼容模型（DeepSeek V4 等）会报：
```json
{"error": "tool_call_id 'call_xxx' not found in previous messages"}
```

## DeerFlow 解决方案

三步恢复：

### Step 1: 检测

识别 assistant 消息中 tool_calls 数量 > 后续 tool 消息数量。

### Step 2: 剥离元数据

将中断的 assistant 消息中的原始 tool-call 元数据剥离（保留消息本身，去掉 tool_calls 字段）。

### Step 3: 注入占位结果

为每个悬空的 tool_call_id 注入一条 tool 消息：

```json
{
  "role": "tool",
  "tool_call_id": "call_dangling_xxx",
  "content": "[Tool call interrupted — provider stopped before this tool could complete]"
}
```

## 实现

```python
from typing import Literal


def recover_interrupted_tool_loop(
    messages: list[dict]
) -> tuple[list[dict], Literal["repaired", "clean"]]:
    """
    检测并修复被 provider 中断的工具调用循环。
    
    返回：(修复后的消息列表, 状态)
    - "repaired": 检测到中断并已修复
    - "clean": 无中断，原始消息通过
    """
    
    # 收集所有 tool_call_id
    pending_ids: set[str] = set()
    last_assistant_idx: int | None = None
    
    for i, msg in enumerate(messages):
        if msg.get("role") == "assistant":
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                pending_ids.clear()  # 新一批 tool_calls 覆盖旧悬空
                for tc in tool_calls:
                    pending_ids.add(tc["id"])
                last_assistant_idx = i
        
        elif msg.get("role") == "tool":
            tc_id = msg.get("tool_call_id")
            if tc_id in pending_ids:
                pending_ids.discard(tc_id)
    
    # 全部完成 → 无需修复
    if not pending_ids:
        return messages, "clean"
    
    # 需要修复
    repaired = list(messages)
    
    # Step 1: 剥离中断 assistant 的原始 tool_calls 元数据
    if last_assistant_idx is not None:
        repaired[last_assistant_idx] = {
            **repaired[last_assistant_idx],
            "tool_calls": [],  # 清空 tool_calls 数组
            "_recovery_note": f"Original {len(pending_ids)} dangling tool_call(s) stripped"
        }
    
    # Step 2: 为每个悬空 tool_call_id 注入占位结果
    for dangling_id in sorted(pending_ids):
        repaired.append({
            "role": "tool",
            "tool_call_id": dangling_id,
            "content": (
                "[Tool call interrupted — provider stopped before "
                "this tool could complete. Results are unavailable.]"
            )
        })
    
    return repaired, "repaired"


# === 集成到 Gateway ===
def prepare_messages_for_model(raw_messages: list[dict]) -> list[dict]:
    """Gateway 在每次模型调用前执行。"""
    messages, status = recover_interrupted_tool_loop(raw_messages)
    
    if status == "repaired":
        logger.warning(
            f"Tool-call loop repaired: injected placeholder results "
            f"for {len([m for m in messages if m.get('role') == 'tool' and '[Tool call interrupted' in m.get('content', '')])} dangling calls"
        )
    
    return messages
```

## 适用条件

| 条件 | 是否需要恢复 |
|------|:---:|
| provider `finish_reason` ≠ `tool_calls` 且存在未完成的 tool_call | ✅ 需要 |
| 所有 tool_call 都有对应 tool_result | ❌ 不需要 |
| 对话中有多轮完整 tool 调用 | ❌ 不需要 |

## 边界情况

1. **部分结果** — 3 个 tool_call，2 个完成，1 个中断 → 修复第 3 个
2. **完全中断** — 3 个 tool_call，0 个完成 → 全部注入占位
3. **嵌套中断** — 连续两轮中断 → 分别修复，不混淆 tool_call_id
4. **重试后成功** — provider 重试时完整完成 → 覆盖之前的修复消息

## 实施清单

- [ ] Gateway 添加 `recover_interrupted_tool_loop()` 到消息预处理管道
- [ ] 添加日志记录：每次修复时记录 dangling tool_call 数量
- [ ] 添加监控指标：`hermes_tool_loop_recovery_total` counter
- [ ] 测试：模拟 provider 中断场景的集成测试

---

> *"不要因为 provider 的中断而丢掉整个会话。"*
