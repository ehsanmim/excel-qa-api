"""Turn a natural-language question into a QueryPlan using an LLM.

Only the table's schema is sent to the model, never the rows.
Two providers are supported, chosen with the LLM_PROVIDER environment variable:
- "anthropic" (default): Claude through the Anthropic SDK.
- "openai": any OpenAI-compatible API (OpenAI, OpenRouter, Gemini, Ollama, ...).
"""

import json
import os
from typing import Any, Protocol

import anthropic
import openai
import pandas as pd
from pandas.api import types
from pydantic import ValidationError

from app.models import QueryPlan

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5-5"
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

REFUSED_PLAN = QueryPlan(operation="unsupported", reason="the model declined to answer this question")


class PlannerError(Exception):
    """The LLM is not configured, could not be reached, or gave no usable plan."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class Planner(Protocol):
    def plan(self, question: str, schema: list[dict[str, Any]]) -> QueryPlan: ...


def make_planner() -> Planner:
    provider = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()
    if provider == "anthropic":
        return ClaudePlanner()
    if provider == "openai":
        return OpenAICompatiblePlanner()
    raise PlannerError(500, f"unknown LLM_PROVIDER '{provider}'; use 'anthropic' or 'openai'")


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


def user_prompt(question: str, schema: list[dict[str, Any]]) -> str:
    return json.dumps({"columns": schema, "question": question}, indent=2)


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise PlannerError(503, f"{name} is not set on the server")
    return value


class ClaudePlanner:
    def __init__(self) -> None:
        self.model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
        self._client: anthropic.Anthropic | None = None

    def plan(self, question: str, schema: list[dict[str, Any]]) -> QueryPlan:
        try:
            response = self._get_client().messages.parse(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt(question, schema)}],
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
            return REFUSED_PLAN
        if response.parsed_output is None:
            raise PlannerError(502, "the LLM did not return a valid query plan")
        return response.parsed_output

    def _get_client(self) -> anthropic.Anthropic:
        require_env("ANTHROPIC_API_KEY")
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client


class OpenAICompatiblePlanner:
    """Uses OPENAI_API_KEY, OPENAI_MODEL and optionally OPENAI_BASE_URL (e.g. https://openrouter.ai/api/v1)."""

    def __init__(self) -> None:
        self._client: openai.OpenAI | None = None

    def plan(self, question: str, schema: list[dict[str, Any]]) -> QueryPlan:
        model = require_env("OPENAI_MODEL")
        try:
            completion = self._get_client().chat.completions.parse(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt(question, schema)},
                ],
                response_format=QueryPlan,
            )
        except openai.AuthenticationError as exc:
            raise PlannerError(502, "LLM authentication failed; check OPENAI_API_KEY") from exc
        except openai.RateLimitError as exc:
            raise PlannerError(503, "LLM rate limit reached; try again shortly") from exc
        except openai.APIStatusError as exc:
            raise PlannerError(502, f"LLM request failed with status {exc.status_code}") from exc
        except openai.APIConnectionError as exc:
            raise PlannerError(503, "could not reach the LLM service") from exc
        except (openai.LengthFinishReasonError, openai.ContentFilterFinishReasonError, ValidationError) as exc:
            raise PlannerError(502, "the LLM did not return a valid query plan") from exc

        message = completion.choices[0].message
        if message.refusal:
            return REFUSED_PLAN
        if message.parsed is None:
            raise PlannerError(502, "the LLM did not return a valid query plan")
        return message.parsed

    def _get_client(self) -> openai.OpenAI:
        require_env("OPENAI_API_KEY")
        if self._client is None:
            # An empty OPENAI_BASE_URL means "use OpenAI itself".
            self._client = openai.OpenAI(base_url=os.environ.get("OPENAI_BASE_URL") or None)
        return self._client
