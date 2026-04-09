# NL2SQL / DataAgent 领域全景：痛点、方法与工程实践

> 写给有一定基础的中级研究者，聚焦"怎么做能上线"而不只是"论文怎么写"。

---

## 一、评测基准：你的系统到底算好还是不好？

### 1.1 Spider (2018) → Spider 2.0 (2024)

**Spider 1.0**（Yale, 2018）是 NL2SQL 领域的 ImageNet。200 个数据库、10,181 个问题，按 SQL 复杂度分 Easy/Medium/Hard/Extra Hard。

**问题**：Spider 太"干净"了。数据库小（平均 5 张表），没有脏数据，没有模糊表述，和真实场景差距很大。当前 SOTA 已经刷到 91%+，但拿到真实业务上准确率可能只有 40-50%。

**Spider 2.0**（ICLR 2025 Oral）是回应这个问题的：
- 632 个真实企业级任务
- 数据库来自 BigQuery、Snowflake 等真实系统
- 单个数据库可能有 **1000+ 列**（和你的场景很像）
- 需要理解数据库文档、方言差异、跨库查询
- **o1-preview 只解决了 21.3% 的任务**（vs Spider 1.0 的 91.2%）

**对你的意义**：Spider 2.0 的设定和你的电信场景更接近——大 schema、专业领域、复杂查询。不要被 Spider 1.0 上的高分迷惑，那个基准已经不能代表真实难度了。

> 论文：Can Language Models Resolve Real-World Enterprise Text-to-SQL Workflows?
> 代码：https://github.com/xlang-ai/Spider2

### 1.2 BIRD (2023)

**BIRD**（Big Bench for Large-Scale Database Grounded Text-to-SQL）是目前最被认可的"中等难度"基准。

- 12,751 个 QA 对，95 个数据库，37 个专业领域
- 总数据量 33.4 GB（不是玩具数据）
- 引入了 **Evidence**（外部知识提示），模拟真实场景中用户会给额外上下文
- 新指标 **VES（Valid Efficiency Score）**：不只看 SQL 对不对，还看执行效率

**当前 BIRD 排行榜（2025）**：

| 排名 | 方法 | 执行准确率 (EX) | 特点 |
|------|------|----------------|------|
| 1 | Distillery + GPT-4o | ~72% | 蒸馏+规划 |
| 2 | CHASE-SQL | ~71% | 多候选+自验证 |
| 3 | ExSL + Granite | ~70% | Schema Linking 强化 |
| 4 | MCS-SQL | ~68% | 多选择校正 |
| 5 | MAC-SQL | ~65% | 多 Agent 协作 |

**关键发现**：排行榜前几名清一色是 **multi-step / multi-agent** 方案，没有一个是"一次生成就完事"的。

> 论文：Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQL
> 网站：https://bird-bench.github.io/

### 1.3 其他值得关注的基准

| 基准 | 特点 | 适用场景 |
|------|------|---------|
| **SParC** | 多轮对话 SQL | 你未来要做追问/多轮交互 |
| **CoSQL** | 对话式 SQL + 澄清 | 用户问题不清晰时的交互策略 |
| **KaggleDBQA** | 真实 Kaggle 数据 | 脏数据、异构 schema |
| **SEDE** | Stack Exchange 真实 SQL | 复杂嵌套查询 |
| **Dr.Spider** | 对抗性扰动 | 测试鲁棒性（同义词替换、schema 变化） |

---

## 二、核心痛点与解决方案

### 痛点 1：Schema 太大，LLM 装不下

**问题描述**：

你的场景是 100 张表、每表 ~35 列、共 ~3500 列。全量 DDL 约 52K tokens。加上 prompt 模板和 few-shot，轻松超过 60K tokens。即使 Claude 有 200K context，塞这么多也会导致：
- LLM "注意力稀释"，对关键信息的关注度下降
- 成本高昂
- 延迟不可接受

**业界方案对比**：

#### 方案 A：Schema Linking（最主流）

