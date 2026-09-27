import os
from pathlib import Path

_env_file = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_file.exists():
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

"""
AEGIS-SAR Main FastAPI Application.

Autonomous Maritime Oil Spill Intelligence & Vessel Attribution Platform
Operator Control Layer & Backend Orchestration Service.
"""

import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.api.routes import (
    system_router,
    watch_router,
    satellite_router,
    incidents_router,
    ais_router,
    attribution_router,
    reports_router,
    settings_router,
    search_router,
    jobs_router,
)
from src.api.ws import global_ws_hub, setup_job_ws_forwarding
from src.api.state import global_app_state


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    loop = asyncio.get_running_loop()
    global_ws_hub.set_event_loop(loop)
    setup_job_ws_forwarding()
    yield
    # Shutdown actions
    if global_app_state._watch_running:
        global_app_state.stop_watch()


app = FastAPI(
    title="AEGIS-SAR Intelligence Platform API",
    description="Operational command and control API for SIH Problem Statement 26143.",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount REST API routers
app.include_router(system_router)
app.include_router(watch_router)
app.include_router(satellite_router)
app.include_router(incidents_router)
app.include_router(ais_router)
app.include_router(attribution_router)
app.include_router(reports_router)
app.include_router(settings_router)
app.include_router(search_router)
app.include_router(jobs_router)


# WebSocket endpoint for real-time streaming
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await global_ws_hub.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle any incoming client ping or message if needed
    except WebSocketDisconnect:
        global_ws_hub.disconnect(websocket)
    except Exception:
        global_ws_hub.disconnect(websocket)


# Mount static data folder for SAR rasters and assets
data_dir = Path("data")
if data_dir.exists():
    app.mount("/data", StaticFiles(directory=str(data_dir)), name="data")

# Mount static build of React frontend if present
frontend_dist = Path("frontend/dist")
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="API route not found")
        file_path = frontend_dist / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(frontend_dist / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)
