# WrenAI NL2SQL 完整流程说明

## 示例问题

> 查询所有华为厂商的PE设备，要求运行状态正常

---

## 整体架构

```
浏览器 (localhost:3000)
  │
  │  GraphQL
  ▼
Next.j![[deep-research-report]]s (wren-ui)          ← 前端 + GraphQL 网关，不做 AI 逻辑
  │
  │  HTTP REST
  ▼
FastAPI (wren-ai-service)  ← AI 编排引擎，管理全部 pipeline
  │
  ├──→ Ollama              ← embedding 模型 (nomic-embed-text)
  ├──→ DeepSeek API        ← LLM 模型 (deepseek-chat)
  ├──→ Qdrant              ← 向量数据库（存 schema 索引）
  │
  │  HTTP REST
  ▼
wren-engine                ← SQL 引擎 + 语义层翻译
  │
  ▼
DuckDB (内存)              ← 真正执行 SQL 的地方
```

---

## 前置步骤：Deploy（部署索引）

在用户提问之前，系统已经做了一次索引。每次你在 UI 里点 Deploy 或脚本触发 `mutation { deploy }` 时：

### MDL 怎么变成 DDL

`telecom_mdl.json` 里每个 model 的定义：
```json
{
  "name": "t_network_element",
  "properties": { "description": "网元/设备表 - 路由器、交换机等网络设备信息" },
  "columns": [
    { "name": "vendor", "type": "VARCHAR",
      "properties": { "displayName": "Vendor", "description": "厂商。取值: HUAWEI;ZTE;CISCO;JUNIPER;NOKIA" }
    }
  ]
}
```

被转换成带注释的 DDL chunk（这是实际传给 LLM 的格式）：
```sql
/* 网元/设备表 - 路由器、交换机等网络设备信息 */
CREATE TABLE t_network_element (
  -- {"alias": "NE ID", "description": "网元唯一标识"}
  ne_id VARCHAR PRIMARY KEY,
  -- {"alias": "Vendor", "description": "厂商。取值: HUAWEI;ZTE;CISCO;JUNIPER;NOKIA"}
  vendor VARCHAR,
  -- {"alias": "Role", "description": "设备角色。取值: PE;P;RR;ASBR"}
  role VARCHAR,
  -- {"alias": "Oper Status", "description": "运行状态（设备实际工作状态）。取值: UP;DOWN;DEGRADED"}
  oper_status VARCHAR,
  -- ... 其他 27 列
  FOREIGN KEY (site_id) REFERENCES t_site(site_id)  -- 网元所属站点
);
```

**关键点**：LLM 看到的不是 JSON，而是 CREATE TABLE 语句。这是因为：
1. LLM 对 SQL DDL 的理解远好于自定义 JSON 格式（训练数据里大量 DDL）
2. 中文描述作为 SQL 注释嵌入，让 LLM 理解每个字段的业务含义
3. 外键关系也以 FOREIGN KEY 形式出现，LLM 能直接理解 JOIN 条件

### 索引过程

```
telecom_mdl.json (14表 356列)
  │
  ├─ DB Schema Indexing
  │    → 14 张表拆成约 60 个 chunk（每张表拆为表结构 + 多组列）
  │    → 每个 chunk 用 Ollama nomic-embed-text 生成 768 维向量
  │    → 写入 Qdrant "Document" 集合
  │
  ├─ Table Description Indexing
  │    → 14 条表描述（中文）生成向量
  │    → 写入 Qdrant "table_descriptions" 集合
  │
  ├─ SQL Pairs Indexing（当前为空）
  ├─ Instructions Indexing（当前为空）
  └─ Historical Question Indexing（当前为空）
```

索引完成后，Qdrant 里存了约 60 个 schema 向量，等待用户提问时做语义检索。

---

## 用户提问流程

### 阶段 0：请求入口

