"""Validator 单元测试。"""
from chart_engine.validator import validate_and_fix
from chart_engine.models import ChartType, ChartRecommendation, DataProfile, ColumnProfile, ColumnDType
from chart_engine.config import SelectorConfig


def _dummy_profile(row_count=10):
    return DataProfile(
        row_count=row_count, col_count=2,
        columns=[
            ColumnProfile("cat", ColumnDType.CATEGORICAL, 5, 0.5, 0, ["A", "B"], True, False),
            ColumnProfile("val", ColumnDType.QUANTITATIVE, 10, 1.0, 0, [1, 2], False, True),
        ],
    )


def _dummy_rec(chart_type=ChartType.BAR):
    return ChartRecommendation(chart_type=chart_type, field_mapping={"x": "cat", "y": "val"}, reasoning="test")


def test_valid_option_passes():
    option = {
        "title": {"text": "测试"}, "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": ["A", "B"]},
        "yAxis": {"type": "value"},
        "series": [{"type": "bar", "data": [10, 20]}],
        "color": ["#5470c6"],
    }
    result = validate_and_fix(option, _dummy_rec(), _dummy_profile(), "测试", SelectorConfig())
    assert result.echarts_option == option
    assert result.fallback is False
    assert len(result.warnings) == 0


def test_missing_title_auto_fixed():
    option = {"series": [{"type": "bar", "data": [10]}]}
    result = validate_and_fix(option, _dummy_rec(), _dummy_profile(), "我的问题", SelectorConfig())
    assert "title" in result.echarts_option
    assert any("title" in w for w in result.warnings)


def test_missing_tooltip_auto_fixed():
    option = {"title": {"text": "ok"}, "series": [{"type": "bar", "data": [10]}]}
    result = validate_and_fix(option, _dummy_rec(), _dummy_profile(), "q", SelectorConfig())
    assert "tooltip" in result.echarts_option


def test_missing_color_auto_fixed():
    option = {"title": {"text": "ok"}, "tooltip": {}, "series": [{"type": "bar", "data": [10]}]}
    result = validate_and_fix(option, _dummy_rec(), _dummy_profile(), "q", SelectorConfig())
    assert "color" in result.echarts_option
    assert len(result.echarts_option["color"]) == 10


def test_missing_series_fallback_to_table():
    option = {"title": {"text": "啥也没有"}}
    result = validate_and_fix(option, _dummy_rec(), _dummy_profile(), "q", SelectorConfig())
    assert result.fallback is True


def test_kpi_card_passes_through():
    option = {"kpi_card": True, "title": "总数", "value": 42, "unit": "台"}
    rec = _dummy_rec(ChartType.KPI_CARD)
    result = validate_and_fix(option, rec, _dummy_profile(1), "总数", SelectorConfig())
    assert result.echarts_option == option
    assert result.fallback is False


def test_table_passes_through():
    option = {"table": True, "columns": ["a"], "rows": [{"a": 1}]}
    rec = _dummy_rec(ChartType.TABLE)
    result = validate_and_fix(option, rec, _dummy_profile(), "q", SelectorConfig())
    assert result.echarts_option == option
    assert result.fallback is False


def test_pie_high_cardinality_downgrade(high_cardinality_pie_data):
    option = {
        "title": {"text": "分布"}, "tooltip": {},
        "series": [{"type": "pie", "data": [{"name": f"Cat-{i:02d}", "value": 100 - i * 3} for i in range(15)]}],
    }
    rec = _dummy_rec(ChartType.PIE)
    profile = DataProfile(
        row_count=15, col_count=2,
        columns=[
            ColumnProfile("category", ColumnDType.CATEGORICAL, 15, 1.0, 0, [], True, False),
            ColumnProfile("value", ColumnDType.QUANTITATIVE, 15, 1.0, 0, [], False, True),
        ],
    )
    result = validate_and_fix(option, rec, profile, "分布", SelectorConfig(pie_max_categories=7))
    assert result.echarts_option["series"][0]["type"] == "bar"
    assert any("降级" in w for w in result.warnings)
