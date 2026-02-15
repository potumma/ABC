from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import time
import logging

from app.routes.movies import router as movies_router
from app.routes.showtimes import router as showtimes_router
from app.routes.public import router as public_router
from app.routes.bookings import router as bookings_router
from app.routes.users import router as users_router
from app.routes.auth import router as auth_router
from app.routes.review import router as reviews_router
from app.routes.loyalty import router as loyalty_router

from app.core.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    generic_exception_handler
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="ABCineplex API",
    description="Movie booking system API - Optimized for performance",
    version="2.0.0"
)

# Setup CORS - allow all origins during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# Performance logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(f"{request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s")
    response.headers["X-Process-Time"] = str(process_time)
    return response


# Register global exception handlers - handles all errors centrally
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Include routers
app.include_router(auth_router)
app.include_router(movies_router)
app.include_router(showtimes_router)
app.include_router(public_router)
app.include_router(bookings_router)
app.include_router(users_router)
app.include_router(reviews_router)
app.include_router(loyalty_router)


@app.get("/")
def root():
    return {
        "message": "ABCineplex API is running",
        "version": "2.0.0",
        "status": "optimized",
        "docs": "/docs"
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)