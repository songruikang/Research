# DataAgent 二次开发技术指引

## 一、现状分析

### 1.1 当前架构（WrenAI）

```
用户问题
  → Intent Classification (LLM)      ← 已关闭，省 1 次调用
  → Schema Retrieval (embedding)       ← Ollama nomic-embed-text
  → Column Pruning (LLM)              ← 1 次 DeepSeek/Claude 调用
  → SQL Generation Reasoning (LLM)    ← 已关闭，省 1 次调用
  → SQL Generation (LLM)              ← 1 次 DeepSeek/Claude 调用
  → Dry Run (wren-engine)
  → SQL Correction (LLM, 0~1 次)      ← 仅失败时触发
  → Execute (DuckDB)
```

### 1.2 Token 消耗实测

基于电信 NMS 14 表 356 列的实际 trace 数据：

| 步骤 | 模型 | Prompt Tokens | Completion Tokens | 用途 |
|------|------|-------------|-----------------|------|
| Schema Embedding | nomic-embed-text | 20,416 | 0 | 向量化 schema 用于检索 |
| Column Pruning | deepseek-chat | 9,335 | 655 | 判断需要哪些列 |
| SQL Generation | deepseek-chat | 2,067 | 325 | 生成 SQL |
| SQL Generation (retry) | deepseek-chat | 597 | 67 | SQL 纠错 |
| **单次查询合计** | | **~12,000** | **~1,050** | |

### 1.3 Schema 不同表示格式的 Token 成本

| 格式 | Token 数 | 说明 |
|------|---------|------|
| **A. Full DDL + 中文描述** | 7,305 | WrenAI 当前方式，14 表全量 |
| B. 仅表名和列名 | 1,344 | 无类型无描述 |
| **C. Markdown + 描述** | 7,181 | 与 DDL 差不多，可读性更好 |
| **D. 3 张相关表 Full DDL** | 1,620 | 检索后只传相关表 |
| E. 1 张表裁剪后 5 列 | 71 | Column Pruning 后的结果 |
| F. 领域术语表 | 86 | 枚举值 + 业务映射 |
| G. 5 个 Few-shot 示例 | 117 | Question-SQL 对 |

**关键发现**：

Demo 的 14 张表只有 7,305 tokens，但生产环境是 **100+ 张表、每表约 35 列、总计约 3,500 列**，预估全量 schema 约 **52,000 tokens**。

> **全量 schema 塞进 prompt 不可行。Schema 检索和 Column Pruning 在生产规模下是必须的，但 WrenAI 的实现效率太低——需要重新设计更高效的检索和裁剪策略。**

当前 14 表 demo 可以全量传入做开发验证，但架构必须面向 100 表设计。

### 1.4 当前 15 个测试用例难度分级

| 难度 | 数量 | 典型问题 | 核心挑战 |
|------|------|---------|---------|
| 简单（单表过滤） | 3 | Q01 华为PE设备, Q03 SRv6状态 | 字段映射 |
| 中等（JOIN + 过滤） | 4 | Q04 北京网元+站点, Q06 VPN+PE | 关系理解 |
| 较难（聚合 + 分组） | 4 | Q02 大区统计, Q05 端口数量, Q09 带宽分布 | 聚合逻辑 |
| 困难（多表+时间+计算） | 3 | Q07 24h CPU, Q10 趋势环比, Q14 周对比 | 时间窗口 + 计算 |
| 极难（复杂业务逻辑） | 1 | Q12 单点故障链路, Q15 健康评分 | 多表交叉 + 业务规则 |

---

## 二、目标架构

### 2.1 设计原则

1. **一次调用优先**：能一次 LLM 调用解决的，不拆成多次
2. **Schema 全量传入**：14 表 7K tokens 直接放进 prompt，不做检索
3. **领域知识前置**：把电信术语映射、枚举值、常见查询模式直接写进 system prompt
4. **执行验证驱动**：不依赖 dry run，直接执行 SQL，根据结果判断是否正确
5. **渐进增强**：从简单 pipeline 开始，按需加复杂度

### 2.2 目标架构