```
浏览器输入: "查询所有华为厂商的PE设备，要求运行状态正常"
  │
  │ POST /api/graphql → createThreadResponse mutation
  │
  ▼
Next.js 转发到 AI 服务:
  POST http://wren-ai-service:5555/v1/asks
  body: {
    query: "查询所有华为厂商的PE设备，要求运行状态正常",
    mdl_hash: "517cc524...",
    histories: []
  }
```

AI 服务收到后进入 `AskService.ask()` 编排方法。

---

### 阶段 1：understanding（理解意图）

#### 1.1 Historical Question Retrieval

```
输入: "查询所有华为厂商的PE设备，要求运行状态正常"
  │
  ▼ Ollama embedding
  │
  ▼ Qdrant 向量搜索 "historical_question" 集合
  │
  ▼ 结果: 无匹配（首次提问，没有历史）
```

如果之前问过相似的问题并且成功生成了 SQL，这里会直接返回缓存的 SQL，**跳过后续所有步骤**。

#### 1.2 SQL Pairs + Instructions Retrieval（并发）

```
同时发两个向量搜索:

SQL Pairs:
  → embedding → Qdrant "sql_pairs" 集合 → 无匹配
  （如果你在 Knowledge 页配置了 Question-SQL 训练对，这里会命中）

Instructions:
  → embedding → Qdrant "instructions" 集合 → 无匹配
  （如果你在 Knowledge 页配置了指令如"所有查询都用中文别名"，这里会命中）
```

**以上三步都只用 Ollama embedding，不调 DeepSeek**。

#### 1.3 Intent Classification（意图分类）

**开关**：`allow_intent_classification`（当前 = false，已关闭）

如果开启，会调一次 DeepSeek，让 LLM 判断用户问题属于哪个类别：

| 意图类型 | 含义 | 后续动作 |
|---------|------|---------|
| `TEXT_TO_SQL` | 用户想查数据，需要生成 SQL | 继续后续所有步骤 |
| `GENERAL` | 用户在问数据库相关的一般问题，但信息不完整不能生成 SQL。比如"这个数据库有什么数据？"、"帮我分析客户行为" | 走"数据助手"，LLM 直接回答文本，不生成 SQL |
| `MISLEADING_QUERY` | 问题和数据库无关，或太模糊。比如"今天天气怎样"、"帮我写个PPT" | 直接返回"问题不相关"提示，不生成 SQL |
| `USER_GUIDE` | 用户在问 WrenAI 本身的使用方法。比如"怎么连接数据库？"、"怎么画图表？" | 走"用户指南助手"，返回操作指引 |

Intent Classification 的 prompt 会把全部 schema DDL + 用户问题 + 对话历史一起发给 LLM，所以 **token 消耗很大（约 5-8 万）**。

**为什么关闭**：对于我们的场景，提问基本都是 TEXT_TO_SQL 类型。关掉后直接默认走 TEXT_TO_SQL，省一次 LLM 调用。

---

### 阶段 2：searching（检索相关表）

#### 2.1 DB Schema Retrieval（向量检索）

```
输入: "查询所有华为厂商的PE设备，要求运行状态正常"
  │
  ▼ Ollama embedding
  │
  ▼ Qdrant 向量搜索 "Document" 集合（60 个 schema chunk）
  │  按语义相似度排序，取 top 10（table_retrieval_size: 10）
  │
  ▼ 检索结果（按相关度排序）:
    1. t_network_element 的列 chunk（含 vendor, role, oper_status）
    2. t_network_element 的表结构 chunk
    3. t_board 的列 chunk（含 ne_id）
    4. t_site 的列 chunk
    5. ... 其他相关表
```

**这步只用 Ollama embedding，不调 DeepSeek**。

检索到的表会被组装成完整的 DDL（此时包含所有列），准备传给 LLM。

#### 2.2 Column Pruning（列裁剪）⭐

**开关**：`enable_column_pruning`（当前 = true，已开启）

