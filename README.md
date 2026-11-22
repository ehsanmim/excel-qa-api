# Excel Q&A API

Upload `.xlsx` files and ask questions about them in plain English. An LLM turns each question into a query plan (filter, sum or count, which columns, which value) and pandas computes the answer, so every number comes from pandas.

## Setup

Python 3.12 or newer.

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env    # then add your API key
```

The app loads `.env` at startup; variables set in the shell take precedence. It supports two providers:

- OpenAI or any OpenAI-compatible API such as OpenRouter, the default: `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_MODEL` (for example `openai/gpt-6-luna`) and, for anything other than OpenAI itself, `OPENAI_BASE_URL` (OpenRouter: `https://openrouter.ai/api/v1`). The model must support structured output.
- Anthropic: `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`, and optionally `ANTHROPIC_MODEL` (default `claude-opus-5-5`).

## Run and test

```powershell
bin\serve    # starts the server and prints the URLs; Swagger UI is at http://127.0.0.1:8000/docs
bin\test     # runs pytest; extra arguments are passed on
```

On macOS or Linux, use `uvicorn app.main:app --reload` and `python -m pytest`.

The tests use a fake planner and need no network. `tests/test_live_llm.py` sends the five example questions to the real LLM and runs only when a key is configured.

## API

`POST /upload` takes one or more `.xlsx` files in the field `files`, reads the first sheet of each, and returns `workbook_id`, `filename`, `worksheet_name` and `columns` for every file.

```bash
curl -F "files=@sample_data/sample.xlsx" http://127.0.0.1:8000/upload
```

`POST /chat` takes a workbook ID and a question:

```bash
curl -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" \
  -d '{"workbook_id": "<id>", "question": "What is the total revenue for Germany?"}'
```

```json
{
  "status": "ok",
  "operation": "sum",
  "result": 110207.5,
  "count": 23,
  "message": null,
  "plan": {"operation": "sum", "target_column": "Revenue_EUR", "filter_column": "Country",
           "filter_value": "Germany", "reason": null},
  "filename": "sample.xlsx",
  "worksheet_name": "Sales_Data"
}
```

On the sample workbook, total revenue is 651497.5 and there are 120 records, 21 of them for France. "Show all records for Germany" returns the 23 matching rows in `result`. A question outside the three operations, such as an average, returns `status: "unsupported"` with a message listing what is supported.

## Design

- `excel.py` reads the first sheet into a DataFrame, and `store.py` keeps it in memory under a UUID.
- `planner.py` sends the LLM only the schema: column names, types, and the values of text columns with at most 30 distinct values. That is enough to map "revenue" to `Revenue_EUR` and "germany" to `Germany`, and the rows never leave the server. Structured output parses the reply straight into a Pydantic `QueryPlan`.
- `executor.py` checks the plan against the DataFrame and runs it with pandas. Text filters are exact matches that ignore case and surrounding spaces; numeric and date values are converted first. Integer sums stay integers and float sums are rounded to 2 decimals. Zero matches is a valid result.
- `main.py` wires the pieces together. The planner is a FastAPI dependency, so the tests swap in a fake.

| Error | Status |
| --- | --- |
| File is not `.xlsx`, can't be read, or has an empty first sheet (one bad file stores nothing) | 400 |
| Unknown workbook ID | 404 |
| Empty question, unknown column, sum of a text column, or a non-numeric value for a numeric filter | 422 |
| LLM error or invalid plan | 502 |
| LLM not configured, rate-limited or unreachable (60 second timeout) | 503 |

## Limitations and next steps

Workbooks live in memory and are lost on restart. Each question gets one exact-match filter and only sum or count, and there is no paging, authentication or upload size limit. Next I would add persistence, average and group-by, multiple filters, authentication and size limits, and logging of each plan next to its question.