```
用户问题
  │
  ├─ [本地] Few-shot 精确匹配            ← 历史 QA 对，关键词/语义匹配
  │    命中 → 直接返回 SQL（零 LLM 调用）
  │    未命中 ↓
  │
  ├─ [本地/LLM] 智能 Schema 检索         ← 从 100 表中筛选 5~10 张相关表
  │    阶段1: 关键词 + 表描述匹配（本地，零成本）
  │    阶段2: 必要时 LLM 辅助判断（复杂跨表场景）
  │
  ├─ [LLM] Column Pruning（可选）        ← 检索到的表如果列数 > 阈值，裁剪
  │    5~10 张表 × 35 列 ≈ 175~350 列
  │    裁剪到 30~50 个相关列
  │
  ├─ [LLM] SQL 生成                     ← 精简 schema + 领域知识 + few-shot
  │
  ├─ [本地] SQL 执行                     ← DuckDB 直接执行
  │    成功 → 返回结果
  │    失败 ↓
  │
  ├─ [LLM] SQL 修正（Agent 循环，最多 2 次）
  │
  └─ 返回结果
```

**对比**：

| 指标 | WrenAI 当前 | 目标架构 | 说明 |
|------|------------|---------|------|
| LLM 调用次数 | 2~4 次 | 1~3 次 | 简单查询 1 次，复杂查询 2-3 次 |
| Schema 检索 | embedding 全走 Qdrant | 本地关键词优先 + embedding 兜底 | 减少 embedding 依赖 |
| Column Pruning | 每次必做 | 仅检索结果超阈值时做 | 避免不必要的 LLM 调用 |
| Prompt tokens/次 | 9,000~12,000 | 3,000~8,000 | 精准检索后 schema 更小 |
| 总 tokens/查询 | 12,000~30,000 | 5,000~15,000 | |
| 延迟 | 8~15 秒 | 3~8 秒 | |
| 依赖组件 | 6 个容器 | LLM API + DuckDB + 可选 embedding | |

### 2.3 保留什么、丢弃什么

| WrenAI 组件 | 决策 | 理由 |
|------------|------|------|
| MDL (telecom_mdl.json) | **保留并增强** | 语义层是核心资产 |
| wren-engine + DuckDB | **保留** | SQL 执行能力 |
| Qdrant 向量库 | **保留，但降低依赖** | 100 表需要向量检索，但优先走本地关键词匹配 |
| wren-ai-service | **丢弃，自己实现** | Pipeline 过重，自己实现更轻更可控 |
| Embedding 模型 | **保留，但换方案** | 考虑用 API embedding（如 Voyage/OpenAI）替代本地 Ollama，质量更高 |
| wren-ui (Next.js) | **保留二次开发的页面** | SQL Query + Trace 页面 |
| Column Pruning | **保留，但条件触发** | 检索到的表列数超阈值（如 >150 列）时才做，避免不必要的 LLM 调用 |
| Intent Classification | **丢弃** | 投入产出比太低，直接当 TEXT_TO_SQL 处理 |

---

## 三、核心模块设计

### 3.1 领域知识层（Domain Knowledge）

**这是 DataAgent 区别于通用 NL2SQL 的核心竞争力。**

目前 `telecom_mdl.json` 存了表结构和中文描述，但缺少以下关键领域知识：

#### 3.1.1 术语映射表（Term Mapping）

用户的自然语言和数据库字段之间的映射：

```yaml
# domain_glossary.yaml
terms:
  - natural: ["华为", "华为设备", "华为厂商"]
    sql: "vendor = 'HUAWEI'"

  - natural: ["PE设备", "PE路由器", "PE"]
    sql: "role = 'PE'"

  - natural: ["运行正常", "运行状态正常", "正常运行"]
    sql: "oper_status = 'UP'"

  - natural: ["GOLD级别", "金牌", "金牌VPN"]
    sql: "service_level = 'GOLD'"

  - natural: ["过去24小时", "最近一天"]
    sql: "collect_time >= NOW() - INTERVAL 24 HOUR"

  - natural: ["北京", "北京市", "北京地区"]
    sql: "city = '北京'"  # 或 province = '北京'

  - natural: ["SLA违规", "SLA不达标"]
    sql: "sla_overall_met = false"
```

**价值**：LLM 不需要猜 `'HUAWEI'` 还是 `'Huawei'` 还是 `'huawei'`，术语表直接告诉它。这解决了 NL2SQL 中最常见的错误——**枚举值不匹配**。

#### 3.1.2 查询模式库（Query Patterns）

电信领域的典型查询模式：

