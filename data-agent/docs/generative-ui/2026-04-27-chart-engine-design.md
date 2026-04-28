# Chart Engine 设计文档

> 独立图表生成模块，从 SQL 查询结果生成 ECharts option JSON。
> 四步管线：数据画像 → 图表选型 → Spec 生成 → 校验修正。

## 1. 模块结构

```
data-agent/chart_engine/
├── __init__.py          # 公共 API: generate_chart()
├── config.py            # LLM/服务配置，读 config.yaml
├── profiler.py          # Step 1: 数据画像（纯计算）
├── selector.py          # Step 2: 图表选型（规则引擎）
├── generator.py         # Step 3: ECharts option 生成（LLM）
├── validator.py         # Step 4: 校验 + 自动修正
├── examples.py          # few-shot 示例管理
├── cli.py               # CLI 入口
├── server.py            # FastAPI 服务
├── prompts/
│   └── echarts_gen.py   # prompt 模板
└── config.yaml.example  # 配置模板
```

## 2. 核心数据流

```
generate_chart(question, sql, data, config) -> EChartsResult
```

### 2.1 输入

```python
@dataclass
class ChartInput:
    question: str              # 用户自然语言问题
    sql: str                   # 生成的 SQL
    data: list[dict]           # SQL 查询结果，[{"col1": val1, ...}, ...]
    columns: list[str] | None  # 列名（可选，从 data 推断）
```

### 2.2 输出

```python
@dataclass
class ChartResult:
    chart_type: str            # 使用的图表类型
    echarts_option: dict       # 完整 ECharts option JSON
    reasoning: str             # 选型理由（调试用）
    profile: DataProfile       # 数据画像（调试用）
    warnings: list[str]        # 校验修正的警告信息
    fallback: bool             # 是否降级到了表格
```

## 3. Step 1: Profiler（数据画像）

纯 Python 计算，不调 LLM。目标：把 SQL 结果的统计特征提取出来，消除 LLM 猜测。

```python
@dataclass
class ColumnProfile:
    name: str
    dtype: str           # temporal | quantitative | categorical | identifier
    distinct_count: int
    distinct_ratio: float
    null_count: int
    sample_values: list   # 最多 5 个代表性取值
    is_dimension: bool    # 适合做分组/分类轴
    is_measure: bool      # 适合做数值轴
    time_granularity: str | None  # year | month | day | hour（仅 temporal）
    min_val: float | None # 仅 quantitative
    max_val: float | None # 仅 quantitative

@dataclass
class DataProfile:
    row_count: int
    col_count: int
    columns: list[ColumnProfile]
    dimensions: list[str]   # is_dimension=True 的列名
    measures: list[str]     # is_measure=True 的列名
    temporals: list[str]    # dtype=temporal 的列名
```

### 类型推断规则

```python
def infer_dtype(values: list) -> str:
    non_null = [v for v in values if v is not None]
    if not non_null:
        return "categorical"

    # 1. 时间检测：尝试 parse 前 20 个非空值
    if _is_temporal(non_null[:20]):
        return "temporal"

    # 2. 数值检测
    if _is_numeric(non_null[:20]):
        distinct_ratio = len(set(non_null)) / len(non_null)
        # 高基数数值且非聚合结果 → identifier（如 device_id 是数字）
        if distinct_ratio > 0.9 and len(set(non_null)) > 50:
            return "identifier"
        return "quantitative"

    # 3. 分类 vs 标识符
    distinct_ratio = len(set(non_null)) / len(non_null)
    if distinct_ratio > 0.8 and len(set(non_null)) > 50:
        return "identifier"

    return "categorical"
```

### 时间粒度推断

```python
def infer_time_granularity(values: list[datetime]) -> str:
    """从相邻时间差推断粒度"""
    sorted_vals = sorted(set(values))
    if len(sorted_vals) < 2:
        return "day"
    diffs = [(sorted_vals[i+1] - sorted_vals[i]) for i in range(min(10, len(sorted_vals)-1))]
    median_diff = sorted(diffs)[len(diffs)//2]

    if median_diff >= timedelta(days=300):
        return "year"
    elif median_diff >= timedelta(days=25):
        return "month"
    elif median_diff >= timedelta(days=5):
        return "week"
    elif median_diff >= timedelta(hours=20):
        return "day"
    else:
        return "hour"
```

