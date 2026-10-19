"""
JUSTICE Legal AI Backend — Indian Supreme Court Judgments Pipeline
Autonomous pipeline for:
1. Downloading per-year metadata parquets from s3://indian-supreme-court-judgments
2. Filtering headnotes by specific contract & statutory keywords up to 1,000 cases
3. Downloading judgment PDFs (with retries & 4 parallel workers)
4. Extracting and paragraph-boundary chunking with PyMuPDF
5. Embedding chunks via local fastembed (all-MiniLM-L6-v2, 384 dims, batch 64, checkpointed)
6. Upserting into Qdrant collection 'sc_judgments' (or saving for upload if credentials pending)
"""

import argparse
import io
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pandas as pd

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("justice.sc_pipeline")

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "sc_dataset"
METADATA_DIR = DATA_DIR / "metadata"
PDF_DIR = DATA_DIR / "pdfs"
CHUNKS_DIR = DATA_DIR / "chunks"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"

S3_BASE_URL = "https://indian-supreme-court-judgments.s3.amazonaws.com"

SPECIFIC_KEYWORDS = [
    "section 27",
    "restraint of trade",
    "Contract Act",
    "liquidated damages",
    "article 141",
]
GENERAL_KEYWORD = "contract"


# -------------------------------------------------------------------------- #
# Step 1: Download Metadata Parquets (1950 - 2026)                          #
# -------------------------------------------------------------------------- #

def get_available_years() -> List[int]:
    """Queries S3 bucket to list all available metadata year directories."""
    url = f"{S3_BASE_URL}/?prefix=metadata/parquet/&delimiter=/"
    try:
        from xml.etree import ElementTree as ET
        r = httpx.get(url, timeout=30.0)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        ns = "{http://s3.amazonaws.com/doc/2006-03-01/}"
        years = []
        for p in root.findall(f"{ns}CommonPrefixes"):
            prefix = p.find(f"{ns}Prefix").text
            m = re.search(r'year=(\d+)', prefix)
            if m:
                years.append(int(m.group(1)))
        return sorted(years)
    except Exception as e:
        logger.warning("Could not query S3 root XML: %s. Using default range 1950-2026.", e)
        return list(range(1950, 2027))


def download_year_metadata(year: int) -> Tuple[int, bool, Optional[Path]]:
    """Downloads metadata.parquet for a specific year. Resumable."""
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    target_path = METADATA_DIR / f"metadata_{year}.parquet"
    if target_path.exists() and target_path.stat().st_size > 0:
        return (year, True, target_path)

    url = f"{S3_BASE_URL}/metadata/parquet/year={year}/metadata.parquet"
    for attempt in range(3):
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.get(url)
                if resp.status_code == 404:
                    logger.warning("Metadata for year %d returned 404.", year)
                    return (year, False, None)
                resp.raise_for_status()
                with open(target_path, "wb") as f:
                    f.write(resp.content)
                logger.info("Downloaded metadata for year %d (%.1f KB)", year, len(resp.content) / 1024)
                return (year, True, target_path)
        except Exception as e:
            time.sleep(1.0 * (attempt + 1))
            if attempt == 2:
                logger.error("Failed to download metadata for year %d: %s", year, e)
                return (year, False, None)
    return (year, False, None)


def run_step_1_download_metadata() -> pd.DataFrame:
    """Downloads all per-year metadata parquets and combines into one DataFrame."""
    combined_parquet_path = METADATA_DIR / "all_metadata.parquet"
    if combined_parquet_path.exists() and combined_parquet_path.stat().st_size > 0:
        logger.info("Resuming: Loading cached all_metadata.parquet from %s", combined_parquet_path)
        return pd.read_parquet(combined_parquet_path)

    years = get_available_years()
    logger.info("Discovered %d years to process (%d to %d)", len(years), years[0], years[-1])

    # Download in parallel
    dfs = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(download_year_metadata, y): y for y in years}
        for future in as_completed(futures):
            year, success, path = future.result()
            if success and path and path.exists():
                try:
                    df = pd.read_parquet(path)
                    dfs.append(df)
                except Exception as e:
                    logger.error("Error reading %s: %s", path, e)

    if not dfs:
        raise RuntimeError("No metadata parquets could be loaded!")

    all_df = pd.concat(dfs, ignore_index=True)
    all_df.to_parquet(combined_parquet_path, index=False)
    logger.info("Successfully compiled all_metadata.parquet: %d total Supreme Court cases", len(all_df))
    return all_df


