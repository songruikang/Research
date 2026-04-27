"""Step 3: ECharts option 生成 — 调用 LLM，职责单一。"""
from __future__ import annotations

import json
import logging

import litellm

from chart_engine.config import LLMConfig
from chart_engine.models import DataProfile, ChartRecommendation, ChartType
from chart_engine.prompts.echarts_gen import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)


def generate_echarts(question, sql, data, profile, recommendation, config):
    """调用 LLM 生成 ECharts option。返回 dict。"""
    # KPI 卡片和表格不需要 LLM
    if recommendation.chart_type == ChartType.KPI_CARD:
        return _build_kpi_card(question, data, recommendation)
    if recommendation.chart_type == ChartType.TABLE:
        return _build_table(data, profile)

    user_prompt = build_user_prompt(
        question=question, sql=sql, data=data,
        profile=profile, recommendation=recommendation, sample_size=50,
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
        if "option" in parsed:
            return parsed["option"]
        return parsed
    except json.JSONDecodeError as e:
        logger.error("LLM 返回非法 JSON: %s", e)
        return _build_table(data, profile)
    except Exception as e:
        logger.error("LLM 调用失败: %s", e)
        return _build_table(data, profile)


def _build_kpi_card(question, data, rec):
    value_field = rec.field_mapping.get("value", "")
    value = data[0].get(value_field, 0) if data else 0
    return {"kpi_card": True, "title": question[:30], "value": value, "unit": ""}


def _build_table(data, profile):
    columns = [c.name for c in profile.columns] if profile.columns else []
    return {"table": True, "columns": columns, "rows": data[:100]}
