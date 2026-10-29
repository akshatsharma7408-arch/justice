"""
JUSTICE Legal AI Backend — Statute Query Service
Provides high-performance, embedded querying across Indian Bare Acts and Statutory Provisions
persisted in backend/data/justice_statutes.db.
"""

import sqlite3
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("justice.statute_service")

# Resolve DB path relative to current module: backend/data/justice_statutes.db
CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent.parent
DATA_DIR = BACKEND_DIR / "data"
DB_PATH = DATA_DIR / "justice_statutes.db"


KNOWN_ENACTMENTS: Dict[str, Dict[str, Any]] = {
    "cpc": {
        "canonical_id": "cpc-1908",
        "title": "The Code of Civil Procedure, 1908",
        "short_name": "CPC",
        "year": "1908",
        "jurisdiction": "Central",
        "aliases": ["code of civil procedure", "civil procedure code", "civil procedure", "cpc"],
        "is_real_act": True
    },
    "contract": {
        "canonical_id": "contract-act-1872",
        "title": "The Indian Contract Act, 1872",
        "short_name": "Contract Act",
        "year": "1872",
        "jurisdiction": "Central",
        "aliases": ["indian contract act", "contract act", "contract"],
        "is_real_act": True
    },
    "specific_relief": {
        "canonical_id": "specific-relief-act-1963",
        "title": "The Specific Relief Act, 1963",
        "short_name": "Specific Relief Act",
        "year": "1963",
        "jurisdiction": "Central",
        "aliases": ["specific relief act", "specific relief", "sra"],
        "is_real_act": True
    },
    "arbitration": {
        "canonical_id": "arbitration-act-1996",
        "title": "The Arbitration and Conciliation Act, 1996",
        "short_name": "Arbitration Act",
        "year": "1996",
        "jurisdiction": "Central",
        "aliases": ["arbitration and conciliation act", "arbitration act", "arbitration"],
        "is_real_act": True
    },
    "tpa": {
        "canonical_id": "transfer-of-property-act-1882",
        "title": "The Transfer of Property Act, 1882",
        "short_name": "TPA",
        "year": "1882",
        "jurisdiction": "Central",
        "aliases": ["transfer of property act", "transfer of property", "tpa"],
        "is_real_act": True
    },
    "ni_act": {
        "canonical_id": "negotiable-instruments-act-1881",
        "title": "The Negotiable Instruments Act, 1881",
        "short_name": "NI Act",
        "year": "1881",
        "jurisdiction": "Central",
        "aliases": ["negotiable instruments act", "negotiable instruments", "ni act"],
        "is_real_act": True
    },
    "companies_act": {
        "canonical_id": "companies-act-2013",
        "title": "The Companies Act, 2013",
        "short_name": "Companies Act",
        "year": "2013",
        "jurisdiction": "Central",
        "aliases": ["indian companies act", "companies act"],
        "is_real_act": True
    },
    "limitation_act": {
        "canonical_id": "limitation-act-1963",
        "title": "The Limitation Act, 1963",
        "short_name": "Limitation Act",
        "year": "1963",
        "jurisdiction": "Central",
        "aliases": ["limitation act"],
        "is_real_act": True
    },
    "consumer_protection": {
        "canonical_id": "consumer-protection-act-2019",
        "title": "The Consumer Protection Act, 2019",
        "short_name": "Consumer Protection Act",
        "year": "2019",
        "jurisdiction": "Central",
        "aliases": ["consumer protection act", "consumer protection", "copra"],
        "is_real_act": True
    },
    "crpc": {
        "canonical_id": "crpc-1973",
        "title": "The Code of Criminal Procedure, 1973",
        "short_name": "CrPC",
        "year": "1973",
        "jurisdiction": "Central",
        "aliases": ["code of criminal procedure", "criminal procedure code", "criminal procedure", "crpc"],
        "is_real_act": True
    },
    "ipc": {
        "canonical_id": "ipc-1860",
        "title": "The Indian Penal Code, 1860",
        "short_name": "IPC",
        "year": "1860",
        "jurisdiction": "Central",
        "aliases": ["indian penal code", "penal code", "ipc"],
        "is_real_act": True
    },
    "evidence_act": {
        "canonical_id": "evidence-act-1872",
        "title": "The Indian Evidence Act, 1872",
        "short_name": "Evidence Act",
        "year": "1872",
        "jurisdiction": "Central",
        "aliases": ["indian evidence act", "evidence act"],
        "is_real_act": True
    },
    "mva": {
        "canonical_id": "motor-vehicles-act-1988",
        "title": "The Motor Vehicles Act, 1988",
        "short_name": "MVA",
        "year": "1988",
        "jurisdiction": "Central",
        "aliases": ["motor vehicles act", "motor vehicles", "mva", "hit and run"],
        "is_real_act": True
    },
    "it_act": {
        "canonical_id": "information-technology-act-2000",
        "title": "The Information Technology Act, 2000",
        "short_name": "IT Act",
        "year": "2000",
        "jurisdiction": "Central",
        "aliases": ["information technology act", "it act"],
        "is_real_act": True
    },
    "constitution": {
        "canonical_id": "constitution-of-india-1950",
        "title": "The Constitution of India, 1950",
        "short_name": "Constitution",
        "year": "1950",
        "jurisdiction": "Constitutional",
        "aliases": ["constitution of india", "indian constitution", "constitution", "article", "art"],
        "is_real_act": True
    }
}

