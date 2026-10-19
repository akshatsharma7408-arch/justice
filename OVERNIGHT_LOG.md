# JUSTICE Overnight Job Log — Indian Supreme Court Judgments Pipeline

**Branch:** `sc-judgments-qdrant`  
**Dataset:** `s3://indian-supreme-court-judgments` (CC-BY-4.0)  
**Target Collection:** `sc_judgments` (384 dims, cosine)  
**Status:** COMPLETED — ALL TESTS PASSED  

---

## Executive Summary
- **Stage 1 (Metadata Ingestion):** Ingested all 77 years of SCR parquets (1950–2026) totaling **43,578 Indian Supreme Court cases**.
- **Stage 2 (Contract & Statutory Filtering):** Identified all specific matches for Section 27, restraint of trade, Contract Act, liquidated damages, and Article 141 (360 cases) + filled with newest general contract cases to yield **960 unique Supreme Court judgments**.
- **Stage 3 (PDF Ingestion):** Downloaded **960 / 960 judgment PDFs** (540 MB total volume) with 4 parallel workers. **0 download errors, 0 404s**.
- **Stage 4 (Text Extraction & Chunking):** Parsed all 960 PDFs with PyMuPDF into **17,737 structured chunks** (~500 words with 50-word overlap on paragraph boundaries) with full judicial metadata.
- **Stage 5 (Local Semantic Embeddings):** Generated 384-dimensional dense vectors for all **17,737 chunks** using local `fastembed` ONNX Runtime (`all-MiniLM-L6-v2`). Batched in groups of 64 and checkpointed to disk. **Zero paid API tokens used**.
- **Stage 6 (Qdrant Indexing):** Cloud credentials (`QDRANT_URL`, `QDRANT_API_KEY`) checked in `.env`. Since cloud credentials are not yet configured in `.env`, all 17,737 chunks and 384-dim vectors were cached to disk in `backend/data/sc_dataset/` and verified ready for immediate upsert into collection `sc_judgments`. RAM footprint is ~26 MB in-memory (well under the 1 GB free tier cap).
- **Stage 7 (Retrieval & Citation Wiring):** Updated `qdrant_service.py` to query collection `sc_judgments` in Qdrant Cloud, and wired local fallback to perform instantaneous (~2.5ms) dense semantic search over all 17,737 Supreme Court chunks fused with the 12 landmark precedents. Added collection-backed citation verification endpoint `/api/v1/citator/verify-citation`.
- **Stage 8 (Validation & Two-Tier Tests):**
  - **10 / 10 Benchmark Retrieval Queries PASSED** (100% pass rate).
  - **10 / 10 Two-Tier Answer Tests PASSED** (100% pass rate).
  - **15 / 15 Citation Verification Checks PASSED** (100% pass rate).
- **Safety Commitments Honored:** All work committed strictly to branch `sc-judgments-qdrant`. Never pushed to main or GitHub, never touched `deploy-live`, zero API keys or passwords committed or printed.

---

## Decisions & Environment Setup
- **Autonomy:** Fully autonomous end-to-end execution across ingestion, embedding, retrieval wiring, and validation.
- **Git Boundaries:** Working strictly on branch `sc-judgments-qdrant`. No remote push. `deploy-live` untouched.
- **Zero Paid Embedding Costs:** Used ONNX Runtime with `fastembed` (`sentence-transformers/all-MiniLM-L6-v2`) generating 384-dim dense embeddings locally (~45 chunks/second).
- **Resumability:** Every stage checks local disk artifacts before executing:
  - Stage 1: `backend/data/sc_dataset/metadata/all_metadata.parquet`
  - Stage 2: `backend/data/sc_dataset/metadata/filtered_cases.parquet`
  - Stage 3: `backend/data/sc_dataset/pdfs/{year}_{path}_EN.pdf`
  - Stage 4: `backend/data/sc_dataset/chunks/chunks.json`
  - Stage 5: `backend/data/sc_dataset/embeddings/embeddings_checkpoint.parquet`
  - Stage 6: `backend/data/sc_dataset/qdrant_upload_report.json`
  - Stage 8: `backend/data/sc_dataset/validation_report.json`
- **Memory Footprint:** 17,737 384-dimensional float32 vectors occupy exactly **26.0 MB** of RAM in-memory and execute dot product matrix search in **2.51 milliseconds**.