这是控制 token 成本的关键步骤。

**不裁剪时的问题**：
```
检索到 t_network_element（31列）、t_board（22列）、t_site（22列）...
全部列的 DDL 拼起来可能有几千行
加上 system prompt + 指令 → 总 prompt 达到 20-30 万 token
```

**裁剪的工作方式**：

```
第一步：把检索到的所有表的完整 DDL 发给 DeepSeek（一次 LLM 调用）

prompt:
  "你是数据分析专家。根据以下数据库 schema 和用户问题，
   判断每张表中哪些列是回答问题所必需的。

   Database Schema:
   CREATE TABLE t_network_element (
     ne_id VARCHAR PRIMARY KEY,
     ne_name VARCHAR,
     ne_type VARCHAR,
     vendor VARCHAR,          ← 与"华为厂商"相关
     model VARCHAR,
     software_version VARCHAR,
     ...全部 31 列...
     role VARCHAR,            ← 与"PE设备"相关
     oper_status VARCHAR,     ← 与"运行状态正常"相关
     ...
   );
   CREATE TABLE t_board (...全部 22 列...);
   ...

   问题: 查询所有华为厂商的PE设备，要求运行状态正常

   请返回每张表需要的列名。"

DeepSeek 返回:
  {
    "results": [
      {
        "table_name": "t_network_element",
        "table_contents": {
          "columns": ["ne_id", "ne_name", "vendor", "role", "oper_status"]
        }
      }
    ]
  }
```

```
第二步：根据 LLM 的判断，只保留需要的列，重新构建精简 DDL

裁剪前（传给 SQL Generation 的内容）:
  CREATE TABLE t_network_element (31 列) → 约 2000 token
  CREATE TABLE t_board (22 列) → 约 1500 token
  CREATE TABLE t_site (22 列) → 约 1500 token
  ... 共约 15000 token

裁剪后:
  CREATE TABLE t_network_element (5 列) → 约 300 token
  其他表被完全去掉
  ... 共约 300 token
```

**为什么裁剪调一次 LLM 反而能省 token**：
- 裁剪这一次调用：约 3-5 万 token（发完整 schema + 收简短回复）
- 后续 SQL Generation 少传的 token：约 10-20 万
- **净省 7-15 万 token**
- 如果还有 SQL Correction 重试，每次都省，收益更大

---

### 阶段 3：planning（规划，可选）

**开关**：`allow_sql_generation_reasoning`（当前 = false，已关闭）

如果开启，会调一次 DeepSeek：
```
prompt: "分析这个问题需要怎样的 SQL 查询步骤：
  1. 需要哪些表？
  2. 需要什么 WHERE 条件？
  3. 需要 JOIN 吗？
  4. 需要聚合吗？"

DeepSeek 返回推理步骤（chain of thought）
```

这些推理步骤会作为额外上下文传给下一步的 SQL 生成，帮助 LLM 生成更准确的 SQL。

**为什么关闭**：对简单查询帮助不大，省一次 LLM 调用（约 5-8 万 token）。复杂的多表 JOIN + 聚合场景开启会更好。

---

### 阶段 4：generating（生成 SQL）⭐

这是最核心的一步。

#### 4.1 SQL Functions Retrieval（可选）

**开关**：`allow_sql_functions_retrieval`（当前 = false，已关闭）

如果开启，会从 ibis-server 获取 DuckDB 支持的所有 SQL 函数列表，塞进 prompt。让 LLM 知道可以用 `DATE_TRUNC`、`REGEXP_MATCHES` 等 DuckDB 特有函数。

**为什么关闭**：函数列表很长，增加 prompt token。简单查询不需要特殊函数。

#### 4.2 SQL Generation（LLM 生成 SQL）

