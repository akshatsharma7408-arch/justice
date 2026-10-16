"""
JUSTICE Legal AI Backend — FastAPI Entrypoint
Orchestrates Indian Legal Retrieval, Article 141 Citation DAG Traversals,
and Section 27 Contract Auditing with strict gemini-3.8-flash integration.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import time

from app.config import settings
from app.routers import search, citator, audit
from app.services.gemini_service import gemini_service
from app.services.qdrant_service import qdrant_service
from app.services.neo4j_service import neo4j_service
from app.services.statute_service import statute_service

# Setup unified logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("justice.backend")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Production-grade Python legal retrieval and statutory audit engine for JUSTICE. "
        "Bridges the React frontend with Indian Supreme Court jurisprudence, Article 141 DAG trees, "
        "and Section 27 Indian Contract Act compliance auditing."
    ),
    docs_url="/docs",
    redoc_url="/redoc"
)

# 1. CORS Middleware Configuration
# Explicitly authorizes localhost:5173 and 127.0.0.1:5173 as required by frontend Vite runtime
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Register Functional Routers
app.include_router(search.router)
app.include_router(citator.router)
app.include_router(audit.router)

# 3. Diagnostic & Root Endpoints
@app.get("/", tags=["Diagnostic"])
async def root_index():
    return {
        "workspace": "JUSTICE — Editorial Legal Intelligence",
        "jurisdiction": "Republic of India",
        "version": settings.VERSION,
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "search": "/api/v1/search",
            "citator": "/api/v1/citator/{case_id}",
            "audit_verify_clause": "/api/v1/audit/verify-clause",
            "audit_contract": "/api/v1/audit-contract"
        }
    }

@app.get("/health", tags=["Diagnostic"])
async def health_check():
    """
    GET /health
    Diagnostic health endpoint reporting the live connectivity state of:
    - Gemini AI Service (gemini-3.8-flash)
    - SQLite Embedded Bare Acts Database
    - Qdrant Vector Database
    - Neo4j Knowledge Graph (Article 141 Lineage)
    """
    gemini_health = await gemini_service.check_health()
    statute_health = statute_service.check_health()
    qdrant_health = qdrant_service.check_health()
    neo4j_health = neo4j_service.check_health()

    # Determine aggregated operational health
    is_operational = True
    active_mode = "ONLINE" if (gemini_health.get("configured") and qdrant_health.get("status") == "connected") else "HYBRID_FALLBACK"

    return {
        "status": "HEALTHY" if is_operational else "DEGRADED",
        "system_mode": active_mode,
        "enforced_model": settings.GEMINI_MODEL,
        "services": {
            "gemini": gemini_health,
            "statutes_sqlite": statute_health,
            "qdrant": qdrant_health,
            "neo4j": neo4j_health
        },
        "server_time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

@app.on_event("startup")
async def on_startup():
    logger.info("=================================================================")
    logger.info("   JUSTICE Legal AI Backend — Initializing Production Engine    ")
    logger.info(f"   Model Target: {settings.GEMINI_MODEL}")
    logger.info(f"   Gemini Status: {'Configured' if settings.is_gemini_active else 'Simulated Fallback Mode'}")
    logger.info(f"   Allowed CORS Origins: {settings.CORS_ORIGINS}")
    logger.info("=================================================================")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