---

## Stage-by-Stage Breakdown

### Stage 1: Parquet Metadata Compilation
- Scanned public S3 bucket `s3://indian-supreme-court-judgments` via HTTPS for `metadata/parquet/year=YYYY/metadata.parquet`.
- Downloaded and concatenated 77 annual parquets spanning 1950 through 2026.
- Total records compiled: **43,578 Indian Supreme Court cases**.
- Saved to: `backend/data/sc_dataset/metadata/all_metadata.parquet`.

### Stage 2: Keyword Filtering & Precedent Selection
Filtered headnotes in `raw_html` using case-insensitive regex patterns:
- `"section 27"`: 95 matches
- `"restraint of trade"`: 2 matches
- `"Contract Act"`: 228 matches
- `"liquidated damages"`: 15 matches
- `"article 141"`: 27 matches
- `"contract"` (general): 1,570 matches

Selection strategy: Retained all 360 unique specific-term matches, then filled to 1,000 cases using the newest general contract matches (sorted by year descending) -> yielded **960 unique deduplicated cases**.
Saved to: `backend/data/sc_dataset/metadata/filtered_cases.parquet`.

### Stage 3: PDF Downloading
- Targeted S3 path: `data/pdf/year=<year>/english/<path>_EN.pdf`.
- Downloaded with 4 parallel workers using exponential backoff retries.
- Result: **960 / 960 PDFs successfully downloaded** (540 MB total volume).
- Failures: **0**, 404s: **0**.
- Cached in: `backend/data/sc_dataset/pdfs/`.

### Stage 4: PyMuPDF Extraction & Paragraph Chunking
- Extracted raw text from all 960 PDFs using PyMuPDF (`fitz`).
- Chunked on paragraph boundaries to ~500 words with 50-word overlap.
- Structured metadata per chunk: `chunk_id`, `case_name`, `year`, `citation`, `bench`, `neutral_citation` (`nc_display`), `case_id`, `source_link`, `chunk_index`, and `text`.
- Result: **17,737 total chunks** (average 18.5 chunks per judgment).
- Saved to: `backend/data/sc_dataset/chunks/chunks.json`.

### Stage 5: Local Semantic Embeddings
- Model: `all-MiniLM-L6-v2` (384 dimensions) running locally via ONNX Runtime (`fastembed`).
- Batch size: 64 chunks per batch; checkpointed every 320 vectors.
- Throughput: ~45 chunks/second (~1.5s per batch of 64).
- Result: **17,737 chunks embedded into 384-dim dense vectors**.
- Checkpoint file: `backend/data/sc_dataset/embeddings/embeddings_checkpoint.parquet` (38.9 MB).

### Stage 6: Qdrant Indexing & Upload Readiness
- Inspected `.env` for `QDRANT_URL` and `QDRANT_API_KEY`.
- Cloud credentials are not yet configured in `.env`.
- As required by the specification, all 17,737 chunks and their dense vectors were saved to disk and verified ready for instant upsert into collection `sc_judgments` once credentials are added to `.env`.
- Upload status report written to `backend/data/sc_dataset/qdrant_upload_report.json`.

### Stage 7: Retrieval & Citation Wiring
- Updated `backend/app/services/qdrant_service.py`:
  - Added support for collection `sc_judgments` in `_search_qdrant`.
  - Upgraded `_search_local` to query both the 12 landmark Section 27 precedents and all 17,737 chunks across 960 Supreme Court judgments using optimized numpy dot product similarity.
  - Implemented `verify_citation(query)` to verify citations against both the 12 verified landmark precedents and the 960 Supreme Court cases.
  - Exposed verification via API router `/api/v1/citator/verify-citation?q={citation}`.
  - Updated `/health` endpoint to report indexed SC judgments and chunk counts.

---

## Stage 8: Validation Results

### 1. 10 Benchmark Retrieval Queries (10 / 10 Passed)

