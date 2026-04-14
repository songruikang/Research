# 知识分层体系设计

> 综合 RubikSQL、SiriusBI、Oracle Semantic Store、dbt MetricFlow、BIRD Evidence、Tk-Boost 等业界实践，结合电信 NMS 场景设计。

---

## 一、为什么要分层

你之前说得很准确：**description 已经能描述很多语义了，剩下的是指标和公式，这些单个 description 不好描述的跨表逻辑。**

业界的共识也是如此——RubikSQL 定义了 8 种知识模板，Oracle 的 Semantic Store 分了 6 个维度，但核心都是同一个问题：**哪些知识能从 schema 自动推断，哪些必须人工定义？**

```
能从 schema 推断的（不需要额外知识）:
  - 表名、列名、类型 → DDL 已有
  - 主键、外键 → relationships 已有
  - 枚举值 → description 里的"取值: HUAWEI;ZTE;..."

不能推断的（需要额外知识层）:
  - 业务概念 → "单点故障" = 站点对间链路数=1
  - 计算指标 → "SLA违规率" = SUM(NOT met) / COUNT(*)
  - 组合条件 → "100GE物理端口" = phy_type + if_type 两个字段
  - 查询模式 → "趋势" = GROUP BY DATE + LAG
  - 领域术语 → "PE" = Provider Edge，角色是 role='PE'
  - 业务规则 → "在网" = oper_status='UP'（不是 admin_status）
```

---

## 二、知识分层架构

参考 RubikSQL 的 6 层架构和 dbt 的 Semantic Layer，设计 4 层知识体系：

```
┌─────────────────────────────────────────────┐
│  Layer 4: Query Patterns（查询模式）          │  → 怎么写
│  趋势/环比/分布/TopN/对比 的 SQL 模板          │
├─────────────────────────────────────────────┤
│  Layer 3: Metrics & Rules（指标与规则）       │  → 怎么算
│  计算公式/评分规则/阈值定义/跨表计算           │
├─────────────────────────────────────────────┤
│  Layer 2: Business Concepts（业务概念）       │  → 是什么
│  术语映射/组合条件/业务实体定义                │
├─────────────────────────────────────────────┤
│  Layer 1: Schema Semantics（Schema 语义）    │  → 有什么
│  表描述/列描述/枚举值/外键关系                 │
│  （已由 MDL description 覆盖）               │
└─────────────────────────────────────────────┘
```

### Layer 1: Schema Semantics（已有，MDL description 覆盖）

**来源**: `telecom_mdl.json` 的 properties.description
**治理方式**: 修改 MDL 即可
**注入方式**: WrenAI 自动从 MDL 构建 DDL prompt

```
示例（已有）:
  vendor 列 description: "设备厂商。取值: HUAWEI;CISCO;ZTE;JUNIPER"
  role 列 description: "网元角色：PE(Provider Edge)、P(骨干)、CE(客户侧)..."
```

**不需要额外做什么**——除非 description 质量不够，才需要补充。

### Layer 2: Business Concepts（术语表）

**定义**: 用户用自然语言说的"东西"和数据库字段之间的映射。

**分类**:

| 子类 | 示例 | 特征 |
|------|------|------|
| **术语→枚举值** | "华为设备" → `vendor='HUAWEI'` | 单字段单值 |
| **术语→组合条件** | "100GE物理端口" → `phy_type='100GE' AND if_type='PHYSICAL'` | 多字段组合 |
| **术语→列集合** | "设备基本信息" → `ne_id, ne_name, vendor, role, oper_status` | 概念→多列 |
| **消歧义** | "在网" → `oper_status='UP'`（不是 `admin_status`） | 易混淆概念 |
| **同义词** | "金牌VPN" / "GOLD级别" / "GOLD VPN" → `service_level='GOLD'` | 多种表达 |

**数据结构**:

```yaml
# knowledge/L2_business_concepts.yaml
concepts:
  - id: BC001
    terms: ["华为", "华为设备", "华为厂商"]
    mapping:
      type: enum_value
      table: t_network_element
      condition: "vendor = 'HUAWEI'"
    confidence: 1.0  # 数据验证通过
    source: auto_extracted  # 来源标记

  - id: BC002
    terms: ["100GE物理端口", "100GE物理口"]
    mapping:
      type: composite_condition
      table: t_interface
      condition: "phy_type = '100GE' AND if_type = 'PHYSICAL'"
    confidence: 1.0
    source: manual
    note: "两个字段的组合，单列description无法完整表达"

  - id: BC003
    terms: ["设备基本信息", "网元信息"]
    mapping:
      type: column_set
      table: t_network_element
      columns: [ne_id, ne_name, vendor, model, role, oper_status, management_ip]
    confidence: 0.8  # 人工定义，可能不完整
    source: manual

  - id: BC004
    terms: ["在网", "在网设备"]
    mapping:
      type: disambiguation
      table: t_network_element
      condition: "oper_status = 'UP'"
      not_to_confuse: "admin_status（管理状态，人工设置）"
    confidence: 1.0
    source: manual
```

### Layer 3: Metrics & Rules（指标与规则）

**定义**: 需要计算的派生指标、业务规则、阈值定义。这是 description 最覆盖不了的部分。

**参考**: dbt MetricFlow 的 Metric 定义（Simple/Ratio/Derived/Cumulative）

**分类**:

| 子类 | 示例 | 复杂度 |
|------|------|--------|
| **单表公式** | 机柜利用率 = `used_rack_count / total_rack_count` | 低 |
| **跨表公式** | SLA违规率 = VPN SLA KPI 表的聚合 | 中 |
| **自定义评分** | 健康评分 = 4 项各 25 分 | 高 |
| **业务规则** | "单点故障" = 站点对间链路数=1 且承载 GOLD VPN | 高 |
| **阈值规则** | "高CPU" = cpu_usage_avg_pct > 80 | 低 |

**数据结构**:

```yaml
# knowledge/L3_metrics_rules.yaml
metrics:
  - id: MR001
    name: "机柜利用率"
    type: ratio  # dbt MetricFlow 分类
    formula: "used_rack_count * 100.0 / NULLIF(total_rack_count, 0)"
    table: t_site
    unit: "%"
    note: "NULLIF 防除零"
    triggers: ["机柜利用率", "机柜使用率", "机柜占用"]

  - id: MR002
    name: "SLA违规率"
    type: ratio
    formula: "SUM(CASE WHEN NOT sla_overall_met THEN 1 ELSE 0 END) * 100.0 / COUNT(*)"
    table: t_vpn_sla_kpi
    unit: "%"
    dimensions: [vpn_id, customer_name]  # 可按这些维度聚合
    time_column: collect_time
    triggers: ["SLA违规率", "SLA达标率", "违规率"]
    note: "达标率 = 100 - 违规率"

  - id: MR003
    name: "BGP对等体可用率"
    type: ratio
    formula: "bgp_peer_up_count * 100.0 / NULLIF(bgp_peer_total_count, 0)"
    table: t_ne_perf_kpi
    unit: "%"
    triggers: ["BGP可用率", "BGP对等体"]

rules:
  - id: RL001
    name: "单点故障链路"
    type: business_rule
    definition: |
      两个站点之间只有一条物理链路（oper_status='UP'），
      且该链路承载了 GOLD/PLATINUM 级别的 VPN 业务。
    sql_pattern: |
      WITH site_pair AS (
        SELECT LEAST(a_site_id, z_site_id) AS s1,
               GREATEST(a_site_id, z_site_id) AS s2,
               COUNT(*) AS link_cnt
        FROM t_physical_link WHERE oper_status = 'UP'
        GROUP BY s1, s2 HAVING COUNT(*) = 1
      )
      -- 再关联 VPN 业务判断是否承载 GOLD
    triggers: ["单点故障", "单链路风险"]

  - id: RL002
    name: "设备健康评分"
    type: scoring_rule
    definition: |
      需要问题中给出评分规则（如各项各25分）。
      常见评分维度: CPU利用率、内存利用率、温度、告警数。
      模式: CASE WHEN 指标 < 阈值 THEN 满分 ELSE 0 END，各项求和。
    triggers: ["健康评分", "健康分", "综合评分"]
```