```yaml
# query_patterns.yaml
patterns:
  - name: "设备过滤查询"
    description: "按厂商/角色/状态过滤网元"
    template: |
      SELECT ne_id, ne_name, vendor, role, oper_status
      FROM t_network_element
      WHERE {conditions}
    example_questions:
      - "查询所有华为PE设备"
      - "哪些设备处于DOWN状态"

  - name: "KPI 时间窗口查询"
    description: "查询指定时间范围内的性能指标"
    template: |
      SELECT ne_id, collect_time, {kpi_columns}
      FROM {kpi_table}
      WHERE collect_time >= {start_time}
        AND collect_time < {end_time}
        {additional_filters}
    notes: "时间字段是 collect_time，粒度字段是 granularity_min"
    example_questions:
      - "过去24小时CPU利用率超过80%的网元"
      - "最近7天隧道丢包率趋势"

  - name: "VPN SLA 分析"
    description: "VPN 业务的 SLA 达标分析"
    template: |
      SELECT v.vpn_name, v.service_level, v.customer_name,
             AVG(k.e2e_latency_avg_ms), AVG(k.e2e_jitter_avg_ms),
             SUM(CASE WHEN k.sla_overall_met THEN 1 ELSE 0 END) as met_count,
             COUNT(*) as total
      FROM t_vpn_sla_kpi k
      JOIN t_l3vpn_service v ON k.vpn_id = v.vpn_id
      WHERE {time_condition}
      GROUP BY v.vpn_name, v.service_level, v.customer_name
    example_questions:
      - "GOLD级别VPN的SLA达标率"
      - "哪些客户SLA违规最多"

  - name: "拓扑关联查询"
    description: "跨表的拓扑关系查询（网元-站点-接口-链路）"
    notes: |
      关键关系链:
      t_site → t_network_element (site_id)
      t_network_element → t_interface (ne_id)
      t_network_element → t_board (ne_id)
      t_interface → t_physical_link (a_if_id / z_if_id)
      t_l3vpn_service → t_vpn_pe_binding (vpn_id) → t_network_element (ne_id)
```

#### 3.1.3 常见错误规避（Error Prevention）

从实际运行中积累的 LLM 易犯错误：

```yaml
# error_prevention.yaml
rules:
  - rule: "DuckDB 不支持 INTERVAL '24 HOURS'，应使用 INTERVAL 24 HOUR（无引号无复数）"
  - rule: "布尔字段（如 sla_overall_met）不要用 = 'true'，直接用 WHERE sla_overall_met"
  - rule: "时间比较用 collect_time >= CURRENT_TIMESTAMP - INTERVAL 24 HOUR"
  - rule: "百分比字段（如 cpu_usage_avg_pct）存的是 0-100 的数值，不是 0-1"
  - rule: "vendor 值全大写：HUAWEI, ZTE, CISCO, JUNIPER, NOKIA"
  - rule: "is_intra_site 是布尔值，表示是否为站内链路"
  - rule: "associated_vpn_ids 是 VARCHAR 类型的 JSON 数组字符串，不能直接 JOIN"
```

### 3.2 Prompt 工程

#### 3.2.1 System Prompt 结构

```
┌─────────────────────────────────────────┐
│ 角色定义 (50 tokens)                      │
│ "你是电信网管系统的SQL专家..."              │
├─────────────────────────────────────────┤
│ Schema 概览 (500~800 tokens)              │
│ 100 张表的名称 + 一句话描述（用于兜底理解） │
├─────────────────────────────────────────┤
│ 检索到的相关表 DDL (2,000~5,000 tokens)   │
│ 5~10 张表的完整 DDL + 中文描述 + 外键       │
│ （Column Pruning 后可能只剩 1,000~2,000）  │
├─────────────────────────────────────────┤
│ 领域术语表 (200~300 tokens)              │
│ 枚举值映射 + 时间表达式规则               │
├─────────────────────────────────────────┤
│ 常见错误规避 (100~200 tokens)             │
│ DuckDB 语法注意事项                      │
├─────────────────────────────────────────┤
│ 输出格式要求 (50 tokens)                  │
│ 返回 JSON: {"sql": "...", "explanation": "..."} │
├─────────────────────────────────────────┤
│ Few-shot 示例 (200~500 tokens)           │
│ 3~5 个与当前问题最相关的 QA 对             │
├─────────────────────────────────────────┤
│ 用户问题 (20~50 tokens)                  │
└─────────────────────────────────────────┘
Total: ~3,500~7,500 tokens (取决于检索到的表数量和是否裁剪)
```