**核心思想**：先判断问题涉及哪些表和列，只传相关的部分给 LLM。

**RESDSQL**（阿里 DAMO, 2023）提出了 ranking + skeleton 解耦方法：
1. 训练一个小模型（T5-base）做 schema 排序，给每张表/每列打相关性分数
2. 只取 top-K 的表和列
3. 再用大模型生成 SQL

```
用户问题: "查询华为PE设备的CPU利用率"
  → Schema Ranker 输出:
    t_network_element: 0.95 (有 vendor, role)
    t_ne_perf_kpi: 0.92 (有 cpu_usage_avg_pct)
    t_site: 0.35 (无直接关联)
    t_board: 0.20 (无关)
    ...
  → 取 top-5 表传给 SQL 生成模型
```

**对你的启发**：你不需要训练一个专门的模型，但 Schema Linking 的分层检索思路可以用更简单的方式实现（关键词匹配 + embedding 兜底，我们在技术指引里已经设计了）。

> 论文：RESDSQL: Decoupling Schema Linking and Skeleton Parsing for Text-to-SQL (AAAI 2023)

#### 方案 B：Schema 压缩

**PURPLE**（2024）提出了一种激进的压缩方式：不传 DDL，传"伪 SQL"——把 schema 信息编码成 SQL 注释格式，比 DDL 短 40-60%：

```
-- 压缩前 (DDL)
CREATE TABLE t_network_element (
  ne_id VARCHAR PRIMARY KEY COMMENT '网元唯一标识',
  ne_name VARCHAR COMMENT '网元名称',
  vendor VARCHAR COMMENT '厂商。取值: HUAWEI;ZTE;CISCO;JUNIPER;NOKIA',
  ...31 列
);

-- 压缩后 (PURPLE 风格)
-- t_network_element: ne_id(PK), ne_name, vendor[HUAWEI|ZTE|CISCO|JUNIPER|NOKIA],
--   role[PE|P|RR|ASBR], oper_status[UP|DOWN|DEGRADED], site_id->t_site.site_id, ...
```

**对你的启发**：我们可以设计一种专门针对电信 schema 的压缩格式，在不丢失关键信息的前提下，把 52K tokens 压缩到 15-20K。

#### 方案 C：动态 Schema（Agent 驱动）

**XiYan-SQL**（2024，阿里通义）让 Agent 自己决定需要什么表：

```
Agent 第一轮: "根据问题，我需要 t_network_element 和 t_ne_perf_kpi"
系统: [只返回这两张表的 DDL]
Agent 第二轮: "我还需要 t_site 来获取省份信息"
系统: [追加 t_site 的 DDL]
Agent 第三轮: 生成 SQL
```

优点是 LLM 自己判断需要什么，比静态检索更灵活。缺点是多轮调用增加延迟和成本。

---

### 痛点 2：SQL 生成准确率不够

**问题描述**：

即使给了正确的表和列，LLM 生成的 SQL 仍然经常出错。常见错误类型：

| 错误类型 | 占比 | 举例 |
|---------|------|------|
| **Schema Linking 错误** | ~35% | 选错表/列、用了不存在的列 |
| **JOIN 条件错误** | ~20% | JOIN 方向反了、漏了 JOIN |
| **值匹配错误** | ~15% | `'huawei'` vs `'HUAWEI'`，`'正常'` vs `'UP'` |
| **聚合逻辑错误** | ~15% | GROUP BY 遗漏列、错误的聚合函数 |
| **SQL 方言错误** | ~10% | MySQL 语法在 DuckDB 里不能用 |
| **业务逻辑错误** | ~5% | 理解了字面意思但理解错了业务含义 |

**业界方案**：

#### 方案 A：多候选 + 投票（Self-Consistency）

**CHASE-SQL**（2024）生成多个候选 SQL，然后通过执行结果投票选最优：

