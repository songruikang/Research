# Telecom NMS NL2SQL DataAgent

电信网管系统 NL2SQL 研究项目。基于 WrenAI 二次开发，包含评测框架和语义层工具。

## 目录结构

```
data-agent/
├── docs/                              # 研究文档
│   ├── NL2SQL_Research_Landscape.md   #   领域全景分析
│   ├── DataAgent_Technical_Guide.md   #   二次开发技术指引
│   └── NL2SQL_100Q_TestReport.md      #   100题评测报告
│
├── eval/                              # 评测体系
│   ├── eval_framework.py              #   评测框架（三级判定）
│   ├── refresh_timestamps.py          #   时间戳刷新脚本
│   ├── telecom_test_cases_100.json    #   100道测试用例
│   ├── exp0_opus_100q.json            #   Opus零知识基线SQL
│   └── eval_result_opus_100q.json     #   评测结果
│
├── telecom/                           # 电信语义层
│   ├── telecom_mdl.json               #   MDL定义（14表/356字段/29关系）
│   ├── generate_mock_data.py          #   Mock数据生成器
│   ├── csv_to_ddl.py                  #   CSV→DDL转换（被generate_mock_data调用）
│   └── scripts/
│       ├── export_init_sql.py         #   导出 Init SQL + CSV
│       └── update_wren_metadata.py    #   导入中文元数据到WrenAI
│
├── WrenAI/                            # WrenAI源码（git submodule）
│   ├── docker/
│   │   ├── docker-compose.yaml        #   搜索 [自定义] 看改动
│   │   ├── .env                       #   ★ 必改：PLATFORM、API Key
│   │   ├── config.yaml                #   ★ 必改：LLM模型、Embedding
│   │   └── data/                      #   CSV数据文件（volume挂载到容器）
│   └── wren-ui/                       #   UI源码（有Trace日志改动）
│
├── README.md                          # 本文件
├── PROJECT_CONTEXT.md                 # 发给AI助手的项目背景
├── pyproject.toml
└── .gitignore
```

### 不在 git 中、需要生成的文件

| 文件 | 生成命令 | 说明 |
|------|---------|------|
| `telecom_nms.duckdb` | `cd telecom && python generate_mock_data.py` | 14表mock数据 |
| `WrenAI/docker/data/*.csv` | `python telecom/scripts/export_init_sql.py` | 容器挂载的CSV |
| `telecom_init.sql` | 同上 | 56行Init SQL |
| `.venv/` | `uv venv --python 3.11` | Python虚拟环境 |
| `wren-ui-custom:latest` | `docker build -t wren-ui-custom:latest WrenAI/wren-ui/` | 自定义UI镜像 |

---

## 一、纯评测部署（不需要Docker）

```bash
git clone --recursive git@github.com:songruikang/Research.git
cd Research/data-agent

# Python环境
uv venv --python 3.11
source .venv/bin/activate          # Linux/Mac
# .venv\Scripts\activate           # Windows
uv pip install duckdb pytz

# 生成数据库
cd telecom && python generate_mock_data.py && cd ..

# 刷新时间戳（让KPI数据覆盖"最近7天"等查询）
python eval/refresh_timestamps.py

# 跑评测
python eval/eval_framework.py eval/exp0_opus_100q.json "opus_baseline"
```

---

## 二、WrenAI Docker 部署

### 2.1 构建自定义 UI 镜像

```bash
cd WrenAI/wren-ui
docker build -t wren-ui-custom:latest .
cd ../docker
```

### 2.2 配置文件（★ 必改项）

#### `.env` 文件必改项

```bash
cp .env.example .env    # 如果没有就从下面模板创建
```

| 变量 | 必改？ | 说明 | 示例 |
|------|--------|------|------|
| `PLATFORM` | **是** | Mac ARM填 `linux/arm64`，x86服务器填 `linux/amd64` | `linux/amd64` |
| `OPENAI_API_KEY` | **是** | LLM API Key（OpenAI/DeepSeek通用） | `sk-xxx` |
| `GENERATION_MODEL` | 建议改 | UI显示用的模型名 | `gpt-4o` |
| `HOST_PORT` | 看需要 | UI对外端口 | `3000` |
| `AI_SERVICE_FORWARD_PORT` | 看需要 | AI Service对外端口 | `5555` |
| `TELEMETRY_ENABLED` | 建议关 | 遥测上报 | `false` |
| `PLATFORM` | **公司环境必改** | Mac是arm64，公司Ubuntu通常是amd64 | - |