**Schema 概览的作用**：即使只传了 5 张相关表的详细 DDL，LLM 仍然能看到全部 100 张表的名称和描述。当 LLM 发现检索到的表不够用时，它可以在回复中说明"可能还需要 xxx 表"，触发二次检索。这比完全看不到其他表要好得多。

100 张表的概览格式（每表一行）：
```
t_site: 站点/机房表
t_network_element: 网元/设备表
t_board: 单板表
...（共 100 行）
```
预估约 800 tokens，成本可控。

#### 3.2.2 Few-shot 示例选择策略

不需要向量检索，用简单的关键词匹配：

```python
def select_few_shots(question: str, all_examples: list, top_k: int = 5) -> list:
    """根据问题关键词匹配最相关的 few-shot 示例"""
    # 关键词提取
    keywords = extract_keywords(question)  # jieba 分词 + 停用词过滤

    scored = []
    for ex in all_examples:
        # 关键词重叠度
        ex_keywords = extract_keywords(ex["question"])
        overlap = len(keywords & ex_keywords) / max(len(keywords), 1)

        # 涉及的表重叠度（从 SQL 中提取表名）
        q_tables = guess_tables(question)  # 简单的表名匹配
        ex_tables = extract_tables_from_sql(ex["sql"])
        table_overlap = len(q_tables & ex_tables) / max(len(q_tables), 1)

        scored.append((overlap * 0.6 + table_overlap * 0.4, ex))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [ex for _, ex in scored[:top_k]]
```

**不用 embedding 的原因**：
1. 15 个测试用例太少，embedding 检索优势不明显
2. 关键词匹配对中文技术术语反而更准（"华为PE" 关键词匹配比语义相似度更直接）
3. 省掉 Ollama + Qdrant 两个组件

### 3.3 SQL Agent 执行引擎

```python
class SQLAgent:
    def __init__(self, llm, db, prompt_builder, max_retries=2):
        self.llm = llm
        self.db = db  # DuckDB connection
        self.prompt_builder = prompt_builder
        self.max_retries = max_retries

    async def ask(self, question: str) -> dict:
        # Step 1: 构建 prompt
        few_shots = select_few_shots(question, self.examples)
        prompt = self.prompt_builder.build(question, few_shots)

        # Step 2: LLM 生成 SQL
        result = await self.llm.generate(prompt)
        sql = extract_sql(result)

        # Step 3: 执行 + Agent 循环
        for attempt in range(self.max_retries + 1):
            try:
                rows = self.db.execute(sql).fetchall()
                columns = [desc[0] for desc in self.db.description]

                # 基础结果验证
                if len(rows) == 0:
                    # 空结果不一定是错，但可以让 LLM 确认
                    pass

                return {
                    "sql": sql,
                    "columns": columns,
                    "data": rows,
                    "attempts": attempt + 1,
                    "trace": self.trace  # 完整调用记录
                }

            except Exception as e:
                if attempt >= self.max_retries:
                    return {"sql": sql, "error": str(e), "attempts": attempt + 1}

                # 构建纠错 prompt
                correction_prompt = self.prompt_builder.build_correction(
                    question=question,
                    failed_sql=sql,
                    error=str(e),
                )
                result = await self.llm.generate(correction_prompt)
                sql = extract_sql(result)
```

### 3.4 Trace 系统（复用当前成果）

当前已实现的 Trace 系统直接复用：
- litellm callback 捕获每次 LLM 调用
- 前端 Trace tab 展示调用详情
- Logs 页面按问题/Pipeline 分类查看

新架构下 trace 更简单（步骤少），但信息更丰富：
- 完整的 prompt 原文
- Few-shot 示例选择理由
- SQL 执行结果或错误
- Agent 循环次数

---

## 四、实施路线

### Phase 1: 轻量化 Pipeline（1~2 天）

**目标**：用最简单的方式替代 WrenAI 的 AI service，token 消耗降 50%+。

```
新建 dataagent/
├── agent.py          # SQL Agent 核心逻辑
├── prompt.py         # Prompt 构建器
├── domain.py         # 领域知识加载
├── server.py         # FastAPI 服务（替代 wren-ai-service）
└── config.yaml       # 配置
```

