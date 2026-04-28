"""Generator 测试 — mock LLM 调用。"""
import json
from unittest.mock import patch, MagicMock

from chart_engine.core.generator import generate_echarts
from chart_engine.core.profiler import profile_data
from chart_engine.core.selector import select_chart
from chart_engine.config import LLMConfig, ProfilerConfig, SelectorConfig
from chart_engine.core.models import ChartType


def _setup(data, question):
    prof = profile_data(data, ProfilerConfig())
    rec = select_chart(prof, question, SelectorConfig())
    return prof, rec


def test_kpi_card_no_llm(single_value_data):
    prof, rec = _setup(single_value_data, "总设备数")
    assert rec.chart_type == ChartType.KPI_CARD
    result = generate_echarts("总设备数", "SELECT COUNT(*)", single_value_data, prof, rec, LLMConfig())
    assert result["kpi_card"] is True
    assert result["value"] == 50


def test_table_fallback_no_llm():
    prof, rec = _setup([], "随便")
    assert rec.chart_type == ChartType.TABLE
    result = generate_echarts("随便", "SELECT 1", [], prof, rec, LLMConfig())
    assert result["table"] is True


@patch("chart_engine.core.generator.litellm")
def test_bar_chart_calls_llm(mock_litellm, categorical_data):
    expected_option = {
        "title": {"text": "各厂商设备数"},
        "xAxis": {"type": "category", "data": ["HUAWEI", "ZTE", "CISCO", "JUNIPER"]},
        "yAxis": {"type": "value"},
        "series": [{"type": "bar", "data": [20, 15, 10, 5]}],
    }
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({"option": expected_option})
    mock_litellm.completion.return_value = mock_response

    prof, rec = _setup(categorical_data, "各厂商设备数")
    result = generate_echarts("各厂商设备数", "SELECT ...", categorical_data, prof, rec, LLMConfig())

    assert mock_litellm.completion.called
    assert result["title"]["text"] == "各厂商设备数"
    assert result["series"][0]["type"] == "bar"


@patch("chart_engine.core.generator.litellm")
def test_llm_returns_invalid_json_fallback_to_table(mock_litellm, categorical_data):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "这不是JSON"
    mock_litellm.completion.return_value = mock_response

    prof, rec = _setup(categorical_data, "各厂商设备数")
    result = generate_echarts("各厂商设备数", "SELECT ...", categorical_data, prof, rec, LLMConfig())
    assert result["table"] is True


@patch("chart_engine.core.generator.litellm")
def test_llm_exception_fallback_to_table(mock_litellm, categorical_data):
    mock_litellm.completion.side_effect = Exception("connection timeout")

    prof, rec = _setup(categorical_data, "各厂商设备数")
    result = generate_echarts("各厂商设备数", "SELECT ...", categorical_data, prof, rec, LLMConfig())
    assert result["table"] is True
