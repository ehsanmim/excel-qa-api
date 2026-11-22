"""Pydantic models for requests, responses and the LLM query plan."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, StringConstraints

Operation = Literal["filter", "sum", "count", "unsupported"]
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class QueryPlan(BaseModel):
    """What the LLM thinks the question asks for. pandas does the actual work."""

    operation: Operation
    target_column: str | None = None
    filter_column: str | None = None
    filter_value: str | int | float | None = None
    reason: str | None = None


class UploadedWorkbook(BaseModel):
    workbook_id: str
    filename: str
    worksheet_name: str
    columns: list[str]


class UploadResponse(BaseModel):
    workbooks: list[UploadedWorkbook]


class ChatRequest(BaseModel):
    workbook_id: NonEmptyStr
    question: NonEmptyStr


class ChatResponse(BaseModel):
    status: Literal["ok", "unsupported"]
    operation: Operation
    result: int | float | list[dict[str, Any]] | None = None
    count: int | None = None
    message: str | None = None
    plan: QueryPlan
    filename: str
    worksheet_name: str