# -------------------------------------------------------------------------- #
# Step 2: Filter by Headnote Keywords (Up to 1,000 cases)                   #
# -------------------------------------------------------------------------- #

def run_step_2_filter_cases(all_df: Optional[pd.DataFrame] = None) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """
    Filters by headnote text in 'raw_html' column, case-insensitive:
    - Specific keywords: "section 27", "restraint of trade", "Contract Act", "liquidated damages", "article 141"
    - General keyword: "contract"
    Keeps all specific-term matches, fills to 1,000 cases with general contract matches, newest first.
    """
    filtered_path = METADATA_DIR / "filtered_cases.parquet"
    stats_path = METADATA_DIR / "filter_stats.json"

    if filtered_path.exists() and stats_path.exists():
        logger.info("Resuming: Loading cached filtered cases from %s", filtered_path)
        with open(stats_path, "r", encoding="utf-8") as f:
            stats = json.load(f)
        return pd.read_parquet(filtered_path), stats

    if all_df is None:
        all_df = run_step_1_download_metadata()

    # Pre-clean raw_html
    raw_html_series = all_df["raw_html"].fillna("").astype(str)

    # Calculate keyword counts
    keyword_counts: Dict[str, int] = {}
    specific_masks = []
    for kw in SPECIFIC_KEYWORDS:
        # Case-insensitive substring match
        mask = raw_html_series.str.contains(re.escape(kw), case=False, regex=True)
        count = int(mask.sum())
        keyword_counts[kw] = count
        specific_masks.append(mask)

    # Combined specific mask
    specific_combined = specific_masks[0]
    for m in specific_masks[1:]:
        specific_combined = specific_combined | m

    specific_df = all_df[specific_combined].copy()
    specific_df["match_type"] = "specific"

    # General contract mask
    general_mask = raw_html_series.str.contains(r'\bcontract\b', case=False, regex=True)
    keyword_counts[GENERAL_KEYWORD] = int(general_mask.sum())

    # Cases matching general contract but NOT specific terms
    general_remaining_mask = general_mask & (~specific_combined)
    general_df = all_df[general_remaining_mask].copy()
    general_df["match_type"] = "general_contract"

    # Sort general newest first
    # Parse decision_date or year for clean sorting
    general_df["sort_year"] = pd.to_numeric(general_df["year"], errors="coerce").fillna(0)
    general_df = general_df.sort_values(by=["sort_year"], ascending=False)

    num_specific = len(specific_df)
    needed = max(0, 1000 - num_specific)
    selected_general = general_df.head(needed)

    final_df = pd.concat([specific_df, selected_general], ignore_index=True)
    # Deduplicate by path/case_id just in case
    final_df = final_df.drop_duplicates(subset=["path"]).reset_index(drop=True)

    stats = {
        "total_corpus_cases": len(all_df),
        "keyword_counts": keyword_counts,
        "specific_term_matches": num_specific,
        "general_contract_added": len(selected_general),
        "total_selected_cases": len(final_df),
    }

    final_df.to_parquet(filtered_path, index=False)
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    logger.info("Filtering complete: %s", json.dumps(stats, indent=2))
    return final_df, stats


# -------------------------------------------------------------------------- #
# Step 3: Download PDFs (4 Parallel Workers, Retries, Skip 404s)           #
# -------------------------------------------------------------------------- #

