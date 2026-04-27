# Chart Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independent chart generation module that takes SQL query results and produces ECharts option JSON through a 4-step pipeline: data profiling → chart selection → spec generation → validation.

**Architecture:** Core Python library (`chart_engine/`) with 4-step pipeline. Each step is a standalone module with clear input/output contracts. LiteLLM for unified LLM access. FastAPI for WrenAI integration. CLI for testing.

**Tech Stack:** Python 3.11+, LiteLLM, FastAPI, Pydantic, DuckDB, PyYAML

---

## File Structure

```
data-agent/
├── chart_engine/
│   ├── __init__.py          # Public API: generate_chart()
│   ├── models.py            # All Pydantic data models
│   ├── config.py            # Config loading (YAML + env)
│   ├── profiler.py          # Step 1: Data profiling (pure computation)
│   ├── selector.py          # Step 2: Chart type selection (rules engine)
│   ├── generator.py         # Step 3: ECharts option generation (LLM)
│   ├── validator.py         # Step 4: Validation + auto-correction
│   ├── examples.py          # Few-shot example management
│   ├── cli.py               # CLI entry point (__main__.py delegates here)
│   ├── server.py            # FastAPI service
│   ├── __main__.py          # python -m chart_engine
│   ├── prompts/
│   │   ├── __init__.py
│   │   └── echarts_gen.py   # Prompt templates
│   └── config.yaml.example  # Config template
├── tests/
│   └── chart_engine/
│       ├── __init__.py
│       ├── test_profiler.py
│       ├── test_selector.py
│       ├── test_validator.py
│       ├── test_generator.py  # With LLM mock
│       ├── test_cli.py
│       ├── test_integration.py
│       └── conftest.py        # Shared fixtures (sample data)
```

---

### Task 1: Project Scaffolding — Data Models + Config

**Files:**
- Create: `chart_engine/__init__.py`
- Create: `chart_engine/models.py`
- Create: `chart_engine/config.py`
- Create: `chart_engine/config.yaml.example`
- Create: `chart_engine/__main__.py`
- Create: `tests/chart_engine/__init__.py`
- Create: `tests/chart_engine/conftest.py`

- [ ] **Step 1: Create config.yaml.example**

```yaml
# chart_engine/config.yaml.example
llm:
  model: ollama_chat/qwen3:32b
  api_base: http://10.220.239.55:11343
  timeout: 120
  temperature: 0

server:
  host: 0.0.0.0
  port: 8100

examples:
  few_shot_path: eval/few_shot_pairs.json
  db_init_sql: telecom/output/telecom_init.sql

profiler:
  sample_size: 50
  max_column_samples: 5

selector:
  pie_max_categories: 7
  bar_max_categories: 20
```

- [ ] **Step 2: Create data models**

```python
# chart_engine/models.py
"""Chart Engine 的所有数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ChartType(str, Enum):
    BAR = "bar"
    GROUPED_BAR = "grouped_bar"
    STACKED_BAR = "stacked_bar"
    LINE = "line"
    MULTI_LINE = "multi_line"
    AREA = "area"
    PIE = "pie"
    SCATTER = "scatter"
    HEATMAP = "heatmap"
    GAUGE = "gauge"
    FUNNEL = "funnel"
    KPI_CARD = "kpi_card"
    TABLE = "table"


class ColumnDType(str, Enum):
    TEMPORAL = "temporal"
    QUANTITATIVE = "quantitative"
    CATEGORICAL = "categorical"
    IDENTIFIER = "identifier"


@dataclass
class ColumnProfile:
    name: str
    dtype: ColumnDType
    distinct_count: int
    distinct_ratio: float
    null_count: int
    sample_values: list
    is_dimension: bool
    is_measure: bool
    time_granularity: str | None = None  # year|month|week|day|hour
    min_val: float | None = None
    max_val: float | None = None


@dataclass
class DataProfile:
    row_count: int
    col_count: int
    columns: list[ColumnProfile]

    @property
    def dimensions(self) -> list[str]:
        return [c.name for c in self.columns if c.is_dimension]

    @property
    def measures(self) -> list[str]:
        return [c.name for c in self.columns if c.is_measure]

    @property
    def temporals(self) -> list[str]:
        return [c.name for c in self.columns if c.dtype == ColumnDType.TEMPORAL]


@dataclass
class ChartRecommendation:
    chart_type: ChartType
    field_mapping: dict  # {"x": "col1", "y": "col2", "group": "col3"}
    reasoning: str
    alternatives: list[ChartType] = field(default_factory=list)


@dataclass
class ChartResult:
    chart_type: str
    echarts_option: dict
    reasoning: str
    profile: DataProfile
    warnings: list[str] = field(default_factory=list)
    fallback: bool = False
```

- [ ] **Step 3: Create config loader**

```python
# chart_engine/config.py
"""配置加载：YAML 文件 + 环境变量覆盖。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class LLMConfig:
    model: str = "ollama_chat/qwen3:32b"
    api_base: str = "http://10.220.239.55:11343"
    timeout: int = 120
    temperature: float = 0


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8100


@dataclass
class ProfilerConfig:
    sample_size: int = 50
    max_column_samples: int = 5


@dataclass
class SelectorConfig:
    pie_max_categories: int = 7
    bar_max_categories: int = 20


@dataclass
class ExamplesConfig:
    few_shot_path: str = "eval/few_shot_pairs.json"
    db_init_sql: str = "telecom/output/telecom_init.sql"


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    profiler: ProfilerConfig = field(default_factory=ProfilerConfig)
    selector: SelectorConfig = field(default_factory=SelectorConfig)
    examples: ExamplesConfig = field(default_factory=ExamplesConfig)


def load_config(config_path: str | None = None) -> AppConfig:
    """加载配置。优先级：环境变量 > YAML > 默认值。"""
    cfg = AppConfig()

    # 从 YAML 加载
    if config_path is None:
        for candidate in ["config.yaml", "chart_engine/config.yaml"]:
            if Path(candidate).exists():
                config_path = candidate
                break

    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
        if "llm" in raw:
            cfg.llm = LLMConfig(**raw["llm"])
        if "server" in raw:
            cfg.server = ServerConfig(**raw["server"])
        if "profiler" in raw:
            cfg.profiler = ProfilerConfig(**raw["profiler"])
        if "selector" in raw:
            cfg.selector = SelectorConfig(**raw["selector"])
        if "examples" in raw:
            cfg.examples = ExamplesConfig(**raw["examples"])

    # 环境变量覆盖
    if os.environ.get("CHART_LLM_MODEL"):
        cfg.llm.model = os.environ["CHART_LLM_MODEL"]
    if os.environ.get("CHART_LLM_API_BASE"):
        cfg.llm.api_base = os.environ["CHART_LLM_API_BASE"]

    return cfg
```

- [ ] **Step 4: Create package entry points**

```python
# chart_engine/__init__.py
"""Chart Engine: SQL 查询结果 → ECharts option JSON。"""
from chart_engine.models import ChartResult, ChartType, DataProfile


def generate_chart(
    question: str,
    sql: str,
    data: list[dict],
    config_path: str | None = None,
) -> ChartResult:
    """主入口：生成图表。"""
    from chart_engine.config import load_config
    from chart_engine.profiler import profile_data
    from chart_engine.selector import select_chart
    from chart_engine.generator import generate_echarts
    from chart_engine.validator import validate_and_fix

    config = load_config(config_path)

    # Step 1: 数据画像
    prof = profile_data(data, config.profiler)

    # Step 2: 图表选型
    rec = select_chart(prof, question, config.selector)

    # Step 3: ECharts spec 生成
    raw_option = generate_echarts(question, sql, data, prof, rec, config.llm)

    # Step 4: 校验修正
    result = validate_and_fix(raw_option, rec, prof, question, config.selector)

    return result


__all__ = ["generate_chart", "ChartResult", "ChartType", "DataProfile"]
```

