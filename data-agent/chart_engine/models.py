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
    time_granularity: str | None = None
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
    field_mapping: dict
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
