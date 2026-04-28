"""CLI 入口：python -m chart_engine。"""
from __future__ import annotations

import argparse
import json
import sys

from chart_engine.config import load_config
from chart_engine.profiler import profile_data
from chart_engine.selector import select_chart


def main(return_result: bool = False):
    parser = argparse.ArgumentParser(prog="chart_engine", description="SQL 查询结果 → ECharts option JSON")
    parser.add_argument("--question", "-q", required=True, help="用户自然语言问题")
    parser.add_argument("--sql", "-s", default="", help="SQL 语句（可选）")
    parser.add_argument("--data", "-d", required=True, help="数据文件路径（JSON 数组）")
    parser.add_argument("--output", "-o", help="输出文件路径（默认 stdout）")
    parser.add_argument("--config", "-c", help="配置文件路径")
    parser.add_argument("--model", "-m", help="覆盖 LLM 模型名")
    parser.add_argument("--mock", action="store_true", help="Mock 模式：只跑 profiler + selector，不调 LLM")

    args = parser.parse_args()

    with open(args.data) as f:
        data = json.load(f)

    config = load_config(args.config)
    if args.model:
        config.llm.model = args.model

    if args.mock:
        profile = profile_data(data, config.profiler)
        rec = select_chart(profile, args.question, config.selector)
        result = {
            "chart_type": rec.chart_type.value,
            "field_mapping": rec.field_mapping,
            "reasoning": rec.reasoning,
            "alternatives": [a.value for a in rec.alternatives],
            "profile": {
                "row_count": profile.row_count,
                "dimensions": profile.dimensions,
                "measures": profile.measures,
                "temporals": profile.temporals,
            },
        }
    else:
        from chart_engine import generate_chart
        chart_result = generate_chart(args.question, args.sql, data, args.config)
        result = {
            "chart_type": chart_result.chart_type,
            "echarts_option": chart_result.echarts_option,
            "reasoning": chart_result.reasoning,
            "warnings": chart_result.warnings,
            "fallback": chart_result.fallback,
        }

    output_str = json.dumps(result, ensure_ascii=False, indent=2, default=str)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_str)
        print(f"已写入 {args.output}", file=sys.stderr)
    elif return_result:
        return result
    else:
        print(output_str)

    if return_result:
        return result
