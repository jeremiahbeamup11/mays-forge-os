"""Aggregator for all v1 API routers.

Each feature file (health.py, ingest.py, analyze.py, etc.) defines its own
APIRouter. This file brings them all together under a single /api/v1 prefix.

When you add a new feature:
1. Create app/api/v1/<feature>.py with its own `router = APIRouter(...)`
2. Import it here and call `api_router.include_router(...)`
3. That's it — the endpoint is live.
"""

from fastapi import APIRouter

from app.api.v1 import health

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
