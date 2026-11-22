"""Read the first worksheet of an .xlsx file into a DataFrame."""

from dataclasses import dataclass
from io import BytesIO

import pandas as pd


class ExcelError(ValueError):
    """The uploaded file is not a usable .xlsx workbook."""


@dataclass
class Sheet:
    worksheet_name: str
    dataframe: pd.DataFrame


def read_first_sheet(filename: str, content: bytes) -> Sheet:
    if not filename.lower().endswith(".xlsx"):
        raise ExcelError(f"'{filename}' is not an .xlsx file")

    try:
        with pd.ExcelFile(BytesIO(content), engine="openpyxl") as workbook:
            worksheet_name = workbook.sheet_names[0]
            dataframe = pd.read_excel(workbook, sheet_name=0)
    except Exception as exc:
        raise ExcelError(f"'{filename}' could not be read as an Excel workbook") from exc

    dataframe.columns = [str(column).strip() for column in dataframe.columns]
    if dataframe.empty:
        raise ExcelError(f"the first worksheet '{worksheet_name}' in '{filename}' has no data")

    return Sheet(worksheet_name=worksheet_name, dataframe=dataframe)
