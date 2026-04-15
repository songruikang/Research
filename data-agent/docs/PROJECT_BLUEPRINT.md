# DataAgent 项目蓝图

> 版本: 2.0 | 更新: 2026-04-15
> v1.0 → v2.0 变更：重新定义设计纲领，从"功能堆砌"转向"工程驱动 + 最小化 LLM 调用"

---

## 一、系统定位

构建一个端到端的电信智能查询系统：用户用中文提问 → AI 生成 SQL → 查询引擎在异构数据源上高效执行。

两个子系统通过 **SQL** 解耦：

```
用户自然语言
    │
    ▼
DataAgent (NL2SQL)               ← 本项目
    │ 标准 SQL
    ▼
Pushdown Engine                  ← PMC 主导
    │ 改写后的 REMOTE_TABLE SQL
    ▼
StarRocks (联邦执行，零修改)
    │
    ├── Region 1: GaussDB (OLTP)
    ├── Region 2: Druid (OLAP)
    └── Region N: ClickHouse / Hive / ES (扩展)
```

DataAgent 不需要知道底层有几个数据源，下推引擎不需要知道 SQL 是人写的还是 AI 生成的。

### 与下推引擎的接口约定

| 约定项 | 规格 | 备注 |
|--------|------|------|
| SQL 方言 | 标准 SQL（StarRocks 兼容语法） | DataAgent 生成的 SQL 应能直接在 StarRocks 上 dry-run |
| 表名/列名 | 与 MDL 中的 DDL 定义一致 | 两系统共享同一套电信 Schema DDL |
| 测试数据 | DataAgent 100 题评测集的 SQL 直接作为下推引擎的输入测试集 | 天然对齐，不需要额外造数据 |
| 错误反馈 | 下推引擎返回结构化错误码（如 `UNSUPPORTED_SYNTAX`、`SOURCE_UNREACHABLE`） | Phase 2：DataAgent 据此学习哪些 SQL pattern 不可执行 |
| 能力声明 | 下推引擎提供 `capabilities.yaml`，声明各数据源支持的算子/函数 | Phase 2：DataAgent 生成 SQL 时可参考 |

---

## 二、设计纲领（六原则）

这六条原则指导所有技术决策。当功能需求与原则冲突时，原则优先。

### 原则 1：LLM 是推理引擎，不是万能胶水

只有"从自然语言到 SQL 的最终组装"需要 LLM。其他步骤——Schema 定位、列选择、JOIN 路径、模式识别、SQL 验证——优先用确定性工程手段。

```
当前 WrenAI（4-7 次 LLM 调用/查询）：
  Q → [LLM:意图分类] → [LLM:列选择] → [LLM:推理规划] → [LLM:SQL生成] → [LLM:纠错×N]

目标（1-2 次 LLM 调用/查询）：
  Q → [工程:Schema Linking] → [工程:Few-shot检索] → [工程:模式匹配]
    → [LLM:SQL生成]
    → [工程:sqlglot校验 + dry-run]
    → (失败时) [LLM:纠错，限1次]
```

### 原则 2：工程兜底，模型锦上添花

系统的基准能力来自工程层，不来自模型能力。换一个更弱的模型，准确率应该优雅降级而非崩溃。

| 步骤 | 工程覆盖 | LLM 职责 |
|------|---------|---------|
| Schema Linking | 关键词匹配 + FK 图扩展（覆盖 ~85%） | 兜底模糊匹配（~15%） |
| JOIN 路径 | FK 图确定性推导 | 无 |
| 查询模式识别 | 规则匹配（聚合/排名/趋势/对比/分布） | 无法匹配时由 LLM 判断 |
| SQL 骨架 | 模板覆盖常见模式 | 填槽 + 复杂推理 |
| SQL 验证 | sqlglot 解析 + dry-run | 无 |

### 原则 3：精准上下文 > 丰富上下文

对资源受限模型（32B 级别），3 张精准表 > 14 张表里有 3 张相关的。不相关的上下文不只是浪费 token，会主动误导模型。