```python
# chart_engine/__main__.py
"""python -m chart_engine 入口。"""
from chart_engine.cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Create test fixtures**

```python
# tests/chart_engine/__init__.py
```

```python
# tests/chart_engine/conftest.py
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
```

- [ ] **Step 6: Commit**

```bash
git add chart_engine/__init__.py chart_engine/models.py chart_engine/config.py \
       chart_engine/config.yaml.example chart_engine/__main__.py \
       tests/chart_engine/__init__.py tests/chart_engine/conftest.py
git commit -m "feat(chart-engine): 项目骨架 — 数据模型、配置加载、测试 fixtures"
```

---

### Task 2: Profiler — 数据画像

**Files:**
- Create: `chart_engine/profiler.py`
- Create: `tests/chart_engine/test_profiler.py`

- [ ] **Step 1: Write profiler tests**

```python
# tests/chart_engine/test_profiler.py
"""Profiler 单元测试。"""
from chart_engine.profiler import profile_data
from chart_engine.config import ProfilerConfig
from chart_engine.models import ColumnDType


def test_time_series_profiling(time_series_data):
    """时序数据：collect_time 应识别为 temporal，cpu 应为 quantitative。"""
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
    """分类数据：vendor 应为 categorical，device_count 应为 quantitative。"""
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
    """单值结果：row_count=1, 一个 quantitative 列。"""
    prof = profile_data(single_value_data, ProfilerConfig())
    assert prof.row_count == 1
    assert prof.col_count == 1
    assert prof.measures == ["total_devices"]


def test_null_handling():
    """含空值的数据应正确统计 null_count。"""
    data = [
        {"name": "A", "val": 10},
        {"name": "B", "val": None},
        {"name": None, "val": 30},
    ]
    prof = profile_data(data, ProfilerConfig())
    col_map = {c.name: c for c in prof.columns}
    assert col_map["val"].null_count == 1
    assert col_map["name"].null_count == 1


def test_high_cardinality_identifier():
    """高基数字符串应识别为 identifier。"""
    data = [{"device_id": f"DEV-{i:04d}", "status": "UP"} for i in range(100)]
    prof = profile_data(data, ProfilerConfig())
    col_map = {c.name: c for c in prof.columns}
    assert col_map["device_id"].dtype == ColumnDType.IDENTIFIER
    assert col_map["device_id"].is_dimension is False


def test_sample_values_limited(categorical_data):
    """sample_values 最多 5 个。"""
    prof = profile_data(categorical_data, ProfilerConfig(max_column_samples=3))
    for col in prof.columns:
        assert len(col.sample_values) <= 3


def test_dimensions_and_measures(two_dim_data):
    """dimensions 和 measures 属性应正确汇总。"""
    prof = profile_data(two_dim_data, ProfilerConfig())
    assert "region" in prof.dimensions
    assert "vendor" in prof.dimensions
    assert "count" in prof.measures
    assert len(prof.temporals) == 0


def test_empty_data():
    """空数据不应崩溃。"""
    prof = profile_data([], ProfilerConfig())
    assert prof.row_count == 0
    assert prof.col_count == 0
    assert prof.columns == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/songruikang/Research/data-agent && python -m pytest tests/chart_engine/test_profiler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chart_engine.profiler'`

- [ ] **Step 3: Implement profiler**

```python
# chart_engine/profiler.py
"""Step 1: 数据画像 — 从 SQL 结果提取每列的统计特征。纯计算，不调 LLM。"""
from __future__ import annotations

from datetime import datetime, timedelta
from dateutil import parser as dateutil_parser

from chart_engine.config import ProfilerConfig
from chart_engine.models import ColumnProfile, ColumnDType, DataProfile


def profile_data(data: list[dict], config: ProfilerConfig) -> DataProfile:
    """对 SQL 查询结果做数据画像。"""
    if not data:
        return DataProfile(row_count=0, col_count=0, columns=[])

    columns = list(data[0].keys())
    row_count = len(data)
    col_profiles = []

    for col_name in columns:
        values = [row.get(col_name) for row in data]
        col_profiles.append(_profile_column(col_name, values, row_count, config))

    return DataProfile(row_count=row_count, col_count=len(columns), columns=col_profiles)


def _profile_column(
    name: str, values: list, row_count: int, config: ProfilerConfig
) -> ColumnProfile:
    """对单列做画像。"""
    non_null = [v for v in values if v is not None]
    null_count = len(values) - len(non_null)
    distinct = list(set(non_null))
    distinct_count = len(distinct)
    distinct_ratio = distinct_count / row_count if row_count > 0 else 0

    # 推断数据类型
    dtype = _infer_dtype(non_null, distinct_count, distinct_ratio)

    # sample values
    sample_values = distinct[: config.max_column_samples]

    # 维度/度量判断
    is_measure = dtype == ColumnDType.QUANTITATIVE
    is_dimension = dtype in (ColumnDType.CATEGORICAL, ColumnDType.TEMPORAL)

    # 时间粒度
    time_granularity = None
    if dtype == ColumnDType.TEMPORAL:
        parsed_times = _parse_times(non_null[:50])
        if parsed_times:
            time_granularity = _infer_time_granularity(parsed_times)

    # 数值范围
    min_val = None
    max_val = None
    if dtype == ColumnDType.QUANTITATIVE and non_null:
        numeric_vals = [_to_float(v) for v in non_null if _to_float(v) is not None]
        if numeric_vals:
            min_val = min(numeric_vals)
            max_val = max(numeric_vals)

    return ColumnProfile(
        name=name,
        dtype=dtype,
        distinct_count=distinct_count,
        distinct_ratio=distinct_ratio,
        null_count=null_count,
        sample_values=sample_values,
        is_dimension=is_dimension,
        is_measure=is_measure,
        time_granularity=time_granularity,
        min_val=min_val,
        max_val=max_val,
    )


def _infer_dtype(
    non_null: list, distinct_count: int, distinct_ratio: float
) -> ColumnDType:
    """从值推断列的数据类型。"""
    if not non_null:
        return ColumnDType.CATEGORICAL

    sample = non_null[:20]

    # 1. 时间检测
    if _is_temporal(sample):
        return ColumnDType.TEMPORAL

    # 2. 数值检测
    if _is_numeric(sample):
        if distinct_ratio > 0.9 and distinct_count > 50:
            return ColumnDType.IDENTIFIER
        return ColumnDType.QUANTITATIVE

    # 3. 字符串：分类 vs 标识符
    if distinct_ratio > 0.8 and distinct_count > 50:
        return ColumnDType.IDENTIFIER

    return ColumnDType.CATEGORICAL


def _is_temporal(sample: list) -> bool:
    """判断样本值是否为时间类型。"""
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


def _is_numeric(sample: list) -> bool:
    """判断样本值是否为数值类型。"""
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


def _to_float(v) -> float | None:
    """安全转 float。"""
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _parse_times(values: list) -> list[datetime]:
    """把值列表解析为 datetime。"""
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


def _infer_time_granularity(times: list[datetime]) -> str:
    """从时间间隔推断粒度。"""
    sorted_times = sorted(set(times))
    if len(sorted_times) < 2:
        return "day"

    diffs = [
        sorted_times[i + 1] - sorted_times[i]
        for i in range(min(10, len(sorted_times) - 1))
    ]
    median_diff = sorted(diffs)[len(diffs) // 2]

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/songruikang/Research/data-agent && python -m pytest tests/chart_engine/test_profiler.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add chart_engine/profiler.py tests/chart_engine/test_profiler.py
git commit -m "feat(chart-engine): Step 1 — 数据画像模块（类型推断/基数/时间粒度）"
```

---

### Task 3: Selector — 图表选型规则引擎

**Files:**
- Create: `chart_engine/selector.py`
- Create: `tests/chart_engine/test_selector.py`

- [ ] **Step 1: Write selector tests**

