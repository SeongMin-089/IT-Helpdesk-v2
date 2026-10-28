from fastapi import FastAPI

from app.routers import archive, assignees, categories, faqs, legacy, reference, tickets


app = FastAPI(
    title="IT Helpdesk v2 API",
    version="0.2.0",
)

app.include_router(legacy.router)
app.include_router(archive.router)
app.include_router(tickets.router)
app.include_router(faqs.router)
app.include_router(reference.router)
app.include_router(assignees.router)
app.include_router(categories.router)
