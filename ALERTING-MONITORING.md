# ALERTING & MONITORING — 告警与自愈系统

> **让报错有人处理 = 精准监控 + 分级告警 + 自动响应 + 持续复盘。**
>
> 基于棘轮机制：每次故障都变成一条护栏，同类问题永不复发。

---

## 四层闭环架构

```
┌─────────────────────────────────────────────────────────┐
│                   发现层 (Detect)                        │
│  自监控体系：进程存活 / 锁状态 / 连接 / 资源 / 延迟        │
├─────────────────────────────────────────────────────────┤
│                   通知层 (Alert)                         │
│  P0 → P1 → P2 → P3 分级，飞书交互式卡片，去重 + IP 归因    │
├─────────────────────────────────────────────────────────┤
│                   响应层 (Respond)                       │
│  自动修复 SOP：诊断 → 修复 → 验证 → 升级                   │
├─────────────────────────────────────────────────────────┤
│                   复盘层 (Review)                        │
│  48h 故障复盘 → 根因 → 行动项 → 经验蒸馏 → 新护栏          │
└─────────────────────────────────────────────────────────┘
```

---

## 一、发现层：自监控体系

Hermes 监控自己，无需外部工具：

| 监控项 | 检测方式 | 频率 | 失败级别 |
|--------|---------|------|---------|
| **Gateway 心跳** | `pgrep gateway` 或读取 `gateway.pid` | 60s | 🔴 P0 |
| **飞书连接状态** | 读取 `gateway_state.json` 的 connected 字段 | 120s | 🔴 P0 |
| **锁文件僵尸** | 比对 PID 是否存活，死进程残留锁 | 300s | 🟡 P1 |
| **磁盘使用率** | `df` 检查 >85% | 600s | 🟠 P2 |
| **响应延迟** | 端到端消息往返时间 | 300s | 🟡 P1 |

### 实现：30 分钟快速探针

```bash
#!/bin/bash
set -euo pipefail

# 检查 Gateway 进程
if ! tasklist | grep -q "$gw_pid"; then
    issues+="- 🔴 Gateway 进程已死\n"
fi

# 检查锁文件残留
lock_count=$(find "$HERMES_HOME" -name "*.lock" | wc -l)
if [ "$lock_count" -gt 2 ]; then
    issues+="- 🟡 残留锁文件: ${lock_count}个\n"
fi

# 检查磁盘
disk_pct=$(df "$HOME" | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$disk_pct" -gt 85 ]; then
    issues+="- 🟠 磁盘使用率: ${disk_pct}%\n"
fi
```

---

## 二、通知层：分级告警

### 告警等级

| 等级 | 含义 | 触发条件 | 响应 |
|------|------|---------|------|
| 🔴 **P0** | 致命 — 完全不工作 | Gateway 死 / 飞书断连 >2min | 自动修复 + 飞书推送 |
| 🟡 **P1** | 严重 — 部分功能异常 | 锁残留 / 延迟 >30s / 连续失败 | 自动清理 + 飞书通知 |
| 🟠 **P2** | 一般 — 不影响主流程 | 磁盘 >85% / 单次失败 | 记录日志 + 每日汇总 |
| 🔵 **P3** | 信息 — 仅供复盘 | 工具超时(已重试) / 新错误模式 | 仅记录，不通知 |

### 飞书卡片格式

```json
{
  "msg_type": "interactive",
  "card": {
    "header": {
      "title": { "tag": "plain_text", "content": "🚨 Hermes 健康告警" },
      "template": "red"
    },
    "elements": [
      {
        "tag": "markdown",
        "content": "- 🔴 Gateway 进程已死\n- 🟡 残留锁文件: 3个\n- 🟠 磁盘使用率: 89%"
      },
      {
        "tag": "note",
        "elements": [
          { "tag": "plain_text", "content": "Monitor · 2026-06-12 14:30:00 · 🌐 47.121.129.203（中国 浙江 杭州）" }
        ]
      }
    ]
  }
}
```

颜色规则：`red`(告警) `yellow`(警告) `green`(恢复) `blue`(信息)

### 去重机制

```
仅在状态变化时发送告警：

/tmp/hermes-monitor-state.txt 存储上次状态（"OK" 或 "ALERT"）
  → 当前状态 = 上次状态 → 不发送
  → 当前状态 != 上次状态 → 发送 + 更新状态文件
```

避免"闪断→恢复→闪断"刷屏。恢复通知使用 `green` 模板。

### 3 条铁律

1. **中文数据不经过 printf/sed 拼接** → JSON 写入临时文件后 `curl -d @file`
2. **Webhook URL 不硬编码** → 从 `~/.hermes/feishu-webhook.url` 读取
3. **Token 绝不出现在命令行** → curl 传参全部通过文件

