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
        pairs = self._load_pairs()
        return [
            {"id": p["id"], "question": p["question"],
             "pattern": p.get("pattern", ""), "tables": p.get("tables", [])}
            for p in pairs
        ]

    def get_chart(self, example_id: str) -> dict:
        pairs = self._load_pairs()
        pair = next((p for p in pairs if p["id"] == example_id), None)
        if not pair:
            raise ValueError(f"示例 {example_id} 不存在")

        db = self._get_db()
        try:
            result = db.execute(pair["sql"]).fetchdf()
            data = result.to_dict("records")
        except Exception as e:
            logger.error("执行示例 SQL 失败 [%s]: %s", example_id, e)
            data = []

        chart_result = generate_chart(pair["question"], pair["sql"], data)
        return {
            "id": pair["id"], "question": pair["question"], "sql": pair["sql"],
            "chart_type": chart_result.chart_type, "echarts_option": chart_result.echarts_option,
            "reasoning": chart_result.reasoning, "warnings": chart_result.warnings,
            "data_rows": len(data),
        }

    def generate_all(self, output_dir: str) -> list[dict]:
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
        with open(out / "summary.json", "w") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        return results
