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


class PipelineStep(BaseModel):
    name: str
    duration_ms: int
    input: dict
    output: dict


class LLMTrace(BaseModel):
    model: str = ""
    system_prompt: str = ""
    user_prompt: str = ""
    response: str = ""
    duration_ms: int = 0


class ChartResponse(BaseModel):
    chart_type: str
    echarts_option: dict
    reasoning: str
    warnings: list[str]
    fallback: bool
    pipeline: list[PipelineStep] = []
    llm_trace: LLMTrace | None = None


@app.post("/generate", response_model=ChartResponse)
async def api_generate(req: GenerateRequest) -> ChartResponse:
    import time
    import json

    try:
        pipeline_steps = []

        # Step 1: Profiler
        config = get_config()
        t0 = time.time()
        profile = profile_data(req.data, config.profiler)
        t1 = time.time()

        profile_output = {
            "row_count": profile.row_count,
            "col_count": profile.col_count,
            "dimensions": profile.dimensions,
            "measures": profile.measures,
            "temporals": profile.temporals,
            "columns": [
                {
                    "name": c.name,
                    "dtype": c.dtype.value,
                    "distinct_count": c.distinct_count,
                    "is_dimension": c.is_dimension,
                    "is_measure": c.is_measure,
                    "time_granularity": c.time_granularity,
                    "sample_values": c.sample_values[:3],
                }
                for c in profile.columns
            ],
        }
        pipeline_steps.append(PipelineStep(
            name="Profiler",
            duration_ms=int((t1 - t0) * 1000),
            input={"data_rows": len(req.data), "data_cols": len(req.data[0]) if req.data else 0},
            output=profile_output,
        ))

        # Step 2: Selector
        t0 = time.time()
        rec = select_chart(profile, req.question, config.selector)
        t1 = time.time()

        selector_output = {
            "chart_type": rec.chart_type.value,
            "field_mapping": rec.field_mapping,
            "reasoning": rec.reasoning,
            "alternatives": [a.value for a in rec.alternatives],
        }
        pipeline_steps.append(PipelineStep(
            name="Selector",
            duration_ms=int((t1 - t0) * 1000),
            input={"question": req.question, "profile_summary": f"{profile.row_count}行, dims={profile.dimensions}, measures={profile.measures}"},
            output=selector_output,
        ))

        llm_trace = None

        if req.mock:
            # Step 3: Builder (mock)
            from chart_engine.builder import build_echarts_from_data

            t0 = time.time()
            raw_option = build_echarts_from_data(req.data, rec, req.question)
            t1 = time.time()

            pipeline_steps.append(PipelineStep(
                name="Builder (mock)",
                duration_ms=int((t1 - t0) * 1000),
                input={"chart_type": rec.chart_type.value, "field_mapping": rec.field_mapping},
                output={"echarts_option_keys": list(raw_option.keys())},
            ))
        else:
            # Step 3: Generator (LLM)
            from chart_engine.prompts.echarts_gen import SYSTEM_PROMPT, build_user_prompt
            from chart_engine.generator import generate_echarts

            user_prompt = build_user_prompt(
                question=req.question, sql=req.sql, data=req.data,
                profile=profile, recommendation=rec, sample_size=50,
            )

            t0 = time.time()
            raw_option = generate_echarts(req.question, req.sql, req.data, profile, rec, config.llm)
            t1 = time.time()

            llm_trace = LLMTrace(
                model=config.llm.model,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response=json.dumps(raw_option, ensure_ascii=False, default=str),
                duration_ms=int((t1 - t0) * 1000),
            )

            pipeline_steps.append(PipelineStep(
                name="Generator (LLM)",
                duration_ms=int((t1 - t0) * 1000),
                input={"model": config.llm.model, "prompt_length": len(user_prompt)},
                output={"echarts_option_keys": list(raw_option.keys()) if isinstance(raw_option, dict) else []},
            ))

        # Step 4: Validator
        from chart_engine.validator import validate_and_fix

        t0 = time.time()
        result = validate_and_fix(raw_option, rec, profile, req.question, config.selector)
        t1 = time.time()

        pipeline_steps.append(PipelineStep(
            name="Validator",
            duration_ms=int((t1 - t0) * 1000),
            input={"has_series": "series" in raw_option if isinstance(raw_option, dict) else False},
            output={"chart_type": result.chart_type, "warnings": result.warnings, "fallback": result.fallback},
        ))

        return ChartResponse(
            chart_type=result.chart_type,
            echarts_option=result.echarts_option,
            reasoning=result.reasoning,
            warnings=result.warnings,
            fallback=result.fallback,
            pipeline=pipeline_steps,
            llm_trace=llm_trace,
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
