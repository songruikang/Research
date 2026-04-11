# 数据 Pipeline 动线

## 唯一源头

**`telecom/input/telecom_mdl.json`** — 整个系统的唯一 schema 定义。

包含：14 个表定义、356 个字段（名称/类型/主键/非空/中文描述）、29 条外键关系。
加表、改列、改描述、改关系，只改这一个文件。

---

## 目录结构

```
telecom/
├── input/                              # 输入（git 跟踪）
│   ├── telecom_mdl.json               #   ★ 唯一源头
│   └── nms_field_dictionary_full.csv   #   原始数据字典（归档，不再被代码引用）
│
├── output/                             # 生成文件（.gitignore，脚本自动产出）
│   ├── telecom_nms.duckdb             #   Step 1 产出
│   ├── telecom_init.sql               #   Step 2 产出
│   └── wren_ui_db.sqlite3             #   Step 3 临时文件
│
├── scripts/                            # 用户执行的脚本（按编号顺序）
│   ├── 1_generate_data.py             #   MDL → DDL → 建表 → mock 数据
│   ├── 2_export_init_sql.py           #   DuckDB → CSV + Init SQL
│   ├── 3_update_metadata.py           #   MDL → WrenAI 容器元数据
│   └── 4_refresh_timestamps.py        #   KPI 时间戳平移
│
├── _internal/                          # 内部模块（用户不需要关心）
│   ├── __init__.py
│   └── generate_mock_data.py          #   数据生成逻辑（被 1_generate_data.py 调用）
│
└── PIPELINE.md                         # 本文件

eval/                                   # 评测体系
├── eval_framework.py                   #   评测框架（输入 SQL → 执行 → 对比）
├── telecom_test_cases_100.json         #   100 道测试用例
├── exp0_opus_100q.json                 #   Opus 零知识基线生成的 SQL
└── eval_result_opus_100q.json          #   上次评测结果
```

---

## 脚本执行流水线

### Step 1: 生成数据库

```bash
python telecom/scripts/1_generate_data.py
```

| | |
|---|---|
| **输入** | `telecom/input/telecom_mdl.json` |
| **做什么** | 从 MDL 提取 DDL → 在 DuckDB 中建 14 张表 → 插入 21086 行 mock 数据（UUID 主键） |
| **输出** | `telecom/output/telecom_nms.duckdb` |
| **何时跑** | 首次、或 MDL 改了表结构、或需要全新数据 |

### Step 2: 导出 Init SQL

```bash
python telecom/scripts/2_export_init_sql.py
```

| | |
|---|---|
| **输入** | `telecom/output/telecom_nms.duckdb` |
| **做什么** | 每张表导出 CSV 到 `WrenAI/docker/data/` + 生成 56 行 Init SQL（DDL + `read_csv_auto`） |
| **输出** | `WrenAI/docker/data/*.csv`（14 个文件）+ `telecom/output/telecom_init.sql` |
| **何时跑** | Step 1 跑完后 |

### Step 3: WrenAI 导入（手动 + 脚本）

**3a. 手动：UI 导入表结构和数据**

1. 打开 http://localhost:3000
2. 选择 DuckDB
3. Display Name: `telecom_nms`
4. Init SQL: 粘贴 `telecom/output/telecom_init.sql` 的 56 行内容
5. Next → 全选 14 张表 → Submit
6. 等待 1-2 分钟建立 embedding 索引

**3b. 脚本：推送中文元数据**

```bash
python telecom/scripts/3_update_metadata.py
```

| | |
|---|---|
| **输入** | `telecom/input/telecom_mdl.json` + 运行中的 WrenAI 容器 |
| **做什么** | docker cp 拷出 SQLite → 写入中文描述/关系/主键 → 拷回 → 重启 wren-ui |
| **输出** | 容器内 SQLite 更新完成 |
| **注意** | 必须在 3a 完成后执行（容器里要有 SQLite 才能拷） |

> 脚本最后会尝试触发 deploy（重建向量索引）。如果超时失败不影响——手动在 UI 上点 Modeling → Deploy 即可。

**公司环境：** 容器名和 SQLite 路径可能不同，通过环境变量覆盖：
```bash
WREN_UI_CONTAINER=你的容器名 python telecom/scripts/3_update_metadata.py
```

### Step 4: 刷新时间戳（评测前）

```bash
python telecom/scripts/4_refresh_timestamps.py
```

| | |
|---|---|
| **输入** | `telecom/output/telecom_nms.duckdb` |
| **做什么** | 将 KPI 数据的 collect_time 平移到当前时间附近 |
| **输出** | `telecom_nms.duckdb` 原地更新 |
| **何时跑** | 每次评测前，确保"最近 7 天"等查询有数据 |
| **注意** | 只改本地 DuckDB，不影响 WrenAI 容器内的数据 |

### Step 5: 运行评测

```bash
python eval/eval_framework.py eval/exp0_opus_100q.json test
```

| | |
|---|---|
| **输入** | `telecom/output/telecom_nms.duckdb` + `eval/telecom_test_cases_100.json` + 生成的 SQL 文件 |
| **做什么** | 对每道题：执行生成 SQL + 执行期望 SQL → 对比结果集 → 三级判定（正确/错误/无法验证） |
| **输出** | 终端打印报告 + `eval/eval_result_xxx.json` |

---

## 修改场景速查

| 我要改什么 | 改哪里 | 重跑哪些步骤 |
|-----------|--------|-------------|
| 加一张表 | MDL + `_internal/generate_mock_data.py`（加数据生成逻辑） | 1 → 2 → 3a → 3b |
| 给已有表加一列 | MDL + `_internal/generate_mock_data.py` | 1 → 2 → 3a → 3b |
| 只改中文描述或关系 | MDL | 只跑 3b |
| 改 mock 数据量/分布 | `_internal/generate_mock_data.py` | 1 → 2，如已导入需 3a → 3b（清库重来） |
| 只跑评测 | 不改 | 4 → 5 |
| 加测试用例 | `eval/telecom_test_cases_100.json` | 5 |

---

## 全量清库重来

当需要完全重新初始化 WrenAI 时：

```bash
# 1. 停止并删除所有数据卷
cd WrenAI/docker && docker compose -f docker-compose-dev.yaml down -v

# 2. 重新生成数据
cd ../..
python telecom/scripts/1_generate_data.py
python telecom/scripts/2_export_init_sql.py

# 3. 重新启动
cd WrenAI/docker && docker compose -f docker-compose-dev.yaml up -d

# 4. UI 导入 + 元数据（Step 3a + 3b）
```

---

## 废弃文件

| 文件 | 原用途 | 现状 |
|------|--------|------|
| `nms_field_dictionary_full.csv` | 原始 schema CSV | 归档到 input/，不再被代码引用 |
| `csv_to_ddl.py` | CSV → DDL 转换 | 删除，DDL 改从 MDL 生成 |
