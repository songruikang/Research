"""Mock 图表构建器 — 不调 LLM，从 selector 结果 + 实际数据直接生成 ECharts option。"""
from __future__ import annotations

from chart_engine.core.models import ChartType, ChartRecommendation, DataProfile

DEFAULT_PALETTE = [
    "#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de",
    "#3ba272", "#fc8452", "#9a60b4", "#ea7ccc", "#5ab1ef",
]


def build_echarts_from_data(
    data: list[dict],
    recommendation: ChartRecommendation,
    question: str,
) -> dict:
    """从数据 + 推荐结果直接构建 ECharts option，不需要 LLM。"""
    ct = recommendation.chart_type
    fm = recommendation.field_mapping

    builders = {
        ChartType.BAR: _build_bar,
        ChartType.GROUPED_BAR: _build_grouped_bar,
        ChartType.STACKED_BAR: _build_stacked_bar,
        ChartType.LINE: _build_line,
        ChartType.MULTI_LINE: _build_multi_line,
        ChartType.AREA: _build_area,
        ChartType.PIE: _build_pie,
        ChartType.SCATTER: _build_scatter,
        ChartType.KPI_CARD: _build_kpi_card,
        ChartType.TABLE: _build_table,
    }

    builder = builders.get(ct, _build_table)
    option = builder(data, fm, question)

    # 统一注入色板
    if "color" not in option and not option.get("kpi_card") and not option.get("table"):
        option["color"] = DEFAULT_PALETTE.copy()

    return option


def _build_bar(data, fm, question):
    x_field = fm.get("x", "")
    y_field = fm.get("y", "")
    categories = [str(row.get(x_field, "")) for row in data]
    values = [row.get(y_field, 0) for row in data]
    option = {
        "title": {"text": question[:40], "left": "center"},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": categories},
        "yAxis": {"type": "value"},
        "series": [{"type": "bar", "data": values, "name": y_field}],
    }
    if len(categories) > 8:
        option["xAxis"]["axisLabel"] = {"rotate": 30}
    return option


def _build_grouped_bar(data, fm, question):
    x_field = fm.get("x", "")
    group_field = fm.get("group", "")
    y_field = fm.get("y", "")

    # 提取分类和分组
    categories = list(dict.fromkeys(str(row.get(x_field, "")) for row in data))
    groups = list(dict.fromkeys(str(row.get(group_field, "")) for row in data))

    # 构建每组的数据
    series = []
    for g in groups:
        g_data = []
        for cat in categories:
            val = next(
                (row.get(y_field, 0) for row in data
                 if str(row.get(x_field, "")) == cat and str(row.get(group_field, "")) == g),
                0,
            )
            g_data.append(val)
        series.append({"type": "bar", "name": g, "data": g_data})

    return {
        "title": {"text": question[:40], "left": "center"},
        "tooltip": {"trigger": "axis"},
        "legend": {"data": groups, "top": 30},
        "xAxis": {"type": "category", "data": categories},
        "yAxis": {"type": "value"},
        "series": series,
        "grid": {"top": 80},
    }


def _build_stacked_bar(data, fm, question):
    option = _build_grouped_bar(data, fm, question)
    for s in option.get("series", []):
        s["stack"] = "total"
    return option


def _build_line(data, fm, question):
    x_field = fm.get("x", "")
    y_field = fm.get("y", "")
    group_field = fm.get("group")

    if group_field and len(set(str(row.get(group_field, "")) for row in data)) > 1:
        # 多分组折线
        groups = list(dict.fromkeys(str(row.get(group_field, "")) for row in data))
        x_values = list(dict.fromkeys(str(row.get(x_field, "")) for row in data))
        series = []
        for g in groups:
            g_data = []
            for x in x_values:
                val = next(
                    (row.get(y_field, 0) for row in data
                     if str(row.get(x_field, "")) == x and str(row.get(group_field, "")) == g),
                    None,
                )
                g_data.append(val)
            series.append({"type": "line", "name": g, "data": g_data, "smooth": True})
        return {
            "title": {"text": question[:40], "left": "center"},
            "tooltip": {"trigger": "axis"},
            "legend": {"data": groups, "top": 30},
            "xAxis": {"type": "category", "data": x_values},
            "yAxis": {"type": "value"},
            "series": series,
            "grid": {"top": 80},
        }

    # 单折线
    x_values = [str(row.get(x_field, "")) for row in data]
    y_values = [row.get(y_field, 0) for row in data]
    return {
        "title": {"text": question[:40], "left": "center"},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": x_values},
        "yAxis": {"type": "value"},
        "series": [{"type": "line", "data": y_values, "smooth": True, "name": y_field}],
    }


def _build_multi_line(data, fm, question):
    x_field = fm.get("x", "")
    y_fields = fm.get("y", [])
    if isinstance(y_fields, str):
        y_fields = [y_fields]

    x_values = [str(row.get(x_field, "")) for row in data]
    series = []
    for yf in y_fields:
        series.append({
            "type": "line",
            "name": yf,
            "data": [row.get(yf, 0) for row in data],
            "smooth": True,
        })

    return {
        "title": {"text": question[:40], "left": "center"},
        "tooltip": {"trigger": "axis"},
        "legend": {"data": y_fields, "top": 30},
        "xAxis": {"type": "category", "data": x_values},
        "yAxis": {"type": "value"},
        "series": series,
        "grid": {"top": 80},
    }


def _build_area(data, fm, question):
    option = _build_line(data, fm, question)
    for s in option.get("series", []):
        s["areaStyle"] = {}
    return option


def _build_pie(data, fm, question):
    cat_field = fm.get("category", "")
    val_field = fm.get("value", "")
    pie_data = [
        {"name": str(row.get(cat_field, "")), "value": row.get(val_field, 0)}
        for row in data
    ]
    return {
        "title": {"text": question[:40], "left": "center"},
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
        "legend": {"orient": "vertical", "left": "left", "top": "middle"},
        "series": [{
            "type": "pie",
            "radius": "60%",
            "center": ["55%", "55%"],
            "data": pie_data,
            "label": {"formatter": "{b}: {d}%"},
            "emphasis": {"itemStyle": {"shadowBlur": 10, "shadowColor": "rgba(0,0,0,0.3)"}},
        }],
    }


def _build_scatter(data, fm, question):
    x_field = fm.get("x", "")
    y_field = fm.get("y", "")
    scatter_data = [[row.get(x_field, 0), row.get(y_field, 0)] for row in data]
    return {
        "title": {"text": question[:40], "left": "center"},
        "tooltip": {"trigger": "item", "formatter": f"{x_field}: {{c0}}<br/>{y_field}: {{c1}}"},
        "xAxis": {"type": "value", "name": x_field},
        "yAxis": {"type": "value", "name": y_field},
        "series": [{"type": "scatter", "data": scatter_data, "symbolSize": 10}],
    }


def _build_kpi_card(data, fm, question):
    value_field = fm.get("value", "")
    value = data[0].get(value_field, 0) if data else 0
    return {"kpi_card": True, "title": question[:30], "value": value, "unit": ""}


def _build_table(data, fm, question):
    columns = list(data[0].keys()) if data else []
    return {"table": True, "columns": columns, "rows": data[:100]}