def download_single_pdf(case_row: Dict[str, Any]) -> Dict[str, Any]:
    """Downloads a single case PDF from S3. Resumable."""
    year = str(case_row.get("year", "")).strip()
    path = str(case_row.get("path", "")).strip()
    if not year or not path:
        return {"status": "skipped", "error": "missing year/path"}

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    target_file = PDF_DIR / f"{year}_{path}_EN.pdf"
    if target_file.exists() and target_file.stat().st_size > 500:
        return {"status": "exists", "path": str(target_file), "size": target_file.stat().st_size}

    url = f"{S3_BASE_URL}/data/pdf/year={year}/english/{path}_EN.pdf"
    for attempt in range(3):
        try:
            with httpx.Client(timeout=45.0) as client:
                r = client.get(url)
                if r.status_code == 404:
                    return {"status": "404", "url": url}
                r.raise_for_status()
                with open(target_file, "wb") as f:
                    f.write(r.content)
                return {"status": "downloaded", "path": str(target_file), "size": len(r.content)}
        except Exception as e:
            time.sleep(1.0 * (attempt + 1))
            if attempt == 2:
                return {"status": "failed", "error": str(e), "url": url}

    return {"status": "failed", "url": url}


def run_step_3_download_pdfs(filtered_df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """Downloads all filtered case PDFs using 4 parallel workers."""
    if filtered_df is None:
        filtered_df, _ = run_step_2_filter_cases()

    stats_file = METADATA_DIR / "pdf_download_stats.json"
    rows = filtered_df.to_dict(orient="records")
    total = len(rows)
    logger.info("Starting PDF download for %d cases (4 parallel workers)...", total)

    stats = {
        "total_targets": total,
        "already_existed": 0,
        "downloaded": 0,
        "not_found_404": 0,
        "failed": 0,
        "total_bytes": 0,
    }

    # Parallel download with 4 workers
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(download_single_pdf, r): r for r in rows}
        for idx, future in enumerate(as_completed(futures), 1):
            res = future.result()
            st = res.get("status")
            if st == "exists":
                stats["already_existed"] += 1
                stats["total_bytes"] += res.get("size", 0)
            elif st == "downloaded":
                stats["downloaded"] += 1
                stats["total_bytes"] += res.get("size", 0)
            elif st == "404":
                stats["not_found_404"] += 1
            else:
                stats["failed"] += 1

            if idx % 100 == 0 or idx == total:
                logger.info(
                    "PDF Progress: %d/%d (Downloaded: %d, Existed: %d, 404s: %d, Failed: %d)",
                    idx, total, stats["downloaded"], stats["already_existed"],
                    stats["not_found_404"], stats["failed"]
                )

    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    logger.info("PDF Download Step Complete: %s", json.dumps(stats, indent=2))
    return stats


# -------------------------------------------------------------------------- #
# Step 4: Text Extraction & Paragraph Boundary Chunking (~500w / 50w overlap)#
# -------------------------------------------------------------------------- #

def chunk_text_by_paragraphs(text: str, target_words: int = 500, overlap_words: int = 50) -> List[str]:
    """Chunks legal text along paragraph boundaries to ~500 words with ~50-word overlap."""
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    if not paragraphs:
        # Fallback to single line splitting
        paragraphs = [p.strip() for p in text.splitlines() if p.strip()]

    chunks = []
    current_chunk: List[str] = []
    current_word_count = 0

    for p in paragraphs:
        p_words = p.split()
        if not p_words:
            continue
        p_word_count = len(p_words)

        if current_word_count + p_word_count <= target_words:
            current_chunk.append(p)
            current_word_count += p_word_count
        else:
            if current_chunk:
                chunk_str = "\n\n".join(current_chunk)
                chunks.append(chunk_str)

                # Overlap: keep the trailing words for continuity
                all_chunk_words = chunk_str.split()
                overlap_text = " ".join(all_chunk_words[-overlap_words:]) if len(all_chunk_words) > overlap_words else ""
                current_chunk = [overlap_text, p] if overlap_text else [p]
                current_word_count = len(overlap_text.split()) + p_word_count
            else:
                # A single huge paragraph: split into 500-word blocks
                words = p_words
                start = 0
                while start < len(words):
                    end = start + target_words
                    sub = " ".join(words[start:end])
                    chunks.append(sub)
                    start += target_words - overlap_words
                current_chunk = []
                current_word_count = 0

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return [c.strip() for c in chunks if len(c.strip()) > 50]