### Layer 4: Query Patterns（查询模式）

**定义**: 反复出现的 SQL 结构模式，LLM 识别模式后填槽位。

**参考**: Tk-Boost 的 "Atomic Correction Statements" + DIN-SQL 的 Query Decomposition

```yaml
# knowledge/L4_query_patterns.yaml
patterns:
  - id: QP001
    name: "时间窗口过滤"
    triggers: ["过去24小时", "最近7天", "最近30天"]
    template: "WHERE collect_time >= CURRENT_TIMESTAMP - INTERVAL {N} {UNIT}"
    note: "DuckDB 语法: INTERVAL 24 HOUR（无引号无复数）"

  - id: QP002
    name: "环比趋势"
    triggers: ["环比", "趋势", "日变化"]
    template: |
      WITH daily AS (
        SELECT DATE_TRUNC('day', collect_time) AS dt, AVG({metric}) AS val
        FROM {table} WHERE {conditions}
        GROUP BY dt
      )
      SELECT dt, val, val - LAG(val) OVER (ORDER BY dt) AS change
      FROM daily

  - id: QP003
    name: "分布统计"
    triggers: ["分布", "空闲", "正常", "繁忙", "过载"]
    template: |
      SELECT {group_col},
        COUNT(CASE WHEN {metric} < {t1} THEN 1 END) AS bucket1,
        COUNT(CASE WHEN {metric} BETWEEN {t1} AND {t2} THEN 1 END) AS bucket2,
        ...

  - id: QP004
    name: "区域内 TopN"
    triggers: ["每个区域", "前三", "排名前"]
    template: |
      SELECT * FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY {region} ORDER BY {metric} DESC) AS rn
        FROM ...
      ) WHERE rn <= {N}

  - id: QP005
    name: "双时间窗对比"
    triggers: ["对比上周", "周环比", "增长超过"]
    template: |
      WITH this_period AS (...WHERE time >= {start1}...),
           last_period AS (...WHERE time >= {start2} AND time < {start1}...)
      SELECT ... this.val - last.val AS change ...
```

---

## 三、知识治理机制

### 3.1 知识来源与置信度

参考 RubikSQL 的 Provenance Layer：

| 来源 | 置信度 | 说明 |
|------|--------|------|
| `schema` | 1.0 | 从 DDL/MDL 自动提取，最可信 |
| `data_profiling` | 0.9 | 从真实数据扫描得到（如 DISTINCT 枚举值） |
| `manual` | 0.8 | 人工定义（可能不完整但逻辑正确） |
| `llm_extracted` | 0.6 | LLM 从文档/问题中提取（需要验证） |
| `user_feedback` | 0.7 | 用户纠正得到 |

### 3.2 知识验证

每条知识附带验证 SQL（我们之前讨论的"数据驱动验证"）：

```yaml
  - id: BC001
    terms: ["华为"]
    condition: "vendor = 'HUAWEI'"
    validation:
      sql: "SELECT DISTINCT vendor FROM t_network_element"
      expected_contains: "HUAWEI"
      last_verified: "2026-04-12"
      status: passed
```

### 3.3 知识冲突检测

参考 AmbiSQL 的 8 种歧义类型：

```
检测规则:
  1. 同一术语映射到不同列 → 冲突
     "设备状态" → oper_status? admin_status?

  2. 同一列在不同上下文有不同含义 → 需消歧
     "状态" 在 t_network_element 是运行状态，在 t_l3vpn_service 是管理状态

  3. 公式定义冲突
     "利用率" 在不同表有不同公式（机柜利用率 vs 带宽利用率）

  4. 阈值定义冲突
     "高CPU" → >80%? >70%? 取决于业务场景
```

### 3.4 知识评分

