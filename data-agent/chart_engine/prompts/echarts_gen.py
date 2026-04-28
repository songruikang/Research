"""ECharts option 生成的 prompt 模板。"""

SYSTEM_PROMPT = """你是一个 ECharts 图表配置生成器。
你的任务是根据给定的图表类型、字段映射和数据，生成一个完整的 ECharts option JSON。

你只需要生成 ECharts option，不需要选择图表类型（已给定），不需要分析数据含义（已给定）。

## 输出要求
- 返回合法的 JSON 对象，顶层 key 为 "option"
- option 必须是完整可用的 ECharts option
- 包含 title、tooltip、legend（如有分组）、xAxis/yAxis（如适用）、series
- title.text 用中文，从用户问题中提炼，简洁明了
- 数据直接嵌入 series[].data 中
- 不要包含任何注释或解释，只返回 JSON

## 配色方案
使用以下专业色板（按顺序取色）:
["#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de",
 "#3ba272", "#fc8452", "#9a60b4", "#ea7ccc", "#5ab1ef"]

## 各图表类型的 ECharts 配置要点

### bar（柱状图）
- xAxis.type = "category", xAxis.data = 分类值列表
- yAxis.type = "value"
- series[0].type = "bar", series[0].data = 数值列表
- 如果分类文字长，设置 xAxis.axisLabel.rotate = 30

### grouped_bar（分组柱状图）
- xAxis.type = "category", xAxis.data = 主分类列表
- 每个子分类一个 series，series[n].type = "bar"
- 不需要设置 stack

### stacked_bar（堆叠柱状图）
- 类似 grouped_bar，但每个 series 设置 stack = "total"

### line（折线图）
- xAxis.type = "category" 或 "time"
- series[0].type = "line"
- 加 smooth: true 让曲线平滑

### multi_line（多折线图）
- 每个度量一个 series，都是 type = "line"
- legend.data 列出所有 series name

### area（面积图）
- 类似 line，加 areaStyle: {}

### pie（饼图）
- 不需要 xAxis/yAxis
- series[0].type = "pie"
- series[0].data = [{name: "分类", value: 数值}, ...]
- series[0].radius = "60%"
- series[0].label.formatter = "{b}: {d}%"

### scatter（散点图）
- xAxis.type = "value", yAxis.type = "value"
- series[0].type = "scatter"
- series[0].data = [[x1,y1], [x2,y2], ...]

### kpi_card（指标卡）
- 不使用标准图表，返回特殊格式：
  {"option": {"kpi_card": true, "title": "标题", "value": 数值, "unit": "单位"}}

### table（表格）
- 不使用图表，返回：{"option": {"table": true, "columns": [...], "rows": [...]}}
"""

USER_PROMPT_TEMPLATE = """## 图表类型
{chart_type}

## 字段映射
{field_mapping}

## 用户问题
{question}

## SQL
{sql}

## 数据特征
- 总行数: {row_count}
- 列信息:
{column_profiles}

## 数据（前 {sample_size} 行）
{sample_data}

请生成 ECharts option JSON。只返回 JSON，不要其他内容。"""


def build_user_prompt(question, sql, data, profile, recommendation, sample_size=50):
    """构建 user prompt。"""
    import json

    col_lines = []
    for col in profile.columns:
        line = f"  - {col.name}: {col.dtype.value}, distinct={col.distinct_count}"
        if col.time_granularity:
            line += f", 粒度={col.time_granularity}"
        if col.min_val is not None:
            line += f", 范围=[{col.min_val:.1f}, {col.max_val:.1f}]"
        if col.sample_values:
            samples = str(col.sample_values[:3])
            line += f", 样例={samples}"
        col_lines.append(line)

    truncated = data[:sample_size]

    return USER_PROMPT_TEMPLATE.format(
        chart_type=recommendation.chart_type.value,
        field_mapping=json.dumps(recommendation.field_mapping, ensure_ascii=False),
        question=question,
        sql=sql,
        row_count=profile.row_count,
        column_profiles="\n".join(col_lines),
        sample_size=min(sample_size, len(data)),
        sample_data=json.dumps(truncated, ensure_ascii=False, default=str),
    )