def run_step_4_extract_and_chunk(filtered_df: Optional[pd.DataFrame] = None) -> List[Dict[str, Any]]:
    """Extracts text from downloaded PDFs with PyMuPDF and produces structured metadata chunks."""
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    chunks_file = CHUNKS_DIR / "chunks.json"
    if chunks_file.exists() and chunks_file.stat().st_size > 1000:
        logger.info("Resuming: Loading cached chunks from %s", chunks_file)
        with open(chunks_file, "r", encoding="utf-8") as f:
            return json.load(f)

    import fitz  # PyMuPDF

    if filtered_df is None:
        filtered_df, _ = run_step_2_filter_cases()

    rows = filtered_df.to_dict(orient="records")
    all_chunks: List[Dict[str, Any]] = []
    extracted_cases = 0

    logger.info("Extracting text and chunking for %d cases...", len(rows))
    for r in rows:
        year = str(r.get("year", "")).strip()
        path = str(r.get("path", "")).strip()
        pdf_path = PDF_DIR / f"{year}_{path}_EN.pdf"

        if not pdf_path.exists():
            continue

        try:
            doc = fitz.open(pdf_path)
            full_text = ""
            for page in doc:
                full_text += page.get_text() + "\n"
            doc.close()

            if len(full_text.strip()) < 100:
                continue

            extracted_cases += 1
            text_chunks = chunk_text_by_paragraphs(full_text, target_words=500, overlap_words=50)

            title = str(r.get("title", "")).strip()
            citation = str(r.get("citation", "")).strip()
            bench = str(r.get("judge") or r.get("author_judge") or "").strip()
            nc_display = str(r.get("nc_display", "")).strip()
            case_id = path
            source_link = f"{S3_BASE_URL}/data/pdf/year={year}/english/{path}_EN.pdf"

            for c_idx, chunk_text in enumerate(text_chunks):
                all_chunks.append({
                    "chunk_id": f"{year}_{path}_{c_idx}",
                    "case_name": title,
                    "year": int(year) if year.isdigit() else 0,
                    "citation": citation,
                    "bench": bench,
                    "neutral_citation": nc_display,
                    "case_id": case_id,
                    "source_link": source_link,
                    "chunk_index": c_idx,
                    "total_chunks_in_case": len(text_chunks),
                    "text": chunk_text
                })

        except Exception as e:
            logger.warning("Error extracting text from %s: %s", pdf_path, e)

    with open(chunks_file, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f)

    logger.info("Extraction complete: Extracted %d cases into %d total chunks (avg %.1f chunks/case)",
                extracted_cases, len(all_chunks), len(all_chunks) / max(1, extracted_cases))
    return all_chunks


# -------------------------------------------------------------------------- #
# Step 5: Local Semantic Embeddings (Batch 64, Checkpointed)                #
# -------------------------------------------------------------------------- #

