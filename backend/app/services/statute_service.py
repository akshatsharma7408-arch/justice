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

class StatuteService:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """Ensures the SQLite database is created and seeded if missing."""
        if not self.db_path.exists():
            try:
                from app.ingest.seed_bare_acts import init_db, seed_database
                logger.info(f"Database not found at {self.db_path}. Automatically seeding Phase 1 statutes...")
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

    def get_provision_by_section(self, act_id: str, section_num: str) -> Optional[Dict[str, Any]]:
        """
        Fetches exact statutory text, title, heading, and judicial explanation from justice_statutes.db.
        Supports fuzzy act_id matching (e.g. 'contract', 'contract-act-1872', 'Indian Contract Act').
        """
        clean_sec = str(section_num).strip()
        act_search = act_id.lower().strip()

        # Normalize common act prefixes
        if "contract" in act_search:
            canonical_act_id = "contract-act-1872"
        elif "specific" in act_search or "relief" in act_search:
            canonical_act_id = "specific-relief-act-1963"
        elif "arbitration" in act_search:
            canonical_act_id = "arbitration-act-1996"
        else:
            canonical_act_id = act_search

        query = """
            SELECT 
                p.id,
                p.act_id,
                p.section_number,
                p.heading,
                p.body,
                p.explanation,
                a.title AS act_title,
                a.act_number,
                a.year AS act_year
            FROM statutory_provisions p
            JOIN bare_acts a ON p.act_id = a.id
            WHERE (p.act_id = ? OR a.title LIKE ?)
              AND p.section_number = ?
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
                a.title AS act_title,
                a.year AS act_year
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
                cursor.execute("SELECT id, title, act_number, year FROM bare_acts ORDER BY year ASC;")
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