具体步骤：
1. 编写 `prompt.py`：从 `telecom_mdl.json` 生成全量 schema prompt
2. 编写 `agent.py`：单次 LLM 调用 + 执行验证 + 纠错循环
3. 编写 `server.py`：实现 `/v1/asks` 接口，兼容 WrenAI UI 调用
4. 用 15 个测试用例验证准确率

**验收标准**：
- 15 个测试用例准确率 >= WrenAI 当前水平
- 单次查询 token 消耗 < 10,000
- 单次查询延迟 < 5 秒

### Phase 2: 领域知识增强（2~3 天）

**目标**：通过领域知识将准确率提升到 90%+。

1. 编写术语映射表 `domain_glossary.yaml`
2. 编写查询模式库 `query_patterns.yaml`
3. 编写错误规避规则 `error_prevention.yaml`
4. 将领域知识注入 system prompt
5. 扩展测试用例到 50 个，覆盖更多场景
6. 建立自动化评测框架

**验收标准**：
- 50 个测试用例准确率 >= 85%
- 简单查询（Q01-Q06）准确率 100%
- 中等查询（Q07-Q11）准确率 >= 90%

### Phase 3: Few-shot + 反馈闭环（2~3 天）

**目标**：建立可持续改进的机制。

1. 实现 Few-shot 示例自动选择
2. 将每次成功的 Question-SQL 对自动存入示例库
3. 将失败案例存入待改进队列
4. 实现 "用户纠正 SQL → 自动学习" 的反馈闭环

```
用户提问 → Agent 生成 SQL → 用户确认/修正
                                ↓
                     自动存入 Few-shot 示例库
                                ↓
                     下次相似问题 → 匹配历史示例 → 更准确
```

### Phase 4: 多模型策略（可选）

**目标**：成本和准确率的最优平衡。

```
简单查询（单表过滤）  → 小模型（DeepSeek V3 / Claude Haiku）  ← 便宜快速
中等查询（JOIN + 聚合）→ 中模型（Claude Sonnet）               ← 平衡
复杂查询（多表 + 计算）→ 大模型（Claude Opus）                ← 保证准确率
```

路由策略：
- 关键词规则（包含 JOIN/GROUP BY/子查询相关词 → 中/大模型）
- 或者先用小模型生成 → 执行失败 → 升级到大模型
- 历史 QA 命中 → 直接返回（零成本）

---

## 五、关键技术决策

### 5.1 Schema 检索策略（100 表规模）

**结论：必须做检索，但采用两级策略降低成本。**

**第一级：本地关键词 + 表描述匹配（零 LLM 成本）**

```python
def local_table_retrieval(question: str, all_tables: list) -> list:
    """基于关键词和表描述的本地检索"""
    scores = {}
    question_keywords = jieba_extract(question)

    for table in all_tables:
        score = 0
        # 1. 表名/列名直接出现在问题中
        for col in table["columns"]:
            if col["name"] in question or col["properties"]["displayName"] in question:
                score += 3
        # 2. 表描述关键词匹配
        desc_keywords = jieba_extract(table["description"])
        score += len(question_keywords & desc_keywords) * 2
        # 3. 术语映射命中（"华为" → vendor 列 → t_network_element 表）
        score += glossary_match(question, table)
        # 4. 外键关联（如果 A 表被选中，与 A 有外键关系的表加分）
        # ... 在第二轮处理

        scores[table["name"]] = score

    # 返回 top-K
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]
```

大部分简单查询在这一级就能准确找到相关表，完全不需要 LLM。

**第二级：Embedding 语义检索（兜底）**

当第一级的最高分低于阈值时，说明关键词匹配不够，启用 embedding：

```
问题: "哪些区域的网络基础设施老化严重？"
  → 关键词匹配: "区域" → region 列，但"老化"匹配不到任何列名
  → Embedding 检索: 语义理解"老化" ≈ commissioning_date 较早 + maintenance_expire 临近
  → 找到 t_network_element + t_site
```

| 检索方式 | 命中场景 | 成本 | 预估覆盖率 |
|---------|---------|------|-----------|
| 关键词 + 表描述 | 直接提及表名/列名/枚举值 | 0 | ~70% |
| 术语映射 | 业务术语（"PE设备"→role='PE'） | 0 | +15% |
| Embedding 兜底 | 语义理解（"老化"→时间字段） | embedding API | +15% |

