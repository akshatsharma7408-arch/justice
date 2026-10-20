"""
JUSTICE Legal AI Backend — Landmark Constitutional Cases Pipeline
Indexes 14 famous Supreme Court of India landmark constitutional decisions into Qdrant 'sc_judgments':
1. Kesavananda Bharati v. State of Kerala (1973) - Basic structure doctrine
2. Maneka Gandhi v. Union of India (1978) - Article 21, procedure established by law
3. K.S. Puttaswamy v. Union of India (2017) - Fundamental right to privacy
4. Vishaka v. State of Rajasthan (1997) - Workplace sexual harassment guidelines
5. Navtej Singh Johar v. Union of India (2018) - Section 377 decriminalization
6. Minerva Mills v. Union of India (1980) - Harmony between fundamental rights & DPSPs
7. I.C. Golaknath v. State of Punjab (1967) - Fundamental rights inviolability
8. S.R. Bommai v. Union of India (1994) - Article 356 federalism & secularism
9. Olga Tellis v. Bombay Municipal Corporation (1985) - Right to livelihood
10. D.K. Basu v. State of West Bengal (1996) - Arrest and custodial safeguards
11. Arnesh Kumar v. State of Bihar (2014) - Arrest checklist & 498A guidelines
12. Lalita Kumari v. Govt. of U.P. (2013) - Mandatory registration of FIR (Section 154)
13. Shreya Singhal v. Union of India (2015) - Freedom of speech & Section 66A IT Act
14. Indra Sawhney v. Union of India (1992) - Mandal Commission & 50% reservation cap

Reuses existing helpers from citizen_rights_pipeline.py:
- PDF download (download_single_pdf)
- chunk_text_by_paragraphs
- fastembed all-MiniLM-L6-v2 embeddings (embedding_service)
- credential loading from .env (load_qdrant_credentials)
- uuid5 point-id scheme with POINT_NS: uuid5(POINT_NS, f"{year}_{path}_{chunk_index}")
- payload index creation (topic, landmark, aliases)
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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pandas as pd

# Add backend directory to sys.path so both `python -m app.ingest...` and script runs work
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.ingest.citizen_rights_pipeline import (
    DATA_DIR,
    METADATA_DIR,
    PDF_DIR,
    CHUNKS_DIR,
    EMBEDDINGS_DIR,
    POINT_NS,
    S3_BASE_URL,
    chunk_text_by_paragraphs,
    download_single_pdf,
    load_qdrant_credentials,
)
from app.services.embedding_service import embedding_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("justice.landmark_pipeline")

COLLECTION_NAME = "sc_judgments"

# Hand-picked 14 Landmark Cases
LANDMARK_CASES: List[Dict[str, Any]] = [
    {
        "year": 1973,
        "path": "S_1973_1_1_1002",
        "common_name": "Kesavananda Bharati v. State of Kerala",
        "short_name": "Kesavananda",
        "benchSize": 13,
        "benchType": "Constitution Bench",
        "leadJudge": "S.M. Sikri, C.J.I.",
        "statutes": ["Article 368", "Article 13", "Article 31C", "Article 31A", "Article 19"],
        "extra_aliases": [
            "Kesavananda Bharati",
            "Kesavananda Bharati case",
            "AIR 1973 SC 1461",
            "A.I.R. 1973 S.C. 1461",
            "(1973) 4 SCC 225",
            "1973 4 SCC 225",
            "[1973] Supp. 1 SCR 1",
            "[1973] Supp 1 SCR 1",
            "1973 Supp 1 SCR 1",
            "[1973] 1 SCR 1",
            "1973INSC91",
            "1973 INSC 91",
            "basic structure doctrine",
            "basic structure"
        ]
    },
    {
        "year": 1978,
        "path": "1978_2_621_776",
        "common_name": "Maneka Gandhi v. Union of India",
        "short_name": "Maneka Gandhi",
        "benchSize": 7,
        "benchType": "Constitution Bench",
        "leadJudge": "M.H. Beg, C.J.I.",
        "statutes": ["Article 21", "Article 14", "Article 19", "Passports Act 1967"],
        "extra_aliases": [
            "Maneka Gandhi case",
            "AIR 1978 SC 597",
            "A.I.R. 1978 S.C. 597",
            "(1978) 1 SCC 248",
            "1978 1 SCC 248",
            "[1978] 2 SCR 621",
            "1978 2 SCR 621",
            "1978INSC19",
            "1978 INSC 19",
            "right to travel abroad",
            "procedure established by law",
            "due process of law"
        ]
    },
    {
        "year": 2017,
        "path": "2017_10_569_999",
        "common_name": "K.S. Puttaswamy v. Union of India (right to privacy)",
        "short_name": "Puttaswamy",
        "benchSize": 9,
        "benchType": "Constitution Bench",
        "leadJudge": "J.S. Khehar, C.J.I.",
        "statutes": ["Article 21", "Article 14", "Article 19", "Aadhaar Act 2016"],
        "extra_aliases": [
            "K.S. Puttaswamy",
            "Justice K.S. Puttaswamy",
            "Justice K.S. Puttaswamy (Retd.) v. Union of India",
            "Puttaswamy case",
            "right to privacy",
            "right to privacy Puttaswamy",
            "(2017) 10 SCC 1",
            "2017 10 SCC 1",
            "AIR 2017 SC 4161",
            "A.I.R. 2017 S.C. 4161",
            "[2017] 10 SCR 569",
            "2017 10 SCR 569",
            "2017INSC752",
            "2017 INSC 752"
        ]
    },
    {
        "year": 1997,
        "path": "S_1997_3_404_418",
        "common_name": "Vishaka v. State of Rajasthan",
        "short_name": "Vishaka",
        "benchSize": 3,
        "benchType": "3-Judge Bench",
        "leadJudge": "J.S. Verma, C.J.I.",
        "statutes": ["Article 14", "Article 19(1)(g)", "Article 21", "CEDAW"],
        "extra_aliases": [
            "Vishaka case",
            "Vishaka guidelines",
            "AIR 1997 SC 3011",
            "A.I.R. 1997 S.C. 3011",
            "(1997) 6 SCC 241",
            "1997 6 SCC 241",
            "[1997] Supp 3 SCR 404",
            "1997 Supp 3 SCR 404",
            "1997INSC665",
            "1997 INSC 665",
            "sexual harassment at workplace"
        ]
    },
    {
        "year": 2018,
        "path": "2018_7_379_746",
        "common_name": "Navtej Singh Johar v. Union of India",
        "short_name": "Navtej Singh Johar",
        "benchSize": 5,
        "benchType": "Constitution Bench",
        "leadJudge": "Dipak Misra, C.J.I.",
        "statutes": ["Section 377 IPC", "Article 14", "Article 15", "Article 19(1)(a)", "Article 21"],
        "extra_aliases": [
            "Navtej Johar",
            "Navtej Singh Johar case",
            "Section 377",
            "(2018) 10 SCC 1",
            "2018 10 SCC 1",
            "AIR 2018 SC 4321",
            "A.I.R. 2018 S.C. 4321",
            "[2018] 7 SCR 379",
            "2018 7 SCR 379",
            "2018INSC790",
            "2018 INSC 790",
            "decriminalization of homosexuality"
        ]
    },
    {
        "year": 1980,
        "path": "1981_1_206_342",
        "common_name": "Minerva Mills v. Union of India",
        "short_name": "Minerva Mills",
        "benchSize": 5,
        "benchType": "Constitution Bench",
        "leadJudge": "Y.V. Chandrachud, C.J.I.",
        "statutes": ["Article 368(4)", "Article 368(5)", "Article 31C", "Article 14", "Article 19"],
        "extra_aliases": [
            "Minerva Mills case",
            "AIR 1980 SC 1789",
            "A.I.R. 1980 S.C. 1789",
            "(1980) 3 SCC 625",
            "1980 3 SCC 625",
            "[1981] 1 SCR 206",
            "1981 1 SCR 206",
            "1980INSC141",
            "1980 INSC 141",
            "balance between fundamental rights and directive principles"
        ]
    },
    {
        "year": 1967,
        "path": "1967_2_762_948",
        "common_name": "I.C. Golaknath v. State of Punjab",
        "short_name": "Golaknath",
        "benchSize": 11,
        "benchType": "Constitution Bench",
        "leadJudge": "K. Subba Rao, C.J.I.",
        "statutes": ["Article 368", "Article 13(2)", "Article 19", "Article 31"],
        "extra_aliases": [
            "I.C. Golaknath",
            "Golak Nath",
            "Golaknath case",
            "AIR 1967 SC 1643",
            "A.I.R. 1967 S.C. 1643",
            "(1967) 2 SCR 762",
            "1967 2 SCR 762",
            "1967INSC45",
            "1967 INSC 45",
            "parliament cannot abridge fundamental rights"
        ]
    },
    {
        "year": 1994,
        "path": "1994_2_644_1000",
        "common_name": "S.R. Bommai v. Union of India",
        "short_name": "S.R. Bommai",
        "benchSize": 9,
        "benchType": "Constitution Bench",
        "leadJudge": "S.R. Pandian, J.",
        "statutes": ["Article 356", "Article 74(2)", "Article 355", "Article 14"],
        "extra_aliases": [
            "Bommai",
            "Bommai case",
            "Article 356",
            "AIR 1994 SC 1918",
            "A.I.R. 1994 S.C. 1918",
            "(1994) 3 SCC 1",
            "1994 3 SCC 1",
            "[1994] 2 SCR 644",
            "1994 2 SCR 644",
            "1994INSC173",
            "1994 INSC 173",
            "secularism basic structure",
            "presidential rule guidelines"
        ]
    },
    {
        "year": 1985,
        "path": "S_1985_2_51_99",
        "common_name": "Olga Tellis v. Bombay Municipal Corporation",
        "short_name": "Olga Tellis",
        "benchSize": 5,
        "benchType": "Constitution Bench",
        "leadJudge": "Y.V. Chandrachud, C.J.I.",
        "statutes": ["Article 21", "Article 19(1)(e)", "Article 19(1)(g)", "Article 39(a)", "Article 41"],
        "extra_aliases": [
            "Olga Tellis case",
            "pavement dwellers case",
            "right to livelihood",
            "AIR 1986 SC 180",
            "A.I.R. 1986 S.C. 180",
            "(1985) 3 SCC 545",
            "1985 3 SCC 545",
            "[1985] Supp 2 SCR 51",
            "1985 Supp 2 SCR 51",
            "1985INSC155",
            "1985 INSC 155"
        ]
    },
    {
        "year": 1996,
        "path": "S_1996_10_284_320",
        "common_name": "D.K. Basu v. State of West Bengal",
        "short_name": "D.K. Basu",
        "benchSize": 2,
        "benchType": "Division Bench",
        "leadJudge": "Kuldip Singh, J.",
        "statutes": ["Article 21", "Article 22", "Section 50 CrPC", "Section 57 CrPC"],
        "extra_aliases": [
            "DK Basu",
            "D.K. Basu case",
            "arrest guidelines",
            "custodial violence guidelines",
            "AIR 1997 SC 610",
            "A.I.R. 1997 S.C. 610",
            "(1997) 1 SCC 416",
            "1997 1 SCC 416",
            "[1996] Supp 10 SCR 284",
            "1996 Supp 10 SCR 284",
            "1996INSC1557",
            "1996 INSC 1557"
        ]
    },
    {
        "year": 2014,
        "path": "2014_8_128_143",
        "common_name": "Arnesh Kumar v. State of Bihar",
        "short_name": "Arnesh Kumar",
        "benchSize": 2,
        "benchType": "Division Bench",
        "leadJudge": "Chandramauli Kumar Prasad, J.",
        "statutes": ["Section 41 CrPC", "Section 41A CrPC", "Section 498A IPC", "Article 21"],
        "extra_aliases": [
            "Arnesh Kumar case",
            "Section 498A arrest",
            "Section 41 CrPC notice",
            "arrest checklist",
            "(2014) 8 SCC 273",
            "2014 8 SCC 273",
            "AIR 2014 SC 2756",
            "A.I.R. 2014 S.C. 2756",
            "[2014] 8 SCR 128",
            "2014 8 SCR 128",
            "2014INSC504",
            "2014 INSC 504"
        ]
    },
    {
        "year": 2013,
        "path": "2013_14_713_802",
        "common_name": "Lalita Kumari v. Govt. of U.P.",
        "short_name": "Lalita Kumari",
        "benchSize": 5,
        "benchType": "Constitution Bench",
        "leadJudge": "P. Sathasivam, C.J.I.",
        "statutes": ["Section 154 CrPC", "Section 156 CrPC", "Section 157 CrPC", "Article 21"],
        "extra_aliases": [
            "Lalita Kumari case",
            "mandatory registration of FIR",
            "Section 154 CrPC FIR",
            "(2014) 2 SCC 1",
            "2014 2 SCC 1",
            "AIR 2014 SC 187",
            "A.I.R. 2014 S.C. 187",
            "[2013] 14 SCR 713",
            "2013 14 SCR 713",
            "2013INSC780",
            "2013 INSC 780"
        ]
    },
    {
        "year": 2015,
        "path": "2015_5_963_1074",
        "common_name": "Shreya Singhal v. Union of India",
        "short_name": "Shreya Singhal",
        "benchSize": 2,
        "benchType": "Division Bench",
        "leadJudge": "J. Chelameswar, J.",
        "statutes": ["Section 66A IT Act", "Article 19(1)(a)", "Article 19(2)", "Article 14"],
        "extra_aliases": [
            "Shreya Singhal case",
            "Section 66A IT Act",
            "online freedom of speech",
            "(2015) 5 SCC 1",
            "2015 5 SCC 1",
            "AIR 2015 SC 1523",
            "A.I.R. 2015 S.C. 1523",
            "[2015] 5 SCR 963",
            "2015 5 SCR 963",
            "2015INSC244",
            "2015 INSC 244"
        ]
    },
    {
        "year": 1992,
        "path": "S_1992_2_454_1007",
        "common_name": "Indra Sawhney v. Union of India",
        "short_name": "Indra Sawhney",
        "benchSize": 9,
        "benchType": "Constitution Bench",
        "leadJudge": "M.H. Kania, C.J.I.",
        "statutes": ["Article 16(4)", "Article 16(1)", "Article 15(4)", "Article 14", "Article 340"],
        "extra_aliases": [
            "Indra Sawhney case",
            "Mandal Commission case",
            "Mandal case",
            "50 percent reservation cap",
            "creamy layer",
            "AIR 1993 SC 477",
            "A.I.R. 1993 S.C. 477",
            "1992 Supp (3) SCC 217",
            "(1992) Supp 3 SCC 217",
            "1992 Supp 3 SCC 217",
            "Supp (3) SCC 217",
            "[1992] Supp 2 SCR 454",
            "1992 Supp 2 SCR 454",
            "1992INSC281",
            "1992 INSC 281"
        ]
    }
]


def load_year_metadata_row(year: int, path: str, common_name: str) -> Optional[Dict[str, Any]]:
    """
    Loads metadata row for given year and path from local metadata parquet or downloads it from S3.
    If path is missing, attempts a fallback search by petitioner name in that year's parquet.
    """
    pq_path = METADATA_DIR / f"metadata_{year}.parquet"
    if not pq_path.exists():
        url = f"{S3_BASE_URL}/metadata/parquet/year={year}/metadata.parquet"
        logger.info("Downloading metadata parquet for %d from %s...", year, url)
        try:
            with httpx.Client(timeout=60.0) as client:
                r = client.get(url)
                if r.status_code == 404:
                    logger.error("Metadata parquet 404 for year %d at %s", year, url)
                    return None
                r.raise_for_status()
                with open(pq_path, "wb") as f:
                    f.write(r.content)
        except Exception as e:
            logger.error("Failed to download metadata parquet for year %d: %s", year, e)
            return None

    try:
        df = pd.read_parquet(pq_path)
        match = df[df["path"] == path]
        if len(match) > 0:
            return match.iloc[0].to_dict()

        # Fallback search by petitioner name
        petitioner = common_name.split(" v. ")[0].split()[-1]
        search_res = df[df["title"].str.contains(petitioner, case=False, na=False)]
        if len(search_res) > 0:
            found_row = search_res.iloc[0].to_dict()
            logger.warning(
                "Path '%s' not found for '%s'; using discovered candidate path '%s' (title: '%s')",
                path, common_name, found_row.get("path"), found_row.get("title")
            )
            return found_row

        logger.error("Could not find path '%s' or petitioner '%s' in year %d metadata.", path, petitioner, year)
        return None
    except Exception as e:
        logger.error("Error reading metadata parquet %s: %s", pq_path, e)
        return None


def extract_parties_from_title(title: str) -> Tuple[str, str]:
    """Splits judgment title into petitioner and respondent."""
    parts = re.split(r'\s+versus\s+|\s+v\.\s+|\s+vs\.?\s+', title, flags=re.IGNORECASE)
    if len(parts) >= 2:
        return parts[0].strip().title(), parts[1].strip().title()
    return title.strip().title(), ""


def step_download_pdfs() -> Dict[str, Any]:
    """Downloads PDFs for the 14 landmark cases."""
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    for case_def in LANDMARK_CASES:
        year = case_def["year"]
        path = case_def["path"]
        name = case_def["common_name"]
        logger.info("Checking/Downloading PDF for %s (%d)...", name, year)
        res = download_single_pdf({"year": year, "path": path})
        if res.get("status") == "404":
            logger.error("404 Not Found for %s: %s", name, res.get("url"))
        results[f"{year}_{path}"] = res
    return results


def step_extract_and_chunk() -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Extracts text from downloaded PDFs, chunks by paragraph (~500w, 50w overlap),
    and adds one extra short metadata chunk per case.
    Returns (all_chunks, chunk_counts_per_case).
    """
    out_file = CHUNKS_DIR / "landmark_chunks.json"
    if out_file.exists() and out_file.stat().st_size > 1000:
        try:
            with open(out_file, "r", encoding="utf-8") as f:
                cached_chunks = json.load(f)
            if len(cached_chunks) >= 3500:
                logger.info("Resuming: Loaded %d cached landmark chunks from %s", len(cached_chunks), out_file)
                counts = {}
                for c in cached_chunks:
                    cname = c.get("common_name", "")
                    counts[cname] = counts.get(cname, 0) + 1
                return cached_chunks, counts
        except Exception as e:
            logger.warning("Could not read cached chunks: %s", e)

    import fitz  # PyMuPDF

    all_chunks: List[Dict[str, Any]] = []
    chunk_counts: Dict[str, int] = {}


    for case_def in LANDMARK_CASES:
        year = case_def["year"]
        path = case_def["path"]
        common_name = case_def["common_name"]
        short_name = case_def["short_name"]
        extra_aliases = case_def.get("extra_aliases", [])

        meta_row = load_year_metadata_row(year, path, common_name)
        if not meta_row:
            logger.error("Skipping %s due to missing metadata.", common_name)
            continue

        pdf_path = PDF_DIR / f"{year}_{path}_EN.pdf"
        if not pdf_path.exists():
            # Try single download
            download_single_pdf({"year": year, "path": path})

        if not pdf_path.exists():
            logger.error("PDF for %s not found at %s. Skipping.", common_name, pdf_path)
            continue

        try:
            doc = fitz.open(pdf_path)
            full_text = ""
            for page in doc:
                full_text += page.get_text() + "\n"
            doc.close()
        except Exception as e:
            logger.error("Error reading PDF %s: %s", pdf_path, e)
            continue

        title = str(meta_row.get("title", common_name)).strip()
        citation = str(meta_row.get("citation", "")).strip()
        bench = str(meta_row.get("judge") or meta_row.get("author_judge") or "").strip()
        nc_display = str(meta_row.get("nc_display", "")).strip()
        source_link = f"{S3_BASE_URL}/data/pdf/year={year}/english/{path}_EN.pdf"

        # Build comprehensive aliases list
        petitioner, respondent = extract_parties_from_title(title)
        aliases_set = set()
        aliases_set.add(common_name)
        aliases_set.add(short_name)
        aliases_set.add(f"{short_name} case")
        aliases_set.add(f"{common_name} case")
        if petitioner:
            aliases_set.add(petitioner)
        if respondent:
            aliases_set.add(respondent)
        if citation:
            aliases_set.add(citation)
        if nc_display:
            aliases_set.add(nc_display)
        for ea in extra_aliases:
            if ea:
                aliases_set.add(ea)

        # Remove empty and sort
        aliases_list = sorted([a.strip() for a in aliases_set if a and len(a.strip()) > 1])

        # Paragraph text chunks
        text_chunks = chunk_text_by_paragraphs(full_text, target_words=500, overlap_words=50)

        # Extra short chunk per case:
        # "<common name>. Citations: <all citations>. Also known as: <aliases>."
        all_cits = [c for c in [citation, nc_display] + [ea for ea in extra_aliases if "SCC" in ea or "AIR" in ea] if c]
        extra_chunk_text = (
            f"{common_name}. Citations: {', '.join(dict.fromkeys(all_cits))}. "
            f"Also known as: {', '.join(aliases_list)}."
        )

        total_chunks = len(text_chunks)

        # Add text chunks
        case_chunks: List[Dict[str, Any]] = []
        for c_idx, chunk_text in enumerate(text_chunks):
            case_chunks.append({
                "chunk_id": f"{year}_{path}_{c_idx}",
                "case_name": title,
                "common_name": common_name,
                "year": int(year),
                "citation": citation,
                "bench": bench,
                "neutral_citation": nc_display,
                "case_id": path,
                "source_link": source_link,
                "chunk_index": c_idx,
                "total_chunks_in_case": total_chunks,
                "topic": "constitutional_landmark",
                "landmark": True,
                "aliases": aliases_list,
                "text": chunk_text
            })

        all_chunks.extend(case_chunks)
        chunk_counts[common_name] = len(case_chunks)
        logger.info("Chunked '%s': %d total judgment chunks (aliases indexed as payload field)", common_name, len(case_chunks))

    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = CHUNKS_DIR / "landmark_chunks.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f)

    return all_chunks, chunk_counts


