# Telecom NMS NL2SQL DataAgent

电信网管系统 NL2SQL 研究项目。基于 WrenAI 二次开发，包含评测框架和语义层工具。

## 目录结构

```
data-agent/
├── telecom/                           # 电信语义层（核心）
│   ├── input/                         #   输入源文件
│   │   └── telecom_mdl.json          #     ★ 唯一 schema 定义
│   ├── output/                        #   生成文件（.gitignore）
│   ├── scripts/                       #   按编号顺序执行的脚本
│   │   ├── 1_generate_data.py        #     MDL → DuckDB
│   │   ├── 2_export_init_sql.py      #     DuckDB → CSV + Init SQL
│   │   ├── 3_update_metadata.py      #     MDL → WrenAI 容器
│   │   └── 4_refresh_timestamps.py   #     KPI 时间戳平移
│   ├── _internal/                     #   内部模块（不需要直接运行）
│   └── PIPELINE.md                    #   完整数据流水线文档
│
├── eval/                              # 评测体系
│   ├── eval_framework.py              #   评测框架（三级判定）
│   ├── telecom_test_cases_100.json    #   100 道测试用例
│   ├── exp0_opus_100q.json            #   Opus 基线 SQL
│   └── eval_result_opus_100q.json     #   评测结果
│
├── docs/                              # 研究文档
│   ├── NL2SQL_Research_Landscape.md   #   领域全景分析
│   ├── DataAgent_Technical_Guide.md   #   二次开发技术指引
│   └── NL2SQL_100Q_TestReport.md      #   100 题评测报告
│
├── WrenAI/                            # WrenAI 源码（git submodule）
│   ├── docker/
│   │   ├── docker-compose.yaml        #   Mac 部署（官方镜像）
│   │   ├── docker-compose-dev.yaml    #   公司云主机部署（本地 build）
│   │   ├── .env.cloud                 #   公司环境变量模板
│   │   ├── config.yaml.cloud          #   公司 AI Service 配置模板
│   │   ├── deploy-cloud.sh            #   公司一键部署脚本
│   │   └── trace_callback.py          #   LLM 调用追踪回调
│   └── wren-ui/
│       ├── Dockerfile                 #   Mac 构建
│       └── Dockerfile.cloud           #   公司构建（代理环境）
│
└── README.md
```

## 快速开始

### 纯评测（不需要 Docker）

```bash
git clone --recursive git@github.com:songruikang/Research.git
cd Research/data-agent

uv venv --python 3.11 && source .venv/bin/activate
uv pip install duckdb pytz numpy

python telecom/scripts/1_generate_data.py
python telecom/scripts/4_refresh_timestamps.py
python eval/eval_framework.py eval/exp0_opus_100q.json test
```

### WrenAI 部署

详见 `telecom/PIPELINE.md` 的 Step 1-4。

**Mac 环境：**
```bash
# 构建 UI + AI Service
cd WrenAI/wren-ui && docker build -t wren-ui-custom:latest .
cd ../../wren-ai-service && docker build -t wrenai-wren-ai-service:latest -f docker/Dockerfile .

# 启动
cd ../docker && docker compose up -d
```

**公司云主机环境：**
```bash
cp WrenAI/docker/.env.cloud WrenAI/docker/.env
cp WrenAI/docker/config.yaml.cloud WrenAI/docker/config.yaml
bash WrenAI/docker/deploy-cloud.sh rebuild
```

## 数据 Pipeline

所有数据操作围绕 4 个编号脚本，详见 [`telecom/PIPELINE.md`](telecom/PIPELINE.md)：

```
Step 1: python telecom/scripts/1_generate_data.py      # MDL → DuckDB
Step 2: python telecom/scripts/2_export_init_sql.py     # DuckDB → CSV + Init SQL
Step 3: UI 粘贴 Init SQL + python telecom/scripts/3_update_metadata.py
Step 4: python telecom/scripts/4_refresh_timestamps.py  # 评测前刷新时间
```

## 配置说明

### `.env` 关键变量

| 变量 | Mac | 公司 | 说明 |
|------|-----|------|------|
| `PLATFORM` | `linux/arm64` | `linux/amd64` | CPU 架构 |
| `OPENAI_API_KEY` | 真实 key | `sk-local-placeholder` | 本地 Ollama 不需要 |
| `ENABLE_RECOMMENDATION_QUESTIONS` | `true` | `false` | 本地大模型慢必须关 |
| `TELEMETRY_ENABLED` | `false` | `false` | 遥测 |

### `config.yaml` 关键配置

| 配置 | Mac | 公司 |
|------|-----|------|
| LLM model | `openai/gpt-4o` | `ollama_chat/qwen3:32b` |
| LLM api_base | 不需要 | `http://10.220.239.55:11434` |
| Embedder model | `openai/text-embedding-3-small` | `openai/bge-m3` |
| Embedder api_base | 不需要 | `http://10.220.239.55:11434/v1` |
| embedding_model_dim | 1536 | 1024 |

### Pipeline 开关（config.yaml settings 段）

| 开关 | 默认 | 说明 |
|------|------|------|
| `allow_intent_classification` | `false` | 意图分类，多 1 次 LLM 调用 |
| `allow_sql_generation_reasoning` | `false` | SQL 推理链，多 1 次 LLM 调用 |
| `enable_column_pruning` | `true` | 列裁剪 |
| `max_sql_correction_retries` | `1` | SQL 纠错重试 |
| `logging_level` | `INFO` | 调试改 `DEBUG` |

## Docker 速查

| 改了什么 | 操作 |
|---------|------|
| `.env` / `config.yaml` 的模型或开关 | `docker compose restart wren-ai-service` |
| `ENABLE_RECOMMENDATION_QUESTIONS` | `docker compose up -d wren-ui` |
| `trace_callback.py` | `docker compose restart wren-ai-service` |
| 前端代码 | 重建镜像 + `docker compose up -d wren-ui` |
| `data/*.csv` | 全量清库：`docker compose down -v && docker compose up -d` |

## LLM Trace

`trace_callback.py` 以 sitecustomize.py 挂载到 ai-service，拦截所有 LLM 调用写入 `data/llm_traces.jsonl`。
数据导入到 SQLite 的 `trace_query` / `trace_step` 表（migration 在 wren-ui 启动时自动执行）。

**Logs 页面：** http://localhost:3000/logs 查看追踪记录。

清空：`> WrenAI/docker/data/llm_traces.jsonl`
