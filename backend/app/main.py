"""
JUSTICE Legal AI Backend — FastAPI Entrypoint
Orchestrates Indian Legal Retrieval, Article 141 Citation DAG Traversals,
and Section 27 Contract Auditing with strict gemini-3.8-flash integration.

Deploy edition: serves the built React frontend and gates the whole site
behind HTTP Basic Auth when SITE_PASSWORD is set (unset = local dev, no gate).
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
import base64
import logging
import os
import secrets
import time
from pathlib import Path

from app.config import settings
from app.routers import search, citator, audit, maxims, docchat
from app.services.llm_service import llm_service
from app.services.qdrant_service import qdrant_service
from app.services.neo4j_service import neo4j_service
from app.services.statute_service import statute_service
from app.services.embedding_service import embedding_service

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

# 1b. Site-wide password gate (HTTP Basic Auth).
# Active only when SITE_PASSWORD is set in the environment; local dev without it is unchanged.
# Any username is accepted; the password must match SITE_PASSWORD.
SITE_PASSWORD = os.getenv("SITE_PASSWORD", "").strip()

@app.middleware("http")
async def site_password_gate(request: Request, call_next):
    if not SITE_PASSWORD or request.url.path == "/health":
        return await call_next(request)
    auth = request.headers.get("authorization", "")
    authenticated = False
    if auth.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(auth[6:].strip()).decode("utf-8")
            _, _, supplied = decoded.partition(":")
            authenticated = bool(supplied) and secrets.compare_digest(supplied, SITE_PASSWORD)
        except Exception:
            authenticated = False
    if not authenticated:
        return PlainTextResponse(
            "Authentication required.",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="JUSTICE"'},
        )
    return await call_next(request)

# 2. Register Functional Routers
app.include_router(search.router)
app.include_router(citator.router)
app.include_router(audit.router)
app.include_router(maxims.router)
app.include_router(docchat.router)

# 3. Diagnostic Health Endpoint
@app.get("/health", tags=["Diagnostic"])
async def health_check():
    """
    GET /health
    Diagnostic health endpoint reporting the live connectivity state of:
    - LLM Service (Groq with openai/gpt-oss-120b & spillover)
    - SQLite Embedded Bare Acts Database
    - Qdrant Vector Database
    - Neo4j Knowledge Graph (Article 141 Lineage)
    """
    llm_health = await llm_service.check_health()
    statute_health = statute_service.check_health()
    qdrant_health = qdrant_service.check_health()
    neo4j_health = neo4j_service.check_health()
    embedding_health = embedding_service.describe()

    # Determine aggregated operational health
    is_operational = True
    active_mode = "ONLINE" if (llm_health.get("configured") and qdrant_health.get("status") == "connected") else "HYBRID_FALLBACK"

    return {
        "status": "HEALTHY" if is_operational else "DEGRADED",
        "system_mode": active_mode,
        "enforced_model": settings.LLM_MODEL,
        "llm_provider": settings.LLM_PROVIDER,
        "embeddings": embedding_health,
        "services": {
            "embeddings": embedding_health,
            "llm": llm_health,
            "gemini": llm_health,  # backward compatibility alias
            "statutes_sqlite": statute_health,
            "qdrant": qdrant_health,
            "neo4j": neo4j_health
        },
        "server_time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

# 4. Serve the built React frontend (Vite dist) with SPA fallback.
# Registered after every API route so /api/v1/*, /docs and /health keep working.
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "dist"
if FRONTEND_DIST.exists():
    if (FRONTEND_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        candidate = FRONTEND_DIST / full_path if full_path else None
        if candidate and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/", tags=["Diagnostic"])
    async def root_index():
        return {
            "workspace": "JUSTICE — Editorial Legal Intelligence",
            "jurisdiction": "Republic of India",
            "version": settings.VERSION,
            "docs": "/docs",
            "health": "/health"
        }

@app.on_event("startup")
async def on_startup():
    logger.info("=================================================================")
    logger.info("   JUSTICE Legal AI Backend — Initializing Production Engine    ")
    logger.info(f"   Model Target: {settings.LLM_MODEL} (Provider: {settings.LLM_PROVIDER})")
    logger.info(f"   LLM Status: {'Configured' if settings.is_llm_active else 'Deterministic Fallback Mode'}")
    logger.info(f"   Embeddings: {embedding_service.mode} ({embedding_service.describe().get('engine')}, dim={embedding_service.dimension})")
    logger.info(f"   Site Password Gate: {'ENABLED' if SITE_PASSWORD else 'disabled (local dev mode)'}")
    logger.info(f"   Frontend Dist: {'serving ' + str(FRONTEND_DIST) if FRONTEND_DIST.exists() else 'not found (API only)'}")
    logger.info(f"   Allowed CORS Origins: {settings.CORS_ORIGINS}")
    logger.info("=================================================================")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
