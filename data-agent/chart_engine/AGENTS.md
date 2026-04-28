# Chart Engine

SQL 查询结果 → ECharts option JSON 的独立图表生成模块。

## 架构

四步管线，每步职责单一：

```
SQL 结果 → Profiler(纯计算) → Selector(规则引擎) → Generator(LLM) → Validator(规则兜底)
```

## 文件说明

| 文件 | 职责 | 调 LLM |
|------|------|--------|
| models.py | 所有数据模型（dataclass） | 否 |
| config.py | 配置加载（YAML + 环境变量） | 否 |
| profiler.py | 数据画像：类型推断、基数、时间粒度 | 否 |
| selector.py | 图表选型：规则引擎，按数据特征+意图匹配 | 否 |
| generator.py | ECharts option 生成：调 LLM，职责收窄 | 是 |
| validator.py | 校验修正：补 title/tooltip/color，饼图降级 | 否 |
| prompts/echarts_gen.py | Prompt 模板 | — |
| examples.py | Few-shot 示例管理（加载/SQL执行/批量生成） | 是 |
| cli.py | CLI 入口 | 视 --mock |
| server.py | FastAPI 服务 | 是 |

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

# 完整模式
python -m chart_engine -q "各厂商设备数" -d data.json

# 批量生成 few-shot 示例图表
python -m chart_engine examples -o output/
```

### API 服务
```bash
python -m chart_engine serve --port 8100

# 生成图表
curl -X POST http://localhost:8100/generate \
  -H "Content-Type: application/json" \
  -d '{"question": "各厂商设备数", "data": [...]}'

# 查看示例列表
curl http://localhost:8100/examples
```

## 配置

复制 `config.yaml.example` 为 `config.yaml`，修改 LLM 端点：

```yaml
llm:
  model: ollama_chat/qwen3:32b
  api_base: http://10.220.239.55:11343
```

## 图表类型

bar / grouped_bar / stacked_bar / line / multi_line / area / pie / scatter / heatmap / gauge / funnel / kpi_card / table

## 测试

```bash
python -m pytest tests/chart_engine/ -v
```
