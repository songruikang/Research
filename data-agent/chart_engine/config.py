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
    db_path: str = "telecom/output/telecom_nms.duckdb"


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

    if os.environ.get("CHART_LLM_MODEL"):
        cfg.llm.model = os.environ["CHART_LLM_MODEL"]
    if os.environ.get("CHART_LLM_API_BASE"):
        cfg.llm.api_base = os.environ["CHART_LLM_API_BASE"]

    return cfg
