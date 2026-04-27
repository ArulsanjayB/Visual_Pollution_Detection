"""
Visual Pollution Detector — FastAPI Backend
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'ml'))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path

from app.config import settings
from app.database import init_firebase
from app.routers import auth, reports, municipal, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting Visual Pollution Detector API...")
    init_firebase()

    # Load ML model into app state (singleton)
    weights_path = settings.model_weights_path
    if Path(weights_path).exists():
        from app.services.inference_service import InferenceService
        app.state.inference = InferenceService(weights_path)
        print(f"ML model loaded: {weights_path}")
    else:
        app.state.inference = None
        print(f"WARNING: Model weights not found at {weights_path}")
        print("         API will start but inference endpoints will return demo data.")
        print("         Train the model first: cd ml && python train.py")

    # Ensure storage directory exists
    os.makedirs(settings.local_storage_path, exist_ok=True)
    os.makedirs(os.path.join(settings.local_storage_path, "images"), exist_ok=True)

    yield
    # Shutdown
    print("Shutting down...")


app = FastAPI(
    title="CivicLens — Visual Pollution Detector API",
    description="AI-powered visual pollution reporting for municipal authorities",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,       prefix="/api/auth",      tags=["Auth"])
app.include_router(reports.router,    prefix="/api/reports",   tags=["Reports"])
app.include_router(municipal.router,  prefix="/api/municipal", tags=["Municipal"])
app.include_router(admin.router,      prefix="/api/admin",     tags=["Admin"])

# Serve uploaded images/XAI visualizations
storage_path = Path(settings.local_storage_path)
storage_path.mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(storage_path)), name="storage")

# Serve web dashboard
dashboard_path = Path(__file__).parent.parent / "dashboard"
if dashboard_path.exists():
    app.mount("/dashboard", StaticFiles(directory=str(dashboard_path), html=True), name="dashboard")


@app.get("/api/health")
async def health():
    has_model = app.state.inference is not None
    return {
        "status": "ok",
        "model_loaded": has_model,
        "model_path": settings.model_weights_path,
        "dev_mode": settings.dev_mode,
        "database_mode": settings.database_mode,
    }


@app.get("/")
async def root():
    return {
        "app": "CivicLens — Visual Pollution Detector",
        "version": "1.0.0",
        "dashboard": "/dashboard/",
        "api_docs": "/docs",
        "health": "/api/health",
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"detail": str(exc)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port, reload=True)

# reload
