"""Runs the example questions through the real LLM. Skipped without ANTHROPIC_API_KEY."""

import os
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")

SAMPLE = Path(__file__).parent.parent / "sample_data" / "sample.xlsx"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture(scope="module")
def session():
    with TestClient(app) as client:
        response = client.post("/upload", files=[("files", ("sample.xlsx", SAMPLE.read_bytes(), XLSX_TYPE))])
        yield client, response.json()["workbooks"][0]["workbook_id"]


def ask(session, question):
    client, workbook_id = session
    response = client.post("/chat", json={"workbook_id": workbook_id, "question": question})
    assert response.status_code == 200, response.text
    return response.json()


def test_example_questions(session):
    df = pd.read_excel(SAMPLE, sheet_name=0)
    germany = df[df["Country"] == "Germany"]

    assert ask(session, "Show all records for Germany.")["count"] == len(germany)
    assert ask(session, "What is the total revenue?")["result"] == pytest.approx(df["Revenue_EUR"].sum())
    assert ask(session, "What is the total revenue for Germany?")["result"] == pytest.approx(germany["Revenue_EUR"].sum())
    assert ask(session, "How many records are there?")["result"] == len(df)
    assert ask(session, "How many records are there for France?")["result"] == (df["Country"] == "France").sum()


def test_unsupported_question(session):
    assert ask(session, "What is the average revenue per country?")["status"] == "unsupported"
