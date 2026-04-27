"""Step 4: 校验修正 — 规则兜底，自动修正常见问题。不调 LLM。"""
from __future__ import annotations

import logging

from chart_engine.config import SelectorConfig
from chart_engine.models import ChartType, ChartRecommendation, ChartResult, DataProfile

logger = logging.getLogger(__name__)

DEFAULT_PALETTE = [
    "#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de",
    "#3ba272", "#fc8452", "#9a60b4", "#ea7ccc", "#5ab1ef",
]


def validate_and_fix(option, recommendation, profile, question, config):
    """校验 ECharts option 并自动修正常见问题。"""
    warnings = []

    # KPI 卡片和表格直接放行（table=True 是主动选择，不是降级，fallback=False）
    if option.get("kpi_card") or option.get("table"):
        return ChartResult(
            chart_type=recommendation.chart_type.value,
            echarts_option=option, reasoning=recommendation.reasoning,
            profile=profile, warnings=[], fallback=False,
        )

    # 致命缺陷 → fallback 到表格
    if "series" not in option or not isinstance(option.get("series"), list):
        return _fallback_table(recommendation, profile, question, ["缺少 series，降级为表格"])

    if not option["series"]:
        return _fallback_table(recommendation, profile, question, ["series 为空，降级为表格"])

    # 补 title
    if "title" not in option or not option.get("title", {}).get("text"):
        option["title"] = {"text": question[:30]}
        warnings.append("自动补充了 title")

    # 补 tooltip
    if "tooltip" not in option:
        option["tooltip"] = {"trigger": "axis"}
        warnings.append("自动补充了 tooltip")

    # 补 color
    if "color" not in option:
        option["color"] = DEFAULT_PALETTE.copy()

    # 饼图高基数降级
    if _is_pie(option):
        pie_series = option["series"][0]
        data_items = pie_series.get("data", [])
        if len(data_items) > config.pie_max_categories:
            _convert_pie_to_bar(option, data_items)
            warnings.append(f"饼图分类超过{config.pie_max_categories}个，已降级为柱状图")

    # 柱状图高基数截断
    if _is_bar(option) and "xAxis" in option:
        x_data = option.get("xAxis", {}).get("data", [])
        if len(x_data) > config.bar_max_categories:
            _truncate_bar(option, config.bar_max_categories)
            warnings.append(f"分类超过{config.bar_max_categories}个，只保留 Top {config.bar_max_categories}")

    return ChartResult(
        chart_type=recommendation.chart_type.value,
        echarts_option=option, reasoning=recommendation.reasoning,
        profile=profile, warnings=warnings, fallback=False,
    )


def _fallback_table(rec, profile, question, warnings):
    return ChartResult(
        chart_type=ChartType.TABLE.value,
        echarts_option={"table": True, "columns": [c.name for c in profile.columns], "rows": []},
        reasoning=rec.reasoning, profile=profile, warnings=warnings, fallback=True,
    )


def _is_pie(option):
    series = option.get("series", [])
    return bool(series) and series[0].get("type") == "pie"


def _is_bar(option):
    series = option.get("series", [])
    return bool(series) and series[0].get("type") == "bar"


def _convert_pie_to_bar(option, data_items):
    sorted_items = sorted(data_items, key=lambda d: d.get("value", 0), reverse=True)
    categories = [d.get("name", "") for d in sorted_items]
    values = [d.get("value", 0) for d in sorted_items]
    option["xAxis"] = {"type": "category", "data": categories}
    option["yAxis"] = {"type": "value"}
    option["series"] = [{"type": "bar", "data": values}]


def _truncate_bar(option, max_count):
    option["xAxis"]["data"] = option["xAxis"]["data"][:max_count]
    for s in option.get("series", []):
        if "data" in s:
            s["data"] = s["data"][:max_count]