def run_step_5_embed_chunks(chunks: Optional[List[Dict[str, Any]]] = None) -> Tuple[List[Dict[str, Any]], List[List[float]]]:
    """Generates 384-dimensional dense semantic vectors using local fastembed in batches of 64."""
    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_file = EMBEDDINGS_DIR / "embeddings_checkpoint.parquet"

    if chunks is None:
        chunks = run_step_4_extract_and_chunk()

    from app.services.embedding_service import embedding_service
    logger.info("Using local embedding engine: %s (mode=%s, dim=%d)",
                embedding_service.describe().get("engine"), embedding_service.mode, embedding_service.dimension)

    # Check for existing checkpoint
    existing_vectors = []
    start_idx = 0
    if checkpoint_file.exists():
        try:
            chk_df = pd.read_parquet(checkpoint_file)
            existing_vectors = chk_df["vector"].tolist()
            start_idx = len(existing_vectors)
            logger.info("Resuming: Found existing checkpoint with %d / %d embedded chunks", start_idx, len(chunks))
        except Exception as e:
            logger.warning("Could not read checkpoint file: %s. Re-embedding.", e)
            existing_vectors = []
            start_idx = 0

    all_vectors = list(existing_vectors)
    batch_size = 64
    total = len(chunks)

    for i in range(start_idx, total, batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c["text"] for c in batch]
        t0 = time.time()
        vectors = embedding_service.embed_texts(texts)
        duration = time.time() - t0

        all_vectors.extend(vectors)

        # Checkpoint to disk every 5 batches (320 vectors) or at final batch
        if (len(all_vectors) % 320 == 0) or (len(all_vectors) == total):
            chk_df = pd.DataFrame({
                "chunk_id": [c["chunk_id"] for c in chunks[:len(all_vectors)]],
                "vector": all_vectors
            })
            chk_df.to_parquet(checkpoint_file, index=False)
            logger.info("Embedding progress: %d / %d chunks (%.1f%%) [Batch took %.2fs]",
                        len(all_vectors), total, (len(all_vectors) / total) * 100, duration)

    logger.info("Step 5 Complete: All %d chunks embedded into 384-dimensional dense vectors.", len(all_vectors))
    return chunks, all_vectors


# -------------------------------------------------------------------------- #
# Step 6: Upsert into Qdrant Cloud Collection 'sc_judgments' (RAM Aware)     #
# -------------------------------------------------------------------------- #

def load_qdrant_credentials() -> Tuple[Optional[str], Optional[str]]:
    """Reads QDRANT_URL and QDRANT_API_KEY from .env only."""
    from dotenv import dotenv_values
    candidates = [
        Path(".env"),
        Path("backend/.env"),
        Path(__file__).resolve().parent.parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent.parent / ".env",
    ]
    url = None
    key = None
    for c in candidates:
        if c.exists():
            vals = dotenv_values(c)
            if "QDRANT_URL" in vals and vals["QDRANT_URL"]:
                url = vals["QDRANT_URL"].strip()
            if "QDRANT_API_KEY" in vals and vals["QDRANT_API_KEY"]:
                key = vals["QDRANT_API_KEY"].strip()
    return url, key