## 4. Step 2: Selector（图表选型）

规则引擎，不调 LLM。基于 DataProfile + 用户问题关键词，推荐图表类型和字段映射。

### 4.1 支持的图表类型

```python
class ChartType(str, Enum):
    BAR = "bar"
    GROUPED_BAR = "grouped_bar"
    STACKED_BAR = "stacked_bar"
    LINE = "line"
    MULTI_LINE = "multi_line"
    AREA = "area"
    PIE = "pie"
    SCATTER = "scatter"
    HEATMAP = "heatmap"
    GAUGE = "gauge"
    FUNNEL = "funnel"
    KPI_CARD = "kpi_card"
    TABLE = "table"          # fallback
```

### 4.2 选型规则

按优先级匹配，第一条命中即选定：

```python
SELECTION_RULES = [
    # 单值结果 → KPI 卡片
    Rule(
        condition=lambda p: p.row_count == 1 and p.col_count <= 3 and len(p.measures) >= 1,
        chart_type=ChartType.KPI_CARD,
    ),

    # 有时间列 + 多个度量列 → 多折线
    Rule(
        condition=lambda p: len(p.temporals) >= 1 and len(p.measures) >= 2,
        chart_type=ChartType.MULTI_LINE,
    ),

    # 有时间列 + 1 个度量 + 问题含"趋势/变化/走势" → 折线
    Rule(
        condition=lambda p, q: len(p.temporals) >= 1 and len(p.measures) >= 1,
        chart_type=ChartType.LINE,
    ),

    # 2 个度量 + 0 时间列 → 散点图
    Rule(
        condition=lambda p: len(p.measures) >= 2 and len(p.temporals) == 0,
        chart_type=ChartType.SCATTER,
    ),

    # 1 维度 + 1 度量 + 维度基数 <= 7 + 问题含"占比/比例/分布" → 饼图
    Rule(
        condition=lambda p, q: (
            len(p.dimensions) >= 1 and len(p.measures) >= 1
            and _get_dim_cardinality(p) <= 7
            and _has_proportion_intent(q)
        ),
        chart_type=ChartType.PIE,
    ),

    # 2 维度 + 1 度量 + 问题含"分布/构成" → 堆叠柱状
    Rule(
        condition=lambda p, q: len(p.dimensions) >= 2 and len(p.measures) >= 1 and _has_composition_intent(q),
        chart_type=ChartType.STACKED_BAR,
    ),

    # 2 维度 + 1 度量 → 分组柱状
    Rule(
        condition=lambda p: len(p.dimensions) >= 2 and len(p.measures) >= 1,
        chart_type=ChartType.GROUPED_BAR,
    ),

    # 1 维度 + 1 度量 → 柱状图
    Rule(
        condition=lambda p: len(p.dimensions) >= 1 and len(p.measures) >= 1,
        chart_type=ChartType.BAR,
    ),

    # fallback → 表格
    Rule(
        condition=lambda p: True,
        chart_type=ChartType.TABLE,
    ),
]
```

### 4.3 字段映射建议

Selector 同时输出字段映射建议，减轻 LLM 负担：

```python
@dataclass
class ChartRecommendation:
    chart_type: ChartType
    field_mapping: dict       # {"x": "collect_time", "y": "cpu_usage_avg_pct", "group": "ne_name"}
    reasoning: str            # "时序数据+单指标→折线图，x=collect_time, y=cpu_usage_avg_pct"
    alternatives: list[ChartType]  # 备选类型
```

## 5. Step 3: Generator（ECharts Spec 生成）

调用 LLM，但职责大幅收窄：**已知图表类型和字段映射，只需要生成 ECharts option JSON**。

### 5.1 LLM 调用方式

