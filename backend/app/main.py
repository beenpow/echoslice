from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db import init_db, DB_PATH

app = FastAPI(title="EchoSlice API", version="0.0.1")

# Frontend dev server(CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://localhost:5173",
        "https://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "ok", "service": "echoslice-backend"}

@app.get("/db/health")
def db_health():
    return {"db": "ok", "path": str(DB_PATH)}