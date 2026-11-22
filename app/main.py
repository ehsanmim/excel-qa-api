"""FastAPI app: POST /upload and POST /chat."""

from functools import lru_cache

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from app.excel import ExcelError, read_first_sheet
from app.executor import SUPPORTED_MESSAGE, PlanError, execute
from app.models import ChatRequest, ChatResponse, UploadedWorkbook, UploadResponse
from app.planner import Planner, PlannerError, describe_columns, make_planner
from app.store import WorkbookStore

app = FastAPI(title="Excel Q&A API", version="1.0.0")


@app.exception_handler(PlannerError)
def planner_error(request: Request, exc: PlannerError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@lru_cache
def get_store() -> WorkbookStore:
    return WorkbookStore()


@lru_cache
def get_planner() -> Planner:
    return make_planner()


@app.post("/upload", response_model=UploadResponse)
async def upload(
    files: list[UploadFile] = File(...),
    store: WorkbookStore = Depends(get_store),
) -> UploadResponse:
    # Read and validate every file first, so one bad file stores nothing.
    sheets = []
    for file in files:
        filename = file.filename or ""
        try:
            sheets.append((filename, read_first_sheet(filename, await file.read())))
        except ExcelError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    workbooks = []
    for filename, sheet in sheets:
        stored = store.add(filename, sheet.worksheet_name, sheet.dataframe)
        workbooks.append(
            UploadedWorkbook(
                workbook_id=stored.workbook_id,
                filename=stored.filename,
                worksheet_name=stored.worksheet_name,
                columns=list(stored.dataframe.columns),
            )
        )
    return UploadResponse(workbooks=workbooks)


@app.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    store: WorkbookStore = Depends(get_store),
    planner: Planner = Depends(get_planner),
) -> ChatResponse:
    workbook = store.get(request.workbook_id)
    if workbook is None:
        raise HTTPException(status_code=404, detail=f"workbook '{request.workbook_id}' not found")

    plan = planner.plan(request.question, describe_columns(workbook.dataframe))

    context = {
        "operation": plan.operation,
        "plan": plan,
        "filename": workbook.filename,
        "worksheet_name": workbook.worksheet_name,
    }

    if plan.operation == "unsupported":
        reason = plan.reason or "This question is not supported."
        return ChatResponse(status="unsupported", message=f"{reason} {SUPPORTED_MESSAGE}", **context)

    try:
        result = execute(plan, workbook.dataframe)
    except PlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ChatResponse(status="ok", result=result.value, count=result.count, **context)
