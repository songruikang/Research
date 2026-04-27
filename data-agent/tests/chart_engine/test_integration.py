"""集成测试 — 从真实数据走完整管线（mock LLM）。"""
import json
from unittest.mock import patch, MagicMock

from chart_engine import generate_chart
from chart_engine.profiler import profile_data
from chart_engine.selector import select_chart
from chart_engine.config import ProfilerConfig, SelectorConfig


class TestProfilerSelectorIntegration:
    def test_time_series_flow(self, time_series_data):
        prof = profile_data(time_series_data, ProfilerConfig())
        rec = select_chart(prof, "CPU 利用率趋势", SelectorConfig())
        assert rec.chart_type.value == "line"
        assert rec.field_mapping["x"] == "collect_time"
        assert rec.field_mapping["y"] == "cpu_usage_avg_pct"

    def test_categorical_flow(self, categorical_data):
        prof = profile_data(categorical_data, ProfilerConfig())
        rec = select_chart(prof, "各厂商设备数量", SelectorConfig())
        assert rec.chart_type.value == "bar"

    def test_proportion_flow(self, proportion_data):
        prof = profile_data(proportion_data, ProfilerConfig())
        rec = select_chart(prof, "设备状态占比", SelectorConfig())
        assert rec.chart_type.value == "pie"

    def test_single_value_flow(self, single_value_data):
        prof = profile_data(single_value_data, ProfilerConfig())
        rec = select_chart(prof, "总设备数", SelectorConfig())
        assert rec.chart_type.value == "kpi_card"


class TestFullPipelineWithMockLLM:
    @patch("chart_engine.generator.litellm")
    def test_bar_chart_full_pipeline(self, mock_litellm, categorical_data):
        mock_option = {
            "title": {"text": "各厂商设备数量"},
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": ["HUAWEI", "ZTE", "CISCO", "JUNIPER"]},
            "yAxis": {"type": "value"},
            "series": [{"type": "bar", "data": [20, 15, 10, 5]}],
        }
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({"option": mock_option})
        mock_litellm.completion.return_value = mock_response

        result = generate_chart("各厂商设备数量", "SELECT vendor, COUNT(*) ...", categorical_data)
        assert result.chart_type == "bar"
        assert result.fallback is False
        assert "color" in result.echarts_option
        assert result.echarts_option["series"][0]["type"] == "bar"

    def test_kpi_card_no_llm(self, single_value_data):
        result = generate_chart("总设备数", "SELECT COUNT(*)", single_value_data)
        assert result.chart_type == "kpi_card"
        assert result.echarts_option["value"] == 50
