"""Few-shot 示例管理 — 加载、执行、生成图表（支持 mock 模式）。"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb

from chart_engine.config import AppConfig
from chart_engine.core.profiler import profile_data
from chart_engine.core.selector import select_chart
from chart_engine.core.builder import build_echarts_from_data
from chart_engine.core.validator import validate_and_fix
from chart_engine.utils.renderer import save_html

logger = logging.getLogger(__name__)


class ExampleManager:
    def __init__(self, config: AppConfig, base_dir: str | None = None):
        self.config = config
        self.base_dir = Path(base_dir) if base_dir else Path(".")
        self._pairs: list[dict] = []
        self._db: duckdb.DuckDBPyConnection | None = None

    def _load_pairs(self, input_path: str | None = None) -> list[dict]:
        if not self._pairs:
            path = Path(input_path) if input_path else self.base_dir / self.config.examples.few_shot_path
            with open(path) as f:
                self._pairs = json.load(f)
        return self._pairs

    def _get_db(self) -> duckdb.DuckDBPyConnection:
        if self._db is None:
            db_path = self.base_dir / self.config.examples.db_path
            if db_path.exists():
                self._db = duckdb.connect(str(db_path), read_only=True)
            else:
                logger.warning("DuckDB 文件不存在: %s，使用空数据库", db_path)
                self._db = duckdb.connect(":memory:")
        return self._db

    def list(self, input_path: str | None = None) -> list[dict]:
        pairs = self._load_pairs(input_path)
        return [
            {"id": p["id"], "question": p["question"],
             "pattern": p.get("pattern", ""), "tables": p.get("tables", [])}
            for p in pairs
        ]

    def get_chart_mock(self, pair: dict) -> dict:
        """Mock 模式：不调 LLM，直接从数据构建 ECharts option。"""
        db = self._get_db()
        try:
            result = db.execute(pair["sql"]).fetchdf()
            data = result.to_dict("records")
        except Exception as e:
            logger.error("执行 SQL 失败 [%s]: %s", pair.get("id", "?"), e)
            data = []

        prof = profile_data(data, self.config.profiler)
        rec = select_chart(prof, pair["question"], self.config.selector)
        raw_option = build_echarts_from_data(data, rec, pair["question"])
        chart_result = validate_and_fix(raw_option, rec, prof, pair["question"], self.config.selector)

        return {
            "id": pair.get("id", ""),
            "question": pair["question"],
            "sql": pair["sql"],
            "chart_type": chart_result.chart_type,
            "echarts_option": chart_result.echarts_option,
            "reasoning": chart_result.reasoning,
            "warnings": chart_result.warnings,
            "data_rows": len(data),
        }

    def get_chart_llm(self, pair: dict) -> dict:
        """LLM 模式：走完整四步管线。"""
        from chart_engine import generate_chart

        db = self._get_db()
        try:
            result = db.execute(pair["sql"]).fetchdf()
            data = result.to_dict("records")
        except Exception as e:
            logger.error("执行 SQL 失败 [%s]: %s", pair.get("id", "?"), e)
            data = []

        chart_result = generate_chart(pair["question"], pair["sql"], data)
        return {
            "id": pair.get("id", ""),
            "question": pair["question"],
            "sql": pair["sql"],
            "chart_type": chart_result.chart_type,
            "echarts_option": chart_result.echarts_option,
            "reasoning": chart_result.reasoning,
            "warnings": chart_result.warnings,
            "data_rows": len(data),
        }

    def generate_all(
        self,
        output_dir: str,
        input_path: str | None = None,
        mock: bool = True,
    ) -> list[dict]:
        """批量生成所有示例的图表，输出 JSON + HTML。"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        pairs = self._load_pairs(input_path)
        results = []
        all_charts = []

        for pair in pairs:
            example_id = pair.get("id", f"unknown_{len(results)}")
            print(f"  生成 {example_id}: {pair['question'][:40]}...")

            try:
                chart = self.get_chart_mock(pair) if mock else self.get_chart_llm(pair)
                with open(out / f"{example_id}.json", "w") as f:
                    json.dump(chart, f, ensure_ascii=False, indent=2, default=str)
                results.append({"id": example_id, "status": "ok", "chart_type": chart["chart_type"]})
                all_charts.append(chart)
            except Exception as e:
                logger.error("生成失败 [%s]: %s", example_id, e)
                results.append({"id": example_id, "status": "error", "error": str(e)})

        # 写汇总 JSON
        with open(out / "summary.json", "w") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        # 生成可浏览的 HTML 页面
        save_html(all_charts, str(out / "index.html"), title="Chart Engine 示例图表")

        return results