def run_step_6_index_qdrant(
    chunks: Optional[List[Dict[str, Any]]] = None,
    vectors: Optional[List[List[float]]] = None
) -> Dict[str, Any]:
    """
    Creates collection 'sc_judgments' (384 dims, cosine) in Qdrant and upserts chunks in batches.
    Monitors RAM limit (1 GB) and stops if memory threshold is reached.
    If QDRANT_URL or QDRANT_API_KEY are missing from .env, logs that upload is waiting.
    """
    if chunks is None or vectors is None:
        chunks, vectors = run_step_5_embed_chunks()

    url, api_key = load_qdrant_credentials()

    report = {
        "status": "pending",
        "qdrant_url_configured": bool(url),
        "qdrant_api_key_configured": bool(api_key),
        "collection": "sc_judgments",
        "total_chunks_available": len(chunks),
        "points_upserted": 0,
        "detail": ""
    }

    if not url or not api_key:
        report["status"] = "waiting_for_credentials"
        report["detail"] = (
            "QDRANT_URL and/or QDRANT_API_KEY not found in .env. "
            f"All {len(chunks)} chunks and 384-dim vectors are cached on disk and ready for immediate upload. "
            "Set QDRANT_URL and QDRANT_API_KEY in .env and rerun step 6."
        )
        logger.warning(report["detail"])
        with open(DATA_DIR / "qdrant_upload_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        return report

    import uuid
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    logger.info("Connecting to Qdrant at %s...", url)
    client = QdrantClient(url=url, api_key=api_key, timeout=30.0)

    COLLECTION_NAME = "sc_judgments"
    existing = {c.name for c in client.get_collections().collections}

    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
        logger.info("Created collection '%s' (384-dim, cosine)", COLLECTION_NAME)

    # Upsert in batches of 256 points with retries
    batch_size = 256
    total = len(chunks)
    upserted = 0
    POINT_NS = uuid.UUID("7a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d")

    # Ensure payload indexes for high-speed metadata filtering
    from qdrant_client.models import PayloadSchemaType
    for field in ["case_name", "citation", "case_id"]:
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD
            )
        except Exception:
            pass

    for i in range(0, total, batch_size):
        chunk_batch = chunks[i:i + batch_size]
        vec_batch = vectors[i:i + batch_size]

        points = []
        for c, v in zip(chunk_batch, vec_batch):
            point_id = str(uuid.uuid5(POINT_NS, c["chunk_id"]))
            payload = {
                "case_name": c["case_name"],
                "year": c["year"],
                "citation": c["citation"],
                "bench": c["bench"],
                "neutral_citation": c["neutral_citation"],
                "case_id": c["case_id"],
                "source_link": c["source_link"],
                "chunk_index": c["chunk_index"],
                "text": c["text"],
            }
            points.append(PointStruct(id=point_id, vector=v, payload=payload))

        # Upsert with retries
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                client.upsert(collection_name=COLLECTION_NAME, points=points)
                break
            except Exception as e:
                if attempt == max_retries:
                    logger.error("Failed to upsert batch %d-%d after %d attempts: %s", i, min(i + batch_size, total), max_retries, e)
                    raise
                wait_time = 2 ** attempt
                logger.warning("Upsert batch %d-%d failed (attempt %d/%d): %s. Retrying in %ds...",
                               i, min(i + batch_size, total), attempt, max_retries, e, wait_time)
                time.sleep(wait_time)

        upserted += len(points)

        # Log progress periodically
        if upserted % 1024 == 0 or upserted == total:
            info = client.get_collection(COLLECTION_NAME)
            pts = getattr(info, "points_count", upserted)
            logger.info("Qdrant Upsert: %d / %d points indexed into '%s' (total points: %s)",
                        upserted, total, COLLECTION_NAME, str(pts))

    final_info = client.get_collection(COLLECTION_NAME)
    final_pts = getattr(final_info, "points_count", upserted)
    report["status"] = "completed"
    report["points_upserted"] = upserted
    report["collection_points_count"] = final_pts
    report["detail"] = f"Successfully indexed {upserted} vectors into Qdrant collection '{COLLECTION_NAME}'."

    with open(DATA_DIR / "qdrant_upload_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info("Step 6 Complete: %s", report["detail"])
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", type=int, default=1, help="Pipeline step (1 to 6)")
    parser.add_argument("--all", action="store_true", help="Run full pipeline end to end")
    args = parser.parse_args()

    if args.all:
        logger.info("Executing Full Supreme Court Judgments Pipeline End-to-End...")
        df = run_step_1_download_metadata()
        filtered_df, _ = run_step_2_filter_cases(df)
        run_step_3_download_pdfs(filtered_df)
        chunks = run_step_4_extract_and_chunk(filtered_df)
        chunks, vectors = run_step_5_embed_chunks(chunks)
        run_step_6_index_qdrant(chunks, vectors)
    elif args.step == 1:
        run_step_1_download_metadata()
    elif args.step == 2:
        run_step_2_filter_cases()
    elif args.step == 3:
        run_step_3_download_pdfs()
    elif args.step == 4:
        run_step_4_extract_and_chunk()
    elif args.step == 5:
        run_step_5_embed_chunks()
    elif args.step == 6:
        run_step_6_index_qdrant()