目标：每次 LLM 调用的 Schema 上下文控制在 3-5 张表以内。

### 原则 4：知识是结构化数据，不是 prompt 文本

领域知识编码为结构化数据（YAML/JSON），在工程层按需提取，只将当前查询相关的知识片段注入 prompt。不堆砌自然语言规则。

```yaml
# 结构化知识示例
columns:
  t_network_element.ne_type:
    enum: [eNodeB, gNodeB, NodeB, RNC, BSC]
    zh_alias: [网元类型, 设备类型, NE类型]
  t_network_element.vendor:
    enum: [HUAWEI, ZTE, CISCO, ERICSSON, NOKIA]
    zh_alias: [厂商, 设备厂家, 供应商]

join_paths:
  - from: t_network_element
    to: t_ne_perf_kpi
    on: ne_id
    semantic: "设备→性能KPI"
```

知识注入到 prompt 中的形式：写在 DDL 注释里（`-- vendor 取值: HUAWEI|ZTE|CISCO`），而非单独的规则段落。

### 原则 5：Few-shot 是最高 ROI 投入

对非前沿模型，few-shot 示例选择质量是影响准确率的最大单一因素。

- 离线准备：从 100 题评测集中筛选 50-80 个高质量 (question, SQL) 对
- 在线检索：question embedding 余弦相似度 → top-3，零 LLM 消耗
- SQL 骨架多样性：优先选结构不同的示例，避免 3 个示例都是简单 SELECT

### 原则 6：可度量的每一层

不只看端到端准确率，每层有独立指标，才能定位瓶颈。

| 层 | 指标 | 目标 |
|----|------|------|
| Schema Linking | Recall@5（前 5 张表中包含正确表的比率） | >95% |
| Few-shot 检索 | 检索到的示例与当前查询模式匹配率 | >80% |
| SQL 生成 | 给定正确 Schema + Few-shot 时的准确率（"理想条件准确率"） | 度量模型天花板 |
| SQL 验证 | 错误 SQL 被 sqlglot + dry-run 拦截的比率 | >90% |
| 端到端 | 宽松 EX / 严格 EX | 在模型天花板范围内最大化 |

---

## 三、现状与实验数据

### 3.1 评测数据（4 轮对照实验，2026-04-13，Opus）

| 实验 | Schema 策略 | 知识注入 | 宽松准确率 | 关键发现 |
|------|------------|---------|-----------|---------|
| 全量 Schema | 14 表全量 DDL | 无 | 38% | 上下文噪音严重 |
| 流水线 A | 精简 ~2.7 表 | 无 | **50%** | 上下文缩减 75%，准确率 +12% |
| 流水线 B | 精简 ~2.7 表 | 通用规则+专项定义 | 39% | 粗粒度知识注入负优化 -11% |
| Sonnet 对照 | 全量/精简 | 有/无 | 均低于 Opus | 模型能力是基本面 |

### 3.2 核心洞察

**洞察 1：精简上下文在当前阶段 > 知识注入**

实验 B 的负优化说明粗粒度规则注入对强模型有害。但这不代表知识注入本身无用——代表注入方式（自然语言规则堆砌）和粒度（与查询无关的规则也注入）有问题。知识注入在精准检索就绪后需要重新实验验证。

**洞察 2：87% 的"错误"是列选择问题，不是逻辑错误**

100 题中未严格匹配的 87 题：37 题逻辑正确但列不同，11 题边界情况，34 题真逻辑错误（集中在 Hard/ExtraHard），5 题不可验证。

**实践启示**：列选择可标准化（查询类型 → 返回列模板），真正需要攻关的 34 题需要 few-shot 示例引导，而非更多规则。

**洞察 3：模型能力是基本面，工程是放大器**

Opus > Sonnet 在所有实验条件下都成立。同理，Qwen3 32B 的基准能力低于 Opus，需要更多工程补偿。工程优化可以缩小差距，但无法逆转模型能力差。如果工程优化后 32B 的天花板仍不满足需求，需要考虑微调或换模型，而不是继续堆工程。

### 3.3 待验证：Qwen3 32B 理想条件天花板

