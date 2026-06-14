# EMBEDDED SDK PATTERN — 嵌入式 Python SDK 模式

> **来源**：DeerFlow 精华提炼 #3  
> **核心设计**：SDK 返回 Schema 与 HTTP Gateway API 完全对齐，CI 自动验证一致性  

---

## DeerFlow 设计

```python
from deerflow.client import DeerFlowClient

client = DeerFlowClient()

# 所有 dict-returning methods 在 CI 中由 TestGatewayConformance 验证
# → SDK 始终与 HTTP API Schema 同步

models = client.list_models()        # {"models": [...]}
skills = client.list_skills()        # {"skills": [...]}
client.update_skill("web-search", enabled=True)
```

## Hermes SDK 设计草案

### 安装

```bash
pip install hermes-client
```

### 接口

```python
from hermes.client import HermesClient

# 连接（默认指向本地 OpenViking）
client = HermesClient(endpoint="http://127.0.0.1:1933")

# === 记忆操作（对齐 viking_* 工具） ===
# search
results = client.memory.search("多Agent协同", mode="fast", limit=5)
# → [{"uri": "viking://...", "score": 0.85, "abstract": "..."}, ...]

# remember (含写入去重)
result = client.memory.remember(
    "用户偏好：监控面板使用纯中文",
    category="preference"
)
# → {"status": "stored", "uri": "viking://..."}
# 或 → {"status": "deduplicated", "existing_uri": "viking://..."}

# read
content = client.memory.read("viking://resources/methodology/CONSTITUTION", level="overview")
# → "# CONSTITUTION — 核心宪法..."

# === 知识库操作（对齐 viking_* 工具） ===
docs = client.knowledge.search("棘轮循环", limit=5)
client.knowledge.add_resource(
    "https://github.com/user/repo/blob/main/doc.md",
    reason="方法论文档"
)

# === 会话管理 ===
sessions = client.session.recall(
    thread_id="hermes_sync_test",
    query="上次说的端口问题"
)

# === Health ===
health = client.health()
# → {"status": "ok", "version": "0.3.24", "uptime": 12345}
```

## Schema 对齐机制

```python
# CI 测试：SDK 返回 Schema vs HTTP API Schema
class TestSDKConformance:
    """确保 hermes-client SDK 与 Hermes Gateway HTTP API 返回 Schema 一致"""
    
    def test_memory_search_matches_http(self):
        # SDK 调用
        sdk_result = client.memory.search("test")
        # HTTP 调用
        http_result = requests.post(
            "http://127.0.0.1:1933/api/memory/search",
            json={"query": "test"}
        ).json()
        
        # 验证返回结构一致
        assert sdk_result.keys() == http_result.keys()
        assert sdk_result["results"][0].keys() == http_result["results"][0].keys()
```

## 分布式 Worker 使用场景

```python
# Worker 机器上，不装 Hermes Desktop，只装 hermes-client
# pip install hermes-client

from hermes.client import HermesClient

client = HermesClient(endpoint="http://47.121.129.203:1933")  # 连主服务器

# 检索分布式协同的相关记忆
context = client.memory.search("Roundtable Worker 接口约定")

# 完成后记录经验
client.memory.remember(
    "Worker dev-01: Flask /api/health 实现中遇到端口占用问题，
    解决方案：启动前自动 netstat 检查并随机分配备用端口",
    category="event"
)
```

## 实施路线

- [ ] Python 包骨架：`hermes-client/` + `setup.py`
- [ ] 核心接口：`memory` / `knowledge` / `session` / `health`
- [ ] Schema 对齐：从 OpenViking HTTP API 自动生成 Pydantic models
- [ ] CI 验证：`TestSDKConformance` 类
- [ ] 发布 PyPI：(可选) `pip install hermes-client`

---

> *"SDK 不是另一种 API，是同一套 API 的进程内版本。"*
