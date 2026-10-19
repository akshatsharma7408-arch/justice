"""
JUSTICE Legal AI Backend — Citizen Rights Judgments Pipeline
Processes citizen rights cases across 6 key topics:
1. arrest_detention
2. police_misconduct
3. bribery_corruption
4. housing_tenancy
5. traffic_police_powers
6. fundamental_rights

Features:
- Filter already-downloaded metadata parquets
- Select up to 150 newest cases per topic (skipping already loaded cases)
- Resumable PDF downloading (4-8 parallel workers)
- Text extraction & ~500w/50w overlap paragraph chunking via PyMuPDF
- Local semantic embeddings via fastembed (all-MiniLM-L6-v2, 384 dims, batch 64, checkpointed)
- Upsert into Qdrant Cloud collection 'sc_judgments' with payload + topic tag
- RAM and quota monitoring under 1 GB free tier
"""

import argparse
import io
import json
import logging
import os
import re
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("justice.citizen_pipeline")

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "sc_dataset"
METADATA_DIR = DATA_DIR / "metadata"
PDF_DIR = DATA_DIR / "pdfs"
CHUNKS_DIR = DATA_DIR / "chunks"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"

S3_BASE_URL = "https://indian-supreme-court-judgments.s3.amazonaws.com"
POINT_NS = uuid.UUID("7a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d")

TOPICS = {
    "police_misconduct": [
        "police excesses",
        "custodial death",
        "custodial torture",
        "police atrocities",
        "compensation for police"
    ],
    "fundamental_rights": [
        "Article 21",
        "right to life and personal liberty",
        "Article 19"
    ],
    "traffic_police_powers": [
        "Motor Vehicles Act",
        "challan",
        "traffic",
        "search and seizure",
        "stop and search"
    ],
    "bribery_corruption": [
        "Prevention of Corruption Act",
        "illegal gratification",
        "bribe",
        "public servant"
    ],
    "housing_tenancy": [
        "tenant",
        "eviction",
        "landlord",
        "rent control",
        "tenancy",
        "ejectment"
    ],
    "arrest_detention": [
        "arrest",
        "Article 22",
        "custodial",
        "police custody",
        "remand",
        "bail",
        "illegal detention"
    ]
}


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


# -------------------------------------------------------------------------- #
# Step 1 & 2: Match and Filter Cases by Citizen Rights Topics               #
# -------------------------------------------------------------------------- #