def step_embed_chunks(chunks: List[Dict[str, Any]]) -> List[List[float]]:
    """Embeds all chunks using local fastembed all-MiniLM-L6-v2."""
    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_file = EMBEDDINGS_DIR / "landmark_embeddings_checkpoint.parquet"
    if checkpoint_file.exists():
        try:
            chk_df = pd.read_parquet(checkpoint_file)
            if len(chk_df) == len(chunks):
                logger.info("Resuming: Loaded %d pre-computed vectors from %s", len(chk_df), checkpoint_file)
                return chk_df["vector"].tolist()
        except Exception as e:
            logger.warning("Could not load vector checkpoint: %s. Re-embedding.", e)

    logger.info("Generating dense embeddings for %d landmark chunks...", len(chunks))
    all_vectors: List[List[float]] = []
    batch_size = 64
    total = len(chunks)

    for i in range(0, total, batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c["text"] for c in batch]
        t0 = time.time()
        vectors = embedding_service.embed_texts(texts)
        dur = time.time() - t0
        all_vectors.extend(vectors)
        if len(all_vectors) % 256 == 0 or len(all_vectors) == total:
            logger.info("Embedding progress: %d/%d (%.1f%%) [Batch took %.2fs]",
                        len(all_vectors), total, (len(all_vectors) / total) * 100, dur)

    # Save parquet checkpoint
    chk_df = pd.DataFrame({
        "chunk_id": [c["chunk_id"] for c in chunks],
        "vector": all_vectors
    })
    chk_df.to_parquet(checkpoint_file, index=False)
    logger.info("Embedding complete: Saved %d vectors to %s", len(all_vectors), checkpoint_file)
    return all_vectors


