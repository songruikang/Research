# NL2SQL 语义层：行业实践洞察与本项目定位

> 2026-04-27 | 基于行业调研 + 本项目 10 组实验数据

## 一、行业格局

### 谁在做，怎么做

| 厂商 | 产品 | 语义层形态 | NL2SQL 策略 | 公开成绩 |
|------|------|-----------|------------|---------|
| Databricks | Unity Catalog + AI/BI Genie | Catalog 元数据 + Knowledge Store（同义词/示例SQL/指令） | 全量上下文注入 + Trusted Assets 精确匹配 | RLVR 32B 模型 BIRD 75.68% |
| Snowflake | Cortex Analyst | YAML 语义模型（Facts/Dimensions/Metrics/Relationships） | 多模型动态选择（Claude/GPT/Arctic/Mistral/Llama） | Arctic-Text2SQL 32B BIRD 73.84% |
| Cube.dev | Cube Semantic Layer | 业务指标/维度/关系定义 | Meta API → 向量化 → RAG 检索 → LLM 生成 Cube Query（非原生 SQL） | 无公开数据 |
| dbt | Semantic Layer + MetricFlow | YAML 语义模型（Entities/Dimensions/Measures） | 作为上下文供下游 AI 工具消费 | 无公开数据 |
| WrenAI | MDL + Context Engine | MDL 定义模型/关系/计算字段/视图 | RAG pipeline（4-7 次 LLM 调用） | 号称"10x 准确"，无具体数字 |
| Defog | SQLCoder | 无独立语义层，靠模型微调 | 15B 微调模型，schema-specific fine-tuning | 匹配 GPT-4（特定 schema） |

### 行业共识与分歧

**共识：**
- 语义层的载体正在收敛为 **YAML/JSON 定义文件**（Snowflake YAML、dbt YAML、WrenAI MDL），版本化管理，代码即配置
- 维护责任归数据团队（谁写 transform 谁写语义层），业务方贡献描述和术语
- 32B 是本地部署 Text-to-SQL 的甜区（Databricks / Snowflake / 多家中国团队的 BIRD 榜单成绩集中在 73-76%）

**分歧：**
- Cube.dev 认为 LLM 不应该直接写 SQL，应该生成语义 API 调用——这从根本上消除了幻觉但牺牲了灵活性
- Defog 认为微调比语义层更直接——对固定 schema 有效，但不适合 schema 频繁变更的场景
- Google VLDB 2025 论文认为长 context 模型可以暴力塞入更多原始 schema——弱化了 Schema Linking 的必要性

---

## 二、语义层的真实 ROI

### 学术基准

| 基准 | 特点 | 当前最佳 | 人类水平 |
|------|------|---------|---------|
| Spider 1.0 | 干净 schema、学术场景 | 91.2%（MiniSeek） | ~95% |
| BIRD | 真实脏 schema、需要外部知识 | 81.95%（AskData Agent） | 92.96% |

BIRD 专门测试外部知识的价值。**排行榜前列几乎全部使用了外部知识**，知识/无知识系统的差距约 5-15pp。

### 最关键的一篇论文：Sequeda et al. 2023

- 场景：保险行业企业数据库，列名晦涩（`col_a1`、`tbl_x2`）
- GPT-4 裸跑：**16%**
- GPT-4 + 知识图谱本体层：**54%**
- **3.4 倍提升**

### 我们的实验数据

- 场景：电信 NMS，14 表 ~200 列，列名语义清晰（`cpu_usage_avg_pct`、`oper_status`）
- Opus 裸跑：**82%**
- Opus + 知识注入：**86%**（±5pp 噪声范围内）
- Opus + Few-shot + 知识：**87%**

### 结论

**语义层的 ROI 与 schema 质量成反比。**

| schema 质量 | 语义层 ROI | 典型场景 |
|------------|-----------|---------|
| 晦涩命名（`col_a1`） | 极高（3.4x） | 遗留企业系统 |
| 一般命名 + 复杂关系 | 中等（+5-15pp） | BIRD 基准 |
| 语义清晰命名 | 边际（±5pp 噪声内） | 我们的电信 NMS |

我们的电信 schema 命名规范、关系明确，模型自身就能理解——这解释了为什么知识注入对我们无效。**但这个结论只在 14 表全量注入成立。**

---

## 三、Schema Linking：不是知识问题，是工程瓶颈

### 行业做法

| 方法 | 思路 | 效果 | 代表 |
|------|------|------|------|
| Embedding 检索 | 问题向量 → 最近邻表/列 | 快但精度不够（同义词、隐式关联丢失） | Cube.dev、WrenAI |
| 关键词 + 规则 | TF-IDF / 同义词表 / 表关系图 | 稳定但僵化 | 传统方案 |
| LLM 自选表 | 给压缩 schema 让模型自己选 | 准确但多一次 LLM 调用 | PET-SQL（两阶段） |
| Agent 多步 | 专门的 Schema Selector Agent | CHESS: +2% 准确率 + 5x token 缩减 | CHESS、MAC-SQL |
| 不做 Linking | 长 context 暴力塞全量 | 对小 schema 可行 | Google VLDB 2025 |

### 学术亮点

- **CHESS（2024）**：四 Agent 框架，其中 Schema Selector 单独负责裁剪。结果：BIRD 71.10%，LLM 调用减少 83%。**这是 Schema Linking 作为独立环节的最清晰 ROI 证据。**
- **PET-SQL（2024）**：先生成粗略 SQL → 从中提取涉及的实体 → 重新 Linking 到精简 schema → 再生成精确 SQL。Spider 87.6%。核心洞察：**让模型自己做第一轮 Linking，比外部检索更准。**
- **VLDB 2025（Google）**：长 context LLM 直接塞更多原始信息，不做精细裁剪也能保持准确率。暗示：**随着 context 窗口增长，Schema Linking 的必要性会递减。**

