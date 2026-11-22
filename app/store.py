"""In-memory workbook store. Everything is lost when the process stops."""

from dataclasses import dataclass
from uuid import uuid4

import pandas as pd


@dataclass
class StoredWorkbook:
    workbook_id: str
    filename: str
    worksheet_name: str
    dataframe: pd.DataFrame


class WorkbookStore:
    def __init__(self) -> None:
        self._workbooks: dict[str, StoredWorkbook] = {}

    def add(self, filename: str, worksheet_name: str, dataframe: pd.DataFrame) -> StoredWorkbook:
        workbook = StoredWorkbook(uuid4().hex, filename, worksheet_name, dataframe)
        self._workbooks[workbook.workbook_id] = workbook
        return workbook

    def get(self, workbook_id: str) -> StoredWorkbook | None:
        return self._workbooks.get(workbook_id)
