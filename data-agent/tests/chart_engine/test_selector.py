"""Selector 单元测试。"""
from chart_engine.profiler import profile_data
from chart_engine.selector import select_chart
from chart_engine.config import ProfilerConfig, SelectorConfig
from chart_engine.models import ChartType


def _profile(data):
    return profile_data(data, ProfilerConfig())


def test_single_value_selects_kpi_card(single_value_data):
    prof = _profile(single_value_data)
    rec = select_chart(prof, "总设备数是多少", SelectorConfig())
    assert rec.chart_type == ChartType.KPI_CARD


def test_time_series_selects_line(time_series_data):
    prof = _profile(time_series_data)
    rec = select_chart(prof, "CPU利用率趋势", SelectorConfig())
    assert rec.chart_type == ChartType.LINE
    assert "collect_time" in rec.field_mapping.values()


def test_multi_measure_time_selects_multi_line(multi_measure_time_data):
    prof = _profile(multi_measure_time_data)
    rec = select_chart(prof, "CPU和内存趋势", SelectorConfig())
    assert rec.chart_type == ChartType.MULTI_LINE


def test_categorical_selects_bar(categorical_data):
    prof = _profile(categorical_data)
    rec = select_chart(prof, "各厂商设备数量", SelectorConfig())
    assert rec.chart_type == ChartType.BAR


def test_proportion_intent_selects_pie(proportion_data):
    prof = _profile(proportion_data)
    rec = select_chart(prof, "设备状态占比分布", SelectorConfig())
    assert rec.chart_type == ChartType.PIE


def test_pie_cardinality_guard(proportion_data):
    data = [{"status": f"S{i}", "count": 10 + i} for i in range(10)]
    prof = _profile(data)
    rec = select_chart(prof, "状态占比", SelectorConfig(pie_max_categories=7))
    assert rec.chart_type != ChartType.PIE


def test_two_dim_selects_grouped_bar(two_dim_data):
    prof = _profile(two_dim_data)
    rec = select_chart(prof, "各区域各厂商设备数", SelectorConfig())
    assert rec.chart_type == ChartType.GROUPED_BAR


def test_two_dim_composition_selects_stacked_bar(two_dim_data):
    prof = _profile(two_dim_data)
    rec = select_chart(prof, "各区域设备构成分布", SelectorConfig())
    assert rec.chart_type == ChartType.STACKED_BAR


def test_scatter_data_selects_scatter(scatter_data):
    prof = _profile(scatter_data)
    rec = select_chart(prof, "时延与丢包率关系", SelectorConfig())
    assert rec.chart_type == ChartType.SCATTER


def test_empty_data_selects_table():
    prof = _profile([])
    rec = select_chart(prof, "随便查点什么", SelectorConfig())
    assert rec.chart_type == ChartType.TABLE


def test_field_mapping_has_required_keys(categorical_data):
    prof = _profile(categorical_data)
    rec = select_chart(prof, "各厂商设备数", SelectorConfig())
    assert "x" in rec.field_mapping
    assert "y" in rec.field_mapping


def test_recommendation_has_reasoning(categorical_data):
    prof = _profile(categorical_data)
    rec = select_chart(prof, "各厂商设备数", SelectorConfig())
    assert len(rec.reasoning) > 0