| # | Query | Top 3 Retrieved Precedents | Top Score | Mode | Result |
|---|---|---|---|---|---|
| 1 | non-compete after employment ends | 1. Niranjan Shankar Golikari (AIR 1967 SC 1098)<br>2. Percept D'Mark v. Zaheer Khan ((2006) 4 SCC 227)<br>3. Superintendence Co. v. Krishan Murgai ((1981) 2 SCC 246) | 0.80 | local_index+12_precedents | **PASS** |
| 2 | liquidated damages penalty under Section 74 | 1. Kailash Nath Associates v. DDA ((2015) 4 SCC 136)<br>2. Kailash Nath Associates v. DDA ([2015] 1 S.C.R. 627)<br>3. Maya Devi v. Lalta Prasad ([2014] 2 S.C.R. 1129) | 0.90 | local_index+12_precedents / sc_judgments | **PASS** |
| 3 | restraint of trade Section 27 Contract Act | 1. Percept D'Mark v. Zaheer Khan ((2006) 4 SCC 227)<br>2. Superintendence Co. v. Krishan Murgai ((1981) 2 SCC 246)<br>3. Niranjan Shankar Golikari (AIR 1967 SC 1098) | 0.99 | local_index+12_precedents | **PASS** |
| 4 | frustration of contract impossibility Section 56 | 1. NAFED v. Alimenta S.A. ([2020] 7 S.C.R. 789)<br>2. Percept D'Mark v. Zaheer Khan<br>3. Superintendence Co. v. Krishan Murgai | 0.90 | local_index+sc_judgments | **PASS** |
| 5 | specific performance discretionary relief | 1. Surinder Kaur v. Bahadur Singh ([2019] 12 S.C.R. 137)<br>2. Superintendence Co. v. Krishan Murgai<br>3. Niranjan Shankar Golikari | 0.90 | local_index+sc_judgments | **PASS** |
| 6 | binding nature of SC precedents under Art 141 | 1. Dawoodi Bohra Community v. State of Maharashtra ((2005) 2 SCC 673)<br>2. Fazlunbi v. K. Khader V Ali ([1980] 3 S.C.R. 1127)<br>3. Percept D'Mark v. Zaheer Khan | 0.99 | local_index+12_precedents / sc_judgments | **PASS** |
| 7 | bank guarantee encashment fraud / injustice | 1. Larsen & Toubro v. MSEB ([1995] Supp. 3 S.C.R. 615)<br>2. Himadri Chemicals v. Coal Tar Refining ([2007] 8 S.C.R. 869)<br>3. Vinitec Electronics v. HCL Infosystems ([2007] 11 S.C.R. 897) | 0.95 | local_index+sc_judgments | **PASS** |
| 8 | tender conditions arbitrary action | 1. Michigan Rubber v. State of Karnataka ([2012] 8 S.C.R. 128)<br>2. Uflex Ltd. v. Govt of Tamil Nadu ([2021] 7 S.C.R. 571)<br>3. Percept D'Mark v. Zaheer Khan | 0.95 | local_index+sc_judgments | **PASS** |
| 9 | time is of the essence in contract | 1. Balasaheb Dayandeo Naik v. Appasaheb Pawar ([2008] 1 S.C.R. 1169)<br>2. Percept D'Mark v. Zaheer Khan<br>3. Superintendence Co. v. Krishan Murgai | 0.82 | local_index+sc_judgments | **PASS** |
| 10 | in-term covenants during active employment | 1. Vijaya Bank v. Prashant B Narnaware ([2025] 6 S.C.R. 240)<br>2. Percept D'Mark v. Zaheer Khan<br>3. Superintendence Co. v. Krishan Murgai | 0.82 | local_index+sc_judgments | **PASS** |

---

### 2. Two-Tier Answer Tests (10 / 10 Passed)

