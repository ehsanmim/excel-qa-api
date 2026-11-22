from io import BytesIO

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app, get_planner, get_store
from app.models import QueryPlan
from app.store import WorkbookStore

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class FakePlanner:
    """Returns a fixed plan and records what it was asked, instead of calling the LLM."""

    def __init__(self) -> None:
        self.next_plan = QueryPlan(operation="unsupported", reason="no plan set")
        self.questions: list[str] = []
        self.schemas: list[list[dict]] = []

    def plan(self, question: str, schema: list[dict]) -> QueryPlan:
        self.questions.append(question)
        self.schemas.append(schema)
        return self.next_plan


def xlsx_bytes(*sheets: tuple[str, pd.DataFrame]) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, dataframe in sheets:
            dataframe.to_excel(writer, sheet_name=name, index=False)
    return buffer.getvalue()


def sales_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Country": ["Germany", "France", "Germany", "Spain"],
            "Revenue": [100.5, 200.25, 50.0, 10.0],
            "Units": [1, 2, 3, 4],
            "Order_Date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]),
        }
    )


@pytest.fixture
def planner() -> FakePlanner:
    return FakePlanner()


@pytest.fixture
def store() -> WorkbookStore:
    return WorkbookStore()


@pytest.fixture
def client(planner: FakePlanner, store: WorkbookStore):
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_planner] = lambda: planner
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def workbook_id(client: TestClient) -> str:
    content = xlsx_bytes(("Sales", sales_frame()))
    response = client.post("/upload", files=[("files", ("sales.xlsx", content, XLSX_TYPE))])
    assert response.status_code == 200
    return response.json()["workbooks"][0]["workbook_id"]
