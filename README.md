# JUSTICE — AI-first Indian legal research

An "easier Manupatra": plain-language search over real Indian case law and
statutes, a document clause auditor, and an Article 141 precedent citator,
all grounded in free public legal sources.

**This repository is private and contains work-in-progress that may be the
subject of a future patent filing. Do not make it public or demo it publicly
without checking first.**

## Stack

- **Frontend:** React 19 + Vite (`src/`), mobile-responsive workspace shell.
- **Backend:** FastAPI (`backend/`), unified LLM service running on Groq
  (`openai/gpt-oss-120b` primary with automated `openai/gpt-oss-20b` spillover;
  Gemini fallback supported) for HyDE synthesis, clause audits, citator analysis,
  grounded document chat, and Latin maxim explanations.
- **Search:** Qdrant vector DB over a verified corpus of real Supreme Court
  and High Court judgments (`backend/app/data/section27_precedents.json`),
  with a labeled local-index fallback when Qdrant is down.
- **Citator:** Neo4j citation-treatment graph, with a labeled in-memory
  fallback graph when Neo4j is down (404 on unknown case IDs).
- **Statutes:** embedded SQLite (`backend/data/justice_statutes.db`),
  auto-seeded from `app.ingest.seed_bare_acts` (12 verified commercial provisions).

## Data sources (free and public only)

Every precedent is verified against a free primary source — Indian Kanoon
full-text judgments and the Supreme Court judis portal — with the link
stored on each record (`source.url`). Ratio summaries are editorial
paraphrases for retrieval; always read the full judgment at the source
link. See `docs/data-sources.md` for the full list. **No Manupatra or any
paywalled database is scraped.**

## Quick start (Docker, recommended)

```bash
cp .env.example .env        # fill in GROQ_API_KEY; .env is gitignored
docker compose up --build
docker compose exec backend python -m app.ingest.seed_qdrant
docker compose exec backend python -m app.ingest.seed_neo4j
```

- Backend API: http://localhost:8000 (Swagger at `/docs`, health at `/health`)
- Qdrant: http://localhost:6333
- Neo4j browser: http://localhost:7474 (neo4j / your `NEO4J_PASSWORD`)

## Quick start (local dev)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # or backend/.env; fill in GROQ_API_KEY
uvicorn app.main:app --reload
```

Without Qdrant/Neo4j running, the backend still works: search and citator
serve the verified corpus from labeled fallbacks, and `/health` shows which
mode each service is in. Without an LLM key, AI features run in labeled
deterministic fallback modes.

Frontend:

```bash
npm install
npm run dev                 # http://localhost:5173
```

## Environment variables

See `.env.example`. Never commit a real key. `GROQ_API_KEY` is the primary
secret the backend reads (with `GEMINI_API_KEY` supported as fallback).
`SITE_PASSWORD` gates public deployments with HTTP Basic Auth.

## API surface (v1)

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | live status of LLM, Qdrant, Neo4j, SQLite (+ active fallback modes) |
| `POST /api/v1/search` | HyDE + hybrid precedent search over the verified corpus |
| `GET /api/v1/citator/{case_id}` | Article 141 treatment tree + citation DAG (404 for unknown ids) |
| `GET /api/v1/citator` | list indexed precedents |
| `POST /api/v1/audit/verify-clause` | Section 27 single clause audit with redline & precedent pinning |
| `POST /api/v1/audit/contract` | Multi-clause document analyzer (accepts PDF/DOCX or text) |
| `POST /api/v1/doc/upload` | Parse and index contract for grounded document Q&A |
| `POST /api/v1/doc/chat` | Grounded contract Q&A (quotes verbatim clause or returns "not found") |
| `GET /api/v1/maxims` | 240+ Latin canons and legal maxims library |
| `POST /api/v1/maxims/explain` | Grounded maxim explanation and factual scenario application |

## Ingestion pipelines

| Script | What it does |
| --- | --- |
| `python -m app.ingest.seed_bare_acts` | seeds the SQLite statute database (auto-runs on first boot) |
| `python -m app.ingest.seed_qdrant` | embeds the verified corpus and upserts it into Qdrant (idempotent) |
| `python -m app.ingest.seed_neo4j` | builds the Case/TREATS citation graph in Neo4j (idempotent) |
| `python -m app.ingest.indiacode_scraper` | structures bare-act sections (India Code, with bundled verified text) |
| `python -m app.ingest.escr_parser` | segments e-SCR Supreme Court judgment PDFs |

## Disclaimer

JUSTICE is a research aid, not legal advice. Retrieval summaries are
editorial paraphrases; verify against the linked full judgments before
relying on anything.
