from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.bootstrap import bootstrap_database
from app.modules.auctions.router import router as auctions_router
from app.modules.auth.router import router as auth_router
from app.modules.external_chits.router import router as external_chits_router
from app.modules.groups.router import router as groups_router
from app.modules.payments.router import router as payments_router
from app.modules.subscribers.router import router as subscribers_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    bootstrap_database()
    yield


app = FastAPI(title="Chit Fund Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(subscribers_router)
app.include_router(groups_router)
app.include_router(auctions_router)
app.include_router(payments_router)
app.include_router(external_chits_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
