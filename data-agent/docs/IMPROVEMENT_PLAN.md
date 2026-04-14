# NL2SQL 系统改进计划

> 基于 100 题评测（可验证准确率 12%）、WrenAI 源码分析、实际部署调试的全面复盘

---

## 一、当前瓶颈诊断

### 调用链路和 Token 消耗

```
当前流程（每次查询）:
  Embedding 检索 (nomic-embed-text, 本地)     → 0 API tokens, 1-2s
  SQL Generation (llama-3.3-70b, Groq)        → 4K-9K tokens, 2-3s
  SQL Dry Run (wren-engine)                    → 0 tokens, <0.1s
  SQL Correction (如果 dry run 失败, 最多3次)  → 3K-8K tokens × 3次

最坏情况: 一次查询消耗 ~30K tokens（含3次纠错）
Groq 免费版 12K TPM → 30秒内只能跑1次查询
```

### 准确率瓶颈分析（100 题评测）

| 错误类型 | 占比 | 根因 |
|---------|------|------|
| 返回列不同 | 91% | 模型不知道"查设备信息"该返回哪些列 |
| JOIN 路径错误 | 19% | 3+表关联时选错了路径 |
| 聚合逻辑不同 | 20% | GROUP BY/聚合函数不一致 |
| 枚举值/条件缺失 | 12% | 缺少 admin_status='ACTIVE' 等业务条件 |
| 业务概念推理 | 8% | "单点故障""健康评分"等概念无法从 schema 推断 |

### 核心结论

**模型的 SQL 语法能力没问题（99% 可执行），问题在于缺少业务知识输入。**

---

## 二、减少 Token 消耗

### P0: Schema 检索精准化（当前最大浪费）

**现状**: `table_retrieval_size=5`，但检索质量差——"华为PE设备"检索到 `t_vpn_pe_binding` 而不是 `t_network_element`。

**方案: 两级检索（关键词优先 + embedding 兜底）**

```
Step 1: 关键词 + 术语表匹配（本地，0 tokens）
  "华为PE设备" → 术语表匹配 → vendor='HUAWEI', role='PE' → t_network_element
  "CPU利用率" → 列名匹配 → cpu_usage_avg_pct → t_ne_perf_kpi
  命中率预估: ~70% 的简单查询直接命中，不需要 embedding

Step 2: embedding 检索（仅关键词未命中时触发）
  只对 Step 1 未命中的查询做 embedding 检索
  预估节省: 70% 查询跳过 embedding，且检索结果更准

实现方式:
  新建 telecom/input/domain_glossary.yaml
  在 ask.py 中 embedding 检索前加关键词匹配逻辑
```

**预期效果**: 简单查询的 prompt 从 4K → 2K tokens（只传 2-3 张相关表）

### P1: Prompt 模板瘦身

**现状**: WrenAI 的 system prompt + DDL 格式冗余。例如每个列的注释格式：
```sql
-- {"alias":"Admin Status","description":"管理状态。取值: UP;DOWN"}
admin_status VARCHAR,
```

**方案: 压缩 schema 格式**

```
压缩前 (WrenAI 格式, ~500 tokens/表):
  /* {'alias': 't_network_element', 'description': '网元/设备表'} */
  CREATE TABLE t_network_element (
    -- {"alias":"NE ID","description":"网元唯一标识"}
    ne_id VARCHAR PRIMARY KEY,
    -- {"alias":"NE Name","description":"网元名称"}
    ne_name VARCHAR NOT NULL,
    ...30+ 列
  );

压缩后 (~150 tokens/表):
  -- t_network_element: 网元/设备表
  -- ne_id(PK), ne_name, vendor[HUAWEI|ZTE|CISCO], role[PE|P|CE|RR|ASBR],
  -- oper_status[UP|DOWN], site_id→t_site, cpu相关→t_ne_perf_kpi
  -- 常用查询: 按厂商/角色/状态过滤

实现方式:
  修改 wren-ai-service 的 DDLChunker，输出压缩格式
  或者自建 prompt builder 替代 WrenAI 的默认模板
```

**预期效果**: 5 张表的 schema 从 2500 tokens → 750 tokens

### P2: 缓存层

**方案: 语义缓存（相似问题复用 SQL）**

```
历史: "查询北京的华为PE设备" → SQL: ... WHERE city='北京' AND vendor='HUAWEI' AND role='PE'
新问题: "查询上海的中兴PE设备"
语义匹配: 同模式，替换参数
→ SQL: ... WHERE city='上海' AND vendor='ZTE' AND role='PE'

命中时: 0 LLM tokens
```

