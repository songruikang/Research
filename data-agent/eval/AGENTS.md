# 评测系统使用指南

> 本文件是 AI Agent 和人类共用的操作手册。切换 session 后读这个文件恢复上下文。

---

## 一、目录结构

```
eval/
├── AGENTS.md                    # 本文件
├── telecom_test_cases_100.json  # 源数据：100题评测集（提交）
├── few_shot_pairs.json          # 源数据：43条few-shot示例（提交）
│
├── scripts/                     # 脚本（提交）
│   ├── generate_sqls.py         #   生成 prompt（6组配置）
│   ├── generate_with_llm.py     #   调用 LLM API 生成 SQL（用于非 Claude Code 环境）
│   ├── eval_framework.py        #   SQL 执行 + 多维评分引擎
│   ├── run_eval.py              #   评测 + 报告
│   ├── run_all.py               #   一键评测（生成 prompt + 评测 + 报告）
│   └── verify_few_shot.py       #   few-shot SQL dry-run 验证
│
├── results/                     # 实验产出（提交）
│   ├── all_sqls.json            #   所有实验的 SQL（唯一文件）
│   └── report_{YYYYMMDD_HHMM}.md  # 评测报告（带时间戳）
│
└── .generated/                  # 脚本生成物（不提交、不删除）
    ├── prompts_*.json           #   generate_sqls.py 生成
    ├── eval_results_*.json      #   run_eval.py 生成（每题详细评分）
    ├── few_shot_embeddings.json #   few-shot embedding 缓存
    ├── full_ddl.sql             #   generate_sqls.py 生成
    └── questions_only.json      #   generate_sqls.py 生成
```

### 文件分类规则

