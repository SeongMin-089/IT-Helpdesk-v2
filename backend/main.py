from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app import config
from app.routers import auth, archive, assignees, categories, faqs, legacy, reference, tickets


app = FastAPI(
    title="IT Helpdesk v2 API",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config.AUTH_ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def protect_state_changes(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/"):
        try:
            auth.require_trusted_origin(request)
        except HTTPException as error:
            return JSONResponse(
                status_code=error.status_code,
                content={"detail": error.detail},
            )
    return await call_next(request)

app.include_router(legacy.router)
app.include_router(auth.router)
auth_dependencies = [Depends(auth.require_authenticated_user)]
app.include_router(archive.router, dependencies=auth_dependencies)
app.include_router(tickets.router, dependencies=auth_dependencies)
app.include_router(faqs.router, dependencies=auth_dependencies)
app.include_router(reference.router, dependencies=auth_dependencies)
app.include_router(assignees.router, dependencies=auth_dependencies)
app.include_router(categories.router, dependencies=auth_dependencies)