**实现**: WrenAI 已有 `sql_pairs` 功能（Knowledge 页面），但目前是手动添加。可以自动化——每次成功的 QA 对自动存入。

---

## 三、提高准确率

### P0: 领域术语表（ROI 最高）

**方案**: 建立 `domain_glossary.yaml`，注入到 SQL Generation 的 system prompt。

```yaml
# telecom/input/domain_glossary.yaml
terms:
  # 枚举值映射
  - natural: ["华为", "华为设备", "华为厂商"]
    sql: "vendor = 'HUAWEI'"
    table: t_network_element
  - natural: ["PE设备", "PE路由器", "PE"]
    sql: "role = 'PE'"
    table: t_network_element
  - natural: ["运行正常", "正常运行", "状态正常"]
    sql: "oper_status = 'UP'"
  - natural: ["在网设备", "在网"]
    sql: "oper_status = 'UP'"
    note: "在网=运行状态正常，不是管理状态"

  # 业务概念 → 多列
  - natural: ["设备基本信息", "网元信息"]
    columns: [ne_id, ne_name, vendor, model, role, oper_status, management_ip]
    table: t_network_element
  - natural: ["100GE物理端口"]
    sql: "phy_type = '100GE' AND if_type = 'PHYSICAL'"
    table: t_interface

  # 业务规则
  - natural: ["SLA违规", "SLA不达标"]
    sql: "sla_overall_met = false"
    table: t_vpn_sla_kpi
  - natural: ["GOLD级别VPN", "金牌VPN"]
    sql: "service_level = 'GOLD' AND admin_status = 'ACTIVE'"
    table: t_l3vpn_service
```

**注入方式**:
- 方式 A: 作为 WrenAI 的 Instructions 通过 API 注入（零代码改动）
- 方式 B: 自建 prompt builder，在 SQL Generation 前拼接术语表到 prompt

**预期效果**: 枚举值匹配错误降为 0，预估准确率 +15-20%

### P1: Few-shot 示例自动选择

**现状**: WrenAI 的 SQL Pairs 功能手动添加，没有自动选择。

**方案**:
1. 从 100 题测试用例中选出正确的 QA 对作为种子
2. 每次查询时，用关键词匹配选 3-5 个最相关的示例
3. 注入到 SQL Generation 的 prompt 中

```
问题: "查询华为PE设备"
匹配到的 few-shot:
  Q: "查询所有ZTE的P设备" → SQL: SELECT ... WHERE vendor='ZTE' AND role='P'
  Q: "统计各厂商PE设备数量" → SQL: SELECT vendor, COUNT(*) ... WHERE role='PE' GROUP BY vendor

LLM 看到示例后，知道:
  - vendor 值是大写
  - role 用 = 过滤
  - 表是 t_network_element
```

**实现**: 通过 WrenAI 的 Knowledge → SQL Pairs API 批量导入

### P2: 查询模式模板

**对复杂查询（趋势、环比、分布、评分）定义 SQL 模板**

```yaml
# telecom/input/query_patterns.yaml
patterns:
  - name: "KPI趋势对比"
    trigger: ["趋势", "环比", "对比上周", "变化"]
    template: |
      WITH current_period AS (
        SELECT {group_col}, AVG({kpi_col}) as current_avg
        FROM {kpi_table}
        WHERE collect_time >= {current_start}
        GROUP BY {group_col}
      ),
      previous_period AS (...)
      SELECT ... current_avg - previous_avg as change ...

  - name: "分布统计"
    trigger: ["分布", "空闲", "正常", "繁忙", "过载"]
    template: |
      SELECT {group_col},
        COUNT(CASE WHEN {metric} < {threshold1} THEN 1 END) AS low,
        COUNT(CASE WHEN {metric} BETWEEN ... THEN 1 END) AS mid,
        ...
```

**LLM 的任务简化为**: 识别模式 + 填槽位，而不是从零生成复杂 SQL

### P3: 自动评测驱动的增量改进

```
闭环:
  跑 100 题评测 → 找到失败的题 → 分析根因 → 针对性补充知识 → 重跑

示例:
  Q05 失败: "100GE物理端口" → 模型不知道要同时过滤 phy_type 和 if_type
  修复: 在术语表加 "100GE物理端口" → phy_type='100GE' AND if_type='PHYSICAL'
  重跑: Q05 通过 ✓

  每轮修复 5-10 题，3-4 轮后准确率从 12% → 50%+
```

---

## 四、自动化获取高质量知识

### P0: 数据驱动的术语表自动生成

**从真实数据中挖掘枚举值和业务术语**