在任何 pipeline 改造之前，必须先做这个实验：

> 手动给 Qwen3 32B 完美输入（正确的 3 张表 + 2-3 个最佳 few-shot + 最小化 prompt），跑 20-30 题，度量"理想条件准确率"。

这个数字决定了工程优化的上限。如果理想条件下只有 40%，说明 32B 在电信 NL2SQL 上能力不足，需要微调或换模型。如果能到 65%+，说明工程层做好就能达标。

---

## 四、目标 Pipeline 架构

### 4.1 当前 WrenAI Pipeline（问题分析）

```
用户问题
  │
  ├─ [LLM #1] 意图分类 (intent_classification)        ← 简单查询不需要
  ├─ [Embedding] Schema 检索 from Qdrant               ← 保留
  ├─ [LLM #2] 列选择 (table_columns_selection)         ← 应工程化
  ├─ [LLM #3] 推理规划 (sql_generation_reasoning)      ← 简单查询不需要
  ├─ [Embedding] Few-shot 检索 (sql_pairs_retrieval)    ← 保留但需增强
  ├─ [LLM #4] SQL 生成 (sql_generation)                ← 核心，保留
  ├─ [Dry-run] SQL 验证                                 ← 保留
  └─ [LLM #5-7] 纠错循环 ×3 (sql_correction)           ← 限制为 1 次
```

问题：4-7 次 LLM 调用，大量 token 浪费在非核心步骤。

### 4.2 目标 Pipeline

```
用户问题
  │
  ▼
[Phase A: 工程预处理，零 LLM 消耗]
  ├─ A1. 关键词提取（jieba 分词 + 领域词典）
  ├─ A2. Schema Linking（关键词→列注释匹配 + FK 图扩展）
  ├─ A3. 查询模式识别（规则匹配：聚合/排名/趋势/对比/分布）
  ├─ A4. Few-shot 检索（embedding 相似度 → top-3，预计算索引）
  └─ A5. 知识片段提取（匹配到的表/列 → 提取枚举值、JOIN 路径）
  │
  ▼
[Phase B: Prompt 组装]
  ├─ 精简 DDL（只含匹配的 3-5 张表，列注释内嵌知识）
  ├─ Few-shot 示例（2-3 个，按 SQL 骨架多样性选择）
  ├─ 查询模式提示（如果匹配到模板，给出 SQL 骨架参考）
  └─ 用户问题
  │
  ▼
[Phase C: LLM 调用，1 次]
  └─ SQL 生成
  │
  ▼
[Phase D: 工程后处理，零 LLM 消耗]
  ├─ D1. sqlglot 解析验证（语法正确性）
  ├─ D2. Schema 一致性检查（表/列是否存在）
  ├─ D3. Dry-run（EXPLAIN 或 LIMIT 1 执行）
  └─ D4. 结果合理性检查（行数、NULL 比率）
  │
  ▼
[Phase E: 纠错，仅在 D 阶段失败时触发，最多 1 次 LLM 调用]
  ├─ 将错误信息 + 原 SQL 喂给 LLM 修正
  └─ 再次走 Phase D 验证
```

### 4.3 改造策略

不推翻 WrenAI 重写，而是**保留外壳（UI + Thread + Trace），替换引擎层**。

具体做法：在 `wren-ai-service/src/pipelines/` 中新建工程化 pipeline，逐步替换现有 LLM-heavy pipeline，每替换一个用评测集验证不退步。

| WrenAI 现有 Pipeline | 改造方式 |
|---------------------|---------|
| `intent_classification` | 删除，用规则匹配替代（正则判断是否 SQL 相关） |
| `db_schema_retrieval` + LLM 列选择 | 替换为工程化 Schema Linking（关键词 + FK 图） |
| `sql_generation_reasoning` | 删除，推理职责合并进 SQL 生成 prompt |
| `sql_pairs_retrieval` | 保留 embedding 检索，增加 SQL 骨架多样性重排 |
| `sql_generation` | 保留，但重写 prompt 模板（精简化 + 结构化） |
| `sql_correction` | 保留，限制为 1 次 |
| `sql_knowledge_retrieval` | 替换为工程化知识提取（从 YAML 按需查询） |