使用 LiteLLM 统一调用接口，兼容 Qwen/Gemini/DeepSeek：

```python
import litellm

def call_llm(prompt: str, config: LLMConfig) -> str:
    response = litellm.completion(
        model=config.model,        # "ollama_chat/qwen3:32b"
        api_base=config.api_base,  # "http://10.220.239.55:11343"
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        timeout=config.timeout,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content
```

### 5.2 Prompt 设计

```python
SYSTEM_PROMPT = """你是一个 ECharts 图表配置生成器。
你的任务是根据给定的图表类型、字段映射和数据特征，生成一个完整的 ECharts option JSON。

你只需要生成 ECharts option，不需要选择图表类型（已给定），不需要分析数据含义（已给定）。

输出要求：
- 返回合法的 JSON，key 为 "option"
- option 必须是完整可用的 ECharts option 对象
- 包含 title、legend、tooltip、xAxis/yAxis（或对应配置）、series
- title.text 用中文，从用户问题中提炼
- 配色使用专业色板，不要用默认颜色
- tooltip 要显示完整信息
- 数据直接嵌入 series.data 中
"""

USER_PROMPT_TEMPLATE = """
## 图表类型
{chart_type}

## 字段映射
{field_mapping}

## 用户问题
{question}

## 数据特征
- 总行数: {row_count}
- 列信息:
{column_profiles}

## 数据（前 {sample_size} 行）
{sample_data}

请生成 ECharts option JSON。
"""
```

### 5.3 为什么 prompt 这么短

对比 WrenAI 的 244 行 prompt：
- **不需要教选型** — Selector 已经选好了图表类型
- **不需要教数据类型** — Profiler 已经标注了每列类型
- **不需要 7 个完整示例** — LLM 对 ECharts 的训练数据充分，不需要 in-context learning
- **职责单一** — 只做 "配置 → JSON"，不做 "理解 → 决策 → 生成"

prompt 短 → token 省 → 留更多空间给数据 → 生成更准。

## 6. Step 4: Validator（校验修正）

纯规则，不调 LLM。

### 6.1 JSON 格式校验

```python
def validate_json(option: dict) -> list[str]:
    """检查 ECharts option 的结构完整性"""
    errors = []
    if "series" not in option:
        errors.append("缺少 series")
    if not isinstance(option.get("series"), list):
        errors.append("series 必须是数组")
    # 根据图表类型检查必要字段
    return errors
```

### 6.2 业务规则修正

```python
CORRECTION_RULES = [
    # 饼图分类 > 7 → 降级为柱状图
    CorrectionRule(
        condition=lambda opt: opt_is_pie(opt) and count_categories(opt) > 7,
        action=convert_pie_to_bar,
        warning="饼图分类超过7个，已降级为柱状图",
    ),

    # 缺少 title → 从 question 自动补充
    CorrectionRule(
        condition=lambda opt: "title" not in opt or not opt["title"].get("text"),
        action=lambda opt, ctx: opt.update({"title": {"text": ctx.question[:30]}}),
        warning="自动补充了图表标题",
    ),

    # 缺少 tooltip → 补充默认 tooltip
    CorrectionRule(
        condition=lambda opt: "tooltip" not in opt,
        action=lambda opt, ctx: opt.update({"tooltip": {"trigger": "axis"}}),
        warning="自动补充了 tooltip",
    ),

    # 柱状图分类 > 20 → 只保留 Top 20
    CorrectionRule(
        condition=lambda opt: opt_is_bar(opt) and count_categories(opt) > 20,
        action=truncate_to_top20,
        warning="分类超过20个，只保留 Top 20",
    ),

    # 颜色缺失 → 注入默认色板
    CorrectionRule(
        condition=lambda opt: "color" not in opt,
        action=lambda opt, ctx: opt.update({"color": DEFAULT_PALETTE}),
        warning=None,  # 静默修正
    ),
]
```

### 6.3 Fallback

所有校验失败 → 返回表格视图（ChartType.TABLE），保证永远有输出。

## 7. CLI 入口