```python
# auto_glossary.py
# 对每张表的每个 VARCHAR 列:
#   SELECT DISTINCT col_name FROM table
#   如果 distinct 值 < 50 → 这是枚举字段 → 自动生成映射

# 示例输出:
# t_network_element.vendor: ['HUAWEI', 'ZTE', 'CISCO', 'JUNIPER']
#   → 自动生成: "华为" → vendor='HUAWEI'
#   → 自动生成: "中兴" → vendor='ZTE'

# t_network_element.role: ['PE', 'P', 'CE', 'RR', 'ASBR', 'ABR']
#   → 自动生成: "PE设备" → role='PE'

# t_l3vpn_service.service_level: ['PLATINUM', 'GOLD', 'SILVER', 'BRONZE']
#   → 自动生成: "金牌VPN" → service_level='GOLD'
```

**实现步骤**:
1. 扫描 DuckDB 所有 VARCHAR 列的 DISTINCT 值
2. 用 LLM 批量生成中文→英文映射（一次性，低成本）
3. 输出 `domain_glossary.yaml`
4. 人工审核后注入系统

### P1: 对抗性探测自动发现知识盲区

```
自动生成"正例+反例"问题:

定义: "PE设备" → role='PE'
自动生成:
  正例: "查询所有PE设备" → 应该 WHERE role='PE'
  反例: "查询所有P设备" → 应该 WHERE role='P'（不是PE）
  边界: "查询PE和P设备" → 应该 WHERE role IN ('PE','P')

跑评测 → 如果反例错了 → 说明模型混淆了 PE 和 P → 需要在术语表中明确区分
```

### P2: 成功查询自动学习

```
用户提问 → SQL 生成 → 执行成功 → 用户确认结果正确
  ↓
自动存入 SQL Pairs（Knowledge 页面）
  ↓
下次相似问题 → 匹配历史示例 → 准确率更高

实现: 在 ask.py 的成功路径上调用 SQL Pairs API 自动保存
```

### P3: 外键关系的 JOIN 路径推导

**现状**: 模型靠看 DDL 中的 FOREIGN KEY 注释猜 JOIN 路径，3+ 表时经常错。

**方案**: 预计算所有表之间的最短 JOIN 路径，作为知识注入 prompt

```
预计算:
  t_l3vpn_service → t_network_element: 经过 t_vpn_pe_binding（2跳）
  t_ne_perf_kpi → t_site: 经过 t_network_element（2跳）

注入 prompt:
  "如果需要关联 VPN 和设备，使用:
   t_l3vpn_service JOIN t_vpn_pe_binding ON vpn_id JOIN t_network_element ON ne_id"
```

---

## 五、实施优先级

| 阶段 | 任务 | 预期准确率提升 | 工作量 | Token 节省 |
|------|------|-------------|--------|-----------|
| **Phase 1** | 术语表(P0) + 数据驱动生成(P0) | 12% → 30% | 1-2 天 | 无 |
| **Phase 1** | Few-shot 种子导入(P1) | +10% | 半天 | 无 |
| **Phase 2** | 两级检索(P0) | +5% | 1-2 天 | -50% tokens |
| **Phase 2** | Prompt 瘦身(P1) | +3% | 1 天 | -60% tokens |
| **Phase 3** | 查询模式模板(P2) | +10% | 2-3 天 | 无 |
| **Phase 3** | JOIN 路径推导(P3) | +5% | 1 天 | 无 |
| **Phase 4** | 对抗性探测(P1) | 持续改进 | 1 天 | 无 |
| **Phase 4** | 成功查询自动学习(P2) | 持续改进 | 半天 | -30% tokens |

**Phase 1 目标**: 30%+ 准确率，1-2 天完成
**Phase 2 目标**: 40%+ 准确率，token 消耗减半
**Phase 3 目标**: 50%+ 准确率
**Phase 4 目标**: 持续自我改进的闭环

---

## 六、技术选型建议

| 组件 | 当前 | 建议 | 理由 |
|------|------|------|------|
| LLM | Groq llama-3.3-70b（12K TPM） | 保持，或升级 Groq 付费版 | SQL 能力够，限流是主要问题 |
| Embedding | 本地 nomic-embed-text | 保持 | 免费，质量够 |
| 检索 | WrenAI embedding only | 关键词优先 + embedding 兜底 | 减少误检索 |
| Column Pruning | 关闭 | 保持关闭（14表场景） | 省 1 次 LLM 调用 |
| 知识注入 | 无 | Instructions + SQL Pairs | WrenAI 已有接口，零代码改动 |
| 评测 | eval_framework.py | 保持 + 增量闭环 | 每次改进后量化验证 |