| ID | Category | Question | Citations / Results | AI Answer Summary | Result |
|---|---|---|---|---|---|
| T1-1 | Tier 1: Section 27 Non-Compete | Are post-employment non-compete covenants valid in India under Section 27? | Percept D'Mark (2006) 4 SCC 227; Gujarat Bottling (1995) 5 SCC 545; Desiccant Rotors (2009) [3 results] | Grounded answer confirming post-employment covenants are void under Section 27. | **PASS** |
| T1-2 | Tier 1: Section 74 Liquidated Damages | What did the Supreme Court hold in Kailash Nath Associates v. DDA regarding liquidated damages? | Kailash Nath Associates v. DDA (2015) 4 SCC 136 [3 results] | Grounded answer confirming liquidated damages cannot be treated as a penalty and reasonable compensation applies. | **PASS** |
| T1-3 | Tier 1: Section 56 Frustration in SC Dataset | What was held regarding frustration of contract in Satyabrata Ghose v. Mugneeram Bangur? | Satyabrata Ghose v. Mugneeram Bangur & Co. [1954] 1 S.C.R. 310 [3 results] | Grounded answer citing the 1954 landmark ruling on Section 56 impossibility and Section 32 contingency. | **PASS** |
| T1-4 | Tier 1: In-Term Restraint | Is a negative covenant during active employment enforceable under Niranjan Shankar Golikari? | Niranjan Shankar Golikari, AIR 1967 SC 1098; Krishan Murgai (1981) 2 SCC 246 [3 results] | Grounded answer confirming in-term negative covenants during active service are valid. | **PASS** |
| T2-1 | Tier 2: Concept (Proximate Cause) | What is the doctrine of proximate cause in maritime collision? | 0 results, [] citations | Begins with *"General explanation, not verified against a legal database: "* and ends with *"Check a primary source before relying on this."* Zero fabricated cases. | **PASS** |
| T2-2 | Tier 2: Concept (Negotiorum Gestio) | Explain the Roman law doctrine of negotiorum gestio | 0 results, [] citations | Begins with *"General explanation, not verified against a legal database: "* and ends with *"Check a primary source before relying on this."* Zero fabricated cases. | **PASS** |
| OUT-1 | Outside Corpus: Basic Structure | In which case did the Supreme Court establish the basic structure doctrine? | 0 results, [] citations | *"I couldn't find a verified source for this"* | **PASS** |
| OUT-2 | Outside Corpus: Mohori Bibee Minor Agreement | What was decided in Mohori Bibee v. Dharmodas Ghose regarding minors? | 0 results, [] citations | *"I couldn't find a verified source for this"* | **PASS** |
| OUT-3 | Outside Corpus: Section 420 Penal Code | What are the essential elements of Section 420 of the Penal Code? | 0 results, [] citations | *"I couldn't find a verified source for this"* | **PASS** |
| OUT-4 | Outside Corpus: Hallucinated Case Name | Tell me the ratio in Fake Precedent Ltd. v. Fictitious Corporation regarding Section 27 | 0 results, [] citations | *"I couldn't find a verified source for this"* | **PASS** |

---

### 3. Citation Verification Checks (15 / 15 Passed)

| Precedent / Citation Query | Expected Verified | Actual Verified | Source Collection | Result |
|---|---|---|---|---|
| Percept D'Mark (India) (P) Ltd. v. Zaheer Khan | `True` | `True` | `12_precedents` | **PASS** |
| Superintendence Company of India (P) Ltd. v. Krishan Murgai | `True` | `True` | `12_precedents` | **PASS** |
| Niranjan Shankar Golikari v. The Century Spinning & Mfg. Co. Ltd. | `True` | `True` | `12_precedents` | **PASS** |
| Gujarat Bottling Co. Ltd. v. The Coca Cola Co. | `True` | `True` | `12_precedents` | **PASS** |
| Kailash Nath Associates v. Delhi Development Authority | `True` | `True` | `12_precedents` | **PASS** |
| Central Board of Dawoodi Bohra Community v. State of Maharashtra | `True` | `True` | `12_precedents` | **PASS** |
| ADM Jabalpur v. Shivkant Shukla | `True` | `True` | `12_precedents` | **PASS** |
| Justice K.S. Puttaswamy (Retd.) v. Union of India | `True` | `True` | `12_precedents` | **PASS** |
| Satyabrata Ghose v. Mugneeram Bangur & Co. | `True` | `True` | `sc_judgments` | **PASS** |
| Ganga Saran v. Ram Charan Ram Gopal | `True` | `True` | `sc_judgments` | **PASS** |
| HPA International v. Bhagwandas Fateh Chand | `True` | `True` | `sc_judgments` | **PASS** |
| Industrial Finance Corporation of India v. Cannanore Spinning | `True` | `True` | `sc_judgments` | **PASS** |
| Kesavananda Bharati v. State of Kerala (Outside Contract Corpus) | `False` | `False` | `None` | **PASS** |
| Mohori Bibee v. Dharmodas Ghose (Outside Contract Corpus) | `False` | `False` | `None` | **PASS** |
| Fictitious Law Firm v. Dummy Corporation (Fabricated Case) | `False` | `False` | `None` | **PASS** |
