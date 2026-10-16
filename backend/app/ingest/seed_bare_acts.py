"""
JUSTICE Legal AI Backend — Phase 1 Bare Acts Database Seeder
Initializes the embedded SQLite database at backend/data/justice_statutes.db
and seeds Phase 1 Indian commercial and civil statutory provisions.

Usage:
    python -m app.ingest.seed_bare_acts
"""

import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("justice.seed_statutes")

# Database destination path: backend/data/justice_statutes.db
CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent.parent
DATA_DIR = BACKEND_DIR / "data"
DB_PATH = DATA_DIR / "justice_statutes.db"

# Phase 1 Curated Statutory Datasets
BARE_ACTS_DATA = [
    {
        "id": "contract-act-1872",
        "title": "The Indian Contract Act, 1872",
        "act_number": "Act No. 9 of 1872",
        "year": 1872
    },
    {
        "id": "specific-relief-act-1963",
        "title": "The Specific Relief Act, 1963",
        "act_number": "Act No. 47 of 1963",
        "year": 1963
    },
    {
        "id": "arbitration-act-1996",
        "title": "The Arbitration and Conciliation Act, 1996",
        "act_number": "Act No. 26 of 1996",
        "year": 1996
    }
]

STATUTORY_PROVISIONS_DATA = [
    # ---------------- Indian Contract Act, 1872 ----------------
    {
        "id": "contract-1872-sec-27",
        "act_id": "contract-act-1872",
        "section_number": "27",
        "heading": "Agreement in restraint of trade, void",
        "body": (
            "Every agreement by which any one is restrained from exercising a lawful profession, "
            "trade or business of any kind, is to that extent void.\n\n"
            "Exception 1.—Saving of agreement not to carry on business of which good-will is sold.—"
            "One who sells the good-will of a business may agree with the buyer to refrain from carrying on a similar business, "
            "within specified local limits, so long as the buyer, or any person deriving title to the good-will from him, "
            "carries on a like business therein, provided that such limits appear to the Court reasonable, "
            "regard being had to the nature of the business."
        ),
        "explanation": (
            "Under Indian jurisprudence (Percept D'Mark v. Zaheer Khan and Krishan Murgai), any negative covenant "
            "operating post-termination is void ab initio. The English common law rule of partial restraint or reasonableness "
            "does not apply under Indian law, except strictly under the statutory goodwill exception."
        )
    },
    {
        "id": "contract-1872-sec-28",
        "act_id": "contract-act-1872",
        "section_number": "28",
        "heading": "Agreements in restraint of legal proceedings, void",
        "body": (
            "Every agreement, by which any party thereto is restricted absolutely from enforcing his rights under or in respect "
            "of any contract, by the usual legal proceedings in the ordinary tribunals, or which limits the time within which "
            "he may thus enforce his rights, is void to that extent.\n\n"
            "Exception 1.—Saving of contract to refer to arbitration dispute that may arise.\n"
            "Exception 2.—Saving of contract to refer questions that have already arisen."
        ),
        "explanation": (
            "Agreements that extinguish rights or curtail statutory limitation periods are void. "
            "Arbitration agreements are expressly protected under Exceptions 1 and 2."
        )
    },
    {
        "id": "contract-1872-sec-74",
        "act_id": "contract-act-1872",
        "section_number": "74",
        "heading": "Compensation for breach of contract where penalty stipulated for",
        "body": (
            "When a contract has been broken, if a sum is named in the contract as the amount to be paid in case of such breach, "
            "or if the contract contains any other stipulation by way of penalty, the party complaining of the breach is entitled, "
            "whether or not actual damage or loss is proved to have been caused thereby, to receive from the party who has broken "
            "the contract reasonable compensation not exceeding the amount so named or, as the case may be, the penalty stipulated for."
        ),
        "explanation": (
            "Liquidated damages clauses are subject to the court's jurisdiction to award only reasonable compensation. "
            "Where loss can be proved, it must be proved (Kailash Nath Associates v. DDA). Genuine pre-estimates are treated as "
            "ceilings rather than forfeitable penalties."
        )
    },

    # ---------------- Specific Relief Act, 1963 ----------------
    {
        "id": "specific-relief-1963-sec-14",
        "act_id": "specific-relief-act-1963",
        "section_number": "14",
        "heading": "Contracts not specifically enforceable",
        "body": (
            "The following contracts cannot be specifically enforced, namely:—\n"
            "(a) where a party to the contract has obtained substituted performance of contract in accordance with the provisions of section 20;\n"
            "(b) a contract, the performance of which involves the performance of a continuous duty which the court cannot supervise;\n"
            "(c) a contract which is so dependent on the personal qualifications of the parties that the court cannot enforce specific performance of its material terms; and\n"
            "(d) a contract which is in its nature determinable."
        ),
        "explanation": (
            "Contracts involving personal service, employment, or determinable contracts cannot be specifically enforced by Indian courts. "
            "Damages constitute the sole admissible remedy."
        )
    },
    {
        "id": "specific-relief-1963-sec-41",
        "act_id": "specific-relief-act-1963",
        "section_number": "41",
        "heading": "Injunction when refused",
        "body": (
            "An injunction cannot be granted—\n"
            "(a) to restrain any person from prosecuting a judicial proceeding pending at the institution of the suit, in which the injunction is sought, unless such restraint is necessary to prevent a multiplicity of proceedings;\n"
            "(b) to restrain any person from instituting or prosecuting any proceeding in a court not subordinate to that from which the injunction is sought;\n"
            "(c) to restrain any person from applying to any legislative body;\n"
            "(d) to restrain any person from instituting or prosecuting any proceeding in a criminal matter;\n"
            "(e) to prevent the breach of a contract the performance of which would not be specifically enforced;\n"
            "(f) to prevent, on the ground of nuisance, an act of which it is not reasonably clear that it will be a nuisance;\n"
            "(g) to prevent a continuing breach in which the plaintiff has acquiesced;\n"
            "(h) when equally efficacious relief can certainly be obtained by any other usual mode of proceeding except in case of breach of trust;\n"
            "(i) when the conduct of the plaintiff or his agents has been such as to disentitle him to the assistance of the court;\n"
            "(j) when the plaintiff has no personal interest in the matter."
        ),
        "explanation": (
            "Clause (e) bars an injunction to restrain the breach of a contract whose specific performance is barred under Section 14 "
            "(such as contracts for personal services or post-service non-compete agreements)."
        )
    },

    # ---------------- Arbitration and Conciliation Act, 1996 ----------------
    {
        "id": "arbitration-1996-sec-8",
        "act_id": "arbitration-act-1996",
        "section_number": "8",
        "heading": "Power to refer parties to arbitration where there is an arbitration agreement",
        "body": (
            "A judicial authority, before which an action is brought in a matter which is the subject of an arbitration agreement shall, "
            "if a party to the arbitration agreement or any person claiming through or under him, so applies not later than the date of "
            "submitting his first statement on the substance of the dispute, then, notwithstanding any judgment, decree or order of the "
            "Supreme Court or of any Court, refer the parties to arbitration unless it finds that prima facie no valid arbitration agreement exists."
        ),
        "explanation": (
            "Mandatory referral to arbitration where a valid arbitration agreement exists, preserving party autonomy and minimal judicial intervention."
        )
    },
    {
        "id": "arbitration-1996-sec-9",
        "act_id": "arbitration-act-1996",
        "section_number": "9",
        "heading": "Interim measures, etc., by Court",
        "body": (
            "A party may, before or during arbitral proceedings or at any time after the making of the arbitral award but before it is enforced "
            "in accordance with section 36, apply to a court—\n"
            "(i) for the appointment of a guardian for a minor or person of unsound mind for the purposes of arbitral proceedings; or\n"
            "(ii) for an interim measure of protection in respect of any of the following matters, namely:—\n"
            "(a) the preservation, interim custody or sale of any goods which are the subject-matter of the arbitration agreement;\n"
            "(b) securing the amount in dispute in the arbitration;\n"
            "(c) the detention, preservation or inspection of any property or thing which is the subject-matter of the arbitration agreement...\n"
            "(d) interim injunction or the appointment of a receiver;\n"
            "(e) such other interim measure of protection as may appear to the court to be just and convenient."
        ),
        "explanation": (
            "Empowers the civil court to grant urgent pre-arbitral or interim protection. Once the arbitral tribunal is formed, "
            "Section 17 applications take precedence unless special circumstances render the tribunal remedy inefficacious."
        )
    }
]