```python
# tests/chart_engine/test_selector.py
"""Selector 单元测试 — 验证各种数据模式选对图表类型。"""
from chart_engine.profiler import profile_data
from chart_engine.selector import select_chart
from chart_engine.config import ProfilerConfig, SelectorConfig
from chart_engine.models import ChartType


def _profile(data):
    return profile_data(data, ProfilerConfig())


def test_single_value_selects_kpi_card(single_value_data):
    """单值 → KPI 卡片。"""
    prof = _profile(single_value_data)
    rec = select_chart(prof, "总设备数是多少", SelectorConfig())
    assert rec.chart_type == ChartType.KPI_CARD


def test_time_series_selects_line(time_series_data):
    """时序 + 单指标 → 折线图。"""
    prof = _profile(time_series_data)
    rec = select_chart(prof, "CPU利用率趋势", SelectorConfig())
    assert rec.chart_type == ChartType.LINE
    assert "collect_time" in rec.field_mapping.values()


def test_multi_measure_time_selects_multi_line(multi_measure_time_data):
    """时序 + 多指标 → 多折线。"""
    prof = _profile(multi_measure_time_data)
    rec = select_chart(prof, "CPU和内存趋势", SelectorConfig())
    assert rec.chart_type == ChartType.MULTI_LINE


def test_categorical_selects_bar(categorical_data):
    """分类 + 度量 → 柱状图。"""
    prof = _profile(categorical_data)
    rec = select_chart(prof, "各厂商设备数量", SelectorConfig())
    assert rec.chart_type == ChartType.BAR


def test_proportion_intent_selects_pie(proportion_data):
    """分类 + 度量 + "占比"意图 → 饼图。"""
    prof = _profile(proportion_data)
    rec = select_chart(prof, "设备状态占比分布", SelectorConfig())
    assert rec.chart_type == ChartType.PIE


def test_pie_cardinality_guard(proportion_data):
    """分类基数 >7 时即使有"占比"意图也不选饼图。"""
    data = [{"status": f"S{i}", "count": 10 + i} for i in range(10)]
    prof = _profile(data)
    rec = select_chart(prof, "状态占比", SelectorConfig(pie_max_categories=7))
    assert rec.chart_type != ChartType.PIE


def test_two_dim_selects_grouped_bar(two_dim_data):
    """双维度 + 度量 → 分组柱状图。"""
    prof = _profile(two_dim_data)
    rec = select_chart(prof, "各区域各厂商设备数", SelectorConfig())
    assert rec.chart_type == ChartType.GROUPED_BAR


def test_two_dim_composition_selects_stacked_bar(two_dim_data):
    """双维度 + "构成"意图 → 堆叠柱状图。"""
    prof = _profile(two_dim_data)
    rec = select_chart(prof, "各区域设备构成分布", SelectorConfig())
    assert rec.chart_type == ChartType.STACKED_BAR


def test_scatter_data_selects_scatter(scatter_data):
    """双度量无时间 → 散点图。"""
    prof = _profile(scatter_data)
    rec = select_chart(prof, "时延与丢包率关系", SelectorConfig())
    assert rec.chart_type == ChartType.SCATTER


def test_empty_data_selects_table():
    """空数据 → 表格 fallback。"""
    prof = _profile([])
    rec = select_chart(prof, "随便查点什么", SelectorConfig())
    assert rec.chart_type == ChartType.TABLE


def test_field_mapping_has_required_keys(categorical_data):
    """field_mapping 应包含必要的轴映射。"""
    prof = _profile(categorical_data)
    rec = select_chart(prof, "各厂商设备数", SelectorConfig())
    assert "x" in rec.field_mapping
    assert "y" in rec.field_mapping


def test_recommendation_has_reasoning(categorical_data):
    """reasoning 不应为空。"""
    prof = _profile(categorical_data)
    rec = select_chart(prof, "各厂商设备数", SelectorConfig())
    assert len(rec.reasoning) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/songruikang/Research/data-agent && python -m pytest tests/chart_engine/test_selector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chart_engine.selector'`

- [ ] **Step 3: Implement selector**

```python
# chart_engine/selector.py
"""Step 2: 图表选型 — 基于数据画像和用户意图的规则引擎。不调 LLM。"""
from __future__ import annotations

import re

from chart_engine.config import SelectorConfig
from chart_engine.models import ChartType, ChartRecommendation, DataProfile, ColumnDType


# 意图关键词
_PROPORTION_KEYWORDS = re.compile(r"占比|比例|分布|百分比|构成比")
_COMPOSITION_KEYWORDS = re.compile(r"构成|组成|堆叠|分布")
_TREND_KEYWORDS = re.compile(r"趋势|变化|走势|增长|下降|波动")


def select_chart(
    profile: DataProfile, question: str, config: SelectorConfig
) -> ChartRecommendation:
    """根据数据画像和用户问题选择最佳图表类型。"""
    if profile.row_count == 0:
        return ChartRecommendation(
            chart_type=ChartType.TABLE,
            field_mapping={},
            reasoning="无数据，使用表格展示",
        )

    dims = profile.dimensions
    measures = profile.measures
    temporals = profile.temporals

    # Rule 1: 单值 → KPI 卡片
    if profile.row_count == 1 and profile.col_count <= 3 and len(measures) >= 1:
        return _make_rec(
            ChartType.KPI_CARD,
            _kpi_mapping(profile),
            "单值结果，使用指标卡",
            alternatives=[ChartType.TABLE],
        )

    # Rule 2: 时序 + 多度量 → 多折线
    if len(temporals) >= 1 and len(measures) >= 2:
        return _make_rec(
            ChartType.MULTI_LINE,
            _multi_line_mapping(profile),
            f"时序数据 + {len(measures)} 个度量指标，使用多折线图",
            alternatives=[ChartType.LINE, ChartType.AREA],
        )

    # Rule 3: 时序 + 度量 → 折线
    if len(temporals) >= 1 and len(measures) >= 1:
        return _make_rec(
            ChartType.LINE,
            _line_mapping(profile),
            "时序数据 + 单指标，使用折线图",
            alternatives=[ChartType.AREA, ChartType.BAR],
        )

    # Rule 4: 双度量无时间 → 散点
    if len(measures) >= 2 and len(temporals) == 0:
        return _make_rec(
            ChartType.SCATTER,
            _scatter_mapping(profile),
            "双度量无时间维度，使用散点图看相关性",
            alternatives=[ChartType.TABLE],
        )

    # Rule 5: 单维度 + 度量 + 占比意图 + 低基数 → 饼图
    if (
        len(dims) >= 1
        and len(measures) >= 1
        and _has_proportion_intent(question)
        and _max_dim_cardinality(profile) <= config.pie_max_categories
    ):
        return _make_rec(
            ChartType.PIE,
            _pie_mapping(profile),
            f"分类占比分析，{_max_dim_cardinality(profile)}个分类适合饼图",
            alternatives=[ChartType.BAR],
        )

    # Rule 6: 双维度 + 度量 + 构成意图 → 堆叠柱状
    if len(dims) >= 2 and len(measures) >= 1 and _has_composition_intent(question):
        return _make_rec(
            ChartType.STACKED_BAR,
            _grouped_bar_mapping(profile),
            "双维度构成分析，使用堆叠柱状图",
            alternatives=[ChartType.GROUPED_BAR],
        )

    # Rule 7: 双维度 + 度量 → 分组柱状
    if len(dims) >= 2 and len(measures) >= 1:
        return _make_rec(
            ChartType.GROUPED_BAR,
            _grouped_bar_mapping(profile),
            "双维度对比，使用分组柱状图",
            alternatives=[ChartType.STACKED_BAR],
        )

    # Rule 8: 单维度 + 度量 → 柱状图
    if len(dims) >= 1 and len(measures) >= 1:
        return _make_rec(
            ChartType.BAR,
            _bar_mapping(profile),
            "分类对比，使用柱状图",
            alternatives=[ChartType.PIE],
        )

    # Fallback → 表格
    return _make_rec(
        ChartType.TABLE,
        {},
        "无法匹配合适的图表类型，使用表格展示",
    )


# --- 意图判断 ---

def _has_proportion_intent(question: str) -> bool:
    return bool(_PROPORTION_KEYWORDS.search(question))


def _has_composition_intent(question: str) -> bool:
    return bool(_COMPOSITION_KEYWORDS.search(question))


# --- 辅助函数 ---

def _max_dim_cardinality(profile: DataProfile) -> int:
    dim_cols = [c for c in profile.columns if c.is_dimension and c.dtype != ColumnDType.TEMPORAL]
    if not dim_cols:
        return 0
    return max(c.distinct_count for c in dim_cols)


def _make_rec(
    chart_type: ChartType,
    field_mapping: dict,
    reasoning: str,
    alternatives: list[ChartType] | None = None,
) -> ChartRecommendation:
    return ChartRecommendation(
        chart_type=chart_type,
        field_mapping=field_mapping,
        reasoning=reasoning,
        alternatives=alternatives or [],
    )


# --- 字段映射 ---

def _first_temporal(profile: DataProfile) -> str:
    return profile.temporals[0]


def _first_measure(profile: DataProfile) -> str:
    return profile.measures[0]


def _first_dim(profile: DataProfile) -> str:
    non_temporal_dims = [
        c.name for c in profile.columns
        if c.is_dimension and c.dtype != ColumnDType.TEMPORAL
    ]
    return non_temporal_dims[0] if non_temporal_dims else profile.dimensions[0]


def _kpi_mapping(profile: DataProfile) -> dict:
    return {"value": _first_measure(profile)}


def _line_mapping(profile: DataProfile) -> dict:
    mapping = {"x": _first_temporal(profile), "y": _first_measure(profile)}
    # 如果有非时间维度，用作 group
    non_temporal_dims = [
        c.name for c in profile.columns
        if c.is_dimension and c.dtype != ColumnDType.TEMPORAL
    ]
    if non_temporal_dims:
        mapping["group"] = non_temporal_dims[0]
    return mapping


def _multi_line_mapping(profile: DataProfile) -> dict:
    return {
        "x": _first_temporal(profile),
        "y": profile.measures,  # 多个度量
    }


def _bar_mapping(profile: DataProfile) -> dict:
    return {"x": _first_dim(profile), "y": _first_measure(profile)}


def _pie_mapping(profile: DataProfile) -> dict:
    return {"category": _first_dim(profile), "value": _first_measure(profile)}


def _grouped_bar_mapping(profile: DataProfile) -> dict:
    non_temporal_dims = [
        c.name for c in profile.columns
        if c.is_dimension and c.dtype != ColumnDType.TEMPORAL
    ]
    return {
        "x": non_temporal_dims[0] if non_temporal_dims else profile.dimensions[0],
        "group": non_temporal_dims[1] if len(non_temporal_dims) > 1 else None,
        "y": _first_measure(profile),
    }


def _scatter_mapping(profile: DataProfile) -> dict:
    return {
        "x": profile.measures[0],
        "y": profile.measures[1],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/songruikang/Research/data-agent && python -m pytest tests/chart_engine/test_selector.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add chart_engine/selector.py tests/chart_engine/test_selector.py
git commit -m "feat(chart-engine): Step 2 — 图表选型规则引擎（12种图表类型）"
```