```
问题: "查华为PE设备"
  → 候选 1: SELECT * FROM t_network_element WHERE vendor='HUAWEI' AND role='PE'
  → 候选 2: SELECT * FROM t_network_element WHERE vendor='Huawei' AND role='PE'
  → 候选 3: SELECT ne_id, ne_name FROM t_network_element WHERE vendor='HUAWEI' AND role='PE'

  执行结果:
  → 候选 1: 返回 8 行 ✓
  → 候选 2: 返回 0 行 ✗ (大小写错误)
  → 候选 3: 返回 8 行 ✓

  投票: 候选 1 和 3 结果一致 → 选候选 1（更完整）
```

**代价**：生成 N 个候选 = N 次 LLM 调用。通常 N=3~5。

**优化**：用 `temperature > 0` 一次生成 N 个，只需 1 次 API 调用（利用 `n` 参数）。但 DeepSeek 等部分模型不支持 `n > 1`。

#### 方案 B：自纠错 Agent（最实用）

**MAC-SQL**（2024, BIRD 榜单前列）的核心是 Multi-Agent Collaboration：

```
Agent 1 (Selector): 选择相关表和列
Agent 2 (Decomposer): 把复杂问题拆成子问题
Agent 3 (Refiner): 执行 SQL，检查结果，自动修正

举例 - 你的 Q15（健康评分）:
  Decomposer:
    子问题 1: 找出所有 GOLD VPN
    子问题 2: 获取每个 VPN 的 SLA 指标
    子问题 3: 计算评分

  Refiner:
    第一次生成 → 执行 → 发现 sla_latency_met 是 BOOLEAN 不是 INTEGER → 修正为 CASE WHEN
    第二次生成 → 执行 → 结果合理 → 返回
```

**对你的启发**：MAC-SQL 的 Decomposer 对你的复杂查询（Q10 趋势环比、Q12 单点故障、Q15 健康评分）特别有价值。简单查询不需要分解，但复杂查询的"先拆后合"策略能显著提升准确率。

> 论文：MAC-SQL: A Multi-Agent Collaborative Framework for Text-to-SQL
> 代码：https://github.com/wbbeyourself/MAC-SQL

#### 方案 C：执行反馈驱动（最可靠）

**DIN-SQL**（2023）和后续的改进工作都强调一个核心理念：**不要只做 dry run，要真执行，看结果**。

```
传统方式（WrenAI）:
  生成 SQL → dry run 检查语法 → 语法对了就返回
  问题: 语法对但语义错的 SQL 检测不出来

执行反馈驱动:
  生成 SQL → 真执行 → 检查结果:
    - 空结果？可能是过滤条件错误
    - 结果数量异常多？可能是 JOIN 条件遗漏
    - 包含 NULL？可能是 LEFT JOIN 问题
    - 数值范围异常？可能是字段选错
  → 如果异常，带着结果反馈让 LLM 修正
```

**实际例子**：
```
问题: "查询过去24小时CPU利用率超过80%的网元"
第一次 SQL: SELECT * FROM t_ne_perf_kpi WHERE cpu_usage_avg_pct > 80
执行结果: 9600 行（全部数据，没有时间过滤！）
反馈: "SQL 返回 9600 行，似乎缺少时间过滤条件"
第二次 SQL: SELECT * FROM t_ne_perf_kpi
            WHERE cpu_usage_avg_pct > 80
            AND collect_time >= CURRENT_TIMESTAMP - INTERVAL 24 HOUR
执行结果: 12 行 ✓
```

---

### 痛点 3：领域知识缺失

**问题描述**：

通用 LLM 不懂你的业务。它不知道：
- "PE" 是 Provider Edge 路由器，不是体育课
- "GOLD VPN" 的 SLA 时延要求是 50ms
- `oper_status = 'UP'` 才是"正常运行"
- 时间字段 `collect_time` 的粒度是 15 分钟

这是 NL2SQL 从实验室到生产环境最大的 gap。

**业界方案**：

#### 方案 A：Few-shot In-Context Learning（最快见效）

**DAIL-SQL**（2023）系统研究了 few-shot 选择策略，发现：