---

## 四、建设成本

### 语义层搭建成本

| 方案 | 表规模 | 搭建周期 | 维护者 | 适用场景 |
|------|--------|---------|--------|---------|
| 最小化（表/列描述） | 10-20 表 | 2-5 天 | 数据工程师 | 概念验证 |
| 标准化（描述+关系+指标） | 50-100 表 | 2-4 周 | 数据工程师 + 领域专家 | 中型部署 |
| 完整（+术语表+示例SQL+同义词） | 100+ 表 | 1-3 月 | 数据团队 + 业务分析师 | 生产环境 |
| dbt 集成（已有 dbt 项目） | 任意 | 1-2 周增量 | 现有 dbt 维护者 | dbt 用户 |

### 最大的隐性成本：schema 漂移

- 每次 DDL 变更（新增列、改表名）都需要同步更新语义层
- 业务逻辑变更（KPI 定义调整、计算规则修改）需要人工审核
- **这是所有厂商都未真正解决的问题**——Snowflake 和 dbt 把它推给用户，Databricks 用 Knowledge Store 做局部覆盖

---

## 五、与本项目的交叉分析

### 我们已经验证的

| 结论 | 我们的数据 | 行业对应 |
|------|-----------|---------|
| 强模型裸跑即可达 80%+ | Opus 82%（全量 14 表） | Spider 86%+（GPT-4, 干净 schema） |
| 知识注入边际有限 | ±5pp 噪声 | VLDB 2025: 长 context 暴力塞也行 |
| Few-shot 是最稳定提升 | +3-5pp | DAIL-SQL: 示例选择是最高 ROI |
| TF-IDF ≈ Embedding | 74% vs 74% | CodeS: 小模型也能靠 schema 特征检索 |
| Schema Linking 裁多了就崩 | 全量 82% vs SL 58% | CHESS: Linking 错误直接决定天花板 |

### 我们尚未验证的

| 问题 | 为什么重要 | 行业参考 |
|------|-----------|---------|
| 100+ 表场景下模型自选表是否可靠 | 决定是否需要外部 Schema Linking | PET-SQL 证明模型自选 > 外部检索 |
| Qwen 32B 在裁剪后 schema 上的表现 | 弱模型可能更依赖精准上下文 | Databricks/Snowflake 32B 在 BIRD 73-76% |
| 多候选投票 / 自校正的增益 | 天花板突破的关键手段 | CHESS: 验证环节减少错误 |
| 电信 NMS 100+ 表的 schema 质量 | 决定语义层 ROI 高低 | Sequeda: 差 schema 受益 3.4x |

---

## 六、洞察与判断

### 1. "语义层"被过度营销，核心价值只有两个

- **对差 schema 的翻译层**：列名晦涩时，描述和术语表是刚需（Sequeda 3.4x）
- **对大 schema 的裁剪入口**：100+ 表塞不下 context 时，结构化元数据是 Schema Linking 的索引基础

我们的电信 schema 命名规范，所以第一个价值不大。**但第二个价值随表规模增长会变成刚需。**

### 2. Schema Linking 的技术路线应该跟随模型能力演进

当前行业有三条路：
- **外部检索**（embedding / TF-IDF）：成熟但精度有限，我们已验证
- **模型自选**（两阶段 LLM 调用）：PET-SQL 证明有效，我们未验证
- **不做 Linking**（长 context 暴力塞）：Google VLDB 2025 方向，取决于模型 context 窗口和推理能力

随着 Qwen 后续版本 context 窗口增长（32K → 128K → 1M），第三条路的可行性会持续提升。**但当前 Qwen 32B 的 32K context 不支持 100+ 表全量注入。**

### 3. 32B 本地部署的天花板已被行业确认

Databricks RLVR 32B（BIRD 75.68%）和 Snowflake Arctic 32B（BIRD 73.84%）证明 32B 是本地部署 Text-to-SQL 的务实选择。我们的 Qwen 32B 在电信领域 69%（有执行率拖累），修复语法问题后预计 75-78%，与行业水平一致。

### 4. 天花板突破需要复合策略，不是单一技术

BIRD 排行榜从 73%（单模型）到 82%（Agent 系统）的 9pp 差距，来自：
- 多 Agent 分工（CHESS: Retriever + Selector + Generator + Tester）
- 执行验证 + 自校正循环
- 多候选投票（Self-consistency）

**没有哪个单一技术能跨越这个 gap。**

---

## 七、对本项目两个研究课题的启示

### 课题一：规模剪裁（14 表 → 100+ 表）

行业数据支持**两阶段 LLM 方案**（PET-SQL 思路）作为优先验证方向：
1. 第一次调用：压缩 schema（表名+列名列表） → 模型选表
2. 第二次调用：选中表的完整 DDL + Few-shot → 生成 SQL

验证成本低（改 prompt 配置 + 跑两轮），如果模型自选表的召回率 > 95%，则不需要复杂的外部检索 pipeline。

**风险点**：Qwen 32B 作为弱模型，自选表能力可能不如 Opus。需要实验确认。

### 课题二：天花板突破（87% → 90%+）

参考 CHESS 框架，最直接的收益来自**执行验证环节**：
- 生成 SQL → DuckDB 执行 → 报错则带错误信息重试
- 这一层直接修复 Qwen 的 12% 执行失败 + 部分逻辑错误
- WrenAI 已有 `sql_correction` pipeline 可复用

**但更深层的天花板突破（复杂聚合、多表交叉条件）尚无行业通用解法，属于开放研究问题。**