```
调 DeepSeek，发送:

System Prompt:
  "你是专业的 SQL 数据分析师。根据用户问题和数据库 schema 生成 SQL。
   规则：
   - 只用给定 schema 中的表和列
   - 不要使用子查询，优先用 JOIN
   - 返回 JSON 格式 { "sql": "SELECT ..." }"

User Prompt:
  "Database Schema:
   /* 网元/设备表 - 路由器、交换机等网络设备信息 */
   CREATE TABLE t_network_element (
     -- {"alias":"NE ID","description":"网元唯一标识"}
     ne_id VARCHAR PRIMARY KEY,
     -- {"alias":"NE Name","description":"网元名称"}
     ne_name VARCHAR,
     -- {"alias":"Vendor","description":"厂商。取值: HUAWEI;ZTE;CISCO;JUNIPER;NOKIA"}
     vendor VARCHAR,
     -- {"alias":"Role","description":"设备角色。取值: PE;P;RR;ASBR"}
     role VARCHAR,
     -- {"alias":"Oper Status","description":"运行状态。取值: UP;DOWN;DEGRADED"}
     oper_status VARCHAR
   );

   Question: 查询所有华为厂商的PE设备，要求运行状态正常"

DeepSeek 返回:
  {
    "sql": "SELECT ne_id, ne_name, vendor, role, oper_status
            FROM t_network_element
            WHERE vendor = 'HUAWEI' AND role = 'PE' AND oper_status = 'UP'"
  }
```

**注意**：因为 Column Pruning 已经裁剪到 5 列，这里的 prompt 很短（约 500 token），DeepSeek 回复也很短。如果没有裁剪，prompt 里会有 14 张表共 356 列的完整 DDL。

#### 4.3 SQL Validation（Dry Run）

```
生成的 SQL 发到 wren-engine 做语法验证:

GET http://wren-engine:8080/v1/mdl/dry-run
body: {
  sql: "SELECT ne_id, ne_name, vendor, role, oper_status
        FROM t_network_element
        WHERE vendor = 'HUAWEI' AND role = 'PE' AND oper_status = 'UP'",
  manifest: { ... telecom_mdl.json 的完整内容 ... }
}

wren-engine 做两件事:
  1. 用 MDL manifest 做语义层翻译（如果用了模型引用就翻译成真实表名）
  2. 在 DuckDB 里验证 SQL 语法和列名是否存在

返回:
  ✓ 通过 → [{ name: "ne_id", type: "VARCHAR" }, ...] 列信息
  ✗ 失败 → 错误信息，如 "column xxx not found"
```

**这步不调 DeepSeek，是 wren-engine 本地验证**。

---

### 阶段 5：correcting（纠错，按需）

**配置**：`max_sql_correction_retries`（当前 = 1）

如果 Dry Run 失败（比如 LLM 生成了不存在的列名）：

```
调 DeepSeek:

prompt:
  "以下 SQL 在 DuckDB 中执行失败:
   SELECT ... FROM t_network_element WHERE sla_class = 'GOLD'

   错误信息: column 'sla_class' does not exist in t_network_element

   Database Schema: （同上）

   请修正 SQL。"

DeepSeek 返回修正后的 SQL
  → 再次 Dry Run 验证
    → 通过 → 进入执行
    → 再次失败 → 返回 NO_RELEVANT_SQL 错误（max_sql_correction_retries=1，只重试 1 次）
```

---

### 阶段 6：finished（执行并返回结果）