#### `config.yaml` 文件必改项

config.yaml 控制 LLM 模型和 Embedding，是最核心的配置。

```yaml
# ===== 第1段：LLM 配置 =====
type: llm
provider: litellm_llm
models:
  - api_key: sk-xxx                      # ★ 必改：你的 API Key
    model: openai/gpt-4o                 # ★ 必改：模型ID（见下表）
    alias: default
    timeout: 600
    kwargs:
      n: 1
      temperature: 0                     # 建议0，SQL生成需要确定性

# ===== 第2段：Embedding 配置 =====
type: embedder
provider: litellm_embedder
models:
  - model: openai/text-embedding-3-small # ★ 必改：embedding模型
    api_key: sk-xxx                      # ★ 必改：同上API Key
    alias: default
    timeout: 600
    # 如果用本地Ollama，改为：
    # model: openai/nomic-embed-text
    # api_base: http://host.docker.internal:11434/v1
    # （不需要api_key）

# ===== 第5段（最后）：开关配置 =====
settings:
  allow_intent_classification: false     # 意图分类（开了多1次LLM调用，建议关）
  allow_sql_generation_reasoning: false  # SQL推理链（开了多1次LLM调用，建议关）
  enable_column_pruning: true            # 列裁剪（100表时必须开，14表可关）
  max_sql_correction_retries: 1          # SQL纠错重试次数（0-3）
  langfuse_enable: false                 # Langfuse追踪（需要额外配置）
  logging_level: INFO                    # 日志级别（DEBUG可看prompt原文）
```

**模型ID对照表（litellm格式）：**

| 服务商 | model 值 | api_key | 说明 |
|--------|----------|---------|------|
| OpenAI | `openai/gpt-4o` | `sk-xxx` | 推荐 |
| OpenAI | `openai/gpt-4o-mini` | `sk-xxx` | 便宜 |
| DeepSeek | `deepseek/deepseek-chat` | `sk-xxx` | 国内直连 |
| Claude | `anthropic/claude-sonnet-4-20250514` | `sk-ant-xxx` | 需Anthropic Key |
| 本地Ollama | `openai/qwen3:8b` | 任意 | 需加 `api_base` |

**Embedding模型对照表：**

| 方式 | model 值 | 需要额外配置 |
|------|----------|-------------|
| OpenAI API | `openai/text-embedding-3-small` | 需api_key |
| 本地Ollama | `openai/nomic-embed-text` | 需 `api_base: http://host.docker.internal:11434/v1` |

> Embedding 维度需要和 config.yaml 第5段的 `embedding_model_dim` 匹配：
> - text-embedding-3-small: 1536
> - nomic-embed-text: 768

### 2.3 启动

```bash
cd WrenAI/docker
docker compose up -d
```

### 2.4 导入电信数据

```bash
cd /path/to/data-agent

# 1. 生成CSV + Init SQL（如果没做过步骤一的数据库生成，先做）
python telecom/scripts/export_init_sql.py

# 2. 在UI中操作（http://localhost:3000）
#    - 选择 DuckDB
#    - Display Name: telecom_nms
#    - Init SQL: 粘贴 telecom_init.sql 的56行内容
#    - Next → 全选14张表 → Submit
#    - 等待1-2分钟建立embedding索引

# 3. 导入中文元数据（表描述、字段描述、关系）
python telecom/scripts/update_wren_metadata.py
```

---

## 三、全量清库重来

当数据损坏或需要重新初始化时：

```bash
cd WrenAI/docker

# 1. 停止所有容器
docker compose down

# 2. 删除所有数据卷（包括SQLite元数据、Qdrant向量索引、DuckDB数据）
docker volume rm wrenai_data

# 3. 如果需要重新生成mock数据
cd /path/to/data-agent/telecom
python generate_mock_data.py
cd ..
python eval/refresh_timestamps.py
python telecom/scripts/export_init_sql.py

# 4. 重新启动
cd WrenAI/docker
docker compose up -d

# 5. 重新走UI导入流程（2.4节）
```

**部分清理（只清WrenAI元数据，不清数据）：**
```bash
# 停止UI容器 → 删除SQLite → 重启
docker compose stop wren-ui
docker compose exec wren-ui rm /app/data/db.sqlite3   # 或者直接删volume
docker compose up -d wren-ui
# 然后重新走UI导入流程
```