---

## 五、开发环境与模型策略

### 5.1 环境

| 环境 | 硬件 | 用途 | 模型 |
|------|------|------|------|
| Mac 本地 | CPU only | 开发、调试、单元测试 | 免费 API（见下表） |
| 公司云 | H100 × 1 | 集成测试、评测、演示 | Qwen3 32B（自部署） |

### 5.2 模型配置表

开发阶段使用免费/低成本 API，通过 `config.yaml` 切换，不改代码。

| 模型 | 提供商 | 免费额度 | 适用场景 | config.yaml model 值 |
|------|--------|---------|---------|---------------------|
| Gemini 2.5 Flash | Google AI Studio | 免费层较充裕 | 日常开发调试 | `gemini/gemini-2.5-flash-preview-04-17` |
| DeepSeek V3 | DeepSeek | 注册赠送 | SQL 生成测试（代码能力强） | `deepseek/deepseek-chat` |
| Qwen3 32B | 公司 H100 | 无限（自部署） | 评测、基准测试 | `openai/qwen3-32b`（via api_base） |

> 模型特征备忘：
> - Gemini Flash：速度快，长上下文好，但 JSON 结构化输出偶尔不稳定，需要 retry
> - DeepSeek V3：SQL/代码能力强，中文理解好，延迟较高
> - Qwen3 32B：目标部署模型，所有评测以此为准

### 5.3 模型切换原则

- 所有 pipeline 改造必须在 Qwen3 32B 上评测验证，不能只在强模型上通过就算完
- 开发过程中用免费 API 快速迭代，但每个里程碑必须切到 32B 跑评测
- prompt 设计面向 32B 能力水平（指令简洁、示例清晰、不依赖模型的世界知识）

---

## 六、下推引擎 — 架构摘要（PMC 主导）

> 详细设计见团队内部文档。此处只摘录与 DataAgent 对接相关的要点。

### 6.1 核心思路

在 StarRocks 外面建一层查询改写微服务，在 SQL 到达 StarRocks 之前完成下推决策、AST 改写、方言翻译，封装为 REMOTE_TABLE 调用。StarRocks 零修改。

### 6.2 处理流水线

```
用户 SQL → SQL 解析 + 源识别 → 下推规则引擎（查能力注册表）
→ 查询改写（AST 切分）→ 方言转换（L1 标准 SQL / L2 YAML / L3 Visitor）
→ REMOTE_TABLE 封装 → StarRocks 执行
```

### 6.3 MVP 验证场景

2 周 demo 聚焦 **Scenario A（单源聚合下推）**+ GaussDB 全查询路由。跨源 JOIN 作为架构演示。

### 6.4 DataAgent 侧的对接预留

DataAgent 不需要为下推引擎做任何特殊处理。只需保证：
1. 生成的 SQL 是合法的 StarRocks SQL（dry-run 验证已覆盖）
2. 表名/列名与 MDL 一致
3. 评测集的 SQL 可导出为 JSON，供下推引擎导入测试

Phase 2 对接（下推引擎就绪后）：
- DataAgent 读取下推引擎的 `capabilities.yaml`，在 SQL 生成时避免不支持的算子
- 下推引擎返回结构化错误时，DataAgent 可做针对性纠错

---

## 七、业界对标

### 7.1 NL2SQL

| 方向 | 代表工作 | 我们的位置 |
|------|---------|-----------|
| 评测标准 | Spider, BIRD | 三级判定 + 宽松 EX 是差异化指标 |
| Few-shot 选择 | DAIL-SQL (VLDB 2024) | 计划采用 question embedding + SQL 骨架多样性 |
| 问题分解 | DIN-SQL, DTS-SQL | Phase 2：Hard 题分解策略 |
| Schema Linking | RESDSQL, C3SQL | 工程化优先，LLM 兜底 |
| 小模型微调 | CodeS (StarCoder 15B) | 阶段性搁置，作为天花板不够时的后手 |
| 多候选投票 | MCS-SQL | Phase 2：多候选生成 + 一致性选择 |

