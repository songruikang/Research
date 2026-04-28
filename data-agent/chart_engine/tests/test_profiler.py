"""Profiler 单元测试。"""
from chart_engine.core.profiler import profile_data
from chart_engine.config import ProfilerConfig
from chart_engine.core.models import ColumnDType


def test_time_series_profiling(time_series_data):
    prof = profile_data(time_series_data, ProfilerConfig())
    assert prof.row_count == 5
    assert prof.col_count == 3
    col_map = {c.name: c for c in prof.columns}
    time_col = col_map["collect_time"]
    assert time_col.dtype == ColumnDType.TEMPORAL
    assert time_col.is_dimension is True
    assert time_col.is_measure is False
    assert time_col.time_granularity == "day"
    cpu_col = col_map["cpu_usage_avg_pct"]
    assert cpu_col.dtype == ColumnDType.QUANTITATIVE
    assert cpu_col.is_measure is True
    assert cpu_col.is_dimension is False


def test_categorical_profiling(categorical_data):
    prof = profile_data(categorical_data, ProfilerConfig())
    col_map = {c.name: c for c in prof.columns}
    vendor_col = col_map["vendor"]
    assert vendor_col.dtype == ColumnDType.CATEGORICAL
    assert vendor_col.distinct_count == 4
    assert vendor_col.is_dimension is True
    count_col = col_map["device_count"]
    assert count_col.dtype == ColumnDType.QUANTITATIVE
    assert count_col.is_measure is True


def test_single_value_profiling(single_value_data):
    prof = profile_data(single_value_data, ProfilerConfig())
    assert prof.row_count == 1
    assert prof.col_count == 1
    assert prof.measures == ["total_devices"]


def test_null_handling():
    data = [{"name": "A", "val": 10}, {"name": "B", "val": None}, {"name": None, "val": 30}]
    prof = profile_data(data, ProfilerConfig())
    col_map = {c.name: c for c in prof.columns}
    assert col_map["val"].null_count == 1
    assert col_map["name"].null_count == 1


def test_high_cardinality_identifier():
    data = [{"device_id": f"DEV-{i:04d}", "status": "UP"} for i in range(100)]
    prof = profile_data(data, ProfilerConfig())
    col_map = {c.name: c for c in prof.columns}
    assert col_map["device_id"].dtype == ColumnDType.IDENTIFIER
    assert col_map["device_id"].is_dimension is False


def test_sample_values_limited(categorical_data):
    prof = profile_data(categorical_data, ProfilerConfig(max_column_samples=3))
    for col in prof.columns:
        assert len(col.sample_values) <= 3


def test_dimensions_and_measures(two_dim_data):
    prof = profile_data(two_dim_data, ProfilerConfig())
    assert "region" in prof.dimensions
    assert "vendor" in prof.dimensions
    assert "count" in prof.measures
    assert len(prof.temporals) == 0


def test_empty_data():
    prof = profile_data([], ProfilerConfig())
    assert prof.row_count == 0
    assert prof.col_count == 0
    assert prof.columns == []
