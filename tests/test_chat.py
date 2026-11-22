from pathlib import Path

import pandas as pd
import pytest

from app.models import QueryPlan
from tests.conftest import XLSX_TYPE

SAMPLE = Path(__file__).parent.parent / "sample_data" / "sample.xlsx"


def ask(client, workbook_id, question="any question"):
    return client.post("/chat", json={"workbook_id": workbook_id, "question": question})


def test_filter_returns_matching_records(client, planner, workbook_id):
    planner.next_plan = QueryPlan(operation="filter", filter_column="Country", filter_value="Germany")
    response = ask(client, workbook_id, "Show all records for Germany.")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["count"] == 2
    assert [row["Revenue"] for row in body["result"]] == [100.5, 50.0]
    assert body["result"][0]["Order_Date"].startswith("2026-01-01")
    assert body["filename"] == "sales.xlsx"
    assert body["worksheet_name"] == "Sales"
    assert body["plan"]["filter_column"] == "Country"


def test_sum_without_filter(client, planner, workbook_id):
    planner.next_plan = QueryPlan(operation="sum", target_column="Revenue")
    body = ask(client, workbook_id).json()

    assert body["result"] == 360.75


def test_sum_with_filter(client, planner, workbook_id):
    planner.next_plan = QueryPlan(
        operation="sum", target_column="Revenue", filter_column="Country", filter_value="Germany"
    )
    body = ask(client, workbook_id).json()

    assert body["result"] == 150.5
    assert body["count"] == 2


def test_sum_of_integer_column_is_int(client, planner, workbook_id):
    planner.next_plan = QueryPlan(operation="sum", target_column="Units")
    body = ask(client, workbook_id).json()

    assert body["result"] == 10
    assert isinstance(body["result"], int)


def test_count_without_filter(client, planner, workbook_id):
    planner.next_plan = QueryPlan(operation="count")
    assert ask(client, workbook_id).json()["result"] == 4


def test_count_with_filter(client, planner, workbook_id):
    planner.next_plan = QueryPlan(operation="count", filter_column="Country", filter_value="France")
    assert ask(client, workbook_id).json()["result"] == 1


def test_numeric_filter_value(client, planner, workbook_id):
    planner.next_plan = QueryPlan(operation="filter", filter_column="Units", filter_value="3")
    body = ask(client, workbook_id).json()

    assert body["count"] == 1
    assert body["result"][0]["Country"] == "Germany"


def test_date_filter_value(client, planner, workbook_id):
    planner.next_plan = QueryPlan(operation="count", filter_column="Order_Date", filter_value="2026-01-02")
    assert ask(client, workbook_id).json()["result"] == 1


def test_zero_matches_is_not_an_error(client, planner, workbook_id):
    planner.next_plan = QueryPlan(
        operation="sum", target_column="Revenue", filter_column="Country", filter_value="Italy"
    )
    body = ask(client, workbook_id).json()

    assert body["status"] == "ok"
    assert body["result"] == 0


def test_unknown_workbook_id(client, planner):
    response = ask(client, "does-not-exist")

    assert response.status_code == 404
    assert planner.questions == []


def test_empty_question_is_rejected(client, workbook_id):
    assert ask(client, workbook_id, "   ").status_code == 422


def test_unknown_column(client, planner, workbook_id):
    planner.next_plan = QueryPlan(operation="sum", target_column="Profit")
    response = ask(client, workbook_id)

    assert response.status_code == 422
    assert "'Profit' not found" in response.json()["detail"]
    assert "Revenue" in response.json()["detail"]


def test_sum_of_text_column(client, planner, workbook_id):
    planner.next_plan = QueryPlan(operation="sum", target_column="Country")
    response = ask(client, workbook_id)

    assert response.status_code == 422
    assert "cannot sum non-numeric column 'Country'" in response.json()["detail"]


def test_text_value_for_numeric_filter(client, planner, workbook_id):
    planner.next_plan = QueryPlan(operation="count", filter_column="Units", filter_value="many")
    assert ask(client, workbook_id).status_code == 422


def test_filter_without_column(client, planner, workbook_id):
    planner.next_plan = QueryPlan(operation="filter")
    assert ask(client, workbook_id).status_code == 422


def test_unsupported_question(client, planner, workbook_id):
    planner.next_plan = QueryPlan(operation="unsupported", reason="Averages are not supported.")
    response = ask(client, workbook_id, "What is the average revenue?")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unsupported"
    assert body["result"] is None
    assert "Averages are not supported." in body["message"]
    assert "Supported questions" in body["message"]


def test_planner_gets_schema_not_rows(client, planner, workbook_id):
    planner.next_plan = QueryPlan(operation="count")
    ask(client, workbook_id, "How many records are there?")

    [schema] = planner.schemas
    assert schema[0] == {"name": "Country", "type": "text", "values": ["France", "Germany", "Spain"]}
    assert schema[1] == {"name": "Revenue", "type": "number"}
    assert schema[3] == {"name": "Order_Date", "type": "date"}


def test_sum_on_sample_workbook_matches_pandas(client, planner):
    response = client.post("/upload", files=[("files", ("sample.xlsx", SAMPLE.read_bytes(), XLSX_TYPE))])
    [workbook] = response.json()["workbooks"]
    expected = pd.read_excel(SAMPLE, sheet_name=0)
    target, filter_column = expected.columns[-4], expected.columns[2]
    value = expected[filter_column].iloc[0]

    planner.next_plan = QueryPlan(
        operation="sum", target_column=target, filter_column=filter_column, filter_value=value
    )
    body = ask(client, workbook["workbook_id"]).json()

    assert body["result"] == pytest.approx(expected.loc[expected[filter_column] == value, target].sum())
