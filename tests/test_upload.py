import pandas as pd

from tests.conftest import XLSX_TYPE, sales_frame, xlsx_bytes


def test_upload_one_file(client):
    content = xlsx_bytes(("Sales", sales_frame()))
    response = client.post("/upload", files=[("files", ("sales.xlsx", content, XLSX_TYPE))])

    assert response.status_code == 200
    [workbook] = response.json()["workbooks"]
    assert workbook["filename"] == "sales.xlsx"
    assert workbook["worksheet_name"] == "Sales"
    assert workbook["columns"] == ["Country", "Revenue", "Units", "Order_Date"]
    assert len(workbook["workbook_id"]) == 32


def test_upload_several_files_get_separate_ids(client):
    first = xlsx_bytes(("A", pd.DataFrame({"x": [1]})))
    second = xlsx_bytes(("B", pd.DataFrame({"y": [2]})))
    response = client.post(
        "/upload",
        files=[("files", ("a.xlsx", first, XLSX_TYPE)), ("files", ("b.xlsx", second, XLSX_TYPE))],
    )

    assert response.status_code == 200
    workbooks = response.json()["workbooks"]
    assert [w["worksheet_name"] for w in workbooks] == ["A", "B"]
    assert [w["columns"] for w in workbooks] == [["x"], ["y"]]
    assert workbooks[0]["workbook_id"] != workbooks[1]["workbook_id"]


def test_only_first_sheet_is_read(client):
    content = xlsx_bytes(("First", pd.DataFrame({"a": [1]})), ("Second", pd.DataFrame({"b": [2]})))
    response = client.post("/upload", files=[("files", ("two.xlsx", content, XLSX_TYPE))])

    [workbook] = response.json()["workbooks"]
    assert workbook["worksheet_name"] == "First"
    assert workbook["columns"] == ["a"]


def test_non_xlsx_file_is_rejected(client):
    response = client.post("/upload", files=[("files", ("data.csv", b"a,b\n1,2", "text/csv"))])

    assert response.status_code == 400
    assert "data.csv" in response.json()["detail"]


def test_corrupt_xlsx_is_rejected(client):
    response = client.post("/upload", files=[("files", ("broken.xlsx", b"not a workbook", XLSX_TYPE))])

    assert response.status_code == 400
    assert "broken.xlsx" in response.json()["detail"]


def test_empty_sheet_is_rejected(client):
    content = xlsx_bytes(("Empty", pd.DataFrame({"a": []})))
    response = client.post("/upload", files=[("files", ("empty.xlsx", content, XLSX_TYPE))])

    assert response.status_code == 400
    assert "no data" in response.json()["detail"]


def test_one_bad_file_stores_nothing(client, store):
    good = xlsx_bytes(("Sales", sales_frame()))
    response = client.post(
        "/upload",
        files=[("files", ("good.xlsx", good, XLSX_TYPE)), ("files", ("bad.txt", b"x", "text/plain"))],
    )

    assert response.status_code == 400
    assert store._workbooks == {}


def test_upload_without_files_is_rejected(client):
    assert client.post("/upload").status_code == 422