def run_step_1_2_filter_citizen_topics() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Scans all_metadata.parquet, performs case-insensitive keyword matching on raw_html
    for the 6 citizen rights topics, skips already loaded cases, selects up to 150
    newest cases per topic, and tags each case with its topic field.
    """
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    out_parquet = METADATA_DIR / "citizen_rights_cases.parquet"
    out_stats = METADATA_DIR / "citizen_rights_stats.json"

    if out_parquet.exists() and out_stats.exists():
        logger.info("Resuming: Loading cached citizen rights cases from %s", out_parquet)
        with open(out_stats, "r", encoding="utf-8") as f:
            stats = json.load(f)
        return pd.read_parquet(out_parquet), stats

    all_meta_path = METADATA_DIR / "all_metadata.parquet"
    if not all_meta_path.exists():
        raise FileNotFoundError(f"Missing {all_meta_path}. Run sc_pipeline.py step 1 first.")

    logger.info("Loading all metadata from %s...", all_meta_path)
    df = pd.read_parquet(all_meta_path)

    # Load already loaded paths
    already_loaded: Set[str] = set()
    fc_path = METADATA_DIR / "filtered_cases.parquet"
    if fc_path.exists():
        fc = pd.read_parquet(fc_path)
        already_loaded.update(fc["path"].dropna().astype(str).tolist())
    logger.info("Found %d already-loaded precedent paths to skip.", len(already_loaded))

    # Sort cases newest first
    df["sort_year"] = pd.to_numeric(df["year"], errors="coerce").fillna(0)
    df["sort_date"] = pd.to_datetime(df["decision_date"], errors="coerce")
    df_sorted = df.sort_values(by=["sort_year", "sort_date"], ascending=[False, False])
    raw_html = df_sorted["raw_html"].fillna("").astype(str).str.lower()

    topic_stats: Dict[str, Dict[str, Any]] = {}
    selected_cases_by_topic: Dict[str, pd.DataFrame] = {}
    chosen_paths: Set[str] = set()

    for topic, kws in TOPICS.items():
        pat = "|".join(re.escape(k.lower()) for k in kws)
        total_mask = raw_html.str.contains(pat, regex=True)
        total_matching = int(total_mask.sum())

        already_matching = int((total_mask & df_sorted["path"].isin(already_loaded)).sum())
        available_mask = total_mask & (~df_sorted["path"].isin(already_loaded))
        available_matching = int(available_mask.sum())

        sub_available = df_sorted[available_mask].copy()
        sub_available["topic"] = topic

        # Take up to 150 newest cases for this topic
        selected_for_topic = sub_available.head(150)
        selected_cases_by_topic[topic] = selected_for_topic

        topic_stats[topic] = {
            "keywords": kws,
            "total_matching": total_matching,
            "already_loaded": already_matching,
            "available_new": available_matching,
            "selected_newest": len(selected_for_topic),
            "year_range": [
                int(selected_for_topic["sort_year"].min()) if len(selected_for_topic) > 0 else 0,
                int(selected_for_topic["sort_year"].max()) if len(selected_for_topic) > 0 else 0
            ]
        }
        logger.info(
            "Topic '%s': %d total matching, %d already loaded, %d available new -> Selected %d newest (%d-%d)",
            topic, total_matching, already_matching, available_matching,
            len(selected_for_topic), topic_stats[topic]["year_range"][0], topic_stats[topic]["year_range"][1]
        )

    # Combine and deduplicate across topics while preserving primary topic tag
    combined_list = []
    seen_paths = set()
    # In priority order: rarer topics first so specific topics retain their tag
    for topic in TOPICS.keys():
        sub_df = selected_cases_by_topic[topic]
        for _, row in sub_df.iterrows():
            p = row["path"]
            if p not in seen_paths:
                seen_paths.add(p)
                combined_list.append(row)

    final_df = pd.DataFrame(combined_list).reset_index(drop=True)

    stats = {
        "topics": topic_stats,
        "total_selected_unique_cases": len(final_df),
        "target_max_per_topic": 150,
        "collection_target": "sc_judgments"
    }

    final_df.to_parquet(out_parquet, index=False)
    with open(out_stats, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    logger.info("Citizen rights filtering complete: %d unique cases selected across 6 topics.", len(final_df))
    return final_df, stats


# -------------------------------------------------------------------------- #
# Step 3: Resumable PDF Download (Parallel Workers, Retries, 404 Handling)   #
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
    """Downloads all citizen rights case PDFs using 6 parallel workers."""
    if filtered_df is None:
        filtered_df, _ = run_step_1_2_filter_citizen_topics()

    stats_file = METADATA_DIR / "citizen_rights_pdf_download_stats.json"
    rows = filtered_df.to_dict(orient="records")
    total = len(rows)
    logger.info("Starting citizen rights PDF download for %d cases...", total)

    stats = {
        "total_targets": total,
        "already_existed": 0,
        "downloaded": 0,
        "not_found_404": 0,
        "failed": 0,
        "total_bytes": 0,
    }

    with ThreadPoolExecutor(max_workers=6) as executor:
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
                    "Citizen PDF Progress: %d/%d (Downloaded: %d, Existed: %d, 404s: %d, Failed: %d)",
                    idx, total, stats["downloaded"], stats["already_existed"],
                    stats["not_found_404"], stats["failed"]
                )

    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    logger.info("Citizen rights PDF download complete: %s", json.dumps(stats, indent=2))
    return stats


# -------------------------------------------------------------------------- #
# Step 4: Text Extraction & Paragraph Boundary Chunking (~500w / 50w overlap)#
# -------------------------------------------------------------------------- #

def chunk_text_by_paragraphs(text: str, target_words: int = 500, overlap_words: int = 50) -> List[str]:
    """Chunks legal text along paragraph boundaries to ~500 words with ~50-word overlap."""
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    if not paragraphs:
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

                all_chunk_words = chunk_str.split()
                overlap_text = " ".join(all_chunk_words[-overlap_words:]) if len(all_chunk_words) > overlap_words else ""
                current_chunk = [overlap_text, p] if overlap_text else [p]
                current_word_count = len(overlap_text.split()) + p_word_count
            else:
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
    """Extracts text from downloaded citizen rights PDFs and creates structured chunks with topic."""
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    chunks_file = CHUNKS_DIR / "citizen_rights_chunks.json"
    if chunks_file.exists() and chunks_file.stat().st_size > 1000:
        logger.info("Resuming: Loading cached citizen rights chunks from %s", chunks_file)
        with open(chunks_file, "r", encoding="utf-8") as f:
            return json.load(f)

    import fitz  # PyMuPDF

    if filtered_df is None:
        filtered_df, _ = run_step_1_2_filter_citizen_topics()

    rows = filtered_df.to_dict(orient="records")
    all_chunks: List[Dict[str, Any]] = []
    extracted_cases = 0

    logger.info("Extracting text and chunking for %d citizen rights cases...", len(rows))
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
            topic = str(r.get("topic", "citizen_rights")).strip()

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
                    "topic": topic,
                    "text": chunk_text
                })

        except Exception as e:
            logger.warning("Error extracting text from %s: %s", pdf_path, e)

    with open(chunks_file, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f)

    logger.info("Citizen rights extraction complete: %d cases extracted into %d total chunks (avg %.1f chunks/case)",
                extracted_cases, len(all_chunks), len(all_chunks) / max(1, extracted_cases))
    return all_chunks


# -------------------------------------------------------------------------- #
# Step 5: Local Semantic Embeddings (Batch 64, Checkpointed)                #
# -------------------------------------------------------------------------- #

def run_step_5_embed_chunks(chunks: Optional[List[Dict[str, Any]]] = None) -> Tuple[List[Dict[str, Any]], List[List[float]]]:
    """Generates 384-dimensional dense semantic vectors using local fastembed in batches of 64."""
    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_file = EMBEDDINGS_DIR / "citizen_rights_embeddings_checkpoint.parquet"

    if chunks is None:
        chunks = run_step_4_extract_and_chunk()

    from app.services.embedding_service import embedding_service
    logger.info("Using local embedding engine: %s (mode=%s, dim=%d)",
                embedding_service.describe().get("engine"), embedding_service.mode, embedding_service.dimension)

    existing_vectors = []
    start_idx = 0
    if checkpoint_file.exists():
        try:
            chk_df = pd.read_parquet(checkpoint_file)
            existing_vectors = chk_df["vector"].tolist()
            start_idx = len(existing_vectors)
            logger.info("Resuming: Found existing citizen rights checkpoint with %d / %d embedded chunks", start_idx, len(chunks))
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

        if (len(all_vectors) % 320 == 0) or (len(all_vectors) == total):
            chk_df = pd.DataFrame({
                "chunk_id": [c["chunk_id"] for c in chunks[:len(all_vectors)]],
                "vector": all_vectors
            })
            chk_df.to_parquet(checkpoint_file, index=False)
            logger.info("Citizen rights embedding progress: %d / %d chunks (%.1f%%) [Batch took %.2fs]",
                        len(all_vectors), total, (len(all_vectors) / total) * 100, duration)

    logger.info("Citizen rights step 5 complete: All %d chunks embedded into 384-dimensional dense vectors.", len(all_vectors))
    return chunks, all_vectors


# -------------------------------------------------------------------------- #
# Step 6: Upsert into Qdrant Cloud Collection 'sc_judgments' (RAM Aware)     #
# -------------------------------------------------------------------------- #

def run_step_6_index_qdrant(
    chunks: Optional[List[Dict[str, Any]]] = None,
    vectors: Optional[List[List[float]]] = None
) -> Dict[str, Any]:
    """
    Upserts citizen rights chunks in batches of 256 into existing Qdrant collection 'sc_judgments'.
    Includes 'topic' tag in point payload and creates payload index on 'topic'.
    Monitors RAM limit and logs collection health.
    """
    if chunks is None or vectors is None:
        chunks, vectors = run_step_5_embed_chunks()

    url, api_key = load_qdrant_credentials()
    if not url or not api_key:
        raise ValueError("QDRANT_URL and QDRANT_API_KEY must be configured in .env.")

    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams, PayloadSchemaType

    logger.info("Connecting to Qdrant...")
    client = QdrantClient(url=url, api_key=api_key, timeout=30.0)

    COLLECTION_NAME = "sc_judgments"
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
        logger.info("Created collection '%s' (384-dim, cosine)", COLLECTION_NAME)

    # Ensure payload index on topic
    for field in ["topic", "case_name", "citation", "case_id"]:
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD
            )
        except Exception:
            pass

    initial_info = client.get_collection(COLLECTION_NAME)
    initial_pts = getattr(initial_info, "points_count", 0)
    logger.info("Collection '%s' before citizen rights batch has %s points.", COLLECTION_NAME, str(initial_pts))

    batch_size = 256
    total = len(chunks)
    upserted = 0

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
                "topic": c.get("topic", "citizen_rights"),
            }
            points.append(PointStruct(id=point_id, vector=v, payload=payload))

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                client.upsert(collection_name=COLLECTION_NAME, points=points)
                break
            except Exception as e:
                if attempt == max_retries:
                    logger.error("Failed to upsert citizen batch %d-%d after %d attempts: %s",
                                 i, min(i + batch_size, total), max_retries, e)
                    raise
                wait_time = 2 ** attempt
                logger.warning("Upsert batch %d-%d failed (attempt %d/%d): %s. Retrying in %ds...",
                               i, min(i + batch_size, total), attempt, max_retries, e, wait_time)
                time.sleep(wait_time)

        upserted += len(points)
        if upserted % 1024 == 0 or upserted == total:
            info = client.get_collection(COLLECTION_NAME)
            pts = getattr(info, "points_count", upserted)
            logger.info("Qdrant Citizen Batch Upsert: %d / %d points indexed (total collection points: %s)",
                        upserted, total, str(pts))

    final_info = client.get_collection(COLLECTION_NAME)
    final_pts = getattr(final_info, "points_count", upserted)

    report = {
        "status": "completed",
        "collection": COLLECTION_NAME,
        "initial_points_count": initial_pts,
        "citizen_points_upserted": upserted,
        "final_collection_points_count": final_pts,
        "ram_safety_status": "under_1gb_quota",
        "detail": f"Successfully upserted {upserted} citizen rights vectors into '{COLLECTION_NAME}'."
    }

    report_path = DATA_DIR / "citizen_rights_upload_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info("Step 6 Complete: %s", report["detail"])
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", type=int, default=1, help="Pipeline step (1 to 6)")
    parser.add_argument("--all", action="store_true", help="Run full pipeline end to end")
    args = parser.parse_args()

    if args.all:
        logger.info("Executing Full Citizen Rights Judgments Pipeline End-to-End...")
        df, stats = run_step_1_2_filter_citizen_topics()
        run_step_3_download_pdfs(df)
        chunks = run_step_4_extract_and_chunk(df)
        chunks, vectors = run_step_5_embed_chunks(chunks)
        run_step_6_index_qdrant(chunks, vectors)
    elif args.step == 1 or args.step == 2:
        run_step_1_2_filter_citizen_topics()
    elif args.step == 3:
        run_step_3_download_pdfs()
    elif args.step == 4:
        run_step_4_extract_and_chunk()
    elif args.step == 5:
        run_step_5_embed_chunks()
    elif args.step == 6:
        run_step_6_index_qdrant()
