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


class GenerateRequest(BaseModel):
    question: str
    sql: str = ""
    data: list[dict]
    mock: bool = True  # 默认 mock 模式，不调 LLM


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


@app.post("/generate", response_model=ChartResponse)
async def api_generate(req: GenerateRequest) -> ChartResponse:
    try:
        if req.mock:
            # Mock 模式：不调 LLM，纯规则生成
            from chart_engine.builder import build_echarts_from_data
            from chart_engine.validator import validate_and_fix

            config = get_config()
            profile = profile_data(req.data, config.profiler)
            rec = select_chart(profile, req.question, config.selector)
            raw_option = build_echarts_from_data(req.data, rec, req.question)
            result = validate_and_fix(raw_option, rec, profile, req.question, config.selector)
        else:
            # LLM 模式：完整四步管线
            result = generate_chart(req.question, req.sql, req.data)

        return ChartResponse(
            chart_type=result.chart_type, echarts_option=result.echarts_option,
            reasoning=result.reasoning, warnings=result.warnings, fallback=result.fallback,
        )
    except Exception as e:
        logger.error("生成图表失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/profile")
async def api_profile(req: ProfileRequest) -> dict:
    config = get_config()
    profile = profile_data(req.data, config.profiler)
    return {
        "row_count": profile.row_count, "col_count": profile.col_count,
        "columns": [
            {"name": c.name, "dtype": c.dtype.value, "distinct_count": c.distinct_count,
             "is_dimension": c.is_dimension, "is_measure": c.is_measure,
             "time_granularity": c.time_granularity, "sample_values": c.sample_values}
            for c in profile.columns
        ],
        "dimensions": profile.dimensions, "measures": profile.measures, "temporals": profile.temporals,
    }


@app.post("/recommend")
async def api_recommend(req: RecommendRequest) -> dict:
    config = get_config()
    profile = profile_data(req.data, config.profiler)
    rec = select_chart(profile, req.question, config.selector)
    return {
        "chart_type": rec.chart_type.value, "field_mapping": rec.field_mapping,
        "reasoning": rec.reasoning, "alternatives": [a.value for a in rec.alternatives],
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


_example_manager = None

def get_example_manager():
    global _example_manager
    if _example_manager is None:
        from chart_engine.examples import ExampleManager
        _example_manager = ExampleManager(get_config())
    return _example_manager


@app.get("/examples")
async def list_examples() -> list[dict]:
    return get_example_manager().list()


@app.get("/examples/{example_id}/chart")
async def get_example_chart(example_id: str) -> dict:
    try:
        return get_example_manager().get_chart(example_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def serve(host: str = "0.0.0.0", port: int = 8100):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