| 类别 | 提交到 git | 说明 |
|------|-----------|------|
| 源数据 | ✅ | 评测集、few-shot 库。人工审核过，不可自动复现 |
| 脚本 | ✅ | scripts/*.py。评测逻辑的唯一源头 |
| LLM 产出 | ✅ | all_sqls.json。LLM 非确定性，重跑结果不同，保留作为实验快照 |
| 报告 | ✅ | .md 报告。人可读的实验结论 |
| 脚本生成物 | ❌ | prompts、详细结果 JSON、embedding 缓存等。跑脚本即可恢复 |

---

## 二、脚本使用

### 一键评测（最常用）

```bash
# 评测 all_sqls.json 中所有实验，输出报告
python eval/scripts/run_all.py

# 先重新生成 prompt 再评测
python eval/scripts/run_all.py --regen

# 只评测指定实验（按索引）
python eval/scripts/run_all.py --exp 0 4 8
```

### 分步操作

```bash
# Step 1: 生成 prompt（6组配置 → .generated/prompts_*.json）
python eval/scripts/generate_sqls.py

# Step 2a: 用 Claude Code sub-agent 生成 SQL（Mac 本地）
#   → 见下方「SQL 生成方式」章节

# Step 2b: 用 LLM API 生成 SQL（公司环境 / 其他模型）
python eval/scripts/generate_with_llm.py \
  --model openai/qwen3-32b \
  --api-base http://10.220.239.55:8000/v1 \
  --prompt-config E \
  --label "Qwen3-32B + Few-shot"

# Step 3: 评测 + 报告
python eval/scripts/run_eval.py              # 全部
python eval/scripts/run_eval.py --exp 0 4    # 指定实验

# 验证 few-shot SQL 可执行性
python eval/scripts/verify_few_shot.py
```

### 脚本输入输出一览

| 脚本 | 输入 | 输出 |
|------|------|------|
| `generate_sqls.py` | `telecom_test_cases_100.json` + `few_shot_pairs.json` + MDL | `.generated/prompts_*.json` (6个) |
| `generate_with_llm.py` | `.generated/prompts_{config}.json` + LLM API | `results/all_sqls.json`（追加） |
| `run_eval.py` | `results/all_sqls.json` + `telecom_test_cases_100.json` + DuckDB | `.generated/eval_results_*.json` + `results/report_*.md` |
| `run_all.py` | 同上 | 同上（组合调用） |
| `verify_few_shot.py` | `few_shot_pairs.json` + DuckDB | 终端输出 pass/fail |

---

## 三、SQL 生成方式

### 方式 A：Claude Code Sub-Agent（Mac 本地）

不调外部 API，直接用 Claude Code 的 Agent 工具派 sub-agent 生成。

**操作步骤：**
1. 跑 `generate_sqls.py` 生成 prompt 文件
2. 派 sub-agent 读取 prompt 文件，逐题生成 SQL
3. 将结果合并追加到 `results/all_sqls.json`

**Sub-Agent Prompt 模板：**

```
你是一个电信网络管理系统的 SQL 专家。你的任务是根据给定的 prompt 为每道题生成一条 SQL。

步骤：
1. 读取 prompt 文件（如 .generated/prompts_fullschema_fewshot.json）
2. 对指定范围的题目（如 Q01-Q50），读取 user_prompt 字段
3. 根据 prompt 中的 DATABASE SCHEMA、SQL SAMPLES、QUERY PATTERN 和 QUESTION 生成 SQL

SQL 要求：
- 只生成一条 SQL，标准 SQL 语法
- 表名和列名严格按 Schema 中的定义
- 适当使用 ORDER BY 使结果有意义
- 浮点数用 ROUND() 保留合理精度
- 不要用 SELECT *，明确列出需要的列
- SQL 末尾加分号
- 参考 SQL SAMPLES 中的写法风格，但不要照搬

输出格式：JSON，key 为题号，value 为 SQL 字符串。
```

**并行策略：** 每 50 题一个 agent，每个配置独立一组，跑完合并到 all_sqls.json。

### 方式 B：LLM API 脚本（公司环境 / 其他模型）

用 `generate_with_llm.py` 调用 OpenAI 兼容 API 或 Ollama。

```bash
# Qwen3 32B（公司 H100，vLLM 部署）
python eval/scripts/generate_with_llm.py \
  --model openai/qwen3-32b \
  --api-base http://10.220.239.55:8000/v1 \
  --prompt-config E \
  --label "Qwen3-32B + Few-shot"

# Ollama 本地模型
python eval/scripts/generate_with_llm.py \
  --model ollama/qwen3:8b \
  --prompt-config E \
  --label "Qwen3-8B test"

# 调试：只跑 10 题
python eval/scripts/generate_with_llm.py \
  --model ollama/qwen3:8b \
  --prompt-config E \
  --label "debug" \
  --range Q01-Q10
```

脚本自动追加到 `all_sqls.json`，完成后提示下一步的 `run_eval.py` 命令。

---

## 四、实验配置

### Prompt 配置（generate_sqls.py 生成）

| 配置 | Schema 策略 | Few-shot | 知识注入 | 对应 prompt 文件 |
|------|------------|----------|---------|-----------------|
| A | 全量 14 表 | 无 | 无 | prompts_fullschema_no_knowledge.json |
| B | 全量 14 表 | 无 | 有 | prompts_fullschema_with_knowledge.json |
| C | Schema Linking ~6 表 | 无 | 无 | prompts_schemalink_no_knowledge.json |
| D | Schema Linking ~6 表 | 无 | 有 | prompts_schemalink_with_knowledge.json |
| E | 全量 14 表 | Top-3 | 无 | prompts_fullschema_fewshot.json |
| F | 全量 14 表 | Top-3 | 有 | prompts_fullschema_fewshot_knowledge.json |

### Few-shot 检索方式

当前使用 DAIL-SQL 风格检索：**TF-IDF 加权相似度 + SQL 骨架多样性重排**。
- Step 1: 对问题做 TF-IDF 加权关键词匹配，取 top-10 候选
- Step 2: 用 sqlglot 提取 SQL 骨架，贪心选择结构最不同的 top-3
- 如果 Ollama 可用，自动使用 nomic-embed-text embedding 替代 TF-IDF（当前实验显示 TF-IDF 对中文领域更优）
- Ollama 不可用时自动 fallback 到关键词匹配

### SQL 文件格式（`results/all_sqls.json`）

```json
{
  "experiments": [
    {
      "label": "全量Schema 无知识",       // 实验标签，也是 sqls 中的 key
      "model": "claude-opus-4-6",        // 模型
      "schema": "full",                  // "full" 或 "schemalink"
      "few_shot": false,                 // 是否有 few-shot
      "knowledge": false,                // 是否有知识注入
      "generated_at": "2026-04-16"       // 生成日期
    }
  ],
  "sqls": {
    "Q01": {
      "全量Schema 无知识": "SELECT ... ;",
      "全量Schema + Few-shot": "SELECT ... ;"
    }
  }
}
```

新增实验时：在 experiments 追加配置，每题的字典追加新 label 对应的 SQL。

---

## 五、Few-shot 示例库维护

### 当前状态

`few_shot_pairs.json`：43 条 (question, SQL) 对，覆盖 10 种 SQL 骨架模式和 13 个领域概念。含 3 条二级聚合示例（FS41-43）。

### 生成方法：双 Agent 信息隔离

为防止与评测集过拟合，few-shot 示例通过两个 agent 生成，第二个 agent 看不到评测原题。

**Agent 1（分析器）Prompt：**

```
你是一个 SQL 分析专家。分析评测集，产出模式总结。

输入：MDL 文件 + 评测集
输出：三层总结，写入 .generated/query_pattern_summary.md

关键约束：输出不能包含任何原始题目的具体问题文本或完整 SQL。

第一层 SQL 骨架分类：按结构类型分类（单表过滤、双表JOIN+聚合、CTE等），每类统计数量和典型子句模式。
第二层 高频表组合：哪些表经常一起 JOIN，按频率排序。不写具体 WHERE 条件。
第三层 领域概念清单：涉及的业务场景（设备管理、SLA监控等），每个标注涉及的表。不写具体问题。
```

**Agent 2（生成器）Prompt：**

```
你是一个电信领域 NL2SQL 专家。生成高质量 (question, SQL) 示例对。

输入：MDL 文件 + Agent 1 的模式总结
约束：不能读取评测集文件（telecom_test_cases_100.json）

输出格式：
[
  {"id": "FS01", "question": "中文问题", "sql": "SELECT ...;", "pattern": "骨架类型", "tables": ["表名"]}
]

质量标准：
- 表名/列名/枚举值严格与 MDL 一致
- question 要自然，像运维工程师的真实提问
- 避免同一查询只换过滤值
- 覆盖不同 SQL 骨架（单表过滤、JOIN+聚合、CTE、窗口函数等）
```

### 更新流程

1. 修改 Agent 2 的 prompt 或覆盖要求
2. 依次跑 Agent 1 → Agent 2
3. 跑 `python eval/scripts/verify_few_shot.py` 验证 SQL 可执行性
4. 人工审核语义正确性
5. 更新 `few_shot_pairs.json`

---

## 六、评分体系

### 判定标准

| 判定 | 含义 |
|------|------|
| correct | 行数相同，且值匹配（精确匹配 / 列交集匹配 / 值子集匹配，三级递进） |
| wrong | 行数不同，或值不匹配 |
| error | SQL 执行失败 |
| unverifiable | 双方均返回 0 行，无法判断 |

**三级匹配机制（代码中依次尝试）：**
1. **精确匹配**：值元组集合完全一致
2. **列交集匹配**：取两侧共有列名，只比交集列的值（共有列值必须完全一致）
3. **值子集匹配**：一侧值为另一侧子集（兜底，列完全不同时）

### 三种准确率指标

| 指标 | 计算方式 | 说明 |
|------|---------|------|
| 严格匹配 | 精确匹配通过数 / 总数 | 最保守，列名+值+行数全部相同 |
| 子集匹配 | (精确+子集)通过数 / 总数 | 容忍列多/少 |
| 列交集匹配 | (精确+交集+子集)通过数 / 总数 | 最宽松，只比共有列 |

### 多维组件评分（5 维度）

| 维度 | 权重 | 说明 |
|------|------|------|
| 表选择 | 15% | 是否选了正确的表 |
| 列选择 | 20% | 返回的列是否匹配 |
| WHERE 条件 | 30% | 过滤条件是否正确 |
| JOIN | 15% | JOIN 关系是否正确 |
| 聚合 | 20% | GROUP BY / ORDER BY / HAVING 等 |

---

## 七、历史实验结果

| 索引 | 日期 | 配置 | 严格匹配 | 子集匹配 | 列交集匹配 | 关键发现 |
|------|------|------|---------|---------|-----------|---------|
| 0 | 2026-04-16 | 全量 无知识 | 12% | 41% | 73% | 基线 |
| 1 | 2026-04-16 | 全量 有知识 | 13% | 42% | 72% | 知识注入对强模型无效 |
| 2 | 2026-04-16 | Schema Linking 无知识 | 5% | 17% | 36% | 列裁剪过激 |
| 3 | 2026-04-16 | Schema Linking 有知识 | 11% | 36% | 58% | 知识在弱 schema 下有效 |
| 4 | 2026-04-18 | 全量 + Few-shot | 18% | 52% | 77% | few-shot 最有效单一优化 |
| 5 | 2026-04-18 | 全量 + Few-shot + 知识 | 23% | 50% | 75% | few-shot + 知识组合 |
| 6 | 2026-04-18 | 全量 + Few-shot + 列知识 | — | 45% | 76% | 列知识注入负优化，已回退 |
| 7 | 2026-04-18 | 全量 + Few-shot(43) + 领域约定 | — | — | 67% | 领域约定注入负优化(-7pp)，已回退 |
| 8 | 2026-04-18 | DAIL Few-shot(TF-IDF+骨架多样性) | — | — | 76% | 多维评分改善，EX 持平 |
| 9 | 2026-04-18 | DAIL Few-shot(Embedding+骨架多样性) | — | — | 73% | nomic 通用模型不如 TF-IDF |

### 关键结论

1. **对 Opus 级强模型，任何形式的显式规则/知识注入都是负优化**（实验 1/6/7 全部退步）
2. **唯一有效的提升手段是 few-shot 示例**（实验 4 vs 0：子集匹配 +11pp）
3. **few-shot 检索方式对 EX 准确率影响不大**（关键词/TF-IDF/Embedding 在 73-75% 区间）
4. **TF-IDF+骨架多样性在多维评分上最优**，作为默认检索方案
5. **知识注入对弱 schema（Schema Linking）有效**（实验 3 vs 2：+24pp），可能对弱模型也有效
6. **剩余 24-26% 错误为真逻辑错误**（二级聚合、JOIN 类型、复杂公式），需靠多候选投票或 SQL 纠错循环解决

---

## 八、公司环境复测指南

### 环境准备

```bash
# 公司 Ubuntu 机器
pip install duckdb sqlglot pyyaml

# 如果用 vLLM 部署 Qwen3 32B
# 确保 API 在 http://10.220.239.55:8000/v1 可访问
```

### 一键复测流程

```bash
# 1. 生成 prompt
python eval/scripts/generate_sqls.py

# 2. 用 Qwen3 32B 生成 SQL（配置 E = 全量 + Few-shot，效果最好的配置）
python eval/scripts/generate_with_llm.py \
  --model openai/qwen3-32b \
  --api-base http://10.220.239.55:8000/v1 \
  --prompt-config E \
  --label "Qwen3-32B + Few-shot"

# 3. 评测（上一步完成后会提示实验索引）
python eval/scripts/run_eval.py --exp <索引>

# 或者一步评测所有已有实验
python eval/scripts/run_all.py
```