1. **相似问题优于随机选择**：用与当前问题最相似的 QA 对做示例，准确率提升 5-10%
2. **包含相似 SQL 模式的示例更重要**：如果当前问题需要 GROUP BY，示例中也有 GROUP BY 的效果最好
3. **5 个示例是最佳数量**：多了反而降低准确率（信息过载）

```
最优 few-shot 选择策略:
  1. 问题相似度 (40% 权重): NL 语义相似
  2. SQL 结构相似度 (40% 权重): 涉及的表、JOIN 模式、聚合方式
  3. 难度匹配 (20% 权重): 简单问题配简单示例，复杂配复杂
```

> 论文：DAIL-SQL: Efficient Few-Shot Text-to-SQL with Optimized Demonstration Selection
> 代码：https://github.com/BeachWang/DAIL-SQL

#### 方案 B：Domain Glossary（枚举值映射）

**CHESS**（2024, BIRD 排行榜前列）特别强调了 **Evidence** 的作用——给 LLM 提供领域知识线索：

```
没有 Evidence:
  问题: "查询GOLD级别VPN的SLA达标情况"
  LLM 可能生成: WHERE level = 'gold'  ← 错！列名和值都错

有 Evidence:
  Evidence: "VPN 等级字段是 service_level，取值 GOLD/SILVER/BRONZE。SLA 达标字段是 sla_overall_met (BOOLEAN)。"
  问题: "查询GOLD级别VPN的SLA达标情况"
  LLM 生成: WHERE service_level = 'GOLD' AND sla_overall_met = true  ← 对
```

BIRD 基准发现，**加了 Evidence 后准确率平均提升 10-15%**。

**对你的启发**：你的 `domain_glossary.yaml`（技术指引中设计的术语映射表）本质就是 CHESS 的 Evidence。这不是锦上添花，而是 **必需品**。

#### 方案 C：指令微调（长期方案）

**SQLCoder**（Defog, 2023-2024）在 CodeLlama/StarCoder 基础上做了 SQL 专项微调：

- SQLCoder-7B 在 BIRD 上超过了 GPT-3.5
- SQLCoder-70B 在部分任务上接近 GPT-4
- 推理成本只有 API 的 1/100

**微调数据来源**：
1. 公开基准（Spider, BIRD 训练集）
2. 合成数据（用 GPT-4 从 schema 生成 QA 对）
3. 用户反馈数据（生产中用户纠正的 SQL）

**对你的启发**：当你的 few-shot 示例库积累到 500+ 对时，可以考虑微调一个电信领域的 SQL 模型。在此之前，用通用大模型 + 领域知识注入更实际。

> 代码：https://github.com/defog-ai/sqlcoder

---

### 痛点 4：复杂查询的准确率断崖

**问题描述**：

简单查询（单表过滤）准确率可以到 90%+，但一旦涉及：
- 多表 JOIN（3 张表以上）
- 嵌套子查询
- 窗口函数
- 时间计算（同比、环比）
- 条件聚合（CASE WHEN + GROUP BY）

准确率会直接掉到 30-50%。你的 Q10（趋势环比）、Q12（单点故障）、Q15（健康评分）都是这类。

**业界方案**：

#### 方案 A：查询分解（Query Decomposition）

**DIN-SQL** 提出的 "Decompose + Solve" 策略：

```
原始问题: "为每条GOLD级VPN业务计算健康评分（时延达标+25分...）"

分解:
  Step 1: 找出所有 GOLD 级 VPN
    → SELECT vpn_id, vpn_name FROM t_l3vpn_service WHERE service_level = 'GOLD'

  Step 2: 获取每个 VPN 的最新 SLA 指标
    → SELECT vpn_id, sla_latency_met, sla_jitter_met, sla_loss_met, sla_availability_met
      FROM t_vpn_sla_kpi WHERE ...

  Step 3: 合并计算评分
    → SELECT v.vpn_name,
             (CASE WHEN k.sla_latency_met THEN 25 ELSE 0 END +
              CASE WHEN k.sla_jitter_met THEN 25 ELSE 0 END + ...) as health_score
      FROM ... JOIN ...

最终 SQL: 合并 Step 1-3 为一条完整查询
```