def step_upload_qdrant(chunks: List[Dict[str, Any]], vectors: List[List[float]]) -> Dict[str, Any]:
    """
    Upserts landmark points into existing Qdrant collection 'sc_judgments'.
    Point ids = uuid5(POINT_NS, f"{year}_{path}_{chunk_index}").
    Monitors RAM limit under 1 GB free tier.
    """
    url, api_key = load_qdrant_credentials()
    if not url or not api_key:
        raise ValueError("QDRANT_URL and QDRANT_API_KEY must be configured in .env.")

    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct, PayloadSchemaType

    client = QdrantClient(url=url, api_key=api_key, timeout=45.0)

    # Verify collection exists
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION_NAME not in existing:
        raise RuntimeError(f"Collection '{COLLECTION_NAME}' does not exist! Never delete or recreate the collection.")

    # Check collection points and storage limit before upload
    info_before = client.get_collection(COLLECTION_NAME)
    pts_before = getattr(info_before, "points_count", 0) or 0
    logger.info("Collection '%s' before upload has %d points.", COLLECTION_NAME, pts_before)

    # Estimate current memory usage: 384 dims float32 = 1.5 KB + payload ~2 KB = ~3.5 KB per point
    est_mb_before = (pts_before * 3500) / (1024 * 1024)
    logger.info("Estimated Qdrant storage before: %.2f MB / 1024 MB (%.1f%%)", est_mb_before, (est_mb_before / 1024) * 100)

    new_points = len(chunks)
    est_mb_after = ((pts_before + new_points) * 3500) / (1024 * 1024)
    if est_mb_after > 920:  # ~90% of 1 GB
        raise RuntimeError(f"Upload aborted: Estimated storage ({est_mb_after:.2f} MB) would exceed 90% of 1 GB free tier.")

    # Ensure payload index on landmark (BOOL), topic (KEYWORD), aliases (KEYWORD)
    index_fields = [
        ("landmark", PayloadSchemaType.BOOL),
        ("topic", PayloadSchemaType.KEYWORD),
        ("aliases", PayloadSchemaType.KEYWORD),
        ("common_name", PayloadSchemaType.KEYWORD),
        ("case_name", PayloadSchemaType.KEYWORD),
        ("citation", PayloadSchemaType.KEYWORD),
        ("case_id", PayloadSchemaType.KEYWORD)
    ]
    for fname, ftype in index_fields:
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=fname,
                field_schema=ftype
            )
        except Exception:
            pass

    # Batch upsert with deterministic point IDs
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
                "common_name": c["common_name"],
                "year": c["year"],
                "citation": c["citation"],
                "bench": c["bench"],
                "neutral_citation": c["neutral_citation"],
                "case_id": c["case_id"],
                "source_link": c["source_link"],
                "chunk_index": c["chunk_index"],
                "total_chunks_in_case": c.get("total_chunks_in_case", 1),
                "topic": "constitutional_landmark",
                "landmark": True,
                "aliases": c["aliases"],
                "text": c["text"],
            }
            points.append(PointStruct(id=point_id, vector=v, payload=payload))

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                client.upsert(collection_name=COLLECTION_NAME, points=points)
                break
            except Exception as e:
                if attempt == max_retries:
                    logger.error("Failed to upsert batch %d-%d after %d attempts: %s",
                                 i, min(i + batch_size, total), max_retries, e)
                    raise
                wait_time = 2 ** attempt
                logger.warning("Upsert retry %d/%d in %ds: %s", attempt, max_retries, wait_time, e)
                time.sleep(wait_time)

        upserted += len(points)
        if upserted % 512 == 0 or upserted == total:
            logger.info("Upserted %d / %d landmark points...", upserted, total)

    info_after = client.get_collection(COLLECTION_NAME)
    pts_after = getattr(info_after, "points_count", pts_before + upserted) or (pts_before + upserted)
    logger.info("Collection '%s' after upload has %d points (Net change: +%d points).",
                COLLECTION_NAME, pts_after, pts_after - pts_before)

    report = {
        "status": "success",
        "collection": COLLECTION_NAME,
        "points_before": pts_before,
        "points_after": pts_after,
        "landmark_points_upserted": upserted,
        "total_cases_indexed": len(LANDMARK_CASES)
    }
    return report


