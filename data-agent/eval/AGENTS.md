# 评测系统使用指南

> 本文件是 AI Agent 和人类共用的操作手册。切换 session 后读这个文件恢复上下文。

---

## 一、目录结构

```
eval/
├── AGENTS.md                    # 本文件
├── telecom_test_cases_100.json  # 源数据：100题评测集（提交）
├── few_shot_pairs.json          # 源数据：40条few-shot示例（提交）
│
├── scripts/                     # 脚本（提交）
│   ├── generate_sqls.py         #   生成6组prompt配置
│   ├── eval_framework.py        #   SQL执行+多维评分引擎
│   ├── run_eval.py              #   一键评测+报告生成
│   └── verify_few_shot.py       #   few-shot SQL dry-run验证
│
├── results/                     # 实验产出（提交）
│   ├── all_sqls.json            #   所有实验的 SQL（唯一文件）
│   └── report_{YYYYMMDD_HHMM}.md  # 评测报告（带时间戳）
│
└── .generated/                  # 脚本生成物（不提交、不删除）
    ├── prompts_*.json           #   generate_sqls.py 生成
    ├── eval_results_{YYYYMMDD_HHMM}.json  # run_eval.py 生成（每题详细评分）
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
| 脚本生成物 | ❌ | prompts、详细结果 JSON 等。跑脚本即可恢复，体积大 |

---

## 二、评测流程

### 完整流程（新增实验）

```
Step 1: 生成 prompt
  python eval/scripts/generate_sqls.py
  → .generated/prompts_*.json（6组配置）

Step 2: 用 sub-agent 生成 SQL
  见下方「SQL 生成 Prompt」章节
  → 合并到 results/all_sqls.json

Step 3: 评测 + 报告
  python eval/scripts/run_eval.py
  → .generated/eval_results_{YYYYMMDD_HHMM}.json（详细）
  → results/report_{YYYYMMDD_HHMM}.md（报告）
```

### 快捷操作

```bash
# 评测全部实验组
python eval/scripts/run_eval.py

# 只跑指定实验（按索引）
python eval/scripts/run_eval.py --exp 0 4 5

# 验证 few-shot SQL 可执行性
python eval/scripts/verify_few_shot.py
```

---

## 三、实验配置

| 索引 | Schema 策略 | Few-shot | 知识注入 | 说明 |
|------|------------|----------|---------|------|
| 0 | 全量 14 表 | 无 | 无 | 基线 |
| 1 | 全量 14 表 | 无 | 有 | 测试知识注入效果 |
| 2 | Schema Linking ~6 表 | 无 | 无 | 测试表选择效果 |
| 3 | Schema Linking ~6 表 | 无 | 有 | 表选择 + 知识 |
| 4 | 全量 14 表 | Top-3 | 无 | 测试 few-shot 效果 |
| 5 | 全量 14 表 | Top-3 | 有 | few-shot + 知识 |

### SQL 文件格式（`results/all_sqls.json`）

```json
{
  "experiments": [
    {
      "label": "全量Schema 无知识",       // 实验标签，也是 sqls 中的 key
      "model": "claude-opus-4-6",        // 生成 SQL 的模型
      "schema": "full",                  // "full" = 全量14表, "schemalink" = 精简~6表
      "few_shot": false,                 // 是否注入 few-shot 示例
      "knowledge": false,                // 是否注入领域知识
      "generated_at": "2026-04-16"       // 生成日期
    }
  ],
  "sqls": {
    "Q01": {
      "全量Schema 无知识": "SELECT ne_id, ne_name ... ;",
      "全量Schema + Few-shot": "SELECT ne_id, ne_name ... ;"
    }
  }
}
```

**字段说明：**
- `experiments`：数组，每个元素描述一组实验的配置。`label` 是唯一标识
- `sqls`：每个题号下用 `label` 作为 key 关联对应实验的 SQL，一目了然
- `run_eval.py` 通过 experiments 的数组索引选择要评测的组

**新增实验的操作：**
1. 用 `generate_sqls.py` 生成 prompt
2. 用 sub-agent 生成 SQL
3. 在 `all_sqls.json` 的 `experiments` 追加新配置，每题的字典追加新 label 对应的 SQL
4. 跑 `run_eval.py` 评测

---

## 四、SQL 生成 Prompt

### 方式：Claude Code Sub-Agent

不调外部 API，直接用 Claude Code 的 Agent 工具派 sub-agent 生成 SQL。

### System Prompt（SQL 生成）

每个 sub-agent 收到的指令：

```
你是一个电信网络管理系统的 SQL 专家。你的任务是根据给定的 prompt 为每道题生成一条 SQL。