class StatuteService:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """Ensures the SQLite database exists and reflects the current statute corpus.

        Seeds when missing, and re-seeds when the database predates the verified
        Constitution corpus (499 articles) so stale local/deployed copies self-heal.
        """
        needs_seed = not self.db_path.exists()
        if not needs_seed:
            try:
                with self._get_connection() as conn:
                    n = conn.execute(
                        "SELECT COUNT(*) FROM statutory_provisions WHERE act_id='constitution-of-india-1950'"
                    ).fetchone()[0]
                if n < 499:
                    logger.info(f"Statute DB stale (Constitution provisions: {n} < 499); reseeding...")
                    needs_seed = True
            except Exception:
                needs_seed = True
        if needs_seed:
            try:
                from app.ingest.seed_bare_acts import init_db, seed_database
                logger.info(f"Seeding statute database at {self.db_path}...")
                conn = init_db(self.db_path)
                seed_database(conn)
                conn.close()
            except Exception as e:
                logger.warning(f"Could not auto-seed database: {e}")

    def _get_connection(self) -> sqlite3.Connection:
        """Returns a configured SQLite connection with row factories."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def resolve_enactment_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Resolves an explicitly requested enactment by name, title, or alias from text.
        Guarantees that act identity is determined before section retrieval.
        Returns enactment metadata dict, or fictitious act dict, or None.
        """
        import re
        t_low = (text or "").lower()

        # Check for explicit fictitious / mythological / sci-fi enactment patterns
        fictitious_match = self.detect_fictitious_or_unrecognized_act(text)
        if fictitious_match:
            return {
                "canonical_id": "unrecognized-fictitious",
                "title": fictitious_match,
                "short_name": fictitious_match,
                "year": "",
                "jurisdiction": "Unrecognized",
                "aliases": [fictitious_match.lower()],
                "is_real_act": False,
                "is_fictitious": True
            }

        # Match against KNOWN_ENACTMENTS aliases using word boundaries
        # Sort aliases by descending length so "code of civil procedure" matches before "cpc"
        best_match = None
        longest_alias_len = 0

        for key, act_meta in KNOWN_ENACTMENTS.items():
            for alias in act_meta["aliases"]:
                # Use word-boundary regex for short acronyms like cpc, tpa, ipc, crpc
                pattern = r'\b' + re.escape(alias) + r'\b'
                if re.search(pattern, t_low):
                    if len(alias) > longest_alias_len:
                        longest_alias_len = len(alias)
                        best_match = act_meta

        if best_match:
            return best_match

        # Check for general explicit "... Act" or "... Code" mentioned in text
        act_match = re.search(r'\b([A-Za-z\s]{3,50}(?:Act|Code)(?:\s*,\s*\d{4})?)\b', text, re.IGNORECASE)
        if act_match:
            extracted_title = act_match.group(1).strip()
            t_lower_clean = extracted_title.lower()
            # Exclude trivial non-enactment phrases
            if t_lower_clean not in ["bare act", "the act", "this act", "an act", "indian act", "act", "code", "civil act", "criminal act"]:
                # Check if fictitious marker inside extracted title
                fict = self.detect_fictitious_or_unrecognized_act(extracted_title)
                if fict:
                    return {
                        "canonical_id": "unrecognized-fictitious",
                        "title": extracted_title,
                        "short_name": extracted_title,
                        "year": "",
                        "jurisdiction": "Unrecognized",
                        "aliases": [t_lower_clean],
                        "is_real_act": False,
                        "is_fictitious": True
                    }
                clean_slug = re.sub(r'[^a-z0-9]+', '-', t_lower_clean).strip('-')
                return {
                    "canonical_id": f"unindexed-{clean_slug}",
                    "title": extracted_title,
                    "short_name": extracted_title,
                    "year": "",
                    "jurisdiction": "Central/State",
                    "aliases": [t_lower_clean],
                    "is_real_act": True,
                    "is_fictitious": False,
                    "is_unindexed": True
                }

        return None

    def detect_fictitious_or_unrecognized_act(self, text: str) -> Optional[str]:
        """
        Detects explicit mentions of fictitious or unrecognized enactments
        (e.g., 'Space Law Act of Atlantis', 'Atlantis Space Law Act', 'Wakanda Accords').
        """
        import re
        fictitious_markers = [
            "atlantis", "wakanda", "gotham", "narnia", "middle earth", "krypton",
            "intergalactic", "outer space law act of", "space law act of"
        ]
        t_low = (text or "").lower()
        for marker in fictitious_markers:
            if marker in t_low:
                # Extract act-like phrase if present
                m = re.search(r'([A-Za-z\s]+(?:Act|Law|Code)(?:\s+of\s+[A-Za-z]+)?)', text, re.IGNORECASE)
                if m:
                    return m.group(1).strip()
                return "Space Law Act of Atlantis" if "atlantis" in t_low else "Fictitious Act"
        return None

    def is_enactment_seeded(self, canonical_id: str) -> bool:
        """Returns True if the enactment is seeded in justice_statutes.db."""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM bare_acts WHERE id = ? LIMIT 1;", (canonical_id,))
                return cur.fetchone() is not None
        except Exception:
            return False

    def normalize_act_id(self, act_search: str) -> str:
        """Resolves common act names and keywords to canonical act_ids."""
        act_search = (act_search or "").lower().strip()
        enactment = self.resolve_enactment_from_text(act_search)
        if enactment and enactment.get("is_real_act"):
            return enactment["canonical_id"]
        return act_search

    def get_provision(self, act_or_type: str, number: str) -> Optional[Dict[str, Any]]:
        """
        Fetches an authoritative provision (Article or Section) with exact number matching.
        Guarantees: '56' matches '56', NOT '356' or '56A'.
        """
        return self.get_provision_by_section(act_or_type, number)

    def get_provision_by_section(self, act_id: str, section_num: str) -> Optional[Dict[str, Any]]:
        """
        Fetches exact statutory text, title, heading, and judicial explanation from justice_statutes.db.
        Supports fuzzy act_id matching (e.g. 'constitution', 'contract', 'mva').
        Ensures exact section/article number match.
        """
        clean_sec = str(section_num).strip().upper()
        act_search = act_id.lower().strip()
        canonical_act_id = self.normalize_act_id(act_search)

        query = """
            SELECT 
                p.id,
                p.act_id,
                p.section_number,
                p.heading,
                p.body,
                p.explanation,
                p.source_url,
                p.effective_date,
                p.status AS provision_status,
                a.title AS act_title,
                a.act_number,
                a.year AS act_year,
                a.jurisdiction,
                a.edition AS act_edition
            FROM statutory_provisions p
            JOIN bare_acts a ON p.act_id = a.id
            WHERE (p.act_id = ? OR a.title LIKE ?)
              AND UPPER(p.section_number) = ?
            LIMIT 1;
        """

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (canonical_act_id, f"%{act_search}%", clean_sec))
                row = cursor.fetchone()
                if row:
                    return dict(row)
        except Exception as e:
            logger.error(f"Error querying statutory provision ({act_id}, Section {section_num}): {e}")

        return None

    def get_provisions_for_number(self, number: str) -> List[Dict[str, Any]]:
        """
        Returns all provisions across all seeded Bare Acts matching an exact section/article number.
        Crucial for detecting and clarifying ambiguous references (e.g., Section 56 in Contract Act vs CrPC).
        """
        clean_num = str(number).strip().upper()
        query = """
            SELECT 
                p.id,
                p.act_id,
                p.section_number,
                p.heading,
                p.body,
                p.explanation,
                p.source_url,
                p.effective_date,
                p.status AS provision_status,
                a.title AS act_title,
                a.act_number,
                a.year AS act_year,
                a.jurisdiction,
                a.edition AS act_edition
            FROM statutory_provisions p
            JOIN bare_acts a ON p.act_id = a.id
            WHERE UPPER(p.section_number) = ?
            ORDER BY a.year ASC;
        """
        results = []
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (clean_num,))
                rows = cursor.fetchall()
                for r in rows:
                    results.append(dict(r))
        except Exception as e:
            logger.error(f"Error querying provisions for number '{number}': {e}")
        return results

    def search_statutes_keyword(self, keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Executes full-text keyword matching across section headings, statutory bodies,
        and explanations in the statutory database.
        """
        term = f"%{keyword.strip()}%"
        query = """
            SELECT 
                p.id,
                p.act_id,
                p.section_number,
                p.heading,
                p.body,
                p.explanation,
                p.source_url,
                p.effective_date,
                a.title AS act_title,
                a.year AS act_year,
                a.jurisdiction
            FROM statutory_provisions p
            JOIN bare_acts a ON p.act_id = a.id
            WHERE p.heading LIKE ? 
               OR p.body LIKE ? 
               OR p.explanation LIKE ?
            ORDER BY 
                CASE 
                    WHEN p.heading LIKE ? THEN 1 
                    ELSE 2 
                END,
                a.year ASC
            LIMIT ?;
        """

        results = []
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (term, term, term, term, limit))
                rows = cursor.fetchall()
                for r in rows:
                    results.append(dict(r))
        except Exception as e:
            logger.error(f"Error searching statutes by keyword '{keyword}': {e}")

        return results

    def get_all_bare_acts(self) -> List[Dict[str, Any]]:
        """Lists all seeded Bare Acts."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, title, act_number, year, jurisdiction FROM bare_acts ORDER BY year ASC;")
                return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error retrieving bare acts: {e}")
            return []

    def check_health(self) -> Dict[str, Any]:
        """Diagnostic health report for the SQLite statutory database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM bare_acts;")
                acts_count = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM statutory_provisions;")
                provs_count = cursor.fetchone()[0]
                return {
                    "status": "connected",
                    "engine": "SQLite3 (Embedded)",
                    "db_path": str(self.db_path),
                    "bare_acts_count": acts_count,
                    "statutory_provisions_count": provs_count
                }
        except Exception as e:
            return {
                "status": "error",
                "engine": "SQLite3 (Embedded)",
                "db_path": str(self.db_path),
                "error": str(e)
            }

statute_service = StatuteService()