---

### Task 4: Prompt Templates + Generator

**Files:**
- Create: `chart_engine/prompts/__init__.py`
- Create: `chart_engine/prompts/echarts_gen.py`
- Create: `chart_engine/generator.py`
- Create: `tests/chart_engine/test_generator.py`

- [ ] **Step 1: Create prompt templates**

```python
# chart_engine/prompts/__init__.py
```

```python
# chart_engine/prompts/echarts_gen.py
"""ECharts option 生成的 prompt 模板。"""

SYSTEM_PROMPT = """你是一个 ECharts 图表配置生成器。
你的任务是根据给定的图表类型、字段映射和数据，生成一个完整的 ECharts option JSON。

你只需要生成 ECharts option，不需要选择图表类型（已给定），不需要分析数据含义（已给定）。

## 输出要求
- 返回合法的 JSON 对象，顶层 key 为 "option"
- option 必须是完整可用的 ECharts option
- 包含 title、tooltip、legend（如有分组）、xAxis/yAxis（如适用）、series
- title.text 用中文，从用户问题中提炼，简洁明了
- 数据直接嵌入 series[].data 中
- 不要包含任何注释或解释，只返回 JSON

## 配色方案
使用以下专业色板（按顺序取色）:
["#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de",
 "#3ba272", "#fc8452", "#9a60b4", "#ea7ccc", "#5ab1ef"]

## 各图表类型的 ECharts 配置要点

### bar（柱状图）
- xAxis.type = "category", xAxis.data = 分类值列表
- yAxis.type = "value"
- series[0].type = "bar", series[0].data = 数值列表
- 如果分类文字长，设置 xAxis.axisLabel.rotate = 30

### grouped_bar（分组柱状图）
- xAxis.type = "category", xAxis.data = 主分类列表
- 每个子分类一个 series，series[n].type = "bar"
- 不需要设置 stack

### stacked_bar（堆叠柱状图）
- 类似 grouped_bar，但每个 series 设置 stack = "total"

### line（折线图）
- xAxis.type = "category" 或 "time"
- series[0].type = "line"
- 加 smooth: true 让曲线平滑

### multi_line（多折线图）
- 每个度量一个 series，都是 type = "line"
- legend.data 列出所有 series name

### area（面积图）
- 类似 line，加 areaStyle: {}

### pie（饼图）
- 不需要 xAxis/yAxis
- series[0].type = "pie"
- series[0].data = [{name: "分类", value: 数值}, ...]
- series[0].radius = "60%"
- series[0].label.formatter = "{b}: {d}%"

### scatter（散点图）
- xAxis.type = "value", yAxis.type = "value"
- series[0].type = "scatter"
- series[0].data = [[x1,y1], [x2,y2], ...]

### kpi_card（指标卡）
- 不使用标准图表，返回特殊格式：
  {"option": {"kpi_card": true, "title": "标题", "value": 数值, "unit": "单位"}}

### table（表格）
- 不使用图表，返回：{"option": {"table": true, "columns": [...], "rows": [...]}}
"""

USER_PROMPT_TEMPLATE = """## 图表类型
{chart_type}

## 字段映射
{field_mapping}

## 用户问题
{question}

## SQL
{sql}

## 数据特征
- 总行数: {row_count}
- 列信息:
{column_profiles}

## 数据（前 {sample_size} 行）
{sample_data}

请生成 ECharts option JSON。只返回 JSON，不要其他内容。"""


def build_user_prompt(
    question: str,
    sql: str,
    data: list[dict],
    profile,  # DataProfile
    recommendation,  # ChartRecommendation
    sample_size: int = 50,
) -> str:
    """构建 user prompt。"""
    import json

    # 列信息
    col_lines = []
    for col in profile.columns:
        line = f"  - {col.name}: {col.dtype.value}, distinct={col.distinct_count}"
        if col.time_granularity:
            line += f", 粒度={col.time_granularity}"
        if col.min_val is not None:
            line += f", 范围=[{col.min_val:.1f}, {col.max_val:.1f}]"
        if col.sample_values:
            samples = str(col.sample_values[:3])
            line += f", 样例={samples}"
        col_lines.append(line)

    # 截取数据
    truncated = data[:sample_size]

    return USER_PROMPT_TEMPLATE.format(
        chart_type=recommendation.chart_type.value,
        field_mapping=json.dumps(recommendation.field_mapping, ensure_ascii=False),
        question=question,
        sql=sql,
        row_count=profile.row_count,
        column_profiles="\n".join(col_lines),
        sample_size=min(sample_size, len(data)),
        sample_data=json.dumps(truncated, ensure_ascii=False, default=str),
    )
```

- [ ] **Step 2: Implement generator**

