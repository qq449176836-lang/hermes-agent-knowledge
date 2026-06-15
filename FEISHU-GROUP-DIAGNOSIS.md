# Hermes 飞书群聊诊断与修复全流程

> **适用场景**：Hermes CN Desktop 的 Bot 被加入飞书群后无响应，@Bot 不回复  
> **诊断实例**：阿里云杭州 Hermes（47.121.129.203）连通「开荒群-AI」全程记录  
> **耗时参考**：排查到修复 15 分钟  
> **日期**：2025-06-15

---

## 1. 症状诊断

### 1.1 确认问题范围

```bash
# 检查 channel_directory.json —— 看看有没有 group 类型的频道
grep "type" "$HERMES_HOME/channel_directory.json"
```

期望看到：

```json
{"type": "dm", ...}    ← 私聊，应该有
{"type": "group", ...}  ← 群聊，必须有
```

如果只有 `dm` 没有 `group` → 问题确认：Gateway 不知道任何群聊存在。

### 1.2 追踪 Gateway 日志

```bash
# 检视日志中是否出现过群消息
grep "group" "$HERMES_HOME/logs/gateway.log" | tail -20

# 检视是否有 bot.added 事件
grep "bot.added" "$HERMES_HOME/logs/gateway.log"
```

空结果 → Gateway 从未接收到群聊相关事件 → 根因在飞书配置。

---

## 2. 根因排查（三层检查法）

### 第一层 — Hermes 内部配置

```bash
# 检查 .env 中的飞书配置
grep "FEISHU" "$HERMES_HOME/.env"
```

关键值检查：

| 变量 | 期望值 | 说明 |
|------|--------|------|
| `FEISHU_GROUP_POLICY` | `enabled` | **不是 `disabled`！** 这是群聊总开关 |
| `FEISHU_REQUIRE_MENTION` | `true`（建议） | 是否只在被@时才回复 |

如果 `FEISHU_GROUP_POLICY=disabled` → 立刻改为 `enabled`：

```bash
sed -i 's/FEISHU_GROUP_POLICY=disabled/FEISHU_GROUP_POLICY=enabled/' "$HERMES_HOME/.env"
```

### 第二层 — 飞书开放平台权限

