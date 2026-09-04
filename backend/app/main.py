"""FastAPI 應用進入點。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.database import close_pool, init_pool
from app.config.settings import app_settings
from app.middleware.error_handler import register_error_handlers
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routers import auth, health, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool(app_settings.DATABASE_URL)
    yield
    await close_pool()


app = FastAPI(title="Employee Portal API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)

register_error_handlers(app)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
