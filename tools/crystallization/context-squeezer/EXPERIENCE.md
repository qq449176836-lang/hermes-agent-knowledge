### 2026-06-12: Context Squeezer — Headroom 设计模式迁移

- **情境**：用户要求研究 Headroom（chopratejas/headroom，24K Stars），一个 AI 输入压缩工具。经分析不适合直接集成（Hermes Gateway 闭源），但设计理念可迁移。
- **行动**：提取 Headroom 五大设计模式（SmartCrusher/CCR/ContentRouter/TOIN/headroom learn），创建 context-squeezer Skill + squeezer.py 引擎。6 轮 26 项测试全部通过。
- **结果**：
  - SKILL.md (293 行) + squeezer.py (567 行)
  - 5 种压缩策略：browser/source/terminal/code/json
  - auto 检测准确率 100%
  - CCR 可逆缓存 + BM25 检索
  - TLR 触发：>50 行或 >2000 字符
- **教训**：
  - 闭源工具无法集成时，不应止步于"不能用"，应提取可迁移的设计模式
  - SmartCrusher 的统计采样思想（常量提取+异常保留+方差采样）是通用的，不依赖 ML 模型
  - CCR（可逆压缩）解决了"压缩太狠丢信息 vs 不压缩烧 Token"的二元困境
  - 知识体系（8 文档）形同虚设，核心方法论未落地执行
- **经验标签**：#压缩 #Headroom #SmartCrusher #CCR #Skill创建 #知识迁移 #方法论复盘