```
SQL 验证通过后:

AI 服务返回给 Next.js:
  { status: "finished", response: [{ sql: "SELECT ...", type: "llm" }] }

Next.js 拿到 SQL，调 previewSql:
  GET http://wren-engine:8080/v1/mdl/preview
  body: {
    sql: "SELECT ne_id, ne_name, vendor, role, oper_status
          FROM t_network_element
          WHERE vendor = 'HUAWEI' AND role = 'PE' AND oper_status = 'UP'",
    manifest: { ... },
    limit: 500
  }

wren-engine → DuckDB 执行 → 返回:
  {
    columns: [
      { name: "ne_id", type: "VARCHAR" },
      { name: "ne_name", type: "VARCHAR" },
      { name: "vendor", type: "VARCHAR" },
      { name: "role", type: "VARCHAR" },
      { name: "oper_status", type: "VARCHAR" }
    ],
    data: [
      ["NE-NJ-PE02", "NJ-CORE-PE02", "HUAWEI", "PE", "UP"],
      ["NE-HZ-PE01", "HZ-CORE-PE01", "HUAWEI", "PE", "UP"],
      ["NE-JN-PE01", "JN-CORE-PE01", "HUAWEI", "PE", "UP"],
      ...
    ]
  }

浏览器渲染结果表格。
```

---

## 完整调用链总结

```
用户输入 "查询所有华为厂商的PE设备，要求运行状态正常"
  │
  │ ───────── 阶段1: understanding ─────────
  │
  ├─ [Ollama] Historical Question embedding → Qdrant → 无命中
  ├─ [Ollama] SQL Pairs embedding → Qdrant → 无命中
  ├─ [Ollama] Instructions embedding → Qdrant → 无命中
  ├─ ❌ Intent Classification → 跳过 (allow_intent_classification=false)
  │
  │ ───────── 阶段2: searching ─────────
  │
  ├─ [Ollama] DB Schema embedding → Qdrant → 返回相关表的 DDL chunks
  ├─ [DeepSeek] Column Pruning → 14表356列裁剪为1表5列 (enable_column_pruning=true)
  │
  │ ───────── 阶段3: planning ─────────
  │
  ├─ ❌ SQL Generation Reasoning → 跳过 (allow_sql_generation_reasoning=false)
  │
  │ ───────── 阶段4: generating ─────────
  │
  ├─ ❌ SQL Functions Retrieval → 跳过 (allow_sql_functions_retrieval=false)
  ├─ [DeepSeek] SQL Generation → 生成 SQL ⭐
  ├─ [wren-engine] Dry Run → 语法验证
  │    ├─ ✓ 通过 → 进入执行
  │    └─ ✗ 失败 → [DeepSeek] SQL Correction (最多 1 次)
  │
  │ ───────── 阶段5: finished ─────────
  │
  └─ [wren-engine] Preview → DuckDB 执行 → 返回数据 → 浏览器渲染
```

## 开关配置速查

| 配置项 | 作用 | 调 DeepSeek? | Token 影响 | 当前值 |
|--------|------|-------------|-----------|--------|
| `allow_intent_classification` | 判断用户意图（TEXT_TO_SQL / GENERAL / MISLEADING / USER_GUIDE） | 是，1次 | +5~8万 | false |
| `enable_column_pruning` | 裁剪不相关的列，缩短后续 prompt | 是，1次 | 本次+3~5万，但后续-10~20万 | true |
| `allow_sql_generation_reasoning` | LLM 先规划 SQL 思路再生成 | 是，1次 | +5~8万 | false |
| `allow_sql_functions_retrieval` | 把 DuckDB 函数列表塞进 prompt | 否 | prompt 变长 | false |
| `max_sql_correction_retries` | SQL 验证失败后的最大重试次数 | 是，每次1次 | 每次+3~5万 | 1 |
| `column_indexing_batch_size` | 索引时每批处理的列数（影响 Ollama） | 否 | 不影响查询 | 10 |
| `table_retrieval_size` | 从 Qdrant 检索多少张相关表 | 否 | 检索越多 prompt 越长 | 10 |

## 当前配置下单次查询的 DeepSeek 调用

| 步骤 | 调用次数 | 预估 Token |
|------|---------|-----------|
| Column Pruning | 1 次 | 3~5 万 |
| SQL Generation | 1 次 | 1~3 万（裁剪后） |
| SQL Correction（仅失败时） | 0~1 次 | 0~3 万 |
| **合计** | **2~3 次** | **4~11 万** |