步骤：
1. 读取 prompt 文件（如 .generated/prompts_fullschema_fewshot.json）
2. 对指定范围的题目（如 Q01-Q50），读取 user_prompt 字段
3. 根据 prompt 中的 DATABASE SCHEMA、SQL SAMPLES、QUERY PATTERN、DOMAIN KNOWLEDGE 和 QUESTION 生成 SQL

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

### 并行策略

100 题拆成多个 sub-agent 并行：
- 每个 agent 处理 50 题（Q01-Q50、Q51-Q100）
- 每个配置独立一组 agent
- 跑完后合并到 `results/all_sqls.json`

---

## 五、Few-shot 示例库维护

### 当前状态

`few_shot_pairs.json`：40 条 (question, SQL) 对，覆盖 10 种 SQL 骨架模式和 13 个领域概念。

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
你是一个电信领域 NL2SQL 专家。生成 40 个高质量 (question, SQL) 示例对。

输入：MDL 文件 + Agent 1 的模式总结
约束：不能读取评测集文件（telecom_test_cases_100.json）

输出格式：
[
  {"id": "FS01", "question": "中文问题", "sql": "SELECT ...;", "pattern": "骨架类型", "tables": ["表名"]}
]

覆盖要求（40 题分配）：
- 单表简单过滤 5 题、单表聚合 3 题、双表JOIN+过滤 3 题
- 双表JOIN+聚合 10 题、多表JOIN 8 题、CTE 5 题
- 窗口函数 3 题、CASE WHEN 2 题、子查询 1 题

质量标准：
- 表名/列名/枚举值严格与 MDL 一致
- question 要自然，像运维工程师的真实提问
- 避免同一查询只换过滤值
```

### 更新流程

1. 修改 Agent 2 的 prompt 或覆盖要求
2. 依次跑 Agent 1 → Agent 2
3. 跑 `python eval/scripts/verify_few_shot.py` 验证 SQL 可执行性
4. 人工审核语义正确性
5. 更新 `few_shot_pairs.json`

---

## 六、评分体系

### 判定标准（对齐 BIRD EX）

| 判定 | 含义 |
|------|------|
| correct | 行数相同，且值集合一致或存在子集关系（列差异不影响判定） |
| wrong | 行数不同，或值集合不匹配 |
| error | SQL 执行失败 |
| unverifiable | 双方均返回 0 行，无法判断 |

**列差异处理：** 列名不同不影响 correct/wrong 判定，只作为诊断信息。这与 BIRD/Spider 的 EX 标准对齐——题目不指定返回列时，多返回或少返回列不算逻辑错误。

### 多维组件评分（5 维度）

| 维度 | 权重 | 说明 |
|------|------|------|
| 表选择 | 15% | 是否选了正确的表 |
| 列选择 | 20% | 返回的列是否匹配 |
| WHERE 条件 | 30% | 过滤条件是否正确 |
| JOIN | 15% | JOIN 关系是否正确 |
| 聚合 | 20% | GROUP BY / ORDER BY / HAVING 等 |

### 关键指标

- **准确率(EX)** = correct / 总数（与 BIRD 基准可比）
- **准确率(可验证)** = correct / (总数 - unverifiable)（排除 0 行无法验证的题）
- 列差异保留在多维评分的"列选择"维度中，作为辅助诊断

---

## 七、历史实验结果

| 索引 | 日期 | 配置 | EX 准确率 | 关键发现 |
|------|------|------|----------|---------|
| 0 | 2026-04-16 | 全量 无知识 | 41% | 基线 |
| 1 | 2026-04-16 | 全量 有知识 | 42% | 知识注入效果微弱 |
| 2 | 2026-04-16 | Schema Linking 无知识 | 17% | 列裁剪过激 |
| 3 | 2026-04-16 | Schema Linking 有知识 | 36% | 知识部分弥补裁剪损失 |
| 4 | 2026-04-18 | 全量 + Few-shot | 52% | few-shot +11pp，最有效单一优化 |
| 5 | 2026-04-18 | 全量 + Few-shot + 知识 | 50% | few-shot+知识组合，Hard 题最强 |