#### 方案 B：查询模板 + 槽位填充

对于业务中反复出现的查询模式，预定义模板比每次重新生成更可靠：

```yaml
# 模板: KPI 趋势对比
template: |
  WITH current_period AS (
    SELECT {group_col}, AVG({kpi_col}) as current_avg
    FROM {kpi_table}
    WHERE collect_time >= {current_start} AND collect_time < {current_end}
    GROUP BY {group_col}
  ),
  previous_period AS (
    SELECT {group_col}, AVG({kpi_col}) as previous_avg
    FROM {kpi_table}
    WHERE collect_time >= {previous_start} AND collect_time < {previous_end}
    GROUP BY {group_col}
  )
  SELECT c.{group_col}, c.current_avg, p.previous_avg,
         c.current_avg - p.previous_avg as change
  FROM current_period c
  JOIN previous_period p ON c.{group_col} = p.{group_col}

# LLM 的任务简化为: 识别问题属于"KPI 趋势对比"模板，填入正确的槽位
# 而不是从零生成整条复杂 SQL
```

**对你的启发**：电信领域的查询模式相对固定（设备过滤、KPI 统计、SLA 分析、拓扑查询、趋势对比）。把这些模式模板化，LLM 只需要做"模式识别 + 槽位填充"，比从零生成简单得多。

---

### 痛点 5：工程化落地

**问题描述**：

论文里的方法在基准测试上效果好，但真正部署到生产环境时会遇到一堆论文不讨论的问题。

#### 5.1 延迟

| 方案 | 延迟 | 原因 |
|------|------|------|
| 单次 LLM 调用 | 2-5 秒 | 可接受 |
| 多 Agent 协作 | 10-30 秒 | 3-5 次 LLM 调用串行 |
| 多候选 + 投票 | 5-15 秒 | 并行调用但等最慢的 |
| 微调小模型 | 0.5-2 秒 | 最快 |

**实际权衡**：用户能接受 5 秒等待，很难接受 30 秒。所以 MAC-SQL 式的多 Agent 方案虽然准确率高，但延迟可能不可接受。

**推荐策略**：分层调度
```
简单查询（预估 <3 秒）→ 单次调用
中等查询（预估 3-8 秒）→ 单次调用 + 执行验证 + 必要时纠错
复杂查询（预估 >8 秒）→ 告知用户"正在分析复杂查询"+ 查询分解
```

#### 5.2 缓存策略

**完全匹配缓存**：相同问题直接返回历史 SQL（命中率低但零成本）。

**语义缓存**：相似问题复用 SQL 模板，只替换参数。

```
历史: "查询北京的华为PE设备" → SQL: ... WHERE city='北京' AND vendor='HUAWEI' AND role='PE'
新问题: "查询上海的中兴PE设备"
语义匹配: 同模式，替换参数
→ SQL: ... WHERE city='上海' AND vendor='ZTE' AND role='PE'
```

**实现**：Vanna.ai 的训练机制本质就是语义缓存——每次成功的 QA 对都存起来，下次优先匹配。

#### 5.3 错误恢复

生产环境的用户不会像你一样看 trace 日志。系统需要：

1. **友好的错误提示**：不是 `column 'xxx' not found`，而是"我在数据库中没有找到您提到的'xxx'字段，您是否指的是 yyy？"
2. **降级策略**：LLM 生成失败时，推荐相似的历史查询
3. **人工兜底**：提供 SQL 编辑界面让用户自己改（你已经做了 SQL Query 页面）

#### 5.4 安全性

NL2SQL 系统如果不做防护，用户可能通过自然语言注入：
- "删除所有数据" → `DROP TABLE`
- "查询所有用户密码" → 数据泄露

