import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import auth, organizations, queues, jobs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scheduler")

app = FastAPI(title="Distributed Job Scheduler API", version="0.1.0")

app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(queues.router)
app.include_router(jobs.router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.warning(f"HTTPException: {exc.status_code} {exc.detail} - {request.url}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.status_code, "message": exc.detail}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"ValidationError: {exc.errors()} - {request.url}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": {"code": 422, "message": "Validation failed", "details": jsonable_encoder(exc.errors())}},
    )


@app.get("/health")
def health():
    return {"status": "ok"}