def init_db(db_path: Path) -> sqlite3.Connection:
    """Initializes SQLite tables for Bare Acts and Statutory Provisions."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bare_acts (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                act_number TEXT NOT NULL,
                year INTEGER NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS statutory_provisions (
                id TEXT PRIMARY KEY,
                act_id TEXT NOT NULL,
                section_number TEXT NOT NULL,
                heading TEXT NOT NULL,
                body TEXT NOT NULL,
                explanation TEXT,
                FOREIGN KEY (act_id) REFERENCES bare_acts(id) ON DELETE CASCADE
            );
        """)
        # Index on act_id + section_number for high performance statutory lookups
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_provision_lookup 
            ON statutory_provisions(act_id, section_number);
        """)
    return conn

def seed_database(conn: sqlite3.Connection) -> Tuple[int, int]:
    """Inserts or updates Phase 1 bare acts and statutory provisions."""
    cursor = conn.cursor()
    
    # 1. Insert bare acts
    acts_inserted = 0
    for act in BARE_ACTS_DATA:
        cursor.execute("""
            INSERT INTO bare_acts (id, title, act_number, year)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                act_number=excluded.act_number,
                year=excluded.year;
        """, (act["id"], act["title"], act["act_number"], act["year"]))
        acts_inserted += 1

    # 2. Insert statutory provisions
    provisions_inserted = 0
    for prov in STATUTORY_PROVISIONS_DATA:
        cursor.execute("""
            INSERT INTO statutory_provisions (id, act_id, section_number, heading, body, explanation)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                act_id=excluded.act_id,
                section_number=excluded.section_number,
                heading=excluded.heading,
                body=excluded.body,
                explanation=excluded.explanation;
        """, (
            prov["id"],
            prov["act_id"],
            prov["section_number"],
            prov["heading"],
            prov["body"],
            prov["explanation"]
        ))
        provisions_inserted += 1

    conn.commit()
    return acts_inserted, provisions_inserted

def main():
    logger.info("=================================================================")
    logger.info("   JUSTICE Legal Intelligence — Phase 1 Statutory Database Seeder ")
    logger.info(f"   Target SQLite DB: {DB_PATH}")
    logger.info("=================================================================")

    conn = init_db(DB_PATH)
    acts_count, provisions_count = seed_database(conn)
    conn.close()

    print(f"\n[SUCCESS] Seeded Phase 1 Indian Statutory Intelligence Engine:")
    print(f"  * Bare Acts Indexed:       {acts_count} acts")
    print(f"  * Statutory Provisions:   {provisions_count} sections")
    print(f"  * Database Location:      {DB_PATH}\n")

if __name__ == "__main__":
    main()
