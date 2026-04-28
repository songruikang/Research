"""Step 1: 数据画像 — 从 SQL 结果提取每列的统计特征。纯计算，不调 LLM。"""
from __future__ import annotations

from datetime import datetime, timedelta
from dateutil import parser as dateutil_parser

from chart_engine.config import ProfilerConfig
from chart_engine.core.models import ColumnProfile, ColumnDType, DataProfile


def profile_data(data: list[dict], config: ProfilerConfig) -> DataProfile:
    if not data:
        return DataProfile(row_count=0, col_count=0, columns=[])
    columns = list(data[0].keys())
    row_count = len(data)
    col_profiles = []
    for col_name in columns:
        values = [row.get(col_name) for row in data]
        col_profiles.append(_profile_column(col_name, values, row_count, config))
    return DataProfile(row_count=row_count, col_count=len(columns), columns=col_profiles)


def _profile_column(name, values, row_count, config):
    non_null = [v for v in values if v is not None]
    null_count = len(values) - len(non_null)
    distinct = list(set(non_null))
    distinct_count = len(distinct)
    distinct_ratio = distinct_count / row_count if row_count > 0 else 0
    dtype = _infer_dtype(non_null, distinct_count, distinct_ratio)
    sample_values = distinct[:config.max_column_samples]
    is_measure = dtype == ColumnDType.QUANTITATIVE
    is_dimension = dtype in (ColumnDType.CATEGORICAL, ColumnDType.TEMPORAL)
    time_granularity = None
    if dtype == ColumnDType.TEMPORAL:
        parsed_times = _parse_times(non_null[:50])
        if parsed_times:
            time_granularity = _infer_time_granularity(parsed_times)
    min_val = max_val = None
    if dtype == ColumnDType.QUANTITATIVE and non_null:
        numeric_vals = [_to_float(v) for v in non_null if _to_float(v) is not None]
        if numeric_vals:
            min_val = min(numeric_vals)
            max_val = max(numeric_vals)
    return ColumnProfile(
        name=name, dtype=dtype, distinct_count=distinct_count, distinct_ratio=distinct_ratio,
        null_count=null_count, sample_values=sample_values, is_dimension=is_dimension,
        is_measure=is_measure, time_granularity=time_granularity, min_val=min_val, max_val=max_val,
    )


def _infer_dtype(non_null, distinct_count, distinct_ratio):
    if not non_null:
        return ColumnDType.CATEGORICAL
    sample = non_null[:20]
    if _is_temporal(sample):
        return ColumnDType.TEMPORAL
    if _is_numeric(sample):
        if distinct_ratio > 0.9 and distinct_count > 50:
            return ColumnDType.IDENTIFIER
        return ColumnDType.QUANTITATIVE
    if distinct_ratio > 0.8 and distinct_count > 50:
        return ColumnDType.IDENTIFIER
    return ColumnDType.CATEGORICAL


def _is_temporal(sample):
    if not sample:
        return False
    parsed_count = 0
    for v in sample:
        if isinstance(v, datetime):
            parsed_count += 1
            continue
        if not isinstance(v, str):
            continue
        try:
            dateutil_parser.parse(str(v))
            parsed_count += 1
        except (ValueError, TypeError, OverflowError):
            pass
    return parsed_count / len(sample) >= 0.8


def _is_numeric(sample):
    if not sample:
        return False
    numeric_count = 0
    for v in sample:
        if isinstance(v, (int, float)):
            numeric_count += 1
        elif isinstance(v, str):
            try:
                float(v)
                numeric_count += 1
            except (ValueError, TypeError):
                pass
    return numeric_count / len(sample) >= 0.8


def _to_float(v):
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _parse_times(values):
    results = []
    for v in values:
        if isinstance(v, datetime):
            results.append(v)
            continue
        try:
            results.append(dateutil_parser.parse(str(v)))
        except (ValueError, TypeError, OverflowError):
            pass
    return results


def _infer_time_granularity(times):
    sorted_times = sorted(set(times))
    if len(sorted_times) < 2:
        return "day"
    diffs = [sorted_times[i+1] - sorted_times[i] for i in range(min(10, len(sorted_times)-1))]
    median_diff = sorted(diffs)[len(diffs)//2]
    if median_diff >= timedelta(days=300):
        return "year"
    elif median_diff >= timedelta(days=25):
        return "month"
    elif median_diff >= timedelta(days=5):
        return "week"
    elif median_diff >= timedelta(hours=20):
        return "day"
    else:
        return "hour"