---

## 四、Docker 日常操作速查

### 改了什么 → 需要什么操作

| 改了什么 | 操作 | 命令 |
|---------|------|------|
| `.env` 里的 API Key | 重启ai-service | `docker compose restart wren-ai-service` |
| `config.yaml` 里的 LLM 模型 | 重启ai-service | `docker compose restart wren-ai-service` |
| `config.yaml` 里的 Embedding 模型 | 重启ai-service + **重新部署** | 重启后在UI点 "Deploy" 重建索引 |
| `config.yaml` 里的 settings 开关 | 重启ai-service | `docker compose restart wren-ai-service` |
| `data/*.csv` 数据文件 | 全量清库重来 | 见第三节 |
| `wren-ui/` 前端代码 | **重新构建镜像** | `docker build -t wren-ui-custom:latest WrenAI/wren-ui/ && docker compose up -d wren-ui` |
| `docker-compose.yaml` | 重建容器 | `docker compose up -d` |
| `.env` 里的端口号 | 重建容器 | `docker compose up -d` |

### 常用命令

```bash
cd WrenAI/docker

# 查看状态
docker compose ps

# 查看日志
docker compose logs -f wren-ai-service   # AI服务日志（看LLM调用）
docker compose logs -f wren-ui            # UI日志
docker compose logs -f wren-engine        # 引擎日志（看SQL执行）

# 重启单个服务
docker compose restart wren-ai-service

# 停止
docker compose down

# 停止并删除数据
docker compose down -v
```

---

## 五、WrenAI Pipeline 开关说明

在 `config.yaml` 的 `settings` 段：

| 开关 | 默认值 | 作用 | 建议 |
|------|--------|------|------|
| `allow_intent_classification` | `false` | 先判断用户意图再生成SQL，多1次LLM调用 | **关**。直接当SQL生成处理 |
| `allow_sql_generation_reasoning` | `false` | 先生成推理链再生成SQL，多1次LLM调用 | **关**。14表场景不需要 |
| `enable_column_pruning` | `true` | 检索到的表列数多时用LLM裁剪 | **开**。对准确率有帮助 |
| `max_sql_correction_retries` | `1` | SQL执行失败后自动修正重试次数 | 1-2 |
| `table_retrieval_size` | `10` | 向量检索返回的表数量 | 14表时可设为14 |
| `table_column_retrieval_size` | `100` | 向量检索返回的列数量 | 100-200 |
| `query_cache_maxsize` | `1000` | 查询缓存大小 | 1000 |
| `query_cache_ttl` | `3600` | 缓存过期秒数 | 3600 |
| `logging_level` | `INFO` | 日志级别 | 调试时改`DEBUG` |
| `langfuse_enable` | `false` | LLM调用追踪 | 需要Langfuse服务 |

---

## 六、公司环境注意事项

| 问题 | 解决方案 |
|------|---------|
| Docker镜像拉不到 | 配置Docker代理或使用镜像仓库 |
| LLM API不通 | DeepSeek国内直连；OpenAI需代理 |
| `uv` 安装被墙 | 用 `pip install duckdb pytz` 替代 |
| `PLATFORM` 不对 | 公司Ubuntu x86必须改为 `linux/amd64` |
| Embedding用本地Ollama | config.yaml改api_base为 `http://host.docker.internal:11434/v1`（Docker Desktop）或宿主机实际IP |
| 端口冲突 | 改 `.env` 中 `HOST_PORT` 和 `AI_SERVICE_FORWARD_PORT` |

---

## 七、快速验证

```bash
# 1. DuckDB数据正常（应输出 50）
python -c "import duckdb; print(duckdb.connect('telecom_nms.duckdb').execute('SELECT COUNT(*) FROM t_network_element').fetchone()[0])"

# 2. 时间窗口有数据（应输出 >0）
python -c "import duckdb; print(duckdb.connect('telecom_nms.duckdb').execute(\"SELECT COUNT(*) FROM t_ne_perf_kpi WHERE collect_time >= CURRENT_TIMESTAMP - INTERVAL 24 HOUR\").fetchone()[0])"

# 3. 评测框架正常
python eval/eval_framework.py eval/exp0_opus_100q.json verify

# 4. WrenAI服务正常（应返回JSON）
curl -s http://localhost:3000/api/graphql -H "Content-Type: application/json" -d '{"query":"{ project { id } }"}' | head -50
```