**必须做的**：
1. SQL 白名单：只允许 SELECT，禁止 DROP/DELETE/UPDATE/INSERT
2. 敏感字段过滤：某些列不允许出现在查询结果中
3. 行级权限：根据用户角色限制可查询的数据范围

---

## 三、值得深读的论文（按优先级排序）

### 第一梯队：必读（直接影响你的架构设计）

| # | 论文 | 年份 | 为什么读它 |
|---|------|------|-----------|
| 1 | **A Survey of NL2SQL in the Era of LLMs** | 2024 (TKDE 2025) | 最全面的综述，覆盖 prompt engineering、fine-tuning、评测方法、错误分析。**先读这篇建立全局观** |
| 2 | **MAC-SQL: Multi-Agent Collaborative Framework** | 2024 | BIRD 排行榜前列，Selector-Decomposer-Refiner 三 Agent 协作架构，**你的复杂查询需要这种思路** |
| 3 | **DAIL-SQL: Efficient Few-Shot Text-to-SQL** | 2023 (EMNLP) | few-shot 选择策略的系统研究，**直接指导你的 few-shot 示例库设计** |
| 4 | **BIRD: Big Bench for Large-Scale Database Grounded Text-to-SQL** | 2023 (NeurIPS) | 当前最主流的评测基准，理解 Evidence 机制，**你的术语映射表设计参考** |
| 5 | **Spider 2.0** | 2024 (ICLR 2025) | 企业级真实场景评测，**校准你对准确率的预期** |

> 综述 arxiv: https://arxiv.org/abs/2408.05109
> MAC-SQL: https://arxiv.org/abs/2402.04845
> DAIL-SQL: https://arxiv.org/abs/2308.15363
> BIRD: https://arxiv.org/abs/2305.03111
> Spider 2.0: https://arxiv.org/abs/2411.07763

### 第二梯队：按需深入

| # | 论文 | 年份 | 解决什么问题 |
|---|------|------|-------------|
| 6 | **CHASE-SQL: Multi-Path Reasoning and Preference Optimized Candidate Selection** | 2024 | 多候选+自验证策略，BIRD SOTA 之一 |
| 7 | **CHESS: Contextual Harnessing for Efficient SQL Synthesis** | 2024 | Evidence/领域知识注入的最佳实践 |
| 8 | **DIN-SQL: Decomposed In-Context Learning** | 2023 | 查询分解的经典方法，Schema Linking + Classification + SQL Generation 解耦 |
| 9 | **RESDSQL: Decoupling Schema Linking and Skeleton Parsing** | 2023 (AAAI) | Schema Linking 单独训练的开山之作 |
| 10 | **CodeS: Natural Language to Code Repository via Multi-Layer Sketch** | 2024 | 在真实 code repo 场景下做 SQL 生成，比单纯 NL2SQL 更接近 DataAgent |

> CHASE-SQL: https://arxiv.org/abs/2410.01943
> CHESS: https://arxiv.org/abs/2405.16755
> DIN-SQL: https://arxiv.org/abs/2304.11015
> RESDSQL: https://arxiv.org/abs/2302.05965
> CodeS: https://arxiv.org/abs/2402.16347

### 第三梯队：特定方向参考

| # | 论文 | 方向 | 什么时候需要 |
|---|------|------|-------------|
| 11 | **SQLCoder** (Defog) | 微调 SQL 模型 | 当你积累了 500+ QA 对想微调时 |
| 12 | **Dr.Spider** | 鲁棒性测试 | 想评估系统对同义词、拼写错误的容忍度 |
| 13 | **C3: Zero-Shot Text-to-SQL with ChatGPT** | Prompt 工程 | 纯 prompt 方案的上限在哪里 |
| 14 | **XiYan-SQL** (阿里通义) | 多 Agent + 中文 | 中文场景的 NL2SQL 参考 |
| 15 | **DB-GPT** (蚂蚁) | DataAgent 平台 | 更完整的 DataAgent 产品形态参考 |