```python
# chart_engine/generator.py
"""Step 3: ECharts option 生成 — 调用 LLM，职责单一。"""
from __future__ import annotations

import json
import logging

import litellm

from chart_engine.config import LLMConfig
from chart_engine.models import DataProfile, ChartRecommendation, ChartType
from chart_engine.prompts.echarts_gen import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)


def generate_echarts(
    question: str,
    sql: str,
    data: list[dict],
    profile: DataProfile,
    recommendation: ChartRecommendation,
    config: LLMConfig,
) -> dict:
    """调用 LLM 生成 ECharts option。返回 dict（option 部分）。"""
    # KPI 卡片和表格不需要 LLM
    if recommendation.chart_type == ChartType.KPI_CARD:
        return _build_kpi_card(question, data, recommendation)
    if recommendation.chart_type == ChartType.TABLE:
        return _build_table(data, profile)

    user_prompt = build_user_prompt(
        question=question,
        sql=sql,
        data=data,
        profile=profile,
        recommendation=recommendation,
        sample_size=config.timeout,  # 这里用 sample_size，先用 50
    )
    # 修正：用 profiler config 的 sample_size，这里 hardcode 50
    user_prompt = build_user_prompt(
        question=question,
        sql=sql,
        data=data,
        profile=profile,
        recommendation=recommendation,
        sample_size=50,
    )

    try:
        response = litellm.completion(
            model=config.model,
            api_base=config.api_base,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=config.temperature,
            timeout=config.timeout,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)

        # 提取 option（LLM 可能返回 {"option": {...}} 或直接 {...}）
        if "option" in parsed:
            return parsed["option"]
        return parsed

    except json.JSONDecodeError as e:
        logger.error("LLM 返回非法 JSON: %s", e)
        return _build_table(data, profile)
    except Exception as e:
        logger.error("LLM 调用失败: %s", e)
        return _build_table(data, profile)


def _build_kpi_card(question: str, data: list[dict], rec: ChartRecommendation) -> dict:
    """不需要 LLM 的 KPI 卡片。"""
    value_field = rec.field_mapping.get("value", "")
    value = data[0].get(value_field, 0) if data else 0
    return {
        "kpi_card": True,
        "title": question[:30],
        "value": value,
        "unit": "",
    }


def _build_table(data: list[dict], profile: DataProfile) -> dict:
    """不需要 LLM 的表格 fallback。"""
    columns = [c.name for c in profile.columns] if profile.columns else []
    return {
        "table": True,
        "columns": columns,
        "rows": data[:100],
    }
```

- [ ] **Step 3: Write generator tests (with LLM mock)**

```python
# tests/chart_engine/test_generator.py
"""Generator 测试 — mock LLM 调用。"""
import json
from unittest.mock import patch, MagicMock

from chart_engine.generator import generate_echarts, _build_kpi_card, _build_table
from chart_engine.profiler import profile_data
from chart_engine.selector import select_chart
from chart_engine.config import LLMConfig, ProfilerConfig, SelectorConfig
from chart_engine.models import ChartType


def _setup(data, question):
    prof = profile_data(data, ProfilerConfig())
    rec = select_chart(prof, question, SelectorConfig())
    return prof, rec


def test_kpi_card_no_llm(single_value_data):
    """KPI 卡片不应调用 LLM。"""
    prof, rec = _setup(single_value_data, "总设备数")
    assert rec.chart_type == ChartType.KPI_CARD
    result = generate_echarts("总设备数", "SELECT COUNT(*)", single_value_data, prof, rec, LLMConfig())
    assert result["kpi_card"] is True
    assert result["value"] == 50


def test_table_fallback_no_llm():
    """表格 fallback 不应调用 LLM。"""
    prof, rec = _setup([], "随便")
    assert rec.chart_type == ChartType.TABLE
    result = generate_echarts("随便", "SELECT 1", [], prof, rec, LLMConfig())
    assert result["table"] is True


@patch("chart_engine.generator.litellm")
def test_bar_chart_calls_llm(mock_litellm, categorical_data):
    """柱状图应调用 LLM 并解析返回的 JSON。"""
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


@patch("chart_engine.generator.litellm")
def test_llm_returns_invalid_json_fallback_to_table(mock_litellm, categorical_data):
    """LLM 返回非法 JSON 时应 fallback 到表格。"""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "这不是JSON"
    mock_litellm.completion.return_value = mock_response

    prof, rec = _setup(categorical_data, "各厂商设备数")
    result = generate_echarts("各厂商设备数", "SELECT ...", categorical_data, prof, rec, LLMConfig())
    assert result["table"] is True


@patch("chart_engine.generator.litellm")
def test_llm_exception_fallback_to_table(mock_litellm, categorical_data):
    """LLM 调用异常时应 fallback 到表格。"""
    mock_litellm.completion.side_effect = Exception("connection timeout")

    prof, rec = _setup(categorical_data, "各厂商设备数")
    result = generate_echarts("各厂商设备数", "SELECT ...", categorical_data, prof, rec, LLMConfig())
    assert result["table"] is True
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/songruikang/Research/data-agent && python -m pytest tests/chart_engine/test_generator.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add chart_engine/prompts/__init__.py chart_engine/prompts/echarts_gen.py \
       chart_engine/generator.py tests/chart_engine/test_generator.py
git commit -m "feat(chart-engine): Step 3 — ECharts option 生成器（LLM 调用 + prompt）"
```

---

### Task 5: Validator — 校验修正

**Files:**
- Create: `chart_engine/validator.py`
- Create: `tests/chart_engine/test_validator.py`

- [ ] **Step 1: Write validator tests**

```python
# tests/chart_engine/test_validator.py
"""Validator 单元测试。"""
from chart_engine.validator import validate_and_fix
from chart_engine.models import ChartType, ChartRecommendation, DataProfile, ColumnProfile, ColumnDType
from chart_engine.config import SelectorConfig


def _dummy_profile(row_count=10):
    return DataProfile(
        row_count=row_count,
        col_count=2,
        columns=[
            ColumnProfile("cat", ColumnDType.CATEGORICAL, 5, 0.5, 0, ["A", "B"], True, False),
            ColumnProfile("val", ColumnDType.QUANTITATIVE, 10, 1.0, 0, [1, 2], False, True),
        ],
    )


def _dummy_rec(chart_type=ChartType.BAR):
    return ChartRecommendation(chart_type=chart_type, field_mapping={"x": "cat", "y": "val"}, reasoning="test")


def test_valid_option_passes():
    """合法的 option 应原样通过。"""
    option = {
        "title": {"text": "测试"},
        "tooltip": {"trigger": "axis"},
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
    """缺少 title 应自动补充。"""
    option = {
        "series": [{"type": "bar", "data": [10]}],
    }
    result = validate_and_fix(option, _dummy_rec(), _dummy_profile(), "我的问题", SelectorConfig())
    assert "title" in result.echarts_option
    assert any("title" in w for w in result.warnings)


def test_missing_tooltip_auto_fixed():
    """缺少 tooltip 应自动补充。"""
    option = {
        "title": {"text": "ok"},
        "series": [{"type": "bar", "data": [10]}],
    }
    result = validate_and_fix(option, _dummy_rec(), _dummy_profile(), "q", SelectorConfig())
    assert "tooltip" in result.echarts_option


def test_missing_color_auto_fixed():
    """缺少 color 应注入默认色板。"""
    option = {
        "title": {"text": "ok"},
        "tooltip": {},
        "series": [{"type": "bar", "data": [10]}],
    }
    result = validate_and_fix(option, _dummy_rec(), _dummy_profile(), "q", SelectorConfig())
    assert "color" in result.echarts_option
    assert len(result.echarts_option["color"]) == 10


def test_missing_series_fallback_to_table():
    """缺少 series 应 fallback 到表格。"""
    option = {"title": {"text": "啥也没有"}}
    result = validate_and_fix(option, _dummy_rec(), _dummy_profile(), "q", SelectorConfig())
    assert result.fallback is True


def test_kpi_card_passes_through():
    """KPI 卡片 option 应直接通过。"""
    option = {"kpi_card": True, "title": "总数", "value": 42, "unit": "台"}
    rec = _dummy_rec(ChartType.KPI_CARD)
    result = validate_and_fix(option, rec, _dummy_profile(1), "总数", SelectorConfig())
    assert result.echarts_option == option
    assert result.fallback is False


def test_table_passes_through():
    """table option 应直接通过。"""
    option = {"table": True, "columns": ["a"], "rows": [{"a": 1}]}
    rec = _dummy_rec(ChartType.TABLE)
    result = validate_and_fix(option, rec, _dummy_profile(), "q", SelectorConfig())
    assert result.echarts_option == option
    assert result.fallback is False


def test_pie_high_cardinality_downgrade(high_cardinality_pie_data):
    """饼图分类 >7 应降级为柱状图。"""
    option = {
        "title": {"text": "分布"},
        "tooltip": {},
        "series": [{
            "type": "pie",
            "data": [{"name": f"Cat-{i:02d}", "value": 100 - i * 3} for i in range(15)],
        }],
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/songruikang/Research/data-agent && python -m pytest tests/chart_engine/test_validator.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement validator**

```python
# chart_engine/validator.py
"""Step 4: 校验修正 — 规则兜底，自动修正常见问题。不调 LLM。"""
from __future__ import annotations

