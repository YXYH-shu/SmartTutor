from __future__ import annotations

import json
from typing import Any


class ResultParserError(RuntimeError):
    pass


class ParsedKTResult:
    def __init__(self, raw_json: dict[str, Any]):
        self.raw_json = raw_json
        self.report_markdown = raw_json.get("llm_analysis", {}).get("report_markdown")
        self.predictions = raw_json.get("predictions", [])
        self.metrics = raw_json.get("metrics", {})


class ResultParser:
    def parse_kt_stdout(self, stdout: str) -> ParsedKTResult:
        try:
            raw = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ResultParserError(f"Invalid JSON output: {exc}") from exc
        if not isinstance(raw, dict):
            raise ResultParserError("KT output must be a JSON object")
        return ParsedKTResult(raw)
