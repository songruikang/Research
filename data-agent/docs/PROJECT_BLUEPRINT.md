# 电信智能查询系统 — 项目蓝图

> 创建: 2026-04-15 | 版本: 1.0

---

## 一、系统定位

构建一个端到端的电信智能查询系统：用户用中文提问 → AI 生成 SQL → 查询引擎在异构数据源上高效执行。

两个子系统通过 **SQL** 解耦：

```
用户自然语言
    │
    ▼
DataAgent (NL2SQL)               ← 本项目，你 + Claude
    │ 标准 SQL
    ▼
External Pushdown Engine         ← PMC 主导，你协调
    │ 改写后的 REMOTE_TABLE SQL
    ▼
StarRocks (联邦执行，零修改)
    │
    ├── Region 1: GaussDB (OLTP)
    ├── Region 2: Druid (OLAP)
    └── Region N: ClickHouse / Hive / ES (扩展)
```

DataAgent 不需要知道底层有几个数据源，下推引擎不需要知道 SQL 是人写的还是 AI 生成的。这是唯一正确的系统边界。

---

## 二、DataAgent — 现状与洞察

### 2.1 实验数据（4 轮对照实验，2026-04-13）

| 实验 | Schema 策略 | 知识注入 | 宽松准确率 | 关键发现 |
|------|------------|---------|-----------|---------|
| 全量 Schema | 14 表全量 DDL | 无 | 38% | 上下文噪音严重 |
| 流水线 A | 精简 ~2.7 表 | 无 | **50%** | 上下文缩减 75%，准确率 +12% |
| 流水线 B | 精简 ~2.7 表 | 通用规则+专项定义 | 39% | **知识注入负优化 -11%** |
| Sonnet 对照 | 全量/精简 | 有/无 | 均低于 Opus | 模型能力是基本面 |

### 2.2 核心洞察

**洞察 1：精简上下文 > 知识注入（与 RubikSQL VLDB 2024 结论一致）**

给强模型（Opus）注入领域知识不仅没用，还降低了准确率。原因：Opus 已经能从 DDL 描述中读懂业务语义（如 `vendor VARCHAR -- 取值: HUAWEI;ZTE;CISCO`），额外注入的规则引入了注意力竞争。

这个发现与业界趋势一致：
- RubikSQL (VLDB 2024) 发现知识注入的 ROI 取决于"模型能力"与"注入精度"的匹配度
- BIRD Benchmark 的 Evidence 机制对弱模型有效，对 GPT-4 级别模型边际收益递减
- Oracle Semantic Store 和 dbt Semantic Layer 都在转向"让 Schema 自己说话"而非堆积外部规则

**实践启示**：我们的架构不应追求"注入更多知识"，而应追求"精准检索最相关的 Schema 片段"。面向 100+ 表生产规模，分层检索（关键词优先 + embedding 兜底）是正确方向。

**洞察 2：87% 的"错误"是列选择问题，不是逻辑错误**

100 题中未严格匹配的 87 题分析：
- 37 题：逻辑完全正确，只是 `SELECT *` vs 期望 5 列 → 不是错误
- 11 题：列不同且值格式差异 → 边界情况
- 34 题：真正逻辑错误 → 集中在 Hard/Extra Hard
- 5 题：双方 0 行，不可验证

**实践启示**：列选择是可标准化的问题（按查询类型定义返回列模板），真正需要攻关的是 34 题的复杂推理——多表 JOIN 路径、时间窗口对比、自定义公式计算。这些需要 few-shot 示例或查询模式模板，而非更多规则。

**洞察 3：评测方法论本身是有价值的产出**

我们建立的评测体系（三级判定 + sqlglot 五维评分 + 宽松/严格双口径）在业界有明确对标：
- 严格 EX 对标 Spider/BIRD 的 Execution Accuracy
- 宽松 EX 是我们的创新——排除列选择噪音后的"逻辑正确率"
- 五维评分（表/列/WHERE/JOIN/聚合）可定位具体哪个维度需要改进

### 2.3 下一步方向

