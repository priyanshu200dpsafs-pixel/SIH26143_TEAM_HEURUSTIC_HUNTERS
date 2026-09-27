"""
Route modules package for AEGIS-SAR API.
"""

from src.api.routes.system import router as system_router
from src.api.routes.watch import router as watch_router
from src.api.routes.satellite import router as satellite_router
from src.api.routes.incidents import router as incidents_router
from src.api.routes.ais import router as ais_router
from src.api.routes.attribution import router as attribution_router
from src.api.routes.reports import router as reports_router
from src.api.routes.settings import router as settings_router
from src.api.routes.search import router as search_router
from src.api.routes.jobs import router as jobs_router

__all__ = [
    "system_router",
    "watch_router",
    "satellite_router",
    "incidents_router",
    "ais_router",
    "attribution_router",
    "reports_router",
    "settings_router",
    "search_router",
    "jobs_router",
]