### 7.2 联邦查询

| 方向 | 代表工作 | 我们的位置 |
|------|---------|-----------|
| 外挂式下推 | Dingo (VLDB 2025 Workshop) | 验证了引擎无关联邦下推的学术可行性 |
| Table Function | Trino query(), DuckDB postgres_query() | REMOTE_TABLE 的设计参考 |
| 聚合分解 | FlexPushdownDB (PVLDB 2021) | separable operators 概念 |

### 7.3 差异化

1. **NL2SQL + 联邦下推端到端闭环**，业界罕见
2. **电信领域真实 schema**（100+ 表 3500 列），不是通用 benchmark
3. **实验驱动**，每个决策有对照数据支撑
4. **工程驱动架构**，不依赖前沿模型能力

---

## 八、Roadmap

### Phase 1：Pipeline 改造（当前）

目标：将 LLM 调用从 4-7 次降到 1-2 次，token 消耗降 60%+，准确率不退步。

| 步骤 | 内容 | 验证标准 |
|------|------|---------|
| **T0** | Qwen3 32B 理想条件天花板实验 | 度量 20-30 题的理想条件准确率 |
| **T1** | 工程化 Schema Linking 替换 LLM 列选择 | Schema Linking Recall > 90% |
| **T2** | Few-shot 检索增强（embedding + 骨架多样性） | few-shot 相关度人工抽检 > 80% |
| **T3** | Prompt 精简重写（面向 32B 能力水平） | 同等输入下准确率不降 |
| **T4** | 删除意图分类 + 推理规划，合并进主 prompt | LLM 调用减到 1-2 次 |
| **T5** | 端到端评测（100 题，Qwen3 32B） | 宽松 EX ≥ 流水线 A 水平 |

### Phase 2：准确率提升

在 Phase 1 基础上，针对 Hard/ExtraHard 题目提升。

| 步骤 | 内容 |
|------|------|
| 查询模式模板 | 聚合/排名/趋势/对比/分布的 SQL 骨架 |
| 结构化知识注入 | 枚举值 + JOIN 路径，写入 DDL 注释 |
| 复杂查询分解 | Hard 题拆分为子查询分步生成 |
| 多候选投票 | 生成 3 个候选 SQL，选最一致的 |

### Phase 3：生产化

| 步骤 | 内容 |
|------|------|
| 100 表 Schema 扩展 | 验证 Schema Linking 在生产规模下的 Recall |
| 下推引擎对接 | 读取 capabilities.yaml，错误反馈闭环 |
| 微调评估 | 如果 Phase 1-2 天花板不够，用 LoRA 微调 32B |
| 性能优化 | 端到端延迟 < 10 秒 |

---

## 九、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Qwen3 32B 理想条件天花板过低 | 工程优化无法达标 | T0 实验提前暴露，及时切换到微调路线 |
| 工程化 Schema Linking Recall 不足 | 准确率天花板被卡住 | 保留轻量 LLM 兜底（可用更小模型如 8B） |
| 免费 API 限流影响开发节奏 | 迭代变慢 | 多个免费 API 轮换；关键验证用 32B |
| Pipeline 改造引入新 bug | 准确率回退 | 每步改造都跑评测集验证，不退步才进下一步 |
| 电信术语同义词覆盖不全 | Schema Linking 漏表 | 从评测集 bad case 中迭代补充术语表 |

---

## 十、成功标准

### Phase 1 完成标准

- [ ] 理想条件天花板实验完成，数字明确
- [ ] 单次查询 LLM 调用 ≤ 2 次
- [ ] 单次查询 token 消耗较当前降低 60%+
- [ ] 100 题评测宽松 EX ≥ 50%（流水线 A 水平）
- [ ] 每层指标可独立度量

### 长期目标

- 宽松 EX > 70%（工程 + 知识 + few-shot 的组合效果）
- 端到端延迟 < 10 秒（H100 + 32B）
- 100 表 Schema 下 Schema Linking Recall > 90%