| 方向 | 为什么 | 预期收益 | 优先级 |
|------|--------|---------|--------|
| **Few-shot 示例自动选择** | 34 题真逻辑错误集中在 Hard/ExtraHard，需要参考示例 | +10-15% Hard 准确率 | P0 |
| **分层检索（关键词+embedding）** | 面向 100 表必须做，当前 embedding 检索质量差 | Token 消耗 -50% | P0 |
| **查询模式模板** | 趋势/环比/分布/TopN 是反复出现的 SQL 结构 | +10% Hard 准确率 | P1 |
| **数据驱动术语表** | 从 DuckDB 自动扫描枚举值，替代手动维护 | 知识维护成本归零 | P1 |
| **100 表 Schema 扩展** | 14 表 demo 无法代表生产复杂度 | 验证架构可行性 | P2 |

### 2.4 与下推引擎的协同

DataAgent 和下推引擎共享同一套电信 Schema：
- `t_network_element`、`t_site` 等存量表 → GaussDB（OLTP）
- `t_ne_perf_kpi`、`t_interface_perf_kpi` 等 KPI 表 → Druid（OLAP 时序）

DataAgent 生成的 SQL 直接作为下推引擎的测试用例。两个子系统的测试数据天然对齐，不需要额外造数据。

---

## 三、External Pushdown Engine — 架构摘要

> 详细设计见团队内部文档。此处只摘录与 DataAgent 对接相关的要点。

### 3.1 核心思路

在 StarRocks 外面建一层查询改写微服务，在 SQL 到达 StarRocks 之前完成下推决策、AST 改写、方言翻译，封装为 REMOTE_TABLE 调用。**StarRocks 零修改。**

### 3.2 处理流水线

```
用户 SQL → SQL 解析 + 源识别 → 下推规则引擎（查能力注册表）
→ 查询改写（AST 切分）→ 方言转换（L1 标准 SQL / L2 YAML / L3 Visitor）
→ REMOTE_TABLE 封装 → StarRocks 执行
```

### 3.3 预期价值（基于架构分析估算）

| 场景 | 传输量减少 | 查询提速 | 核心技术 |
|------|-----------|---------|---------|
| 单源 Druid 聚合 | ↓99.7% | 16× | 聚合下推 |
| GaussDB 全查询路由 | ↓99.9% | 5.3× | 整条 SQL 直接路由 |
| 跨源 JOIN | ↓98% | 16× | Predicate Transfer |
| 多 Region UNION | ↓99.8% | 22× | Partial Aggregation |

### 3.4 MVP 验证场景

2 周 demo 聚焦 **Scenario A（单源聚合下推）**：

```sql
-- 改写前：StarRocks 拉回 800 万行明细做聚合
SELECT device_id, SUM(traffic) FROM druid_traffic
WHERE collect_time >= '2025-03-01' GROUP BY device_id ORDER BY ... LIMIT 20

-- 改写后：Druid 远端聚合，只返回 20 行
SELECT * FROM REMOTE_TABLE(
  "query" = "SELECT device_id, SUM(traffic) ... GROUP BY ... ORDER BY ... LIMIT 20",
  "format" = "jdbc", "uri" = "jdbc:avatica:..."
)
```

GaussDB 全查询路由作为第二验证点。跨源 JOIN（Scenario B/C）作为架构演示，不在 2 周内实跑。

### 3.5 为什么外置而非做在 StarRocks 内部

1. StarRocks RBO 是单趟树变换，不支持 Predicate Transfer 的两阶段有状态决策
2. 方言修复需要小时级上线，不能跟 StarRocks 发版周期
3. 社区没有动力做好联邦查询（CelerData 靠数据导入变现）
4. 引擎无关性：外挂层绑定联邦下推能力域，换引擎 95% 代码可复用

---

## 四、2 周 Demo 计划

### Week 1: 下推引擎骨架 + DataAgent 文档化

| 天 | PMC（查询引擎层） | 你 + Claude |
|---|---|---|
| D1 | Maven 项目 + Calcite SqlParser 集成 | 本文档定稿 + 业界对标分析 |
| D2 | 源识别 + 能力注册表 YAML 加载 | 编写 GaussDB/Druid 能力注册表 + 方言映射 YAML |
| D3 | Filter 下推 (R1) + Projection 裁剪 (R2) | 方言转换器 L1 标准 SQL + L2 Druid YAML |
| D4 | Aggregation 下推 (R4，只 SUM/COUNT/MIN/MAX) | REMOTE_TABLE 封装器（临时表方案） |
| D5 | 单源改写器（AST 切分 + 重组） | 集成测试：手写 SQL → 改写 → 验证 |