### 5.2 Column Pruning 策略

**结论：条件触发，不是每次都做。**

```
检索到的表总列数:
  < 80 列  → 不裁剪，直接传全量 DDL（~2,500 tokens）
  80~200 列 → LLM 裁剪（1 次调用，~5K tokens）
  > 200 列 → 分批裁剪或更激进的本地预过滤
```

**本地预过滤（零 LLM 成本）**：

在 LLM 裁剪之前，先本地去掉明显不相关的列：
- `created_at`, `updated_at` 等审计字段 → 除非问题涉及"创建时间"
- `description`, `serial_number` 等文本字段 → 除非问题涉及搜索
- 与问题关键词零重叠的列

这可以把 200 列降到 80~100 列，很多时候就不需要 LLM 裁剪了。

### 5.3 DuckDB 直接连接 vs wren-engine？

**结论：保留 wren-engine 做验证，但 SQL 执行走直连 DuckDB。**

wren-engine 的价值：
- 语义层翻译（模型名 → 真实表名，处理 calculated fields）
- SQL 方言转换

但我们当前没有 calculated fields，表名就是真实表名，所以可以直连 DuckDB：

```python
import duckdb

conn = duckdb.connect('telecom_nms.duckdb')
result = conn.execute("SELECT * FROM t_network_element WHERE vendor = 'HUAWEI'")
```

直连优势：
- 去掉 wren-engine 容器依赖
- 延迟降低（少一次 HTTP 调用）
- 错误信息更直接

### 5.4 用哪个 LLM？

| 模型 | SQL 生成能力 | 成本 | 推荐场景 |
|------|------------|------|---------|
| Claude Opus | 最强 | 最贵 | 复杂查询、开发调试 |
| Claude Sonnet | 强 | 中等 | 日常使用推荐 |
| Claude Haiku | 够用 | 便宜 | 简单查询 |
| DeepSeek V3 | 强 | 便宜 | 国内部署、成本敏感 |
| SQLCoder-70B | SQL 专精 | 本地免费 | 离线场景 |

**推荐**：开发阶段用 Claude Opus（准确率优先），生产阶段用 Claude Sonnet + 历史缓存。

---

## 六、评测框架

### 6.1 评测维度

```
Level 1: SQL 可执行
  → SQL 语法正确，DuckDB 能执行不报错

Level 2: 结果正确
  → SQL 返回的数据与预期一致（行数 + 关键值）

Level 3: 语义正确
  → SQL 确实回答了用户的问题（不是凑巧返回了正确结果）

Level 4: 最优 SQL
  → SQL 是最简洁高效的写法（没有多余的 JOIN 或子查询）
```

### 6.2 自动化评测脚本

```python
# eval.py
import json
import duckdb

def evaluate(test_cases: list, agent) -> dict:
    results = {"total": 0, "executable": 0, "correct": 0, "failures": []}

    for case in test_cases:
        results["total"] += 1
        question = case["question"]
        expected_sql = case["sql"]

        # Agent 生成 SQL
        response = agent.ask(question)
        generated_sql = response.get("sql")

        if not generated_sql:
            results["failures"].append({"question": question, "error": "no SQL generated"})
            continue

        # Level 1: 可执行？
        try:
            gen_result = conn.execute(generated_sql).fetchall()
            results["executable"] += 1
        except Exception as e:
            results["failures"].append({"question": question, "error": str(e)})
            continue

        # Level 2: 结果匹配？
        exp_result = conn.execute(expected_sql).fetchall()
        if set(map(tuple, gen_result)) == set(map(tuple, exp_result)):
            results["correct"] += 1
        else:
            results["failures"].append({
                "question": question,
                "expected_rows": len(exp_result),
                "actual_rows": len(gen_result),
                "generated_sql": generated_sql,
            })

    return results
```

### 6.3 持续改进循环

```
评测失败的用例
  → 分析失败原因（枚举值错误？JOIN 错误？时间表达式？）
  → 针对性修复：
     枚举值错误 → 补充 domain_glossary.yaml
     JOIN 错误  → 补充 query_patterns.yaml
     语法错误   → 补充 error_prevention.yaml
     复杂逻辑   → 添加 few-shot 示例
  → 重新评测 → 准确率提升
  → 循环
```