去 [飞书开放平台](https://open.feishu.cn) → 你的 App → **权限管理**，确认勾选了：

| 权限 | 用途 |
|------|------|
| `im:chat` | 获取群组信息 |
| `im:message:group` | 接收和发送群消息 |

加完点 **「发布」**，必须发布才生效。

### 第三层 — 飞书开放平台事件订阅

**这一步最容易遗漏。** 权限和事件订阅是两套独立的东西。

去 **事件与回调** → **事件订阅**，添加以下事件：

| 事件 | 触发场景 |
|------|----------|
| `im.message.receive_v1` | 群聊 + 私聊消息 |
| `im.chat.member.bot.added_v1` | 机器人被加入群聊 |

确认 **事件订阅方式** 为 **WebSocket**（与 Hermes 的连接方式一致）。

加完立刻点 **「发布」**。

> ⚠️ **常见陷阱**：权限开了、事件也加了，但忘了点「发布」。不发布 = 不生效。

---

## 3. 修复步骤

### Step 1: 改 .env（30 秒）

```bash
sed -i 's/FEISHU_GROUP_POLICY=disabled/FEISHU_GROUP_POLICY=enabled/' "$HERMES_HOME/.env"
grep FEISHU_GROUP_POLICY "$HERMES_HOME/.env"  # 确认修改
```

### Step 2: 飞书开放平台三连（2 分钟）

1. **权限管理** → 勾选 `im:chat` + `im:message:group` → 发布
2. **事件订阅** → 添加 `im.message.receive_v1` + `im.chat.member.bot.added_v1` → WebSocket → 发布
3. **确认 App 已发布**（不是草稿状态）

### Step 3: 重启 Hermes（1 分钟）

重启 Hermes Desktop → Gateway 自动以新配置启动。

### Step 4: 触发群聊发现（5 秒）

```
Bot 被加群 → 飞书推送 bot.added 事件 → Gateway 注册群到 channel_directory
     ↓
 如果 bot.added 事件被遗漏（Bot 在配置完成前就已经在群里）
     ↓
 在群里 @Bot 发一条消息 → 飞书推送 im.message.receive_v1
     ↓
 Gateway 自动发现这个群 → 写入 channel_directory
```

---

## 4. 验证

### 4.1 直接调用飞书 API（终极确认）

如果修复后仍不确定，用飞书 API 直接确认 Bot 是否在群里：

```python
import json, urllib.request, os

# 读取凭据
with open(f"{os.environ['HERMES_HOME']}/.env") as f:
    env = {k:v for line in f if '=' in line for k,v in [line.strip().split('=',1)]}

# 获取 tenant_access_token
req = urllib.request.Request('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
    data=json.dumps({"app_id": env['FEISHU_APP_ID'], "app_secret": env['FEISHU_APP_SECRET']}).encode(),
    headers={'Content-Type': 'application/json'}, method='POST')
token = json.loads(urllib.request.urlopen(req).read())['tenant_access_token']

# 列出所有群聊
req2 = urllib.request.Request('https://open.feishu.cn/open-apis/im/v1/chats?page_size=20',
    headers={'Authorization': f'Bearer {token}'})
chats = json.loads(urllib.request.urlopen(req2).read())
for c in chats['data']['items']:
    print(f"群: {c['name']} | chat_id={c['chat_id']}")
```

### 4.2 Gateway 日志验证

```bash
# 确认群聊消息记录出现
grep "Inbound group message" "$HERMES_HOME/logs/gateway.log" | tail -5
```

期望看到：
```
[Feishu] Inbound group message received: ... chat_id=oc_xxx ... text='...'
```

---

## 5. 排查全景图

```
问题：群聊无响应
    │
    ├─ Layer 1: Hermes .env
    │   FEISHU_GROUP_POLICY=?  
    │   ├─ disabled → ❌ 改成 enabled
    │   └─ enabled → 进入 Layer 2
    │
    ├─ Layer 2: 飞书权限
    │   im:chat / im:message:group ?
    │   ├─ 缺失 → ❌ 添加 + 发布
    │   └─ 已配置 → 进入 Layer 3
    │
    ├─ Layer 3: 事件订阅
    │   im.message.receive_v1 / bot.added_v1 ?
    │   ├─ 缺失 → ❌ 添加 + 发布（最容易漏）
    │   └─ 已配置 → 进入验证
    │
    └─ 验证
        ├─ 群里 @Bot 发消息
        ├─ grep "group message" gateway.log
        ├─ FEISHU API chats list
        └─ ✅ 全部通过 → 群聊连通
```

---

## 6. 本次诊断实录

| 时间 | 发现 | 行动 |
|------|------|------|
| 排查开始 | channel_directory 15 个 DM，0 个 group | 锁定根因在飞书配置 |
| grep gateway.log | 自 6/10 起零个 `bot.added` 事件 | 飞书侧没推送过 |
| `FEISHU_GROUP_POLICY=disabled` | .env 群聊总开关关闭 | sed 改为 enabled |
| ⚠️ 修改后重启仍无群 | 权限已开但事件订阅可能遗漏 | API 直接查：Bot 在 1 个群 |
| 发送测试消息到群 | API 能发，Gateway 能收 | ✅ **反向通道确认连通** |
| 最终结论 | 三层全修后，群聊 @ 即通 | 通道建立 |

---

## 7. 注意事项

1. **权限开了但没发布** = 没开。飞书开放平台任何改动必须点「发布」
2. **Bot 在配置前加群** → bot.added 事件已被丢弃。群里有熟人 @ 一条消息即可触发 Gateway 自动发现
3. **FEISHU_REQUIRE_MENTION=true** → 群聊里不用 @ 的消息会被忽略，这是**合理的**——防止 Bot 对每条消息都回复
4. **WebSocket 模式不支持所有事件** → 大部分群聊事件（包括消息接收和加群）都支持，极少事件需要 Webhook 模式