### Week 2: 端到端验证 + 可视化

| 天 | PMC（查询引擎层） | 你 + Claude |
|---|---|---|
| D6 | Scenario A 端到端跑通 | Benchmark 脚本 + 测试数据生成 |
| D7 | 性能调优 + Fallback Controller | Demo 可视化 UI（改写过程 4 步展示） |
| D8 | GaussDB 全查询路由验证 | DataAgent 评测报告整理 |
| D9 | 稳定性测试 + 边界 case | 端到端串联（DataAgent SQL → 下推引擎，可选）|
| D10 | 联调 + Demo 彩排 | 文档收尾 + 演示准备 |

### MVP 技术决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Aggregation 范围 | 只 SUM/COUNT/MIN/MAX | AVG 分解有语义陷阱，留 Phase 2 |
| REMOTE_TABLE 替代 | 临时表方案 | MVP 不需要改 StarRocks 内核 |
| 跨源 JOIN | 仅 PPT 演示 | 临时表方案下跨源写入量大，不适合 demo |
| 测试数据 | 复用 DataAgent 电信 Schema | 两系统天然对齐 |
| 方言范围 | GaussDB(≈PostgreSQL) + Druid | 最小异构验证集 |

---

## 五、业界对标

### 5.1 NL2SQL 领域

| 方向 | 代表工作 | 我们的位置 |
|------|---------|-----------|
| 评测标准 | Spider (Yale), BIRD (HKU) | 我们的三级判定 + 宽松 EX 是差异化指标 |
| 知识注入 | RubikSQL (VLDB 2024), Tk-Boost | 实验验证了"强模型不需要规则注入"的结论 |
| 语义层 | dbt Semantic Layer, Oracle Semantic Store | MDL 作为唯一源头，与业界方向一致 |
| 检索增强 | SiriusBI, DIN-SQL | 分层检索（关键词+embedding）是共识 |

### 5.2 联邦查询领域

| 方向 | 代表工作 | 我们的位置 |
|------|---------|-----------|
| 外挂式下推 | Dingo (VLDB 2025 Workshop) | 验证了引擎无关联邦下推的学术可行性 |
| Table Function | Trino query(), DuckDB postgres_query() | REMOTE_TABLE 的设计参考 |
| 聚合分解 | FlexPushdownDB (PVLDB 2021) | separable operators 概念，下推粒度控制 |
| 跨源协同 | Predicate Transfer (CIDR 2024) | Bloom Filter 预过滤的理论基础 |

### 5.3 我们的差异化

1. **两层系统集成**：NL2SQL + 联邦下推的端到端闭环，业界罕见
2. **电信领域验证**：不是通用 benchmark，是真实生产 schema（100+ 表 3500 列）
3. **实验驱动**：不是理论设计，每个决策都有对照实验数据支撑
4. **外挂式架构**：不改 StarRocks 内核，方言修复小时级上线，引擎可替换

---

## 六、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Druid SQL 接口限制多 | MVP Scenario A 可能遇到不支持的语法 | 能力注册表严格声明，不支持的算子不下推 |
| 临时表方案性能不理想 | Demo 的 Before/After 对比不够惊艳 | 选小结果集场景（聚合后 20 行），放大传输量对比 |
| LLM 限流影响 DataAgent | 无法在 demo 中实时展示 NL2SQL | 预录结果 + 离线评测报告，不依赖实时调用 |
| 100 表 Schema 扩展时间不够 | DataAgent 无法展示生产规模能力 | 14 表 demo + 100 表架构设计文档，分开呈现 |

---

## 七、成功标准

### 2 周 Demo

- [ ] Scenario A（Druid 聚合下推）端到端跑通，传输量减少 ≥95%
- [ ] GaussDB 全查询路由跑通
- [ ] Benchmark 脚本输出 Before/After 对比报告
- [ ] Demo 可视化 UI 展示改写过程
- [ ] DataAgent 评测报告 + 业界对标文档

### 后续里程碑

- Month 1: Scenario B（跨源 JOIN）实跑 + DataAgent 准确率 70%+
- Month 2: REMOTE_TABLE 真正实现（StarRocks PR）+ 100 表 Schema 扩展
- Month 3: 生产环境部署 + 端到端性能验证
