from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .errors import AppError
from .routers import all_routers
from .seed import seed_database
from .settings import get_settings

settings = get_settings()
settings.upload_path.mkdir(parents=True, exist_ok=True)

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    request.state.trace_id = str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Trace-Id"] = request.state.trace_id
    return response


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
            "trace_id": getattr(request.state, "trace_id", ""),
        },
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "请求参数不合法",
                "details": {"errors": exc.errors()},
            },
            "trace_id": getattr(request.state, "trace_id", ""),
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "系统内部错误",
                "details": {"reason": str(exc)},
            },
            "trace_id": getattr(request.state, "trace_id", ""),
        },
    )


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    from .database import SessionLocal  # local import to avoid circular reference during app setup

    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()

for router in all_routers:
    app.include_router(router)

# local development convenience; production static files are served by nginx.
app.mount(settings.upload_public_prefix, StaticFiles(directory=settings.upload_path), name="uploads")
