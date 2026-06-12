# OPERATIONS — 操作守则与经验教训

> **来自数百次真实任务的踩坑经验，每条背后都有一段时间的排查。**

---

## GitHub 操作

### 认证方案

```
✅ 双保险：
  1. git credential store  (~/.git-credentials)
  2. GitHub API 用 ~/.netrc (machine api.github.com login TOKEN password x-oauth-basic)

❌ 禁止：
  git clone https://TOKEN@github.com/...          # 明文 Token
  curl -H "Authorization: token $TOKEN" ...       # Token 拼入命令行
```

### 推送策略

- **国内网络不稳定**：github.com 间歇超时，优先用 API 上传（`curl -n -X PUT .../contents/...`）
- **git push 卡住**：`git push -c credential.helper=` 绕过全局 credential helper
- **Token 权限**：Fine-grained PAT 需要 `Contents: Write` 才能 push

### 仓库操作规则

```
AI-General（私有）    → Hermes 独享，可主动上传
hermes（私有）        → 他人使用，禁止上传
hermes-monitor（公开）→ 仅用户明确要求时操作
```

---

## 飞书集成

### 消息发送

```
✅ 正确方式：
  cat > /tmp/msg.json << 'EOF'
  { "msg_type": "text", "content": { "text": "中文消息" } }
  EOF
  curl -X POST -H "Content-Type: application/json; charset=utf-8" \
    -d @/tmp/msg.json "$(cat ~/.hermes/feishu-webhook.url)"

❌ 错误方式：
  printf 拼接 JSON → 破坏中文字符编码
  curl -d "{\"text\":\"...\"}" → Token 出现在命令行
```

### 不对话排查（7 检查点）

| # | 检查点 | 常见坑 |
|---|--------|--------|
| 1 | 应用类型 | 必须是「企业自建应用」，不是「应用商店应用」 |
| 2 | 权限 | `im:message` + `im:message:send_as_bot`，开通后要**发版** |
| 3 | 事件订阅 URL | 填入 Hermes 启动后控制台打印的回调地址 |
| 4 | config.yaml | App ID / App Secret 不能是占位符 |
| 5 | `.env` 白名单 | `FEISHU_ALLOWED_USERS` 必须有值，否则任何人都不响应 |
| 6 | 应用发布 | 「开发中」状态只有管理员能对话 |
| 7 | access_key 延迟 | 刚重启 1-2 分钟内短暂不可用，等就好 |

### 飞书 Access 问题修复

```bash
# 清理飞书 token 缓存锁
rm -f "$HERMES_HOME/gateway-runtime/token-locks/"*.lock
# 然后重启 Hermes
```

---

## Flask 服务管理（Windows）

### 致命陷阱：多进程残留

```
症状：代码已更新但 API 返回旧数据
根因：端口 5000 上有多个旧 Python 进程同时 LISTENING

排查：
  netstat -ano | grep ':5000.*LISTENING'

修复：
  # 一次性杀干净（不能用 kill -9，要用 Windows 方式）
  powershell -Command "Stop-Process -Id <pids> -Force"

验证：
  netstat -ano | grep ':5000'  # 应该只有一个 LISTENING PID
```

### 启动最佳实践

```bash
# 1. 先清理旧进程
pids=$(netstat -ano | grep ':5000.*LISTENING' | awk '{print $NF}' | sort -u)
for pid in $pids; do powershell -Command "Stop-Process -Id $pid -Force" 2>/dev/null; done

# 2. 确认端口清空
sleep 2

# 3. 启动（用 -B 禁止 .pyc 缓存）
python -B server.py
```

---

## 子 Agent 隔离性

### 关键教训

| 问题 | 表现 | 解决 |
|------|------|------|
| 文件路径不一致 | 部门 A 写的文件，部门 B 说找不到 | 委派前统一绝对路径，主 Agent 创建目录并验证 |
| Self-report 不可信 | 子 Agent 说"上传成功"，实际失败 | 获取可验证句柄（URL/路径/状态码）后主动验证 |
| File-mutation verifier 假阳性 | 说文件没修改，实际已修改 | 以 `read_file` / `cat` 实际验证为准 |
| 上下文孤立 | 子 Agent 不知道其他部门的产出 | 主 Agent 在 context 字段中注入关键信息 |

---

## 锁文件管理

Hermes 使用多个锁文件防止并发冲突，异常退出时会残留：

```
$HERMES_HOME/auth.lock
$HERMES_HOME/gateway-runtime/gateway.lock + gateway.pid
$HERMES_HOME/kanban.db.init.lock
$HERMES_HOME/cron/.tick.lock
$HERMES_HOME/skills/.usage.json.lock
$HERMES_HOME/gateway-runtime/token-locks/*.lock
```

**症状**：Gateway 启动后立即退出、飞书连不上、Cron 不执行。

**修复**：删除以上全部 `.lock` 文件后重启。

---

## 路径与变量

### Windows 路径准则

```
✅ 使用变量：
  %APPDATA%\cn.org.hermesagent.desktop\...
  %LOCALAPPDATA%\Programs\hermes-agent-cn-desktop\...

✅ MSYS 兼容：
  /c/Users/Administrator/...  （bash 终端）
  C:\Users\Administrator\...  （Windows 原生命令）

❌ 硬编码用户名：
  C:\Users\张三\...  （换机器就失效）
```

### config.yaml 关键项

```yaml
terminal:
  backend: local           # 必设
  # TERMINAL_CWD 已废弃    # 旧配置需迁移到 config.yaml

delegation:
  max_concurrent_children: 3   # 并行子 Agent 上限
```

---

## 网络与镜像

### 国内加速

```bash
# pip 清华源
pip install <package> -i https://pypi.tuna.tsinghua.edu.cn/simple

# Python 安装包国内镜像
https://registry.npmmirror.com/-/binary/python/3.12.9/python-3.12.9-amd64.exe
```

### curl 超时保护

```bash
# 所有 curl 调用必须加超时
curl --connect-timeout 5 --max-time 30 ...
```

---

## 安装踩坑

| 症状 | 原因 | 解决 |
|------|------|------|
| `python` 跳到 Microsoft Store | 装了 Store 版 | 卸载 → python.org 重装 + 勾选 PATH |
| `pip install` SSL 错误 | 国内网络 | 加 `-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| `ls` `/c/` 命令不识别 | 没装 Git Bash | 装 Git for Windows |
| Gateway 启动后退出 | 锁文件残留 | 删 .lock 文件 |
| `git push` 卡住 | credential helper 冲突 | `git push -c credential.helper=` |
| `netstat`/`taskkill` 乱码 | 中文编码 | `chcp 437` 切换代码页 |

---

## 日常维护

### 开机自启

```powershell
# Windows 计划任务（替代手动重启）
schtasks /create /tn "HermesAutoStart" /tr "path\to\hermes.exe" /sc onlogon /rl highest
```

### 健康检查

```bash
# 检查进程
tasklist | findstr hermes

# 检查端口
netstat -ano | grep ':5000'

# 检查 Cron
hermes cron list
```

### 日志位置

```
$HERMES_HOME/logs/agent.log       # Agent 操作日志
$HERMES_HOME/logs/gateway.log     # 飞书 Gateway 日志
```

---

> *"每条规则背后，都是曾经浪费过的时间。"*