def run_landmark_pipeline(dry_run: bool = True):
    """Executes the landmark indexing pipeline in --dry-run or --upload mode."""
    mode_str = "DRY-RUN (Upload disabled)" if dry_run else "UPLOAD (Live Qdrant Upsert)"
    logger.info("==================================================================")
    logger.info("JUSTICE Supreme Court Landmark Cases Pipeline: %s", mode_str)
    logger.info("==================================================================")

    # 1. Download PDFs
    logger.info("--- Step 1: Resumable PDF Download ---")
    step_download_pdfs()

    # 2. Extract and Chunk
    logger.info("--- Step 2: Extraction and Paragraph Chunking ---")
    chunks, counts = step_extract_and_chunk()

    print("\n--------------------------------------------------------------")
    print("PER-CASE CHUNK COUNTS:")
    print("--------------------------------------------------------------")
    for case_name, count in counts.items():
        print(f"  * {case_name}: {count} chunks")
    print("--------------------------------------------------------------")
    print(f"Total Landmark Chunks Across All 14 Cases: {len(chunks)}")
    print("--------------------------------------------------------------\n")

    # 3. Embed
    logger.info("--- Step 3: Local Dense Embeddings (all-MiniLM-L6-v2) ---")
    vectors = step_embed_chunks(chunks)

    if dry_run:
        logger.info("[DRY RUN COMPLETE] %d chunks extracted and embedded. Upload skipped.", len(chunks))
        return counts, len(chunks)

    # 4. Upload to Qdrant
    logger.info("--- Step 4: Upsert into Qdrant Cloud Collection '%s' ---", COLLECTION_NAME)
    report = step_upload_qdrant(chunks, vectors)
    logger.info("[UPLOAD COMPLETE] Success: %s", report)
    return counts, len(chunks), report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JUSTICE Landmark Precedents Ingestion Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Download, chunk, embed, and print counts without uploading")
    parser.add_argument("--upload", action="store_true", help="Execute full upload to Qdrant Cloud")
    args = parser.parse_args()

    if args.upload:
        run_landmark_pipeline(dry_run=False)
    else:
        run_landmark_pipeline(dry_run=True)