---

## 三、响应层：自动修复 SOP

### SOP-001：Gateway 崩溃

```
诊断：
  cat gateway_state.json
  tail -50 logs/gateway.log
  tail -20 logs/errors.log

修复：
  Step 1: 清理僵尸锁（hermes-cleanup.sh --force）
  Step 2: 重启 Gateway
  Step 3: 等 5 秒后健康检查

回退：
  Step 3 失败 → 回退到上一版本 runtime

升级：
  3 次自动修复失败 → 通知用户手动排查
```

### SOP-002：飞书断连

```
修复：
  Step 1: 清理飞书 token 缓存锁
  Step 2: 重启 Gateway
  Step 3: 发送测试消息验证

升级：
  2 次自动修复失败 → 建议重新授权飞书 app
```

### SOP-003：磁盘满

```
诊断：
  du -sh logs/ sessions/ | sort -rh | head -10

修复：
  Step 1: 自动清理 7 天前的日志
  Step 2: 压缩旧 session 记录

升级：
  清理后仍 >85% → 通知用户扩容
```

### SOP-004：响应变慢

```
修复：
  Step 1: 切换到 fallback API provider
  Step 2: 如有大量压缩 → 建议 /new 开新会话
```

---

## 四、复盘层：故障后 48 小时闭环

### 复盘模板

```yaml
postmortem:
  meta:
    incident_id: "INC-2026-0611-001"
    date: "2026-06-11"
    severity: "P1"
    duration: "15 minutes"

  timeline:
    - "14:51: Gateway 崩溃"
    - "14:52: 系统检测异常，自动修复"
    - "14:53: hermes-cleanup.sh 执行成功"
    - "14:54: Gateway 重启完成，服务恢复"

  root_cause: "Gateway 被 OOM killer 杀掉，未清理锁文件"

  what_worked:
    - "自动检测在 60 秒内发现异常 ✅"
    - "hermes-cleanup.sh 正确清理了所有锁 ✅"

  what_didnt:
    - "没有 OOM 预警，无法提前预防 ❌"

  action_items:
    - action: "添加内存监控，>80% 告警"
      type: "guardrail"
    - action: "研究 Gateway 内存泄漏根因"
      type: "fix"
    - action: "编写 OOM 场景的 SOP-005"
      type: "documentation"
```

### 复盘三原则

1. **不追责人**：聚焦系统缺陷，不指责操作者
2. **必须产出行动项**：每次复盘至少一条 concrete action item
3. **经验不可丢失**：行动项 → guardrail 原则 → 棘轮知识库

---

## 五、健康指标体系

| 指标 | 健康阈值 | 检查频率 |
|------|---------|---------|
| Gateway 进程存活 | 100% | 60s |
| 飞书连接状态 | connected | 120s |
| 锁文件数量 | ≤2 | 300s |
| 磁盘使用率 | <85% | 600s |
| 内存使用率 | <80% | 300s |
| 端到端延迟 | <30s | 300s |
| API 调用成功率 | >99% | 每日 |
| Cron 任务执行率 | 100% | 每日 |

---

## 六、状态流转

```
           ┌──────────┐
           │   正常    │
           └─────┬────┘
                 │ 检测到异常
                 ▼
           ┌──────────┐
           │   告警    │──── 飞书推送（红/黄卡片）
           └─────┬────┘
                 │ 自动修复 / 手动处理
                 ▼
           ┌──────────┐
           │   恢复    │──── 飞书推送（绿色卡片）
           └─────┬────┘
                 │
                 ▼
           ┌──────────┐
           │   正常    │
           └──────────┘
                 │
                 ▼ (48h 后)
           ┌──────────┐
           │   复盘    │──── 经验 → 新护栏 → 棘轮固化
           └──────────┘
```

---

## 七、一键部署

```bash
# 部署 30 分钟探针 cron
hermes cron create "*/30 * * * *" \
  --prompt "执行 health-monitor.sh 快速探针：检查 Gateway/锁文件/磁盘，异常时飞书告警" \
  --skills "hermes-health-sop,feishu-alert" \
  --deliver feishu
```

---

## 八、棘轮演进轨迹

| 版本 | 新增护栏 | 来源 |
|------|---------|------|
| v1.0 | 锁文件必须清理 | Gateway 崩溃 ×3 |
| v1.1 | 进程存活检测 + 自动重启 | v1.0 复盘 |
| v1.2 | 飞书断连自动重连 | Token 过期 |
| v2.0 | 内存预警 + 主动重启 | OOM 复盘 |
| v2.1 | 磁盘自动清理 | 磁盘满告警 |
| ... | 每次故障 = 一条新护栏 | 棘轮永不倒转 |

---

> *"监控不只是发现问题，是确保同样的问题不再发生第二次。"*