import logging

from chart_engine.config import SelectorConfig
from chart_engine.models import (
    ChartType, ChartRecommendation, ChartResult, DataProfile,
)

logger = logging.getLogger(__name__)

DEFAULT_PALETTE = [
    "#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de",
    "#3ba272", "#fc8452", "#9a60b4", "#ea7ccc", "#5ab1ef",
]


def validate_and_fix(
    option: dict,
    recommendation: ChartRecommendation,
    profile: DataProfile,
    question: str,
    config: SelectorConfig,
) -> ChartResult:
    """校验 ECharts option 并自动修正常见问题。"""
    warnings: list[str] = []

    # KPI 卡片和表格直接放行
    if option.get("kpi_card") or option.get("table"):
        return ChartResult(
            chart_type=recommendation.chart_type.value,
            echarts_option=option,
            reasoning=recommendation.reasoning,
            profile=profile,
            warnings=[],
            fallback=option.get("table", False),
        )

    # 致命缺陷 → fallback 到表格
    if "series" not in option or not isinstance(option.get("series"), list):
        logger.warning("缺少 series，fallback 到表格")
        return _fallback_table(recommendation, profile, question, ["缺少 series，降级为表格"])

    if not option["series"]:
        return _fallback_table(recommendation, profile, question, ["series 为空，降级为表格"])

    # --- 自动修正 ---

    # 补 title
    if "title" not in option or not option.get("title", {}).get("text"):
        option["title"] = {"text": question[:30]}
        warnings.append("自动补充了 title")

    # 补 tooltip
    if "tooltip" not in option:
        option["tooltip"] = {"trigger": "axis"}
        warnings.append("自动补充了 tooltip")

    # 补 color
    if "color" not in option:
        option["color"] = DEFAULT_PALETTE.copy()

    # 饼图高基数降级
    if _is_pie(option):
        pie_series = option["series"][0]
        data_items = pie_series.get("data", [])
        if len(data_items) > config.pie_max_categories:
            _convert_pie_to_bar(option, data_items)
            warnings.append(
                f"饼图分类超过{config.pie_max_categories}个，已降级为柱状图"
            )

    # 柱状图高基数截断
    if _is_bar(option) and "xAxis" in option:
        x_data = option.get("xAxis", {}).get("data", [])
        if len(x_data) > config.bar_max_categories:
            _truncate_bar(option, config.bar_max_categories)
            warnings.append(
                f"分类超过{config.bar_max_categories}个，只保留 Top {config.bar_max_categories}"
            )

    return ChartResult(
        chart_type=recommendation.chart_type.value,
        echarts_option=option,
        reasoning=recommendation.reasoning,
        profile=profile,
        warnings=warnings,
        fallback=False,
    )


def _fallback_table(
    rec: ChartRecommendation, profile: DataProfile, question: str, warnings: list[str]
) -> ChartResult:
    return ChartResult(
        chart_type=ChartType.TABLE.value,
        echarts_option={"table": True, "columns": [c.name for c in profile.columns], "rows": []},
        reasoning=rec.reasoning,
        profile=profile,
        warnings=warnings,
        fallback=True,
    )


def _is_pie(option: dict) -> bool:
    series = option.get("series", [])
    return bool(series) and series[0].get("type") == "pie"


def _is_bar(option: dict) -> bool:
    series = option.get("series", [])
    return bool(series) and series[0].get("type") == "bar"


def _convert_pie_to_bar(option: dict, data_items: list[dict]) -> None:
    """饼图 → 柱状图。"""
    sorted_items = sorted(data_items, key=lambda d: d.get("value", 0), reverse=True)
    categories = [d.get("name", "") for d in sorted_items]
    values = [d.get("value", 0) for d in sorted_items]

    option["xAxis"] = {"type": "category", "data": categories}
    option["yAxis"] = {"type": "value"}
    option["series"] = [{"type": "bar", "data": values}]


def _truncate_bar(option: dict, max_count: int) -> None:
    """截断柱状图到 Top N。"""
    x_data = option["xAxis"]["data"][:max_count]
    option["xAxis"]["data"] = x_data
    for s in option.get("series", []):
        if "data" in s:
            s["data"] = s["data"][:max_count]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/songruikang/Research/data-agent && python -m pytest tests/chart_engine/test_validator.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add chart_engine/validator.py tests/chart_engine/test_validator.py
git commit -m "feat(chart-engine): Step 4 — 校验修正器（自动补全/饼图降级/高基数截断）"
```

---

### Task 6: CLI 入口

**Files:**
- Create: `chart_engine/cli.py`
- Create: `tests/chart_engine/test_cli.py`

- [ ] **Step 1: Write CLI tests**

```python
# tests/chart_engine/test_cli.py
"""CLI 测试。"""
import json
import tempfile
from unittest.mock import patch

from chart_engine.cli import main


def test_mock_mode(categorical_data):
    """--mock 模式只跑 profiler + selector，不调 LLM。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(categorical_data, f)
        f.flush()

        with patch("sys.argv", [
            "chart_engine",
            "--question", "各厂商设备数",
            "--data", f.name,
            "--mock",
        ]):
            result = main(return_result=True)

    assert result is not None
    assert result["chart_type"] == "bar"
    assert "field_mapping" in result


def test_output_to_file(categorical_data):
    """--output 应写入文件。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as data_file:
        json.dump(categorical_data, data_file)
        data_file.flush()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as out_file:
            out_path = out_file.name

        with patch("sys.argv", [
            "chart_engine",
            "--question", "各厂商设备数",
            "--data", data_file.name,
            "--mock",
            "--output", out_path,
        ]):
            main()

        with open(out_path) as f:
            output = json.load(f)
        assert "chart_type" in output
```

- [ ] **Step 2: Implement CLI**

```python
# chart_engine/cli.py
"""CLI 入口：python -m chart_engine。"""
from __future__ import annotations

import argparse
import json
import sys

from chart_engine.config import load_config
from chart_engine.profiler import profile_data
from chart_engine.selector import select_chart


