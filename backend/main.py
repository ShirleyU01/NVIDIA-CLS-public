from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import Base, engine
from backend.routes import api_router

# Create tables on startup for MVP (suitable for dev/demo; migrations recommended later).
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Socrates Central Backend", version="0.1.0")

# Dev-friendly CORS so the Vite UI (localhost:5173) can call this service.
# Tighten this list in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


app.include_router(api_router)


