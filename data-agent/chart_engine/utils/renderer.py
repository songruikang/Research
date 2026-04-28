"""ECharts option → 可浏览器打开的 HTML 文件。"""
from __future__ import annotations

import json
from pathlib import Path


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"></script>
<style>
  body {{ margin: 0; padding: 20px; background: #f5f5f5; font-family: -apple-system, sans-serif; }}
  .card {{ background: #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 20px; padding: 20px; }}
  .meta {{ color: #666; font-size: 13px; margin-bottom: 12px; line-height: 1.6; }}
  .meta b {{ color: #333; }}
  .chart-container {{ width: 100%; height: {height}px; }}
  .kpi-card {{ text-align: center; padding: 40px 20px; }}
  .kpi-value {{ font-size: 48px; font-weight: bold; color: #5470c6; }}
  .kpi-title {{ font-size: 16px; color: #666; margin-top: 8px; }}
  table.data-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  table.data-table th {{ background: #f0f0f0; padding: 8px 12px; text-align: left; border: 1px solid #ddd; }}
  table.data-table td {{ padding: 8px 12px; border: 1px solid #ddd; }}
  table.data-table tr:hover {{ background: #f9f9f9; }}
</style>
</head>
<body>
{content}
</body>
</html>"""

CHART_BLOCK = """
<div class="card">
  <div class="meta">
    <b>问题：</b>{question}<br>
    <b>SQL：</b><code>{sql}</code><br>
    <b>图表类型：</b>{chart_type} &nbsp; <b>数据行数：</b>{data_rows}
    {warnings_html}
  </div>
  <div id="{chart_id}" class="chart-container"></div>
</div>
<script>
  (function() {{
    var chart = echarts.init(document.getElementById('{chart_id}'));
    var option = {option_json};
    chart.setOption(option);
    window.addEventListener('resize', function() {{ chart.resize(); }});
  }})();
</script>
"""

KPI_BLOCK = """
<div class="card">
  <div class="meta">
    <b>问题：</b>{question}<br>
    <b>SQL：</b><code>{sql}</code><br>
    <b>图表类型：</b>kpi_card
  </div>
  <div class="kpi-card">
    <div class="kpi-value">{value}</div>
    <div class="kpi-title">{title} {unit}</div>
  </div>
</div>
"""

TABLE_BLOCK = """
<div class="card">
  <div class="meta">
    <b>问题：</b>{question}<br>
    <b>SQL：</b><code>{sql}</code><br>
    <b>图表类型：</b>table &nbsp; <b>数据行数：</b>{data_rows}
  </div>
  <table class="data-table">
    <thead><tr>{headers}</tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
"""


def render_chart_html(
    echarts_option: dict,
    question: str = "",
    sql: str = "",
    chart_type: str = "",
    data_rows: int = 0,
    warnings: list[str] | None = None,
    chart_id: str = "chart_0",
) -> str:
    """把单个图表渲染为 HTML 片段。"""
    warnings = warnings or []

    # KPI 卡片
    if echarts_option.get("kpi_card"):
        return KPI_BLOCK.format(
            question=_escape(question),
            sql=_escape(sql),
            value=echarts_option.get("value", 0),
            title=_escape(str(echarts_option.get("title", ""))),
            unit=_escape(str(echarts_option.get("unit", ""))),
        )

    # 表格
    if echarts_option.get("table"):
        columns = echarts_option.get("columns", [])
        rows_data = echarts_option.get("rows", [])
        headers = "".join(f"<th>{_escape(str(c))}</th>" for c in columns)
        rows = ""
        for row in rows_data[:50]:
            cells = "".join(f"<td>{_escape(str(row.get(c, '')))}</td>" for c in columns)
            rows += f"<tr>{cells}</tr>"
        return TABLE_BLOCK.format(
            question=_escape(question), sql=_escape(sql),
            data_rows=len(rows_data), headers=headers, rows=rows,
        )

    # 标准 ECharts 图表
    warnings_html = ""
    if warnings:
        warnings_html = "<br><b>警告：</b>" + "；".join(warnings)

    return CHART_BLOCK.format(
        question=_escape(question),
        sql=_escape(sql),
        chart_type=chart_type,
        data_rows=data_rows,
        warnings_html=warnings_html,
        chart_id=chart_id,
        option_json=json.dumps(echarts_option, ensure_ascii=False, default=str),
    )


def render_page(charts: list[dict], title: str = "Chart Engine 图表预览") -> str:
    """把多个图表渲染为完整 HTML 页面。

    charts: [{"echarts_option": {...}, "question": "...", "sql": "...", "chart_type": "...", ...}, ...]
    """
    blocks = []
    for i, c in enumerate(charts):
        block = render_chart_html(
            echarts_option=c.get("echarts_option", {}),
            question=c.get("question", ""),
            sql=c.get("sql", ""),
            chart_type=c.get("chart_type", ""),
            data_rows=c.get("data_rows", 0),
            warnings=c.get("warnings", []),
            chart_id=f"chart_{i}",
        )
        blocks.append(block)

    return HTML_TEMPLATE.format(
        title=_escape(title),
        height=450,
        content="\n".join(blocks),
    )


def save_html(charts: list[dict], output_path: str, title: str = "Chart Engine 图表预览"):
    """保存为 HTML 文件。"""
    html = render_page(charts, title)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def _escape(text: str) -> str:
    """基本 HTML 转义。"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