def main(return_result: bool = False):
    """CLI 主函数。"""
    parser = argparse.ArgumentParser(
        prog="chart_engine",
        description="SQL 查询结果 → ECharts option JSON",
    )
    parser.add_argument("--question", "-q", required=True, help="用户自然语言问题")
    parser.add_argument("--sql", "-s", default="", help="SQL 语句（可选）")
    parser.add_argument("--data", "-d", required=True, help="数据文件路径（JSON 数组）")
    parser.add_argument("--output", "-o", help="输出文件路径（默认 stdout）")
    parser.add_argument("--config", "-c", help="配置文件路径")
    parser.add_argument("--model", "-m", help="覆盖 LLM 模型名")
    parser.add_argument("--mock", action="store_true", help="Mock 模式：只跑 profiler + selector，不调 LLM")

    args = parser.parse_args()

    # 加载数据
    with open(args.data) as f:
        data = json.load(f)

    config = load_config(args.config)
    if args.model:
        config.llm.model = args.model

    if args.mock:
        # Mock 模式：只做画像 + 选型
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
        # 完整模式：走四步管线
        from chart_engine import generate_chart
        chart_result = generate_chart(args.question, args.sql, data, args.config)
        result = {
            "chart_type": chart_result.chart_type,
            "echarts_option": chart_result.echarts_option,
            "reasoning": chart_result.reasoning,
            "warnings": chart_result.warnings,
            "fallback": chart_result.fallback,
        }

    # 输出
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
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/songruikang/Research/data-agent && python -m pytest tests/chart_engine/test_cli.py -v`
Expected: All 2 tests PASS

- [ ] **Step 4: Commit**

```bash
git add chart_engine/cli.py tests/chart_engine/test_cli.py
git commit -m "feat(chart-engine): CLI 入口（完整模式 + mock 模式）"
```

---

### Task 7: FastAPI Server

**Files:**
- Create: `chart_engine/server.py`

- [ ] **Step 1: Implement server**

```python
# chart_engine/server.py
"""FastAPI 服务 — WrenAI 集成接口。"""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from chart_engine import generate_chart
from chart_engine.config import load_config
from chart_engine.profiler import profile_data
from chart_engine.selector import select_chart

logger = logging.getLogger(__name__)

app = FastAPI(title="Chart Engine", version="0.1.0")
_config = None


def get_config():
    global _config
    if _config is None:
        _config = load_config()
    return _config


# --- Request/Response Models ---

class GenerateRequest(BaseModel):
    question: str
    sql: str = ""
    data: list[dict]


class ProfileRequest(BaseModel):
    data: list[dict]


class RecommendRequest(BaseModel):
    question: str
    data: list[dict]


class ChartResponse(BaseModel):
    chart_type: str
    echarts_option: dict
    reasoning: str
    warnings: list[str]
    fallback: bool


# --- Routes ---

@app.post("/generate", response_model=ChartResponse)
async def api_generate(req: GenerateRequest) -> ChartResponse:
    """生成图表 — 完整四步管线。"""
    try:
        result = generate_chart(req.question, req.sql, req.data)
        return ChartResponse(
            chart_type=result.chart_type,
            echarts_option=result.echarts_option,
            reasoning=result.reasoning,
            warnings=result.warnings,
            fallback=result.fallback,
        )
    except Exception as e:
        logger.error("生成图表失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/profile")
async def api_profile(req: ProfileRequest) -> dict:
    """只做数据画像（调试用）。"""
    config = get_config()
    profile = profile_data(req.data, config.profiler)
    return {
        "row_count": profile.row_count,
        "col_count": profile.col_count,
        "columns": [
            {
                "name": c.name,
                "dtype": c.dtype.value,
                "distinct_count": c.distinct_count,
                "is_dimension": c.is_dimension,
                "is_measure": c.is_measure,
                "time_granularity": c.time_granularity,
                "sample_values": c.sample_values,
            }
            for c in profile.columns
        ],
        "dimensions": profile.dimensions,
        "measures": profile.measures,
        "temporals": profile.temporals,
    }


