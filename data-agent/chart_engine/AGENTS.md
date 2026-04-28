直接# Chart Engine

SQL 查询结果 → ECharts option JSON 的独立图表生成模块。

## 目录结构

```
chart_engine/
├── __init__.py              # 公共 API: generate_chart()
├── __main__.py              # CLI 入口分发（serve / examples / 默认）
├── config.py                # 配置加载（YAML + 环境变量）
├── config.yaml.example      # 配置模板
├── Dockerfile               # 容器镜像
│
├── core/                    # 四步管线核心
│   ├── models.py            # 数据模型（ChartType, DataProfile, ChartResult）
│   ├── profiler.py          # Step 1: 数据画像（类型推断/基数/时间粒度）
│   ├── selector.py          # Step 2: 图表选型（规则引擎，12 种图表）
│   ├── builder.py           # Step 3a: mock 构建（不调 LLM）
│   ├── generator.py         # Step 3b: LLM 生成
│   ├── validator.py         # Step 4: 校验修正（补全/降级/截断）
│   └── prompts/
│       └── echarts_gen.py   # LLM prompt 模板
│
├── server/                  # FastAPI 服务
│   └── app.py               # /generate /profile /recommend /health
│
├── cli/                     # CLI + 示例管理
│   ├── main.py              # python -m chart_engine -q "..." -d data.json
│   └── examples.py          # few-shot 示例批量生成
│
└── utils/                   # 工具
    └── renderer.py          # ECharts option → HTML 文件
```

## 部署到新环境

### 方式一：本地 Python

```bash
# 1. 克隆仓库
git clone <repo> && cd data-agent

# 2. 安装依赖
uv sync

# 3. 启动服务
python -m chart_engine serve --port 8100

# 4. 验证
curl http://localhost:8100/health
```

### 方式二：Docker 独立运行

```bash
# 1. 构建镜像
docker build -t chart-engine:latest -f chart_engine/Dockerfile chart_engine/

# 2. 启动
docker run -d -p 8100:8100 \
  -e CHART_LLM_MODEL=ollama_chat/qwen3:32b \
  -e CHART_LLM_API_BASE=http://10.220.239.55:11343 \
  chart-engine:latest

# 3. 验证
curl http://localhost:8100/health
```

### 方式三：WrenAI Docker Compose（生产部署）

chart-engine 已集成到 `WrenAI/docker/docker-compose.yaml` 作为第 7 个容器。

```bash
cd WrenAI/docker

# 1. 确保 .env 中有以下变量
#    CHART_ENGINE_PORT=8100
#    CHART_LLM_MODEL=ollama_chat/qwen3:32b
#    CHART_LLM_API_BASE=http://10.220.239.55:11343

# 2. 构建镜像（首次或代码变更后）
docker build -t chart-engine:latest -f ../../chart_engine/Dockerfile ../../chart_engine/
docker build -t wren-ui-custom:latest ../wren-ui/

# 3. 启动全部容器
docker compose up -d

# 4. 访问 Chart SQL 页面
open http://localhost:3000/chart-sql
```

wren-ui 通过环境变量 `CHART_ENGINE_ENDPOINT=http://chart-engine:8100` 访问 chart-engine。

## 使用方式

### Python API

```python
from chart_engine import generate_chart
result = generate_chart("各厂商设备数", "SELECT ...", data)
print(result.echarts_option)
```

### CLI

```bash
# Mock 模式（不调 LLM）
python -m chart_engine -q "各厂商设备数" -d data.json --mock

# LLM 模式
python -m chart_engine -q "各厂商设备数" -d data.json

# 批量生成 few-shot 示例图表
python -m chart_engine examples --input eval/few_shot_pairs.json

# 启动 API 服务
python -m chart_engine serve --port 8100
```

### API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/generate` | POST | 生成图表，返回 echarts_option + pipeline trace |
| `/profile` | POST | 只做数据画像 |
| `/recommend` | POST | 只做图表选型 |
| `/examples` | GET | 列出 few-shot 示例 |
| `/health` | GET | 健康检查 |

`/generate` 参数：`question`(必填), `sql`, `data`(必填), `mock`(默认 true)

## 配置

复制 `config.yaml.example` 为 `config.yaml`：

```yaml
llm:
  model: ollama_chat/qwen3:32b
  api_base: http://10.220.239.55:11343
  timeout: 120
  temperature: 0

examples:
  few_shot_path: eval/few_shot_pairs.json
  db_path: telecom/output/telecom_nms.duckdb
```

环境变量覆盖：`CHART_LLM_MODEL`、`CHART_LLM_API_BASE`

## 图表类型

bar / grouped_bar / stacked_bar / line / multi_line / area / pie / scatter / heatmap / gauge / funnel / kpi_card / table

## 测试

```bash
python -m pytest tests/chart_engine/ -v   # 41 tests
```
