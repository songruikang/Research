"""Chart Engine: SQL 查询结果 → ECharts option JSON。"""
from chart_engine.core.models import ChartResult, ChartType, DataProfile


def generate_chart(
    question: str,
    sql: str,
    data: list[dict],
    config_path: str | None = None,
) -> ChartResult:
    """主入口：生成图表（LLM 模式）。"""
    from chart_engine.config import load_config
    from chart_engine.core.profiler import profile_data
    from chart_engine.core.selector import select_chart
    from chart_engine.core.generator import generate_echarts
    from chart_engine.core.validator import validate_and_fix

    config = load_config(config_path)
    prof = profile_data(data, config.profiler)
    rec = select_chart(prof, question, config.selector)
    raw_option = generate_echarts(question, sql, data, prof, rec, config.llm)
    result = validate_and_fix(raw_option, rec, prof, question, config.selector)
    return result


__all__ = ["generate_chart", "ChartResult", "ChartType", "DataProfile"]