@app.post("/recommend")
async def api_recommend(req: RecommendRequest) -> dict:
    """只做图表选型（调试用）。"""
    config = get_config()
    profile = profile_data(req.data, config.profiler)
    rec = select_chart(profile, req.question, config.selector)
    return {
        "chart_type": rec.chart_type.value,
        "field_mapping": rec.field_mapping,
        "reasoning": rec.reasoning,
        "alternatives": [a.value for a in rec.alternatives],
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


def serve(host: str = "0.0.0.0", port: int = 8100):
    """启动服务。"""
    import uvicorn
    uvicorn.run(app, host=host, port=port)
```

- [ ] **Step 2: Add serve subcommand to CLI**

在 `chart_engine/cli.py` 的 parser 中添加 serve 子命令。修改 `__main__.py` 以支持 `python -m chart_engine serve`:

```python
# chart_engine/__main__.py
"""python -m chart_engine 入口。"""
import sys

if len(sys.argv) > 1 and sys.argv[1] == "serve":
    from chart_engine.server import serve
    from chart_engine.config import load_config
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("serve")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--config", "-c", help="配置文件路径")
    args = parser.parse_args()

    serve(host=args.host, port=args.port)
else:
    from chart_engine.cli import main
    main()
```

- [ ] **Step 3: Commit**

```bash
git add chart_engine/server.py chart_engine/__main__.py
git commit -m "feat(chart-engine): FastAPI 服务（/generate + /profile + /recommend）"
```

---

### Task 8: Example Gallery

**Files:**
- Create: `chart_engine/examples.py`

- [ ] **Step 1: Implement example manager**

```python
# chart_engine/examples.py
"""Few-shot 示例管理 — 加载、执行、生成图表。"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb

from chart_engine import generate_chart
from chart_engine.config import AppConfig

logger = logging.getLogger(__name__)


class ExampleManager:
    """管理 few-shot 示例，支持 SQL 执行和图表生成。"""

    def __init__(self, config: AppConfig, base_dir: str | None = None):
        self.config = config
        self.base_dir = Path(base_dir) if base_dir else Path(".")
        self._pairs: list[dict] = []
        self._db: duckdb.DuckDBPyConnection | None = None

    def _load_pairs(self) -> list[dict]:
        if not self._pairs:
            path = self.base_dir / self.config.examples.few_shot_path
            with open(path) as f:
                self._pairs = json.load(f)
        return self._pairs

    def _get_db(self) -> duckdb.DuckDBPyConnection:
        if self._db is None:
            self._db = duckdb.connect(":memory:")
            init_sql_path = self.base_dir / self.config.examples.db_init_sql
            if init_sql_path.exists():
                sql = init_sql_path.read_text()
                # telecom_init.sql 里 read_csv_auto 路径需要替换
                csv_dir = str(init_sql_path.parent)
                sql = sql.replace("/usr/src/app/data/", csv_dir + "/")
                for statement in sql.split(";"):
                    statement = statement.strip()
                    if statement:
                        try:
                            self._db.execute(statement)
                        except Exception as e:
                            logger.warning("SQL 执行跳过: %s — %s", statement[:50], e)
        return self._db

    def list(self) -> list[dict]:
        """列出所有示例的摘要。"""
        pairs = self._load_pairs()
        return [
            {
                "id": p["id"],
                "question": p["question"],
                "pattern": p.get("pattern", ""),
                "tables": p.get("tables", []),
            }
            for p in pairs
        ]

    def get_chart(self, example_id: str) -> dict:
        """获取指定示例的图表结果。"""
        pairs = self._load_pairs()
        pair = next((p for p in pairs if p["id"] == example_id), None)
        if not pair:
            raise ValueError(f"示例 {example_id} 不存在")

        # 执行 SQL
        db = self._get_db()
        try:
            result = db.execute(pair["sql"]).fetchdf()
            data = result.to_dict("records")
        except Exception as e:
            logger.error("执行示例 SQL 失败 [%s]: %s", example_id, e)
            data = []

        # 生成图表
        chart_result = generate_chart(pair["question"], pair["sql"], data)
        return {
            "id": pair["id"],
            "question": pair["question"],
            "sql": pair["sql"],
            "chart_type": chart_result.chart_type,
            "echarts_option": chart_result.echarts_option,
            "reasoning": chart_result.reasoning,
            "warnings": chart_result.warnings,
            "data_rows": len(data),
        }

    def generate_all(self, output_dir: str) -> list[dict]:
        """批量生成所有示例的图表，保存到目录。"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        pairs = self._load_pairs()
        results = []

        for pair in pairs:
            example_id = pair["id"]
            logger.info("生成示例图表: %s — %s", example_id, pair["question"][:30])
            try:
                chart = self.get_chart(example_id)
                with open(out / f"{example_id}.json", "w") as f:
                    json.dump(chart, f, ensure_ascii=False, indent=2, default=str)
                results.append({"id": example_id, "status": "ok"})
            except Exception as e:
                logger.error("生成失败 [%s]: %s", example_id, e)
                results.append({"id": example_id, "status": "error", "error": str(e)})

        # 写入汇总
        with open(out / "summary.json", "w") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        return results
```

- [ ] **Step 2: Add examples routes to server**

在 `chart_engine/server.py` 中添加：

```python
# 在 server.py 尾部、serve() 函数之前添加

_example_manager = None

def get_example_manager():
    global _example_manager
    if _example_manager is None:
        from chart_engine.examples import ExampleManager
        _example_manager = ExampleManager(get_config())
    return _example_manager


@app.get("/examples")
async def list_examples() -> list[dict]:
    """列出所有 few-shot 示例。"""
    return get_example_manager().list()


@app.get("/examples/{example_id}/chart")
async def get_example_chart(example_id: str) -> dict:
    """获取指定示例的图表。"""
    try:
        return get_example_manager().get_chart(example_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 3: Add examples subcommand to CLI**

在 `chart_engine/__main__.py` 中添加 examples 子命令：

```python
# chart_engine/__main__.py
"""python -m chart_engine 入口。"""
import sys

if len(sys.argv) > 1 and sys.argv[1] == "serve":
    from chart_engine.server import serve
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("serve")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--config", "-c")
    args = parser.parse_args()
    serve(host=args.host, port=args.port)

elif len(sys.argv) > 1 and sys.argv[1] == "examples":
    from chart_engine.examples import ExampleManager
    from chart_engine.config import load_config
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("examples")
    parser.add_argument("--output", "-o", default="chart_engine_examples/")
    parser.add_argument("--config", "-c")
    parser.add_argument("--base-dir", default=".")
    args = parser.parse_args()

    config = load_config(args.config)
    mgr = ExampleManager(config, base_dir=args.base_dir)
    results = mgr.generate_all(args.output)
    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"完成：{ok}/{len(results)} 个示例生成成功")

else:
    from chart_engine.cli import main
    main()
```

- [ ] **Step 4: Commit**

```bash
git add chart_engine/examples.py chart_engine/server.py chart_engine/__main__.py
git commit -m "feat(chart-engine): Example Gallery（few-shot 示例加载/执行/批量生成）"
```

---

### Task 9: Dependencies + Integration Test

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/chart_engine/test_integration.py`

- [ ] **Step 1: Add dependencies to pyproject.toml**

在 `pyproject.toml` 的 `dependencies` 数组中追加：

```toml
"litellm>=1.40.0",
"fastapi>=0.115.0",
"uvicorn>=0.30.0",
"python-dateutil>=2.9.0",
"pyyaml>=6.0",
```

- [ ] **Step 2: Install dependencies**

Run: `cd /Users/songruikang/Research/data-agent && uv sync`

- [ ] **Step 3: Write integration test**

```python
# tests/chart_engine/test_integration.py
"""集成测试 — 从真实数据走完整管线（mock LLM）。"""
import json
from unittest.mock import patch, MagicMock

from chart_engine import generate_chart
from chart_engine.profiler import profile_data
from chart_engine.selector import select_chart
from chart_engine.config import ProfilerConfig, SelectorConfig


class TestProfilerSelectorIntegration:
    """Profiler + Selector 端到端（不需要 LLM）。"""

    def test_time_series_flow(self, time_series_data):
        """时序数据应走到 LINE 图。"""
        prof = profile_data(time_series_data, ProfilerConfig())
        rec = select_chart(prof, "CPU 利用率趋势", SelectorConfig())
        assert rec.chart_type.value == "line"
        assert rec.field_mapping["x"] == "collect_time"
        assert rec.field_mapping["y"] == "cpu_usage_avg_pct"

    def test_categorical_flow(self, categorical_data):
        """分类数据应走到 BAR 图。"""
        prof = profile_data(categorical_data, ProfilerConfig())
        rec = select_chart(prof, "各厂商设备数量", SelectorConfig())
        assert rec.chart_type.value == "bar"

    def test_proportion_flow(self, proportion_data):
        """占比数据 + 意图关键词应走到 PIE 图。"""
        prof = profile_data(proportion_data, ProfilerConfig())
        rec = select_chart(prof, "设备状态占比", SelectorConfig())
        assert rec.chart_type.value == "pie"

    def test_single_value_flow(self, single_value_data):
        """单值应走到 KPI_CARD。"""
        prof = profile_data(single_value_data, ProfilerConfig())
        rec = select_chart(prof, "总设备数", SelectorConfig())
        assert rec.chart_type.value == "kpi_card"


class TestFullPipelineWithMockLLM:
    """完整四步管线（mock LLM）。"""

    @patch("chart_engine.generator.litellm")
    def test_bar_chart_full_pipeline(self, mock_litellm, categorical_data):
        """分类数据 → 完整管线 → 带修正的 ECharts option。"""
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
        assert "color" in result.echarts_option  # validator 应注入色板
        assert result.echarts_option["series"][0]["type"] == "bar"

    def test_kpi_card_no_llm(self, single_value_data):
        """KPI 卡片应完全不调 LLM。"""
        result = generate_chart("总设备数", "SELECT COUNT(*)", single_value_data)
        assert result.chart_type == "kpi_card"
        assert result.echarts_option["value"] == 50
```

- [ ] **Step 4: Run all tests**

Run: `cd /Users/songruikang/Research/data-agent && python -m pytest tests/chart_engine/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/chart_engine/test_integration.py
git commit -m "feat(chart-engine): 依赖配置 + 集成测试"
```

---

### Task 10: Documentation + AGENTS.md

**Files:**
- Create: `chart_engine/AGENTS.md`

- [ ] **Step 1: Write AGENTS.md**

```markdown
# Chart Engine

SQL 查询结果 → ECharts option JSON 的独立图表生成模块。

## 架构

四步管线，每步职责单一：

```
SQL 结果 → Profiler(纯计算) → Selector(规则引擎) → Generator(LLM) → Validator(规则兜底)
```

## 文件说明

| 文件 | 职责 | 调 LLM |
|------|------|--------|
| models.py | 所有数据模型（Pydantic/dataclass） | 否 |
| config.py | 配置加载（YAML + 环境变量） | 否 |
| profiler.py | 数据画像：类型推断、基数、时间粒度 | 否 |
| selector.py | 图表选型：规则引擎，按数据特征+意图匹配 | 否 |
| generator.py | ECharts option 生成：调 LLM，职责收窄 | 是 |
| validator.py | 校验修正：补 title/tooltip/color，饼图降级 | 否 |
| prompts/echarts_gen.py | Prompt 模板 | — |
| examples.py | Few-shot 示例管理（加载/SQL执行/批量生成） | 是 |
| cli.py | CLI 入口 | 视 --mock |
| server.py | FastAPI 服务 | 是 |

## 使用方式

### Python API
```python
from chart_engine import generate_chart
result = generate_chart("各厂商设备数", "SELECT ...", data)
print(result.echarts_option)
```

### CLI
```bash
# Mock 模式（不调 LLM）
python -m chart_engine -q "各厂商设备数" -d data.json --mock

# 完整模式
python -m chart_engine -q "各厂商设备数" -d data.json

# 批量生成 few-shot 示例图表
python -m chart_engine examples -o output/
```

### API 服务
```bash
python -m chart_engine serve --port 8100

# 生成图表
curl -X POST http://localhost:8100/generate \
  -H "Content-Type: application/json" \
  -d '{"question": "各厂商设备数", "data": [...]}'

# 查看示例列表
curl http://localhost:8100/examples
```

## 配置

复制 `config.yaml.example` 为 `config.yaml`，修改 LLM 端点：

```yaml
llm:
  model: ollama_chat/qwen3:32b
  api_base: http://10.220.239.55:11343
```

## 图表类型

bar / grouped_bar / stacked_bar / line / multi_line / area / pie / scatter / heatmap / gauge / funnel / kpi_card / table

## 测试

```bash
python -m pytest tests/chart_engine/ -v
```
```

- [ ] **Step 2: Commit**

```bash
git add chart_engine/AGENTS.md
git commit -m "docs(chart-engine): AGENTS.md 模块说明文档"
```
