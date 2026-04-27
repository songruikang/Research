"""Step 2: 图表选型 — 基于数据画像和用户意图的规则引擎。不调 LLM。"""
from __future__ import annotations

import re

from chart_engine.config import SelectorConfig
from chart_engine.models import ChartType, ChartRecommendation, DataProfile, ColumnDType


_PROPORTION_KEYWORDS = re.compile(r"占比|比例|分布|百分比|构成比")
_COMPOSITION_KEYWORDS = re.compile(r"构成|组成|堆叠|分布")
_TREND_KEYWORDS = re.compile(r"趋势|变化|走势|增长|下降|波动")
# 真实日期格式：YYYY-MM-DD 或 YYYY/MM/DD 等
_REAL_DATE_PATTERN = re.compile(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}")


def select_chart(profile: DataProfile, question: str, config: SelectorConfig) -> ChartRecommendation:
    if profile.row_count == 0:
        return ChartRecommendation(chart_type=ChartType.TABLE, field_mapping={}, reasoning="无数据，使用表格展示")

    dims = profile.dimensions
    measures = profile.measures
    temporals = profile.temporals

    # Rule 1: 单值 → KPI 卡片
    if profile.row_count == 1 and profile.col_count <= 3 and len(measures) >= 1:
        return _make_rec(ChartType.KPI_CARD, _kpi_mapping(profile), "单值结果，使用指标卡", [ChartType.TABLE])

    # Rule 2: 时序 + 多度量 → 多折线（需要有真实日期列）
    if _has_real_temporals(profile) and len(measures) >= 2:
        return _make_rec(ChartType.MULTI_LINE, _multi_line_mapping(profile),
                         f"时序数据 + {len(measures)} 个度量指标，使用多折线图", [ChartType.LINE, ChartType.AREA])

    # Rule 3: 时序 + 度量 → 折线（需要有真实日期列）
    if _has_real_temporals(profile) and len(measures) >= 1:
        return _make_rec(ChartType.LINE, _line_mapping(profile),
                         "时序数据 + 单指标，使用折线图", [ChartType.AREA, ChartType.BAR])

    # Rule 4: 双度量无真实时间维度 → 散点
    if len(measures) >= 2 and not _has_real_temporals(profile):
        return _make_rec(ChartType.SCATTER, _scatter_mapping(profile),
                         "双度量无时间维度，使用散点图看相关性", [ChartType.TABLE])

    # Rule 5: 双维度 + 度量 + 构成意图 → 堆叠柱状（优先于饼图，因为有多个分组维度）
    if len(dims) >= 2 and len(measures) >= 1 and _has_composition_intent(question):
        return _make_rec(ChartType.STACKED_BAR, _grouped_bar_mapping(profile),
                         "双维度构成分析，使用堆叠柱状图", [ChartType.GROUPED_BAR])

    # Rule 6: 单维度 + 度量 + 占比意图 + 低基数 → 饼图
    if (len(dims) >= 1 and len(measures) >= 1 and _has_proportion_intent(question)
            and _max_dim_cardinality(profile) <= config.pie_max_categories):
        return _make_rec(ChartType.PIE, _pie_mapping(profile),
                         f"分类占比分析，{_max_dim_cardinality(profile)}个分类适合饼图", [ChartType.BAR])

    # Rule 7: 双维度 + 度量 → 分组柱状
    if len(dims) >= 2 and len(measures) >= 1:
        return _make_rec(ChartType.GROUPED_BAR, _grouped_bar_mapping(profile),
                         "双维度对比，使用分组柱状图", [ChartType.STACKED_BAR])

    # Rule 8: 单维度 + 度量 → 柱状图
    if len(dims) >= 1 and len(measures) >= 1:
        return _make_rec(ChartType.BAR, _bar_mapping(profile),
                         "分类对比，使用柱状图", [ChartType.PIE])

    # Fallback
    return _make_rec(ChartType.TABLE, {}, "无法匹配合适的图表类型，使用表格展示")


def _has_real_temporals(profile: DataProfile) -> bool:
    """检查是否存在真实日期列（排除被误识别为时间的 ID 列，如 T-001）。"""
    for c in profile.columns:
        if c.dtype != ColumnDType.TEMPORAL:
            continue
        # 至少一个 sample_value 匹配真实日期格式才认定为真时间列
        for v in c.sample_values:
            if isinstance(v, str) and _REAL_DATE_PATTERN.search(v):
                return True
    return False

def _has_proportion_intent(question):
    return bool(_PROPORTION_KEYWORDS.search(question))

def _has_composition_intent(question):
    return bool(_COMPOSITION_KEYWORDS.search(question))

def _max_dim_cardinality(profile):
    dim_cols = [c for c in profile.columns if c.is_dimension and c.dtype != ColumnDType.TEMPORAL]
    return max(c.distinct_count for c in dim_cols) if dim_cols else 0

def _make_rec(chart_type, field_mapping, reasoning, alternatives=None):
    return ChartRecommendation(chart_type=chart_type, field_mapping=field_mapping,
                               reasoning=reasoning, alternatives=alternatives or [])

def _first_temporal(profile):
    return profile.temporals[0]

def _first_measure(profile):
    return profile.measures[0]

def _first_dim(profile):
    non_temporal_dims = [c.name for c in profile.columns if c.is_dimension and c.dtype != ColumnDType.TEMPORAL]
    return non_temporal_dims[0] if non_temporal_dims else profile.dimensions[0]

def _kpi_mapping(profile):
    return {"value": _first_measure(profile)}

def _line_mapping(profile):
    mapping = {"x": _first_temporal(profile), "y": _first_measure(profile)}
    non_temporal_dims = [c.name for c in profile.columns if c.is_dimension and c.dtype != ColumnDType.TEMPORAL]
    if non_temporal_dims:
        mapping["group"] = non_temporal_dims[0]
    return mapping

def _multi_line_mapping(profile):
    return {"x": _first_temporal(profile), "y": profile.measures}

def _bar_mapping(profile):
    return {"x": _first_dim(profile), "y": _first_measure(profile)}

def _pie_mapping(profile):
    return {"category": _first_dim(profile), "value": _first_measure(profile)}

def _grouped_bar_mapping(profile):
    non_temporal_dims = [c.name for c in profile.columns if c.is_dimension and c.dtype != ColumnDType.TEMPORAL]
    return {
        "x": non_temporal_dims[0] if non_temporal_dims else profile.dimensions[0],
        "group": non_temporal_dims[1] if len(non_temporal_dims) > 1 else None,
        "y": _first_measure(profile),
    }

def _scatter_mapping(profile):
    return {"x": profile.measures[0], "y": profile.measures[1]}
