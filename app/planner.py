"""Turn a natural-language question into a QueryPlan using Claude.

Only the table's schema is sent to the model, never the rows.
"""

import json
import os
from typing import Any, Protocol

import anthropic
import pandas as pd
from pandas.api import types

from app.models import QueryPlan

DEFAULT_MODEL = "claude-opus-5-5"
MAX_LISTED_VALUES = 30

SYSTEM_PROMPT = """You turn a question about one spreadsheet table into a query plan. You never compute answers yourself.

Supported operations:
- filter: return the rows where one column equals one value exactly.
- sum: the total of one number column, optionally only for rows where one column equals one value.
- count: the number of rows, optionally only for rows where one column equals one value.

Rules:
- Use column names exactly as they appear in the schema. Map the user's words to the closest column (for example "revenue" to "Revenue_EUR").
- If the schema lists a column's values, use the value exactly as listed (fix capitalisation and spelling).
- Use at most one filter. For sum, target_column must be a number column.
- Leave fields that do not apply as null.
- Anything else (average, minimum, maximum, grouping, sorting, several filters, ranges, comparisons, questions not about the table) is operation "unsupported", with a short reason."""


class PlannerError(Exception):
    """The LLM could not be reached or gave no usable plan."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class Planner(Protocol):
    def plan(self, question: str, schema: list[dict[str, Any]]) -> QueryPlan: ...


def describe_columns(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    """Column names and types, plus the distinct values of short text columns."""
    schema = []
    for name in dataframe.columns:
        series = dataframe[name]
        column: dict[str, Any] = {"name": name, "type": column_type(series)}
        if column["type"] == "text":
            values = series.dropna().astype(str).str.strip().unique()
            if len(values) <= MAX_LISTED_VALUES:
                column["values"] = sorted(values)
        schema.append(column)
    return schema


def column_type(series: pd.Series) -> str:
    if types.is_bool_dtype(series):
        return "boolean"
    if types.is_numeric_dtype(series):
        return "number"
    if types.is_datetime64_any_dtype(series):
        return "date"
    return "text"


class ClaudePlanner:
    def __init__(self) -> None:
        self.model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
        self._client: anthropic.Anthropic | None = None

    def plan(self, question: str, schema: list[dict[str, Any]]) -> QueryPlan:
        prompt = json.dumps({"columns": schema, "question": question}, indent=2)
        try:
            response = self._get_client().messages.parse(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                output_format=QueryPlan,
                output_config={"effort": "low"},
            )
        except anthropic.AuthenticationError as exc:
            raise PlannerError(502, "LLM authentication failed; check ANTHROPIC_API_KEY") from exc
        except anthropic.RateLimitError as exc:
            raise PlannerError(503, "LLM rate limit reached; try again shortly") from exc
        except anthropic.APIStatusError as exc:
            raise PlannerError(502, f"LLM request failed with status {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise PlannerError(503, "could not reach the LLM service") from exc

        if response.stop_reason == "refusal":
            return QueryPlan(operation="unsupported", reason="the model declined to answer this question")
        if response.parsed_output is None:
            raise PlannerError(502, "the LLM did not return a valid query plan")
        return response.parsed_output

    def _get_client(self) -> anthropic.Anthropic:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise PlannerError(503, "ANTHROPIC_API_KEY is not set on the server")
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client
