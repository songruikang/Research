"""共享测试数据。"""
import pytest


@pytest.fixture
def time_series_data():
    """CPU 使用率时序数据 — 典型折线图场景。"""
    return [
        {"collect_time": "2026-04-01", "ne_name": "PE-BJ-01", "cpu_usage_avg_pct": 45.2},
        {"collect_time": "2026-04-02", "ne_name": "PE-BJ-01", "cpu_usage_avg_pct": 52.1},
        {"collect_time": "2026-04-03", "ne_name": "PE-BJ-01", "cpu_usage_avg_pct": 48.7},
        {"collect_time": "2026-04-04", "ne_name": "PE-BJ-01", "cpu_usage_avg_pct": 61.3},
        {"collect_time": "2026-04-05", "ne_name": "PE-BJ-01", "cpu_usage_avg_pct": 55.9},
    ]


@pytest.fixture
def categorical_data():
    """各厂商设备数 — 典型柱状图场景。"""
    return [
        {"vendor": "HUAWEI", "device_count": 20},
        {"vendor": "ZTE", "device_count": 15},
        {"vendor": "CISCO", "device_count": 10},
        {"vendor": "JUNIPER", "device_count": 5},
    ]


@pytest.fixture
def single_value_data():
    """单值结果 — KPI 卡片场景。"""
    return [{"total_devices": 50}]


@pytest.fixture
def two_dim_data():
    """双维度数据 — 分组柱状图场景。"""
    return [
        {"region": "华北", "vendor": "HUAWEI", "count": 8},
        {"region": "华北", "vendor": "ZTE", "count": 5},
        {"region": "华东", "vendor": "HUAWEI", "count": 12},
        {"region": "华东", "vendor": "ZTE", "count": 7},
        {"region": "华南", "vendor": "HUAWEI", "count": 6},
        {"region": "华南", "vendor": "ZTE", "count": 3},
    ]


@pytest.fixture
def proportion_data():
    """状态分布 — 饼图场景。"""
    return [
        {"oper_status": "UP", "count": 35},
        {"oper_status": "DOWN", "count": 8},
        {"oper_status": "DEGRADED", "count": 7},
    ]


@pytest.fixture
def multi_measure_time_data():
    """多指标时序 — 多折线场景。"""
    return [
        {"collect_time": "2026-04-01", "cpu_usage_avg_pct": 45.2, "memory_usage_avg_pct": 60.1},
        {"collect_time": "2026-04-02", "cpu_usage_avg_pct": 52.1, "memory_usage_avg_pct": 63.5},
        {"collect_time": "2026-04-03", "cpu_usage_avg_pct": 48.7, "memory_usage_avg_pct": 58.2},
    ]


@pytest.fixture
def scatter_data():
    """时延 vs 丢包率 — 散点图场景。"""
    return [
        {"latency_avg_ms": 12.5, "packet_loss_rate_pct": 0.01, "tunnel_name": "T-001"},
        {"latency_avg_ms": 25.3, "packet_loss_rate_pct": 0.05, "tunnel_name": "T-002"},
        {"latency_avg_ms": 8.1, "packet_loss_rate_pct": 0.00, "tunnel_name": "T-003"},
        {"latency_avg_ms": 45.7, "packet_loss_rate_pct": 0.12, "tunnel_name": "T-004"},
        {"latency_avg_ms": 15.2, "packet_loss_rate_pct": 0.02, "tunnel_name": "T-005"},
    ]


@pytest.fixture
def high_cardinality_pie_data():
    """高基数分类 — 应触发饼图→柱状图降级。"""
    return [{"category": f"Cat-{i:02d}", "value": 100 - i * 3} for i in range(15)]
