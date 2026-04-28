"""CLI 测试。"""
import json
import tempfile
from unittest.mock import patch

from chart_engine.cli.main import main


def test_mock_mode(categorical_data):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(categorical_data, f)
        f.flush()
        with patch("sys.argv", ["chart_engine", "--question", "各厂商设备数", "--data", f.name, "--mock"]):
            result = main(return_result=True)
    assert result is not None
    assert result["chart_type"] == "bar"
    assert "field_mapping" in result


def test_output_to_file(categorical_data):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as data_file:
        json.dump(categorical_data, data_file)
        data_file.flush()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as out_file:
            out_path = out_file.name
        with patch("sys.argv", ["chart_engine", "--question", "各厂商设备数", "--data", data_file.name, "--mock", "--output", out_path]):
            main()
        with open(out_path) as f:
            output = json.load(f)
        assert "chart_type" in output