---

## 七、长期演进

### 7.1 Schema 规模增长路径

```
Phase 1 (当前): 14 表 356 列 — Demo 验证
  → 开发阶段可全量 in prompt 做快速验证
  → 但架构按 100 表设计，检索/裁剪模块从一开始就实现

Phase 2 (近期): 扩展到 50~100 表 — 覆盖电信网管核心领域
  → 新增: 告警表、工单表、配置变更表、路由表、流量矩阵表等
  → Schema 检索 + 条件裁剪 全面启用
  → Few-shot 示例库扩展到 200+ 对
  → 自动化评测覆盖 100+ 测试用例

Phase 3 (中期): 100+ 表稳定运行
  → 按查询域分组（存量域/性能域/业务域/告警域）
  → 考虑针对高频查询模式微调小模型
  → 引入多轮对话和追问能力
```

### 7.2 从 NL2SQL 到 DataAgent

NL2SQL 只是第一步。完整的 DataAgent 还应包括：

```
DataAgent
├── NL2SQL           ← 当前重点
├── 结果解读          ← LLM 将查询结果转化为自然语言摘要
├── 异常检测          ← 自动发现 KPI 异常并生成告警
├── 报告生成          ← 定期生成网络健康报告
├── 交互式分析        ← 多轮对话，追问细化
└── 知识图谱          ← 从查询历史中构建网络拓扑知识
```

---

## 附录

### A. 文件清单

| 文件 | 用途 | 状态 |
|------|------|------|
| `telecom_mdl.json` | 语义层定义（14 模型 356 字段 29 关系） | 已完成 |
| `telecom_test_cases.json` | 15 个 QA 测试用例 | 已完成，需扩展 |
| `update_wren_metadata.py` | WrenAI SQLite 导入脚本 | 已完成 |
| `telecom/generate_mock_data.py` | Mock 数据生成器 | 已完成 |
| `WrenAI_NL2SQL_Flow.md` | WrenAI 流程分析文档 | 已完成 |
| `DataAgent_Technical_Guide.md` | 本文档 | 当前 |
| `dataagent/` | DataAgent 核心代码 | **待开发** |
| `domain_glossary.yaml` | 领域术语映射 | **待开发** |
| `query_patterns.yaml` | 查询模式库 | **待开发** |
| `error_prevention.yaml` | 错误规避规则 | **待开发** |

### B. Token 成本速查

**Demo 阶段（14 表）：**

| 场景 | Input Tokens | Output Tokens | 说明 |
|------|-------------|---------------|------|
| DataAgent 简单查询（检索命中） | ~3,500 | ~200 | 本地检索 + 1 次 LLM |
| DataAgent 复杂查询（需裁剪） | ~8,000 | ~500 | 检索 + 裁剪 + 生成 |
| DataAgent + 1 次纠错 | ~12,000 | ~800 | 多 1 次 LLM |
| WrenAI 当前实测 | ~12,000 | ~1,050 | Pruning + Generation |

**生产阶段（100 表）估算：**

| 场景 | Input Tokens | Output Tokens | 说明 |
|------|-------------|---------------|------|
| 简单查询（单表过滤） | ~3,000 | ~200 | 本地检索直接命中 1~2 表 |
| 中等查询（2~3 表 JOIN） | ~6,000 | ~400 | 检索 3~5 表，可能需裁剪 |
| 复杂查询（5+ 表 + 聚合） | ~12,000 | ~600 | 检索 5~10 表 + 裁剪 + 生成 |
| 极复杂 + 纠错 | ~20,000 | ~1,000 | 多轮 Agent |
| Few-shot 精确命中 | 0 | 0 | 历史 QA 直接返回 |

### C. 推荐阅读

- [Defog SQLCoder](https://github.com/defog-ai/sqlcoder) — SQL 微调模型，了解 fine-tuning 路线
- [Vanna.ai](https://github.com/vanna-ai/vanna) — RAG + training 的 NL2SQL 框架
- [MAC-SQL](https://github.com/wbbeyourself/MAC-SQL) — Multi-Agent SQL, BIRD 基准 SOTA
- [BIRD Benchmark](https://bird-bench.github.io/) — NL2SQL 评测基准
- [DuckDB SQL Reference](https://duckdb.org/docs/sql/introduction) — DuckDB 语法参考