参考 RubikSQL 的三维评分：

```
Effectiveness Score（有效性）:
  加了这条知识后，有多少题从错变对？
  = (加知识后正确数 - 基线正确数) / 涉及题数

Regression Score（回退率）:
  加了这条知识后，有没有之前对的变错了？
  = 回退题数 / 总题数

Coverage Score（覆盖度）:
  这条知识被多少题使用到？
  = 匹配题数 / 总题数
```

---

## 四、知识注入策略

### 注入到 WrenAI 的映射

| 知识层 | WrenAI 机制 | 说明 |
|--------|------------|------|
| L1 Schema Semantics | MDL description | 已有，不改 |
| L2 Business Concepts | **Instructions API** | 通用规则作为 Instructions 注入 |
| L3 Metrics & Rules | **Instructions API** + **SQL Pairs** | 公式定义作为 Instructions，含公式的 QA 对作为 SQL Pairs |
| L4 Query Patterns | **SQL Pairs API** | 模式示例作为 few-shot |

### 选择性注入逻辑

```
用户提问: "查询华为PE设备的CPU利用率"

Step 1: 关键词匹配
  "华为" → BC001 (vendor='HUAWEI')
  "PE"   → BC005 (role='PE')
  "CPU利用率" → 无匹配（不是公式，是直接字段）

Step 2: 构建注入内容
  通用规则（always inject, ~500 tokens）
  + 匹配到的 BC001, BC005（~100 tokens）
  = 总注入 ~600 tokens

对比全量注入: 所有知识 ~2000 tokens
节省: 70%
```

---

## 五、知识可视化与治理界面

### 需要的界面功能

1. **知识浏览**: 按层级（L1-L4）浏览所有知识条目
2. **知识编辑**: 添加/修改/删除知识条目
3. **冲突检测**: 自动标记冲突的知识对
4. **有效性看板**: 每条知识的 Effectiveness/Regression/Coverage 分数
5. **验证状态**: 上次验证时间、验证结果、验证 SQL
6. **来源追踪**: 每条知识的来源（自动提取/人工/用户反馈）

### 与 Logs 页面的联动

```
Logs 页面看到一个失败的查询:
  问题: "查询100GE物理端口数量超过10个的设备"
  失败原因: 只过滤了 phy_type='100GE'，漏了 if_type='PHYSICAL'

→ 点击"创建知识" → 自动填充:
  terms: ["100GE物理端口"]
  condition: "phy_type = '100GE' AND if_type = 'PHYSICAL'"
  来源: user_feedback
  关联问题: Q05

→ 保存后自动:
  1. 注入 WrenAI Instructions
  2. 重跑 Q05 验证
  3. 更新知识评分
```

---

## 六、与当前系统的关系

```
当前系统:
  telecom_mdl.json (L1) → WrenAI → LLM → SQL

目标系统:
  telecom_mdl.json (L1)
  + knowledge/L2_business_concepts.yaml
  + knowledge/L3_metrics_rules.yaml
  + knowledge/L4_query_patterns.yaml
  ↓
  知识检索 + 选择性注入
  ↓
  WrenAI (Instructions + SQL Pairs + DDL prompt)
  ↓
  LLM → SQL
  ↓
  评测 → 知识评分 → 知识迭代
```

不是替换 WrenAI，而是在它的输入层前面加一个知识治理层。WrenAI 的 Instructions 和 SQL Pairs 就是注入通道。

---

## 七、最小闭环（Phase 1）

```
Day 1:
  1. 从 100 题 implicit_knowledge 自动提取知识 → L2 + L3 yaml 文件
  2. 人工审核 + 补充
  3. 用 Opus 跑三组对照实验验证知识有效性

Day 2:
  4. 有效知识注入 WrenAI（Instructions + SQL Pairs）
  5. WrenAI 端到端评测
  6. 建立知识评分机制

后续:
  7. 知识治理界面（作为 Logs 页面的扩展）
  8. 数据驱动的自动知识发现
  9. 对抗性探测发现盲区
```