> SQLCoder: https://github.com/defog-ai/sqlcoder
> Dr.Spider: https://arxiv.org/abs/2301.08881
> C3: https://arxiv.org/abs/2307.07306
> XiYan-SQL: https://arxiv.org/abs/2411.08599
> DB-GPT: https://github.com/eosphoros-ai/DB-GPT

---

## 四、开源项目速览

| 项目 | Star | 定位 | 核心能力 | 适合你参考什么 |
|------|------|------|---------|-------------|
| **Vanna.ai** | 12K+ | NL2SQL 框架 | RAG + 训练 + 多 DB 支持 | few-shot 训练机制、反馈闭环 |
| **DB-GPT** | 14K+ | DataAgent 平台 | 多 Agent + 知识库 + 可视化 | Agent 编排、知识管理 |
| **WrenAI** | 3K+ | GenBI 平台 | 语义层 + RAG + SQL 生成 | 你已经深度体验了 |
| **SQLChat** | 4K+ | SQL 聊天界面 | 简单的 NL2SQL + 对话 | UI/UX 设计参考 |
| **Dataherald** | 3K+ | NL2SQL API | RAG + 训练 + 评测 | 评测框架设计 |
| **Text2SQL Awesome List** | 5K+ | 论文/项目合集 | 持续更新的资源列表 | 跟踪最新进展 |

> Vanna: https://github.com/vanna-ai/vanna
> DB-GPT: https://github.com/eosphoros-ai/DB-GPT
> Awesome LLM Text2SQL: https://github.com/DEEP-PolyU/Awesome-LLM-based-Text2SQL
> NL2SQL Handbook: https://github.com/HKUSTDial/NL2SQL_Handbook

---

## 五、给你的建议路线图

基于以上分析，你的 DataAgent 应该分阶段吸收这些技术：

### 现在（Phase 1）：扎实基础

```
重点读: 综述论文 (#1) + DAIL-SQL (#3) + BIRD (#4)
核心实现:
  ✅ 领域术语表 (借鉴 CHESS 的 Evidence)
  ✅ Few-shot 示例选择 (借鉴 DAIL-SQL 的策略)
  ✅ 单次生成 + 执行验证 + 纠错 (基础 Agent 循环)
  ✅ 自动化评测框架 (借鉴 BIRD 的 EX + VES 指标)
目标: 15 个测试用例 85%+ 准确率
```

### 近期（Phase 2）：提升复杂查询

```
重点读: MAC-SQL (#2) + DIN-SQL (#8)
核心实现:
  ✅ 查询复杂度分级 + 分层调度
  ✅ 复杂查询分解 (借鉴 MAC-SQL 的 Decomposer)
  ✅ 查询模板库 (电信领域固定模式)
  ✅ 多候选 + 执行结果验证 (借鉴 CHASE-SQL)
目标: 50 个测试用例 80%+ 准确率
```

### 中期（Phase 3）：100 表生产化

```
重点读: RESDSQL (#9) + Spider 2.0 (#5) + CHASE-SQL (#6)
核心实现:
  ✅ 高效 Schema Linking (关键词 + embedding 两级)
  ✅ 条件 Column Pruning
  ✅ Schema 压缩格式
  ✅ 语义缓存 + 反馈闭环
  ✅ 安全防护
目标: 100 表场景，200 个测试用例 75%+ 准确率
```

### 远期（Phase 4）：可选进阶

```
  □ 微调电信领域 SQL 模型 (借鉴 SQLCoder)
  □ 多轮对话 (借鉴 SParC/CoSQL)
  □ 自动异常检测 + 报告生成
  □ 知识图谱增强
```

---

## 六、一句话总结

**NL2SQL 的核心挑战不是"LLM 能不能写 SQL"——它能。挑战是"怎么让它在 100 张表、3500 个字段、用户用模糊的中文描述的情况下，稳定地写出正确的 SQL"。答案是：精准的 Schema Linking + 丰富的领域知识 + 执行验证驱动的 Agent 循环 + 持续的反馈积累。**