```bash
# 基本用法：传入问题 + SQL + 数据文件
python -m chart_engine \
  --question "统计每个厂商的PE设备数量" \
  --sql "SELECT vendor, COUNT(*) as cnt FROM t_network_element WHERE role='PE' GROUP BY vendor" \
  --data result.json

# 只传问题 + 数据（不需要 SQL 也能画图）
python -m chart_engine \
  --question "各厂商设备数对比" \
  --data result.json

# 输出到文件
python -m chart_engine --question "..." --data result.json --output chart.json

# 指定模型
python -m chart_engine --question "..." --data result.json --model gemini/gemini-2.5-flash

# Mock 模式：不调 LLM，只跑 profiler + selector，看推荐结果
python -m chart_engine --question "..." --data result.json --mock

# 生成所有 few-shot 示例的图表
python -m chart_engine examples --input eval/few_shot_pairs.json --output examples_out/
```

## 8. FastAPI 服务

```python
# server.py
app = FastAPI(title="Chart Engine")

@app.post("/generate")
async def generate(req: GenerateRequest) -> ChartResult:
    """生成图表 — WrenAI 或其他客户端调用"""
    return generate_chart(req.question, req.sql, req.data, config)

@app.get("/examples")
async def list_examples() -> list[ExampleSummary]:
    """列出所有 few-shot 示例"""
    return example_manager.list()

@app.get("/examples/{example_id}/chart")
async def get_example_chart(example_id: str) -> ChartResult:
    """获取指定示例的图表（预生成或实时生成）"""
    return example_manager.get_chart(example_id)

@app.post("/profile")
async def profile_data(req: ProfileRequest) -> DataProfile:
    """只做数据画像（调试用）"""
    return profiler.profile(req.data)

@app.post("/recommend")
async def recommend(req: RecommendRequest) -> ChartRecommendation:
    """只做图表选型（调试用）"""
    profile = profiler.profile(req.data)
    return selector.recommend(profile, req.question)
```

## 9. Example Gallery

复用 `eval/few_shot_pairs.json` 中的 question + SQL：

```python
class ExampleManager:
    def __init__(self, few_shot_path: str, db_path: str):
        self.pairs = load_few_shot(few_shot_path)
        self.db = duckdb.connect(db_path)  # 电信 demo 数据库

    def get_chart(self, example_id: str) -> ChartResult:
        pair = self.pairs[example_id]
        # 1. 执行 SQL 拿真实数据
        data = self.db.execute(pair["sql"]).fetchdf().to_dict("records")
        # 2. 走完整 4 步管线
        return generate_chart(pair["question"], pair["sql"], data, self.config)
```

前端展示每个示例：问题 → SQL → 图表，用户可以浏览、对比、理解模型行为。

## 10. 配置

```yaml
# chart_engine/config.yaml.example
llm:
  model: ollama_chat/qwen3:32b
  api_base: http://10.220.239.55:11343
  timeout: 120
  temperature: 0

server:
  host: 0.0.0.0
  port: 8100

examples:
  few_shot_path: ../eval/few_shot_pairs.json
  db_path: ../telecom/telecom.db

profiler:
  sample_size: 50          # 传给 LLM 的最大数据行数
  max_column_samples: 5    # 每列展示的 sample values 数量

selector:
  pie_max_categories: 7
  bar_max_categories: 20
  top_n_default: 20
```

## 11. 依赖

```
litellm          # 统一 LLM 调用（已在 data-agent 使用）
fastapi          # API 服务
uvicorn          # ASGI server
pydantic         # 数据模型
duckdb           # 执行 SQL 获取示例数据
python-dateutil  # 时间解析
pyyaml           # 配置文件
```

## 12. 不做的事

- 不动 WrenAI 任何代码
- 不做前端渲染（只输出 ECharts option JSON）
- 不做流式输出（第一版同步调用）
- 不自建 DSL（直接生成 ECharts option）
- 不做图表编辑/调整 API（第一版只做生成）
- 不做缓存（第一版每次实时生成）
