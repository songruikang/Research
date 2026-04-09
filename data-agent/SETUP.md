# 新环境部署指南

## 目录结构

```
data-agent/
├── docs/                              # 研究文档
│   ├── NL2SQL_Research_Landscape.md   #   NL2SQL 领域全景分析
│   ├── DataAgent_Technical_Guide.md   #   二次开发技术指引
│   └── NL2SQL_100Q_TestReport.md      #   100 题评测报告
│
├── eval/                              # 评测体系
│   ├── eval_framework.py              #   评测框架（三级判定：正确/错误/无法验证）
│   ├── refresh_timestamps.py          #   时间戳刷新脚本（每次评测前运行）
│   ├── telecom_test_cases_100.json    #   100 道测试用例
│   ├── exp0_opus_100q.json            #   Opus 零知识基线生成的 SQL
│   └── eval_result_opus_100q.json     #   Opus 评测详细结果
│
├── telecom/                           # 电信语义层
│   ├── telecom_mdl.json               #   MDL 语义层定义（14表/356字段/29关系）
│   ├── generate_mock_data.py          #   Mock 数据生成器
│   ├── scripts/
│   │   └── update_wren_metadata.py    #   WrenAI 导入脚本
│   └── __init__.py
│
├── WrenAI/                            # WrenAI 源码（git submodule）
│   ├── docker/
│   │   ├── docker-compose.yaml        #   [有自定义改动] 搜索 "[自定义]" 查看改动说明
│   │   └── .env.local                 #   [需手动创建] LLM API key 等配置
│   └── wren-ui/                       #   [有自定义改动] Trace 日志页面等 UI 改动
│
├── SETUP.md                           # 本文件
├── pyproject.toml                     # Python 项目配置
├── .gitignore
├── .env                               # [不提交] 本地环境变量
├── telecom_nms.duckdb                 # [不提交] DuckDB 数据库，需生成
└── sample.duckdb                      # [不提交] 早期 demo 数据库，可忽略
```

## 需要生成的文件（不在 git 中）

| 文件 | 生成方式 | 说明 |
|------|---------|------|
| `telecom_nms.duckdb` | `cd telecom && python generate_mock_data.py` | 14 表 mock 数据 |
| 时间戳刷新 | `python eval/refresh_timestamps.py` | 将 KPI 时间对齐到当前 |
| `.venv/` | `uv venv --python 3.11` | Python 虚拟环境 |
| `WrenAI/docker/.env.local` | 手动从 `.env.example` 复制并填写 | LLM API key |
| `wren-ui-custom:latest` | `cd WrenAI/wren-ui && docker build -t wren-ui-custom:latest .` | 自定义 UI 镜像 |

## 部署步骤

### 步骤 1: 克隆仓库

```bash
git clone --recursive git@github.com:songruikang/Research.git
cd Research/data-agent
```

如果已 clone 但没拉 submodule：
```bash
git submodule update --init --recursive
```

### 步骤 2: Python 环境

```bash
# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 创建虚拟环境
uv venv --python 3.11
source .venv/bin/activate    # Linux/Mac
# .venv\Scripts\activate     # Windows

# 安装依赖
uv pip install duckdb pytz
```

### 步骤 3: 生成数据库

```bash
cd telecom
python generate_mock_data.py    # 生成 telecom_nms.duckdb（约 16MB）
cd ..

python eval/refresh_timestamps.py    # 刷新时间戳到当前时间
```

### 步骤 4: 运行评测（不需要 WrenAI）

```bash
python eval/eval_framework.py eval/exp0_opus_100q.json "opus_baseline"
```

### 步骤 5: WrenAI 部署（可选，需要 Docker）

#### 5a. 构建 + 启动

```bash
# 1. 构建自定义 UI 镜像（包含 Trace 日志页面改动）
cd WrenAI/wren-ui
docker build -t wren-ui-custom:latest .

# 2. 配置环境变量
cd ../docker
cp .env.example .env.local
# 编辑 .env.local，填入:
#   OPENAI_API_KEY=sk-xxx       # OpenAI 或 DeepSeek API key
#   GENERATION_MODEL=gpt-4o     # 或 deepseek-chat

# 3. 启动所有容器
docker compose --env-file .env.local up -d

# 4. 等待启动完成（约 30 秒），然后访问 UI
#    http://localhost:3000
```

#### 5b. 在 UI 中连接 DuckDB 并导入表（首次部署必须做）

这一步必须在 UI 中手动操作，无法跳过：

1. 打开 http://localhost:3000
2. 选择数据源: **DuckDB**
3. 上传数据库文件: 选择项目根目录下的 `telecom_nms.duckdb`
   - 如果还没生成，先回到步骤 3 执行 `python telecom/generate_mock_data.py`
4. 选择要导入的表: **全选 14 张表**（t_site, t_network_element, ...）
5. 点击 "Submit" 完成导入
6. 等待 WrenAI 自动建立 embedding 索引（约 1-2 分钟）

此时 WrenAI 已经可以用了，但表的中文描述、关系、主键等元数据还是空的。

#### 5c. 导入中文语义层元数据

```bash
cd /path/to/Research/data-agent
source .venv/bin/activate
python telecom/scripts/update_wren_metadata.py
```

这个脚本做的事：
1. 从 Docker 容器中拷出 WrenAI 的 SQLite 数据库
2. 用 `telecom/telecom_mdl.json` 中的信息更新：
   - 每张表的中文名称和描述
   - 每个字段的中文名称、描述、类型、主键、非空标记
   - 29 条表间关系（含中文描述）
3. 拷回容器并重启 wren-ui
4. 触发 MDL 重新部署（重建向量索引）
5. 执行一条 JOIN 查询验证导入成功

**前提**: 步骤 5b 已完成（UI 中已导入 14 张表），否则脚本找不到表记录会失败。

WrenAI UI: http://localhost:3000

### Docker Compose 自定义改动说明

docker-compose.yaml 中所有自定义改动都标注了 `[自定义]` 注释，主要包括：

1. **资源限制** — 所有容器加了 CPU/内存限制，防止 Mac 上内存占满
2. **端口映射** — engine 和 ibis-server 改为仅 expose，不映射到宿主机（只有 UI 和 AI service 需要外部访问）
3. **UI 镜像** — 从官方镜像改为 `wren-ui-custom:latest`（包含 Trace 日志等 UI 改动）

## 快速验证

```bash
# 1. 数据库能连（应输出 (50,)）
python -c "import duckdb; c=duckdb.connect('telecom_nms.duckdb'); print(c.execute('SELECT COUNT(*) FROM t_network_element').fetchone())"

# 2. 时间窗口有数据（应输出 >0）
python -c "import duckdb; c=duckdb.connect('telecom_nms.duckdb'); print(c.execute('SELECT COUNT(*) FROM t_ne_perf_kpi WHERE collect_time >= CURRENT_TIMESTAMP - INTERVAL 24 HOUR').fetchone())"

# 3. 评测能跑
python eval/eval_framework.py eval/exp0_opus_100q.json verify
```

## 公司环境注意事项

如果在防火墙内部署：
- Docker 镜像拉取可能需要配置代理或使用镜像仓库
- LLM API 需要确认公司网络可达（DeepSeek 国内直连，OpenAI 需代理）
- `uv` 安装如果被墙，可以用 `pip install duckdb pytz` 替代
- WrenAI 的 Qdrant 向量库不需要外网，纯本地运行
