# 新环境部署指南

## 1. 克隆仓库

```bash
git clone --recursive git@github.com:songruikang/Research.git
cd Research/data-agent
```

`--recursive` 会自动拉取 WrenAI submodule。如果已经 clone 但没拉 submodule：

```bash
git submodule update --init --recursive
```

## 2. Python 环境（评测体系）

```bash
# 安装 uv（Python 包管理器）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 创建虚拟环境 + 安装依赖
uv venv --python 3.11
source .venv/bin/activate
uv pip install duckdb pytz
```

## 3. 准备 DuckDB 数据库

数据库文件（.duckdb）在 .gitignore 中不会被提交，需要重新生成：

```bash
# 生成 mock 数据（14表，含 KPI 性能数据）
cd telecom
python generate_mock_data.py
cd ..

# 刷新时间戳到当前时间（否则时间窗口查询无数据）
python refresh_timestamps.py
```

## 4. 运行评测

```bash
# 用 Opus 基线 SQL 跑评测
python eval_framework.py exp0_opus_100q.json "opus_baseline"
```

输出包含三级指标：
- 可执行率（SQL 语法是否正确）
- 严格准确率（结果集完全匹配）
- 可验证准确率（排除双方都返回 0 行的题）

## 5. WrenAI 部署（如果需要 UI）

```bash
cd WrenAI/docker

# 配置环境变量
cp .env.example .env.local
# 编辑 .env.local，填入 LLM API key：
#   OPENAI_API_KEY=sk-xxx   （兼容 DeepSeek/OpenAI）

# 启动所有服务（约 6 个容器）
docker compose --env-file .env.local up -d

# 导入电信语义层到 WrenAI
cd ../..
python update_wren_metadata.py
```

WrenAI UI 访问地址：http://localhost:3000

## 6. 如果只跑评测不需要 WrenAI

只需要步骤 1-4，不需要 Docker。核心依赖就两个：`duckdb` 和 `pytz`。

## 快速验证

```bash
# 1. 数据库能连（应输出 (50,)）
python -c "import duckdb; c=duckdb.connect('telecom_nms.duckdb'); print(c.execute('SELECT COUNT(*) FROM t_network_element').fetchone())"

# 2. 时间窗口有数据（应输出 >0）
python -c "import duckdb; c=duckdb.connect('telecom_nms.duckdb'); print(c.execute('SELECT COUNT(*) FROM t_ne_perf_kpi WHERE collect_time >= CURRENT_TIMESTAMP - INTERVAL 24 HOUR').fetchone())"

# 3. 评测能跑（应输出完整报告）
python eval_framework.py exp0_opus_100q.json test
```

## 文件说明

| 文件 | 用途 |
|------|------|
| `telecom_test_cases_100.json` | 100 道测试用例 |
| `eval_framework.py` | 评测框架 |
| `refresh_timestamps.py` | 时间戳刷新脚本（每次评测前运行） |
| `exp0_opus_100q.json` | Opus 零知识基线生成的 SQL |
| `eval_result_opus_100q.json` | Opus 评测详细结果 |
| `NL2SQL_100Q_TestReport.md` | 100 题完整测试报告 |
| `NL2SQL_Research_Landscape.md` | NL2SQL 领域全景分析 |
| `DataAgent_Technical_Guide.md` | 二次开发技术指引 |
| `telecom_mdl.json` | 语义层 MDL 定义 |
| `update_wren_metadata.py` | WrenAI 导入脚本 |
| `telecom/generate_mock_data.py` | Mock 数据生成器 |
