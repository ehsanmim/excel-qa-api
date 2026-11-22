"""Run a QueryPlan on a DataFrame with pandas. All numbers come from here."""

import json
from dataclasses import dataclass
from typing import Any

import pandas as pd
from pandas.api import types

from app.models import QueryPlan

SUPPORTED_MESSAGE = (
    "Supported questions: show records where a column equals a value (filter), "
    "the total of a numeric column (sum), and the number of records (count). "
    "Sum and count can use one exact-match filter."
)


class PlanError(ValueError):
    """The plan does not fit the workbook (unknown column, text sum, ...)."""


@dataclass
class ExecutionResult:
    value: int | float | list[dict[str, Any]]
    count: int | None = None


def execute(plan: QueryPlan, dataframe: pd.DataFrame) -> ExecutionResult:
    rows = apply_filter(plan, dataframe)

    if plan.operation == "filter":
        if plan.filter_column is None:
            raise PlanError("a filter question needs a column and a value to match")
        return ExecutionResult(value=to_records(rows), count=len(rows))

    if plan.operation == "sum":
        if plan.target_column is None:
            raise PlanError("a sum question needs a column to add up")
        column = require_column(dataframe, plan.target_column)
        series = rows[column]
        if types.is_bool_dtype(series) or not types.is_numeric_dtype(series):
            raise PlanError(f"cannot sum non-numeric column '{column}'")
        return ExecutionResult(value=round_total(series.sum()), count=len(rows))

    if plan.operation == "count":
        return ExecutionResult(value=len(rows))

    raise PlanError(f"operation '{plan.operation}' cannot be executed")


def apply_filter(plan: QueryPlan, dataframe: pd.DataFrame) -> pd.DataFrame:
    """Keep the rows where filter_column equals filter_value exactly (or all rows)."""
    if plan.filter_column is None:
        return dataframe
    column = require_column(dataframe, plan.filter_column)
    if plan.filter_value is None:
        raise PlanError(f"no value given to filter column '{column}' on")

    series = dataframe[column]
    value = plan.filter_value
    if types.is_numeric_dtype(series) and not types.is_bool_dtype(series):
        mask = series == to_number(value, column)
    elif types.is_datetime64_any_dtype(series):
        mask = series == to_date(value, column)
    else:
        mask = series.astype("string").str.strip() == str(value).strip()
    return dataframe[mask.fillna(False).astype(bool)]


def require_column(dataframe: pd.DataFrame, column: str) -> str:
    if column not in dataframe.columns:
        available = ", ".join(dataframe.columns)
        raise PlanError(f"column '{column}' not found; available columns: {available}")
    return column


def to_number(value: Any, column: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise PlanError(f"column '{column}' is numeric but the filter value '{value}' is not a number") from None


def to_date(value: Any, column: str) -> pd.Timestamp:
    try:
        return pd.Timestamp(str(value))
    except ValueError:
        raise PlanError(f"column '{column}' holds dates but the filter value '{value}' is not a date") from None


def round_total(total: Any) -> int | float:
    """Integer columns give an int; float columns are rounded to 2 decimals."""
    if types.is_integer(total):
        return int(total)
    return round(float(total), 2)


def to_records(rows: pd.DataFrame) -> list[dict[str, Any]]:
    """JSON-safe rows: NaN becomes null, dates become ISO strings, numpy types become Python types."""
    return json.loads(rows.to_json(orient="records", date_format="iso"))
