"""
JUSTICE Legal AI Backend — Phase 1 Bare Acts & Constitutional Provisions Database Seeder
Initializes the embedded SQLite database at backend/data/justice_statutes.db
and seeds Phase 1 Indian constitutional, commercial, motor vehicle, criminal, and civil statutory provisions.

Usage:
    python -m app.ingest.seed_bare_acts
"""

import re
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

# Verified Constitution corpus (official Legislative Department diglot edition).
# Regenerate via scripts/constitution/parse_coi.py + clean_coi.py.
CONSTITUTION_SOURCE_URL = "https://www.legislative.gov.in/static/uploads/2025/07/c9fe9c9b6840524844316f74bb1c556c.pdf"
CONSTITUTION_EDITION = "Diglot edition [As on 1st May, 2026] (incorporating amendments up to the 106th Amendment Act, 2023)"
CONSTITUTION_CORPUS_PATHS = [
    CURRENT_DIR / "constitution_corpus.json",
    BACKEND_DIR.parent / "scripts" / "constitution" / "coi_corpus.json",
]


CRIMINAL_REFORMS_CORPUS_PATH = CURRENT_DIR / "criminal_reforms_corpus.json"
BNS_SOURCE_URL = "https://prsindia.org/files/bills_acts/acts_parliament/2023/The%20Bharatiya%20Nyaya%20Sanhita,%202023.pdf"
BNS_COMMENCEMENT_URL = "https://www.mha.gov.in/sites/default/files/BhartiyaNyayaSanhita_24022024.pdf"
BNSS_SOURCE_URL = "https://prsindia.org/files/bills_acts/acts_parliament/2023/The%20Bharatiya%20Nagarik%20Suraksha%20Sanhita,%202023.pdf"
BNSS_COMMENCEMENT_URL = "https://www.mha.gov.in/sites/default/files/BharatiyaNagarikSurakshaSanhita_24022024.pdf"

# Section-number sort for numeric sections (1..531).
def _section_sort_key(num: str):
    m = re.match(r"(\d+)([A-Z]*)", num)
    return (int(m.group(1)), m.group(2))


def load_criminal_reforms_provisions() -> List[Dict[str, Any]]:
    """Build BNS/BNSS provision rows from the verified corpus JSON.

    Bodies/headings come from criminal_reforms_corpus.json, whose text was
    cross-checked against the official Gazette PDFs (eGazette CG-DL-E-25122023-250883
    for the BNS and CG-DL-E-25122023-250884 for the BNSS, mirrored byte-for-byte by PRS).
    Verification classes per act are recorded in scripts/criminal_reforms/VERIFICATION.md.
    """
    import json as _json
    if not CRIMINAL_REFORMS_CORPUS_PATH.exists():
        logger.warning("Criminal reforms corpus JSON not found; BNS/BNSS will be unseeded")
        return []
    corpus = _json.loads(CRIMINAL_REFORMS_CORPUS_PATH.read_text(encoding="utf-8"))
    meta = {
        "bharatiya-nyaya-sanhita-2023": {
            "id_prefix": "bns-2023-s-",
            "source_url": BNS_SOURCE_URL,
            "effective_date": "1 July 2024 (S.O. 850(E), 23.02.2024; s.106(2) excepted)",
        },
        "bharatiya-nagarik-suraksha-sanhita-2023": {
            "id_prefix": "bnss-2023-s-",
            "source_url": BNSS_SOURCE_URL,
            "effective_date": "1 July 2024 (S.O. 848(E), 23.02.2024; First Schedule entries relating to BNS s.106(2) excepted)",
        },
    }
    provisions = []
    for act_id, m in meta.items():
        entries = corpus.get(act_id, {})
        for num in sorted(entries, key=_section_sort_key):
            e = entries[num]
            explanation = None
            if act_id == "bharatiya-nyaya-sanhita-2023" and num == "106":
                explanation = ("Commencement caveat: sub-section (2) of section 106 (causing death by rash/negligent "
                               "driving and fleeing without reporting) was excepted from commencement by the official "
                               "notification S.O. 850(E) (23.02.2024), which brought the BNS into force w.e.f. "
                               "1 July 2024 except s.106(2). No later notification commencing s.106(2) has been "
                               "located, and press reporting (Hindustan Times, 25-26 Oct 2026) describes it as still "
                               "not in force; its current status rests on that reporting, not a fresh official check. "
                               "Sub-section (1) is in force.")
            provisions.append({
                "id": f"{m['id_prefix']}{num.lower()}",
                "act_id": act_id,
                "section_number": num,
                "heading": e["heading"],
                "body": e["body"],
                "explanation": explanation,
                "source_url": m["source_url"],
                "effective_date": m["effective_date"],
                "status": "in_force",
            })
    logger.info(f"Criminal reforms corpus loaded: {len(provisions)} provisions (BNS + BNSS)")
    return provisions


def _article_sort_key(num: str):
    m = re.match(r"(\d+)([A-Z]*)", num)
    return (int(m.group(1)), m.group(2))


def load_constitution_provisions(curated: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build Constitution provision rows from the verified corpus JSON.

    Bodies/headings come verbatim from the official diglot PDF extraction
    (scripts/constitution/coi_corpus.json); the hand-curated entries only
    contribute landmark-case explanations and effective dates. Falls back to
    the curated entries if the corpus file is unavailable.
    """
    import json as _json
    corpus = None
    for path in CONSTITUTION_CORPUS_PATHS:
        if path.exists():
            corpus = _json.loads(path.read_text(encoding="utf-8"))
            logger.info(f"Constitution corpus loaded from {path} ({len(corpus)} articles)")
            break
    if corpus is None:
        logger.warning("Constitution corpus JSON not found; using curated provisions only")
        return [curated[n] for n in sorted(curated, key=_article_sort_key)]

    provisions = []
    for num in sorted(corpus, key=_article_sort_key):
        art = corpus[num]
        note = curated.get(num.upper(), {})
        status = art.get("status", "in_force")
        provisions.append({
            "id": f"constitution-1950-art-{num.lower()}",
            "act_id": "constitution-of-india-1950",
            "section_number": num,
            "heading": art["title"],
            "body": art["body"],
            "explanation": note.get("explanation"),
            "source_url": CONSTITUTION_SOURCE_URL,
            "effective_date": note.get("effective_date") if status == "in_force" else None,
            "status": status,
        })
    return provisions

# Authoritative Curated Statutory Datasets
SEED_VERSION = "2026-10-29.v8"  # bump on any seed content/corpus correction; self-heal reseeds on mismatch

BARE_ACTS_DATA = [
    {
        "id": "constitution-of-india-1950",
        "title": "The Constitution of India, 1950",
        "act_number": "Adopted by the Constituent Assembly",
        "year": 1950,
        "jurisdiction": "Union of India"
    },
    {
        "id": "contract-act-1872",
        "title": "The Indian Contract Act, 1872",
        "act_number": "Act No. 9 of 1872",
        "year": 1872,
        "jurisdiction": "India"
    },
    {
        "id": "motor-vehicles-act-1988",
        "title": "The Motor Vehicles Act, 1988",
        "act_number": "Act No. 59 of 1988",
        "year": 1988,
        "jurisdiction": "India"
    },
    {
        "id": "crpc-1973",
        "title": "The Code of Criminal Procedure, 1973",
        "act_number": "Act No. 2 of 1974",
        "year": 1973,
        "jurisdiction": "India",
        "edition": "Repealed by the Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS) w.e.f. 1 July 2024, subject to savings: proceedings initiated before that date generally continue under the CrPC, while matters arising on or after it fall under the BNSS. The BNSS is in this database (as-enacted text); for matters arising on or after 1 July 2024 consult the BNSS. Which text applies depends on when the proceeding arose."
    },
    {
        "id": "ipc-1860",
        "title": "The Indian Penal Code, 1860",
        "act_number": "Act No. 45 of 1860",
        "year": 1860,
        "jurisdiction": "India",
        "edition": "Repealed by the Bharatiya Nyaya Sanhita, 2023 (BNS) w.e.f. 1 July 2024, subject to savings: offences committed before that date are generally still governed by the IPC, while offences on or after it fall under the BNS. The BNS is in this database (as-enacted text); for offences committed on or after 1 July 2024 consult the BNS. Which text applies depends on the date of the offence."
    },
    {
        "id": "specific-relief-act-1963",
        "title": "The Specific Relief Act, 1963",
        "act_number": "Act No. 47 of 1963",
        "year": 1963,
        "jurisdiction": "India"
    },
    {
        "id": "arbitration-act-1996",
        "title": "The Arbitration and Conciliation Act, 1996",
        "act_number": "Act No. 26 of 1996",
        "year": 1996,
        "jurisdiction": "India"
    },
    {
        "id": "bharatiya-nyaya-sanhita-2023",
        "title": "The Bharatiya Nyaya Sanhita, 2023",
        "act_number": "Act No. 45 of 2023",
        "year": 2023,
        "jurisdiction": "India",
        "edition": "In force w.e.f. 1 July 2024 (S.O. 850(E), 23.02.2024), EXCEPT section 106(2) (hit-and-run), which has not been commenced as of 29 October 2026. Repeals the Indian Penal Code, 1860 subject to s.358 savings (pre-1 July 2024 offences remain under the IPC). Text: official Gazette PDF (eGazette CG-DL-E-25122023-250883) as enacted on 25.12.2023; subsequent amendments, if any, are not incorporated."
    },
    {
        "id": "bharatiya-nagarik-suraksha-sanhita-2023",
        "title": "The Bharatiya Nagarik Suraksha Sanhita, 2023",
        "act_number": "Act No. 46 of 2023",
        "year": 2023,
        "jurisdiction": "India (except s.1(2) carve-outs: Chapters IX, XI and XII do not apply to Nagaland and tribal areas unless the State Government notifies otherwise; modifications possible for those areas)",
        "edition": "In force w.e.f. 1 July 2024 (S.O. 848(E), 23.02.2024), except First Schedule entries relating to BNS s.106(2). Repeals the Code of Criminal Procedure, 1973 subject to s.531 savings (pending proceedings continue under the CrPC). Text: official Gazette PDF (eGazette CG-DL-E-25122023-250884) as enacted on 25.12.2023; subsequent amendments, if any, are not incorporated."
    }
]

STATUTORY_PROVISIONS_DATA = [
    # ---------------- Constitution of India, 1950 ----------------
    {
        "id": "constitution-1950-art-14",
        "act_id": "constitution-of-india-1950",
        "section_number": "14",
        "heading": "Equality before law",
        "body": (
            "The State shall not deny to any person equality before the law or the equal protection "
            "of the laws within the territory of India."
        ),
        "explanation": (
            "Article 14 guarantees the fundamental right to equality before the law and equal protection of the laws "
            "to all persons (citizens and non-citizens alike) within the territory of India. In E.P. Royappa v. State of Tamil Nadu (1974) "
            "and Maneka Gandhi v. Union of India (1978), the Supreme Court settled that Article 14 embodies a dynamic guarantee against state arbitrariness, "
            "forming the Golden Triangle alongside Articles 19 and 21. Permissible classification requires intelligible differentia and a rational nexus to the statutory objective (Ram Krishna Dalmia)."
        ),
        "source_url": "https://legislative.gov.in/constitution-of-india/",
        "effective_date": "26 January 1950"
    },
    {
        "id": "constitution-1950-art-19",
        "act_id": "constitution-of-india-1950",
        "section_number": "19",
        "heading": "Protection of certain rights regarding freedom of speech, etc.",
        "body": (
            "(1) All citizens shall have the right—\n"
            "(a) to freedom of speech and expression;\n"
            "(b) to assemble peaceably and without arms;\n"
            "(c) to form associations or unions;\n"
            "(d) to move freely throughout the territory of India;\n"
            "(e) to reside and settle in any part of the territory of India; and\n"
            "(g) to practise any profession, or to carry on any occupation, trade or business.\n\n"
            "Clauses (2) to (6) prescribe exhaustive grounds for reasonable restrictions imposed by law."
        ),
        "explanation": (
            "Guarantees the six fundamental democratic freedoms to citizens of India, subject strictly to narrow, reasonable restrictions "
            "under clauses (2) through (6) on specified grounds such as sovereignty, security of the State, public order, and morality."
        ),
        "source_url": "https://legislative.gov.in/constitution-of-india/",
        "effective_date": "26 January 1950"
    },
    {
        "id": "constitution-1950-art-21",
        "act_id": "constitution-of-india-1950",
        "section_number": "21",
        "heading": "Protection of life and personal liberty",
        "body": (
            "No person shall be deprived of his life or personal liberty except according to procedure established by law."
        ),
        "explanation": (
            "Core fundamental right protecting life and personal liberty. In Maneka Gandhi v. Union of India (1978), the Supreme Court "
            "held that the procedure established by law must be just, fair, and reasonable, rejecting narrow literalism. In K.S. Puttaswamy (2017), "
            "a 9-judge Constitution Bench held that the right to privacy is an intrinsic fundamental right guaranteed under Article 21."
        ),
        "source_url": "https://legislative.gov.in/constitution-of-india/",
        "effective_date": "26 January 1950"
    },
    {
        "id": "constitution-1950-art-21a",
        "act_id": "constitution-of-india-1950",
        "section_number": "21A",
        "heading": "Right to education",
        "body": (
            "The State shall provide free and compulsory education to all children of the age of six to fourteen years "
            "in such manner as the State may, by law, determine."
        ),
        "explanation": (
            "Fundamental right guaranteeing free and compulsory elementary education to all children aged 6 to 14 years. "
            "Operationalized by the Right of Children to Free and Compulsory Education Act, 2009."
        ),
        "source_url": "https://legislative.gov.in/constitution-of-india/",
        "effective_date": "1 April 2010 (inserted by the Constitution (Eighty-sixth Amendment) Act, 2002)"
    },
    {
        "id": "constitution-1950-art-32",
        "act_id": "constitution-of-india-1950",
        "section_number": "32",
        "heading": "Remedies for enforcement of rights conferred by this Part",
        "body": (
            "(1) The right to move the Supreme Court by appropriate proceedings for the enforcement of the rights conferred by this Part is guaranteed.\n"
            "(2) The Supreme Court shall have power to issue directions or orders or writs, including writs in the nature of habeas corpus, "
            "mandamus, prohibition, quo warranto and certiorari, whichever may be appropriate, for the enforcement of any of the rights conferred by this Part."
        ),
        "explanation": (
            "Known as the 'heart and soul of the Constitution' (Dr. B.R. Ambedkar), Article 32 itself is a fundamental right guaranteeing "
            "direct recourse to the Supreme Court for judicial enforcement of Part III rights through constitutional prerogative writs."
        ),
        "source_url": "https://legislative.gov.in/constitution-of-india/",
        "effective_date": "26 January 1950"
    },
    {
        "id": "constitution-1950-art-56",
        "act_id": "constitution-of-india-1950",
        "section_number": "56",
        "heading": "Term of office of President",
        "body": (
            "(1) The President shall hold office for a term of five years from the date on which he enters upon his office:\n"
            "Provided that—\n"
            "(a) the President may, by writing under his hand addressed to the Vice-President, resign his office;\n"
            "(b) the President may, for violation of the Constitution, be removed from office by impeachment in the manner provided in article 61;\n"
            "(c) the President shall, notwithstanding the expiration of his term, continue to hold office until his successor enters upon his office.\n\n"
            "(2) Any resignation addressed to the Vice-President under clause (a) of the proviso to clause (1) shall forthwith be communicated by him to the Speaker of the House of the People."
        ),
        "explanation": (
            "Article 56 of the Constitution of India governs the tenure, resignation, and removal of the President of India. "
            "Key constitutional parameters:\n"
            "1. Tenure: Fixed term of five years from the date on which the President enters upon office.\n"
            "2. Resignation: Must be in writing under hand addressed to the Vice-President, who must forthwith communicate it to the Speaker of the Lok Sabha.\n"
            "3. Removal: Solely on the ground of 'violation of the Constitution' through the parliamentary impeachment procedure prescribed under Article 61.\n"
            "4. Continuity: The outgoing President continues to hold office, notwithstanding expiration of the 5-year term, until the successor enters upon office."
        ),
        "source_url": "https://legislative.gov.in/constitution-of-india/",
        "effective_date": "26 January 1950"
    },
    {
        "id": "constitution-1950-art-141",
        "act_id": "constitution-of-india-1950",
        "section_number": "141",
        "heading": "Law declared by Supreme Court to be binding on all courts",
        "body": (
            "The law declared by the Supreme Court shall be binding on all courts within the territory of India."
        ),
        "explanation": (
            "Constitutional foundation of stare decisis and precedent hierarchy in India. Under Central Board of Dawoodi Bohra Community (2005), "
            "the law declared by a larger bench of the Supreme Court is strictly binding on all coordinate and smaller benches of the Court."
        ),
        "source_url": "https://legislative.gov.in/constitution-of-india/",
        "effective_date": "26 January 1950"
    },
    {
        "id": "constitution-1950-art-226",
        "act_id": "constitution-of-india-1950",
        "section_number": "226",
        "heading": "Power of High Courts to issue certain writs",
        "body": (
            "(1) Notwithstanding anything in article 32, every High Court shall have power, throughout the territories in relation to which "
            "it exercise jurisdiction, to issue to any person or authority, including in appropriate cases, any Government, within those territories "
            "directions, orders or writs, including writs in the nature of habeas corpus, mandamus, prohibition, quo warranto and certiorari, "
            "or any of them, for the enforcement of any of the rights conferred by Part III and for any other purpose."
        ),
        "explanation": (
            "Empowers High Courts with extensive judicial review jurisdiction to enforce fundamental rights and ordinary statutory/legal rights ('for any other purpose')."
        ),
        "source_url": "https://legislative.gov.in/constitution-of-india/",
        "effective_date": "26 January 1950"
    },
    {
        "id": "constitution-1950-art-239aa",
        "act_id": "constitution-of-india-1950",
        "section_number": "239AA",
        "heading": "Special provisions with respect to Delhi",
        "body": (
            "(1) As from the date of commencement of the Constitution (Sixty-ninth Amendment) Act, 1991, the Union territory of Delhi shall be called the National Capital Territory of Delhi (hereafter in this Part referred to as the National Capital Territory) and the administrator thereof appointed under article 239 shall be designated as the Lieutenant Governor.\n"
            "(2) (a) There shall be a Legislative Assembly for the National Capital Territory and the seats in such Assembly shall be filled by members chosen by direct election from territorial constituencies in the National Capital Territory...\n"
            "(3) (a) Subject to the provisions of this Constitution, the Legislative Assembly shall have power to make laws for the whole or any part of the National Capital Territory with respect to any of the matters enumerated in the State List or in the Concurrent List, except matters with respect to Entries 1, 2 and 18 of the State List and Entries 64, 65 and 66 of that List in so far as they relate to the said Entries 1, 2 and 18.\n"
            "(4) There shall be a Council of Ministers consisting of not more than ten per cent. of the total number of members in the Legislative Assembly, with the Chief Minister at the head to aid and advise the Lieutenant Governor in the exercise of his functions in relation to matters with respect to which the Legislative Assembly has power to make laws, except in so far as he is, by or under any law, required to act in his discretion..."
        ),
        "explanation": (
            "Article 239AA confers a unique constitutional status on the National Capital Territory of Delhi (NCTD). Key parameters:\n"
            "1. Enactment: Inserted by the Constitution (Sixty-ninth Amendment) Act, 1991, effective 1 February 1992.\n"
            "2. Legislative Competence: The Legislative Assembly of NCTD has plenary legislative powers over subjects in the State List (List II) and Concurrent List (List III), EXCEPT Public Order (Entry 1), Police (Entry 2), and Land (Entry 18).\n"
            "3. Governance & Aid and Advice: In Government of NCT of Delhi v. Union of India (2018) 8 SCC 501 (5-Judge Constitution Bench) and (2023) 9 SCC 1 (5-Judge Constitution Bench), the Supreme Court ruled that the Lieutenant Governor is bound by the aid and advise of the Council of Ministers on all matters over which the Delhi Assembly has legislative power, and the LG does not possess independent executive authority except where specifically conferred by law."
        ),
        "source_url": "https://legislative.gov.in/constitution-of-india/",
        "effective_date": "1 February 1992 (Constitution (Sixty-ninth Amendment) Act, 1991)"
    },
    {
        "id": "constitution-1950-art-239ab",
        "act_id": "constitution-of-india-1950",
        "section_number": "239AB",
        "heading": "Provision in case of failure of constitutional machinery",
        "body": (
            "If the President, on receipt of a report from the Lieutenant Governor or otherwise, is satisfied—\n"
            "(a) that a situation has arisen in which the administration of the National Capital Territory cannot be carried on in accordance with the provisions of article 239AA or of any law made in pursuance of that article; or\n"
            "(b) that for the proper administration of the National Capital Territory it is necessary or expedient so to do,\n"
            "the President may by order suspend the operation of any provision of article 239AA or of all or any of the provisions of any law relating to the Legislative Assembly or to the Council of Ministers and make such incidental and consequential provisions as may appear to him to be necessary or expedient for administering the National Capital Territory in accordance with the provisions of article 239 and article 239AA."
        ),
        "explanation": (
            "Article 239AB of the Constitution of India provides emergency mechanisms in the event of failure of constitutional machinery in the National Capital Territory of Delhi, functioning analogously to President's Rule under Article 356 for States. "
            "Inserted by the Constitution (Sixty-ninth Amendment) Act, 1991 (effective 1 February 1992), it authorizes the President, upon report from the Lieutenant Governor or otherwise, to suspend the operation of Article 239AA and laws governing the Assembly/Ministers."
        ),
        "source_url": "https://legislative.gov.in/constitution-of-india/",
        "effective_date": "1 February 1992 (Constitution (Sixty-ninth Amendment) Act, 1991)"
    },
    {
        "id": "constitution-1950-art-356",
        "act_id": "constitution-of-india-1950",
        "section_number": "356",
        "heading": "Provisions in case of failure of constitutional machinery in States",
        "body": (
            "(1) If the President, on receipt of a report from the Governor of a State or otherwise, is satisfied that a situation has arisen "
            "in which the government of the State cannot be carried on in accordance with the provisions of this Constitution, the President may by Proclamation—\n"
            "(a) assume to himself all or any of the functions of the Government of the State and all or any of the powers vested in or exercisable by the Governor...\n"
            "(b) declare that the powers of the Legislature of the State shall be exercisable by or under the authority of Parliament..."
        ),
        "explanation": (
            "Governs the proclamation of President's Rule in States. In S.R. Bommai v. Union of India (1994) 3 SCC 1 (9-Judge Constitution Bench), "
            "the Supreme Court authoritatively held that presidential proclamations under Article 356 are subject to judicial review, and federalism and secularism are basic features of the Constitution that cannot be abrogated."
        ),
        "source_url": "https://legislative.gov.in/constitution-of-india/",
        "effective_date": "26 January 1950"
    },
    {
        "id": "constitution-1950-art-368",
        "act_id": "constitution-of-india-1950",
        "section_number": "368",
        "heading": "Power of Parliament to amend the Constitution and procedure therefor",
        "body": (
            "(1) Notwithstanding anything in this Constitution, Parliament may in exercise of its constituent power amend by way of addition, "
            "variation or repeal any provision of this Constitution in accordance with the procedure laid down in this article."
        ),
        "explanation": (
            "Governs the constitutional amendment procedure. In Kesavananda Bharati v. State of Kerala (1973) 4 SCC 225 (13-Judge Constitution Bench), "
            "the Supreme Court established the Basic Structure Doctrine, holding that while Parliament has constituent power under Article 368 to amend the Constitution, "
            "that power does not extend to damaging, emasculating, or altering its basic structure or essential framework."
        ),
        "source_url": "https://legislative.gov.in/constitution-of-india/",
        "effective_date": "26 January 1950"
    },

    # ---------------- Motor Vehicles Act, 1988 ----------------
    {
        "id": "mva-1988-sec-161",
        "act_id": "motor-vehicles-act-1988",
        "section_number": "161",
        "heading": "Special provisions as to compensation in case of hit and run motor accident",
        "body": (
            "(1) Notwithstanding anything contained in any other law for the time being in force or any instrument having the force of law, the Central Government shall provide for paying in accordance with the provisions of this Act and the scheme made under sub-section (3), compensation in respect of the death of, or grievous hurt to, persons resulting from hit and run motor accidents.\n"
            "(2) Subject to the provisions of this Act and the scheme made under sub-section (3), there shall be paid as compensation, -\n"
            "(a) in respect of the death of any person resulting from a hit and run motor accident, a fixed sum of two lakh rupees or such higher amount as may be prescribed by the Central Government;\n"
            "(b) in respect of grievous hurt to any person resulting from a hit and run motor accident, a fixed sum of fifty thousand rupees or such higher amount as may be prescribed by the Central Government.\n"
            "(3) The Central Government may, by notification in the Official Gazette, make a scheme specifying the manner in which the scheme shall be administered by the Central Government or General Insurance Council, the form, manner and the time within which applications for compensation may be made, the officers or authorities to whom such applications may be made, the procedure to be followed by such officers or authorities for considering and passing orders on such applications, and all other matters connected with, or incidental to, the administration of the scheme and the payment of compensation under this section.\n"
            "(4) A scheme made under sub-section (3) may provide that, - (a) a payment of such sum as may be prescribed by the Central Government as interim relief to any claimant under such scheme; (b) a contravention of any provision thereof shall be punishable with imprisonment which may extend to two years, or with fine which shall not be less than twenty-five thousand rupees but may extend to five lakh rupees or with both; (c) the powers, functions or duties conferred or imposed on any officer or authority by such scheme may be delegated, with the prior approval in writing of Central Government, by such officer or authority to any other officer or authority."
        ),
        "explanation": (
            "Section 161 of the Motor Vehicles Act, 1988 provides statutory solatium relief specifically for hit-and-run accidents where the identity of the offending vehicle cannot be ascertained (untraced vehicle).\n"
            "Key Legal Parameters & Distinct Legal Route:\n"
            "1. Governing Scheme & Current Amounts: Under Section 161(3) as amended by the Motor Vehicles (Amendment) Act, 2019 (Act 32 of 2019) and the Compensation to Victims of Hit and Run Motor Accidents Scheme, 2022 (MoRTH Notification G.S.R. 163(E) dated 25 February 2022, effective 1 April 2022, superseding the 1989 Scheme):\n"
            "   • Fixed compensation for death: Rs. 2,00,000 (Two Lakh Rupees).\n"
            "   • Fixed compensation for grievous hurt: Rs. 50,000 (Fifty Thousand Rupees).\n"
            "2. Administrative Remedy: Claims are processed administratively through the Claims Enquiry Officer (Sub-Divisional Magistrate / Tehsildar) and sanctioned by the Claims Settlement Commissioner (District Magistrate) out of the Motor Vehicles Accident Fund (Section 164B).\n"
            "3. Strict Legal Route Distinction from MACT: This statutory relief applies solely to untraced vehicles. It does NOT involve ordinary MACT multiplier rules, dependency formulas, or income calculations under Section 166 (Sarla Verma / Pranay Sethi), which apply strictly to traced/identified vehicles against owners and insurance companies.\n"
            "4. Grievous Hurt vs Disability: Compenses statutory 'grievous hurt' as defined in Section 320 IPC, distinct from medical disability percentages.\n"
            "5. Refund/Clawback: Under Section 161(5) and Section 162, if MACT compensation is subsequently awarded for the same accident (e.g. if the offending vehicle is later identified), the Section 161 relief amount must be refunded to the Fund."
        ),
        "source_url": "https://api.sci.gov.in/supremecourt/2012/20376/20376_2012_7_1501_49426_Judgement_12-Jan-2024.pdf",
        "effective_date": "1 April 2022 (s.161 as substituted by Act 32 of 2019; Scheme G.S.R. 163(E) dated 25-2-2022)"
    },
    {
        "id": "mva-1988-sec-164",
        "act_id": "motor-vehicles-act-1988",
        "section_number": "164",
        "heading": "Payment of compensation in case of death or grievous hurt, etc.",
        "body": (
            "(1) Notwithstanding anything contained in this Act or in any other law for the time being in force or instrument "
            "having the force of law, the owner of the motor vehicle or the authorised insurer shall be liable to pay in the case "
            "of death or grievous hurt due to any accident arising out of the use of motor vehicle, a compensation, of a sum of "
            "five lakh rupees in case of death or of two and a half lakh rupees in case of grievous hurt to the legal heirs or "
            "the victim, as the case may be.\n\n"
            "(2) In any claim for compensation under sub-section (1), the claimant shall not be required to plead or establish "
            "that the death or grievous hurt in respect of which the claim has been made was due to any wrongful act or neglect "
            "or default of the owner of the vehicle or of the vehicle concerned or of any other person.\n\n"
            "(3) Where, in respect of death or grievous hurt due to an accident arising out of the use of motor vehicle, "
            "compensation has been paid under any other law for the time being in force, such amount of compensation shall be "
            "reduced from the amount of compensation payable under this section."
        ),
        "explanation": (
            "Provides statutory structured compensation on a no-fault basis where the offending vehicle is identified/traced. "
            "The claimant is not required to plead or prove wrongful act, neglect, or default. Body verified verbatim against the Motor Vehicles (Amendment) Act, 2019 (Act 32 of 2019; official ref: India Code A2019-32)."
        ),
        "source_url": "https://prsindia.org/files/bills_acts/bills_parliament/2019/Motor%20Vehicles%20(Amendment)%20Act,%202019.pdf",
        "effective_date": "1 September 2019 (inserted by Act 32 of 2019)"
    },
    {
        "id": "mva-1988-sec-166",
        "act_id": "motor-vehicles-act-1988",
        "section_number": "166",
        "heading": "Application for compensation",
        "body": (
            "(1) An application for compensation arising out of an accident of the nature specified in sub-section (1) of section 165 may be made—\n"
            "(a) by the person who has sustained the injury; or\n"
            "(b) by the owner of the property; or\n"
            "(c) where death has resulted from the accident, by all or any of the legal representatives of the deceased; or\n"
            "(d) by any agent duly authorised by the person injured or all or any of the legal representatives of the deceased, as the case may be:\n"
            "Provided that where all the legal representatives of the deceased have not joined in any such application for compensation, the application shall be made on behalf of or for the benefit of all the legal representatives of the deceased and the legal representatives who have not so joined, shall be impleaded as respondents to the application.\n"
            "Provided further that where a person accepts compensation under section 164 in accordance with the procedure provided under section 149, his claims petition before the Claims Tribunal shall lapse.\n"
            "(2) Every application under sub-section (1) shall be made, at the option of the claimant, either to the Claims Tribunal having jurisdiction over the area in which the accident occurred or to the Claims Tribunal within the local limits of whose jurisdiction the claimant resides or carries on business or within the local limits of whose jurisdiction the defendant resides, and shall be in such form and contain such particulars as may be prescribed.\n"
            "(3) No application for compensation shall be entertained unless it is made within six months of the occurrence of the accident.\n"
            "(4) The Claims Tribunal shall treat any report of accidents forwarded to it under section 159 as an application for compensation under this Act.\n"
            "(5) Notwithstanding anything in this Act or any other law for the time being in force, the right of a person to claim compensation for injury in an accident shall, upon the death of the person injured, survive to his legal representatives, irrespective of whether the cause of death is relatable to or had any nexus with the injury or not."
        ),
        "explanation": (
            "Governs fault-based adjudication before the Motor Accident Claims Tribunal (MACT) against the owner, driver, and insurance company "
            "of an identified offending vehicle. Compensation is calculated judicially under the structured multiplier system (Sarla Verma (2009) 6 SCC 121 "
            "and National Insurance Co. v. Pranay Sethi (2017) 16 SCC 680) based on age, verified monthly income, future prospects, dependency, and permanent disability percentage."
        ),
        "source_url": "https://prsindia.org/files/bills_acts/bills_parliament/2019/Motor%20Vehicles%20(Amendment)%20Act,%202019.pdf",
        "effective_date": "1 July 1989 (as amended by Act 32 of 2019)"
    },

    # ---------------- Indian Contract Act, 1872 ----------------
    {
        "id": "contract-1872-sec-23",
        "act_id": "contract-act-1872",
        "section_number": "23",
        "heading": "What considerations and objects are lawful, and what not",
        "body": (
            "The consideration or object of an agreement is lawful, unless—\n"
            "it is forbidden by law; or\n"
            "is of such a nature that, if permitted, it would defeat the provisions of any law; or\n"
            "is fraudulent; or\n"
            "involves or implies injury to the person or property of another; or\n"
            "the Court regards it as immoral, or opposed to public policy.\n\n"
            "In each of these cases, the consideration or object of an agreement is said to be unlawful. "
            "Every agreement of which the object or consideration is unlawful is void."
        ),
        "explanation": (
            "Foundational statutory limit on contract freedom under Indian law. Contracts contrary to statutory mandates "
            "or public policy are void ab initio and cannot be cured by estoppel or party consent."
        ),
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2187/2/A187209.pdf",
        "effective_date": "1 September 1872"
    },
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
        ),
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2187/2/A187209.pdf",
        "effective_date": "1 September 1872"
    },
    {
        "id": "contract-1872-sec-28",
        "act_id": "contract-act-1872",
        "section_number": "28",
        "heading": "Agreements in restraint of legal proceedings, void",
        "body": (
            "Every agreement,\u2014\n"
            "(a) by which any party thereto is restricted absolutely from enforcing his rights under or in respect of any contract, "
            "by the usual legal proceedings in the ordinary tribunals, or which limits the time within which he may thus enforce his rights; or\n"
            "(b) which extinguishes the rights of any party thereto, or discharges any party thereto, from any liability, "
            "under or in respect of any contract on the expiry of a specified period so as to restrict any party from enforcing his rights,\n"
            "is void to that extent.\n\n"
            "Exception 1.\u2014Saving of contract to refer to arbitration dispute that may arise.\u2014This section shall not render illegal "
            "a contract, by which two or more persons agree that any dispute which may arise between them in respect of any subject or "
            "class of subjects shall be referred to arbitration, and that only the amount awarded in such arbitration shall be recoverable "
            "in respect of the dispute so referred.\n\n"
            "Exception 2.\u2014Saving of contract to refer questions that have already arisen.\u2014Nor shall this section render illegal "
            "any contract in writing, by which two or more persons agree to refer to arbitration any question between them which has "
            "already arisen, or affect any provision of any law in force for the time being as to references to arbitration."
        ),
        "explanation": (
            "Main para as substituted by the Indian Contract (Amendment) Act, 1996 (Act 1 of 1997) w.e.f. 8-1-1997: clause (b) newly "
            "voids extinguishment/time-bar clauses. The Supreme Court in Union of India v. IndusInd Bank Ltd. (decided 15-09-2016) held "
            "the amendment prospective, so the pre-1997 single-clause text governs agreements entered into before 8-1-1997. "
            "Exception 3 in the current edition saves bank/financial-institution guarantee terms providing extinguishment or "
            "discharge on expiry of a specified period of not less than one year (full text in the source PDF)."
        ),
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2187/2/A187209.pdf",
        "effective_date": "1 September 1872"
    },
    {
        "id": "contract-1872-sec-56",
        "act_id": "contract-act-1872",
        "section_number": "56",
        "heading": "Agreement to do impossible act / Contract to do an act afterwards becoming impossible or unlawful",
        "body": (
            "An agreement to do an act impossible in itself is void.\n\n"
            "Contract to do an act afterwards becoming impossible or unlawful.—A contract to do an act which, after the contract is made, "
            "becomes impossible, or, by reason of some event which the promisor could not prevent, unlawful, becomes void when the act becomes impossible or unlawful.\n\n"
            "Compensation for loss through non-performance of act known to be impossible or unlawful.—Where one person has promised to do something which he knew, "
            "or, with reasonable diligence, might have known, and which the promisee did not know, to be impossible or unlawful, such promisor must make compensation "
            "to such promisee for any loss which such promisee sustains through the non-performance of the promise."
        ),
        "explanation": (
            "Codifies the doctrine of frustration of contracts under Indian law. In Satyabrata Ghose v. Mugneeram Bangur & Co. (1954 SCR 310), "
            "the Supreme Court settled that Section 56 is exhaustive on the subject of supervening impossibility, superseding English common law theories of implied terms. "
            "When the fundamental basis of a contract is destroyed by an unforeseen supervening event without fault of either party, the contract is discharged by frustration."
        ),
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2187/2/A187209.pdf",
        "effective_date": "1 September 1872"
    },
    {
        "id": "contract-1872-sec-73",
        "act_id": "contract-act-1872",
        "section_number": "73",
        "heading": "Compensation for loss or damage caused by breach of contract",
        "body": (
            "When a contract has been broken, the party who suffers by such breach is entitled to receive, "
            "from the party who has broken the contract, compensation for any loss or damage caused to him thereby, "
            "which naturally arose in the usual course of things from such breach, or which the parties knew, "
            "when they made the contract, to be likely to result from the breach of it.\n\n"
            "Such compensation is not to be given for any remote and indirect loss or damage sustained by reason of the breach."
        ),
        "explanation": (
            "Codifies the common law rule of Hadley v. Baxendale. Only direct, proximate, and foreseeable damages "
            "are compensable; speculative, punitive, or remote damages are barred."
        ),
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2187/2/A187209.pdf",
        "effective_date": "1 September 1872"
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
        ),
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2187/2/A187209.pdf",
        "effective_date": "1 September 1872"
    },

    # ---------------- Code of Criminal Procedure, 1973 ----------------
    {
        "id": "crpc-1973-sec-41",
        "act_id": "crpc-1973",
        "section_number": "41",
        "heading": "When police may arrest without warrant",
        "body": (
            "(1) Any police officer may without an order from a Magistrate and without a warrant, arrest any person— (a) who commits, in the presence of a police officer, a cognizable offence; (b) against whom a reasonable complaint has been made, or credible information has been received, or a reasonable suspicion exists that he has committed a cognizable offence punishable with imprisonment for a term which may be less than seven years or which may extend to seven years whether with or without fine, if the following conditions are satisfied, namely:— (i) the police officer has reason to believe on the basis of such complaint, information, or suspicion that such person has committed the said offence; (ii) the police officer is satisfied that such arrest is necessary— (a) to prevent such person from committing any further offence; or (b) for proper investigation of the offence; or (c) to prevent such person from causing the evidence of the offence to disappear or tampering with such evidence in any manner; or (d) to prevent such person from making any inducement, threat or promise to any person acquainted with the facts of the case so as to dissuade him from disclosing such facts to the Court or to the police officer; or (e) as unless such person is arrested, his presence in the Court whenever required cannot be ensured, and the police officer shall record while making such arrest, his reasons in writing: Provided that a police officer shall, in all cases where the arrest of a person is not required under the provisions of this sub-section, record the reasons in writing for not making the arrest.; (ba) against whom credible information has been received that he has committed a cognizable offence punishable with imprisonment for a term which may extend to more than seven years whether with or without fine or with death sentence and the police officer has reason to believe on the basis of that information that such person has committed the said offence; (c) who has been proclaimed as an offender either under this Code or by order of the State Government; or (d) in whose possession anything is found which may reasonably be suspected to be stolen property and who may reasonably be suspected of having committed an offence with reference to such thing; or (e) who obstructs a police officer while in the execution of his duty, or who has escaped, or attempts to escape, from lawful custody; or (f) who is reasonably suspected of being a deserter from any of the Armed Forces of the Union; or (g) who has been concerned in, or against whom a reasonable complaint has been made, or credible information has been received, or a reasonable suspicion exists, of his having been concerned in, any act committed at any place out of India which, if committed in India, would have been punishable as an offence, and for which he is, under any law relating to extradition, or otherwise, liable to be apprehended or detained in custody in India; or (h) who, being a released convict, commits a breach of any rule made under sub-section (5) of section 356; or (i) for whose arrest any requisition, whether written or oral, has been received from another police officer, provided that the requisition specifies the person to be arrested and the offence or other cause for which the arrest is to be made and it appears therefrom that the person might lawfully be arrested without a warrant by the officer who issued the requisition. (2) Subject to the provisions of section 42, no person concerned in a non-cognizable offence or against whom a complaint has been made or credible information has been received or reasonable suspicion exists of his having so concerned, shall be arrested except under a warrant or order of a Magistrate."
        ),
        "explanation": (
            "Governs arrest without warrant. Under Arnesh Kumar v. State of Bihar (2014) 8 SCC 273 and D.K. Basu (1997) 1 SCC 416, "
            "police cannot arrest mechanically for offences punishable up to 7 years without satisfying the statutory checklist of necessity and recording reasons."
        ),
        "source_url": "https://cdnbbsr.s3waas.gov.in/s3ec044a11654ad1e1e48352252859ff30/uploads/2023/11/2023110156.pdf",
        "effective_date": "1 April 1974"
    },
    {
        "id": "crpc-1973-sec-41a",
        "act_id": "crpc-1973",
        "section_number": "41A",
        "heading": "Notice of appearance before police officer",
        "body": (
            "(1) The police officer shall, in all cases where the arrest of a person is not required under the provisions of sub-section (1) of section 41, issue a notice directing the person against whom a reasonable complaint has been made, or credible information has been received, or a reasonable suspicion exists that he has committed a cognizable offence, to appear before him or at such other place as may be specified in the notice. (2) Where such a notice is issued to any person, it shall be the duty of that person to comply with the terms of the notice. (3) Where such person complies and continues to comply with the notice, he shall not be arrested in respect of the offence referred to in the notice unless, for reasons to be recorded, the police officer is of the opinion that he ought to be arrested. (4) Where such person, at any time, fails to comply with the terms of the notice or is unwilling to identify himself, the police officer may, subject to such orders as may have been passed by a competent Court in this behalf, arrest him for the offence mentioned in the notice."
        ),
        "explanation": (
            "Mandates issuance of a notice of appearance instead of arrest for offences punishable up to 7 years where arrest is not strictly necessary."
        ),
        "source_url": "https://cdnbbsr.s3waas.gov.in/s3ec044a11654ad1e1e48352252859ff30/uploads/2023/11/2023110156.pdf",
        "effective_date": "1 November 2010 (inserted by Act 5 of 2009)"
    },
    {
        "id": "crpc-1973-sec-56",
        "act_id": "crpc-1973",
        "section_number": "56",
        "heading": "Person arrested to be taken before Magistrate or officer in charge of police station",
        "body": (
            "A police officer making an arrest without warrant shall, without unnecessary delay and subject to the provisions herein contained as to bail, take or send the person arrested before a Magistrate having jurisdiction in the case, or before the officer in charge of a police station."
        ),
        "explanation": (
            "Statutory procedural mandate giving effect to Article 22(2) of the Constitution: every person arrested without a warrant must be brought "
            "before a Magistrate or police station officer in charge without unnecessary delay."
        ),
        "source_url": "https://cdnbbsr.s3waas.gov.in/s3ec044a11654ad1e1e48352252859ff30/uploads/2023/11/2023110156.pdf",
        "effective_date": "1 April 1974"
    },
    {
        "id": "crpc-1973-sec-161",
        "act_id": "crpc-1973",
        "section_number": "161",
        "heading": "Examination of witnesses by police",
        "body": (
            "(1) Any police officer making an investigation under this Chapter, or any police officer not below such rank as the State Government may, by general or special order, prescribe in this behalf, acting on the requisition of such officer, may examine orally any person supposed to be acquainted with the facts and circumstances of the case. (2) Such person shall be bound to answer truly all questions relating to such case put to him by such officer, other than questions the answers to which would have a tendency to expose him to a criminal charge or to a penalty or forfeiture. (3) The police officer may reduce into writing any statement made to him in the course of an examination under this section; and if he does so, he shall make a separate and true record of the statement of each such person whose statement he records. Provided that statement made under this sub-section may also be recorded by audio-video electronic means: Provided further that the statement of a woman against whom an offence under section 354, section 354A, section 354B, section 354C, section 354D, section 376, section 376A, section 376AB, section 376B, section 376C, section 376D, section 376DA, section 376DB, section 376E or section 509 of the Indian Penal Code (45 of 1860) is alleged to have been committed or attempted shall be recorded, by a woman police officer or any woman officer."
        ),
        "explanation": (
            "Governs oral examination of witnesses by investigating police officers during criminal investigations. "
            "Statements recorded under Section 161 cannot be signed by the witness and cannot be used as substantive evidence at trial; "
            "they may only be used to contradict the witness under Section 162 CrPC and Section 145 Evidence Act."
        ),
        "source_url": "https://cdnbbsr.s3waas.gov.in/s3ec044a11654ad1e1e48352252859ff30/uploads/2023/11/2023110156.pdf",
        "effective_date": "1 April 1974"
    },

    # ---------------- Indian Penal Code, 1860 ----------------
    {
        "id": "ipc-1860-sec-82",
        "act_id": "ipc-1860",
        "section_number": "82",
        "heading": "Act of a child under seven years of age",
        "body": (
            "Nothing is an offence which is done by a child under seven years of age."
        ),
        "explanation": (
            "Codifies the doctrine of absolute doli incapax under Indian criminal jurisprudence. "
            "A child under 7 years is conclusively presumed to lack the capacity to form criminal intent (mens rea) and cannot be convicted of any offence."
        ),
        "source_url": "https://crpf.mha.gov.in/writereaddata/images/pdf/IPC_1860_IN_ENGLISH.pdf",
        "effective_date": "1 May 1861"
    },
    {
        "id": "ipc-1860-sec-83",
        "act_id": "ipc-1860",
        "section_number": "83",
        "heading": "Act of a child above seven and under twelve of immature understanding",
        "body": (
            "Nothing is an offence which is done by a child above seven years of age and under twelve, "
            "who has not attained sufficient maturity of understanding to judge of the nature and consequences of his conduct on that occasion."
        ),
        "explanation": (
            "Provides qualified immunity (doli capax inquiry) for children between 7 and 12 years of age. Criminal liability depends on proof of sufficient maturity."
        ),
        "source_url": "https://crpf.mha.gov.in/writereaddata/images/pdf/IPC_1860_IN_ENGLISH.pdf",
        "effective_date": "1 May 1861"
    },
    {
        "id": "ipc-1860-sec-320",
        "act_id": "ipc-1860",
        "section_number": "320",
        "heading": "Grievous hurt",
        "body": (
            "The following kinds of hurt only are designated as 'grievous':—\n"
            "First.—Emasculation.\n"
            "Secondly.—Permanent privation of the sight of either eye.\n"
            "Thirdly.—Permanent privation of the hearing of either ear.\n"
            "Fourthly.—Privation of any member or joint.\n"
            "Fifthly.—Destruction or permanent impairing of the powers of any member or joint.\n"
            "Sixthly.—Permanent disfiguration of the head or face.\n"
            "Seventhly.—Fracture or dislocation of a bone or tooth.\n"
            "Eighthly.—Any hurt which endangers life or which causes the sufferer to be during the space of twenty days in severe bodily pain, or unable to follow his ordinary pursuits."
        ),
        "explanation": (
            "Defines statutory categories of 'grievous hurt' across Indian law, specifically referenced by Section 161 of the Motor Vehicles Act, 1988 "
            "for fixed statutory relief under the Compensation to Victims of Hit and Run Motor Accidents Scheme, 2022."
        ),
        "source_url": "https://crpf.mha.gov.in/writereaddata/images/pdf/IPC_1860_IN_ENGLISH.pdf",
        "effective_date": "1 May 1861"
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
        ),
        "source_url": "https://indiacode.gov.in/items/e0a1c7bb-8bed-47d7-a0b6-9fd3c8a3944c",
        "effective_date": "1 March 1964"
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
            "(ha) if it would impede or delay the progress or completion of any infrastructure project or interfere with the continued provision of relevant facility related thereto or services being the subject matter of such project.\n"
            "(i) when the conduct of the plaintiff or his agents has been such as to disentitle him to the assistance of the court;\n"
            "(j) when the plaintiff has no personal interest in the matter."
        ),
        "explanation": (
            "Clause (e) bars an injunction to restrain the breach of a contract whose specific performance is barred under Section 14 "
            "(such as contracts for personal services or post-service non-compete agreements)."
        ),
        "source_url": "https://indiacode.gov.in/items/e0a1c7bb-8bed-47d7-a0b6-9fd3c8a3944c",
        "effective_date": "1 March 1964"
    },
    {
        "id": "specific-relief-1963-sec-42",
        "act_id": "specific-relief-act-1963",
        "section_number": "42",
        "heading": "Injunction to perform negative agreement",
        "body": (
            "Notwithstanding anything contained in clause (e) of section 41, where a contract comprises an affirmative agreement "
            "to do a certain act, coupled with a negative agreement, express or implied, not to do a certain act, the circumstance "
            "that the court is unable to compel specific performance of the affirmative agreement shall not preclude it from granting "
            "an injunction to perform the negative agreement:\n\n"
            "Provided that the plaintiff has not failed to perform the contract so far as it is binding on him."
        ),
        "explanation": (
            "Statutory basis for enforcing during-employment exclusive covenants under Niranjan Shankar Golikari (1967). "
            "However, Section 42 cannot be used to circumvent Section 27 to enforce post-employment restraints (Percept D'Mark)."
        ),
        "source_url": "https://indiacode.gov.in/items/e0a1c7bb-8bed-47d7-a0b6-9fd3c8a3944c",
        "effective_date": "1 March 1964"
    },

    # ---------------- Arbitration and Conciliation Act, 1996 ----------------
    {
        "id": "arbitration-1996-sec-8",
        "act_id": "arbitration-act-1996",
        "section_number": "8",
        "heading": "Power to refer parties to arbitration where there is an arbitration agreement",
        "body": (
            "(1) A judicial authority, before which an action is brought in a matter which is the subject of an arbitration agreement shall, if a party to the arbitration agreement or any person claiming through or under him, so applies not later than the date of submitting his first statement on the substance of the dispute, then, notwithstanding any judgment, decree or order of the Supreme Court or any Court, refer the parties to arbitration unless it finds that prima facie no valid arbitration agreement exists.\n"
            "(2) The application referred to in sub-section\n"
            "(1) shall not be entertained unless it is accompanied by the original arbitration agreement or a duly certified copy thereof:\n"
            "Provided that where the original arbitration agreement or a certified copy thereof is not available with the party applying for reference to arbitration under sub-section (1), and the said agreement or certified copy is retained by the other party to that agreement, then, the party so applying shall file such application along with a copy of the arbitration agreement and a petition praying the Court to call upon the other party to produce the original arbitration agreement or its duly certified copy before that Court.\n"
            "(3) Notwithstanding that an application has been made under sub-section\n"
            "(1) and that the issue is pending before the judicial authority, an arbitration may be commenced or continued and an arbitral award made."
        ),
        "explanation": (
            "Mandatory referral to arbitration where a valid arbitration agreement exists, preserving party autonomy and minimal judicial intervention."
        ),
        "source_url": "https://indiacode.gov.in/items/99bffa19-c36b-417d-9175-4098ad6a6cf7",
        "effective_date": "22 August 1996"
    },
    {
        "id": "arbitration-1996-sec-9",
        "act_id": "arbitration-act-1996",
        "section_number": "9",
        "heading": "Interim measures, etc., by Court",
        "body": (
            "(1) A party may, before or during arbitral proceedings or at any time after the making of the arbitral award but before it is enforced in accordance with section 36, apply to a court—\n"
            "(i) for the appointment of a guardian for a minor or person of unsound mind for the purposes of arbitral proceedings; or\n"
            "(ii) for an interim measure of protection in respect of any of the following matters, namely:—\n"
            "(a) the preservation, interim custody or sale of any goods which are the subject-matter of the arbitration agreement;\n"
            "(b) securing the amount in dispute in the arbitration;\n"
            "(c) the detention, preservation or inspection of any property or thing which is the subject-matter of the dispute in arbitration, or as to which any question may arise therein and authorising for any of the aforesaid purposes any person to enter upon any land or building in the possession of any party, or authorising any samples to be taken or any observation to be made, or experiment to be tried, which may be necessary or expedient for the purpose of obtaining full information or evidence;\n"
            "(d) interim injunction or the appointment of a receiver;\n"
            "(e) such other interim measure of protection as may appear to the Court to be just and convenient, and the Court shall have the same power for making orders as it has for the purpose of, and in relation to, any proceedings before it.\n"
            "(2) Where, before the commencement of the arbitral proceedings, a Court passes an order for any interim measure of protection under sub-section (1), the arbitral proceedings shall be commenced within a period of ninety days from the date of such order or within such further time as the Court may determine.\n"
            "(3) Once the arbitral tribunal has been constituted, the Court shall not entertain an application under sub-section (1), unless the Court finds that circumstances exist which may not render the remedy provided under section 17 efficacious."
        ),
        "explanation": (
            "Empowers the civil court to grant urgent pre-arbitral or interim protection. Once the arbitral tribunal is formed, "
            "Section 17 applications take precedence unless special circumstances render the tribunal remedy inefficacious."
        ),
        "source_url": "https://indiacode.gov.in/items/99bffa19-c36b-417d-9175-4098ad6a6cf7",
        "effective_date": "22 August 1996"
    },
    {
        "id": "arbitration-1996-sec-11",
        "act_id": "arbitration-act-1996",
        "section_number": "11",
        "heading": "Appointment of arbitrators",
        "body": (
            "(1) A person of any nationality may be an arbitrator, unless otherwise agreed by the parties.\n"
            "(2) Subject to sub-section (6), the parties are free to agree on a procedure for appointing the arbitrator or arbitrators.\n"
            "(3) Failing any agreement referred to in sub-section (2), in an arbitration with three arbitrators, each party shall appoint one arbitrator, and the two appointed arbitrators shall appoint the third arbitrator who shall act as the presiding arbitrator.\n"
            "(4) If the appointment procedure in sub-section\n"
            "(3) applies and—\n"
            "(a) a party fails to appoint an arbitrator within thirty days from the receipt of a request to do so from the other party; or\n"
            "(b) the two appointed arbitrators fail to agree on the third arbitrator within thirty days from the date of their appointment, the appointment shall be made, upon request of a party, by the Supreme Court or, as the case may be, the High Court or any person or institution designated by such Court ;\n"
            "(5) Failing any agreement referred to in sub-section (2), in an arbitration with a sole arbitrator, if the parties fail to agree on the arbitrator within thirty days from receipt of a request by one party from the other party to so agree the appointment shall be made, upon request of a party, by the Supreme Court or, as the case may be, the High Court or any person or institution designated by such Court.\n"
            "(6) Where, under an appointment procedure agreed upon by the parties,—\n"
            "(a) a party fails to act as required under that procedure; or\n"
            "(b) the parties, or the two appointed arbitrators, fail to reach an agreement expected of them under that procedure; or\n"
            "(c) a person, including an institution, fails to perform any function entrusted to him or it under that procedure, a party may request the Supreme Court or, as the case may be, the High Court or any person or institution designated by such Court to take the necessary measure, unless the agreement on the appointment procedure provides other means for securing the appointment. (6A) The Supreme Court or, as the case may be, the High Court, while considering any application under sub-section\n"
            "(4) or sub-section\n"
            "(5) or sub-section (6), shall, notwithstanding any judgment, decree or order of any Court, confine to the examination of the existence of an arbitration agreement. (6B) The designation of any person or institution by the Supreme Court or, as the case may be, the High Court, for the purposes of this section shall not be regarded as a delegation of judicial power by the Supreme Court or the High Court.\n"
            "(7) A decision on a matter entrusted by sub-section\n"
            "(4) or sub-section\n"
            "(5) or sub-section\n"
            "(6) to the Supreme Court or, as the case may be, the High Court or the person or institution designated by such Court is final and no appeal including Letters Patent Appeal shall lie against such decision.\n"
            "(8) The Supreme Court or, as the case may be, the High Court or the person or institution designated by such Court, before appointing an arbitrator, shall seek a disclosure in writing from the prospective arbitrator in terms of sub-section\n"
            "(1) of section 12, and have due regard to—\n"
            "(a) any qualifications required for the arbitrator by the agreement of the parties; and\n"
            "(b) the contents of the disclosure and other considerations as are likely to secure the appointment of an independent and impartial arbitrator.\n"
            "(9) In the case of appointment of sole or third arbitrator in an international commercial arbitration, the Supreme Court or the person or institution designated by that Court may appoint an arbitrator of a nationality other than the nationalities of the parties where the parties belong to different nationalities.\n"
            "(10) The Supreme Court or, as the case may be, the High Court, may make such scheme as the said Court may deem appropriate for dealing with matters entrusted by sub-section\n"
            "(4) or sub-section\n"
            "(5) or sub-section (6), to it.\n"
            "(11) Where more than one request has been made under sub-section\n"
            "(4) or sub-section\n"
            "(5) or sub-section\n"
            "(6) to the Chief Justices of different High Courts or their designates, different High Courts or their designates, the High Court or its designate to whom the request has been first made under the relevant sub-section shall alone be competent to decide on the request.\n"
            "(12)\n"
            "(a) Where the matters referred to in sub-sections (4), (5), (6), (7),\n"
            "(8) and sub-section\n"
            "(10) arise in an international commercial arbitration, the reference to the “Supreme Court or, as the case may be, the High Court” in those sub-sections shall be construed as a reference to the “Supreme Court”; and\n"
            "(b) Where the matters referred to in sub-sections (4), (5), (6), (7),\n"
            "(8) and sub-section\n"
            "(10) arise in any other arbitration, the reference to “the Supreme Court or, as the case may be, the High Court” in those sub-sections shall be construed as a reference to the “High Court” within whose local limits the principal Civil Court referred to in clause\n"
            "(e) of sub-section\n"
            "(1) of section 2 is situate, and where the High Court itself is the Court referred to in that clause, to that High Court.\n"
            "(13) An application made under this section for appointment of an arbitrator or arbitrators shall be disposed of by the Supreme Court or the High Court or the person or institution designated by such Court, as the case may be, as expeditiously as possible and an endeavour shall be made to dispose of the matter within a period of sixty days from the date of service of notice on the opposite party.\n"
            "(14) For the purpose of determination of the fees of the arbitral tribunal and the manner of its payment to the arbitral tribunal, the High Court may frame such rules as may be necessary, after taking into consideration the rates specified in the Fourth Schedule. Explanation.—For the removal of doubts, it is hereby clarified that this sub-section shall not apply to international commercial arbitration and in arbitrations (other than international commercial arbitration) in case where parties have agreed for determination of fees as per the rules of an arbitral institution."
        ),
        "explanation": (
            "Governs judicial appointment of arbitrators. Under Vidya Drolia (2021) and SBI General Insurance (2024), "
            "the referral court's examination is strictly confined to the prima facie existence of the arbitration agreement."
        ),
        "source_url": "https://indiacode.gov.in/items/99bffa19-c36b-417d-9175-4098ad6a6cf7",
        "effective_date": "22 August 1996"
    },
    {
        "id": "arbitration-1996-sec-34",
        "act_id": "arbitration-act-1996",
        "section_number": "34",
        "heading": "Application for setting aside arbitral award",
        "body": (
            "(1) Recourse to a Court against an arbitral award may be made only by an application for setting aside such award in accordance with sub-section\n"
            "(2) and sub-section (3).\n"
            "(2) An arbitral award may be set aside by the Court only if—\n"
            "(a) the party making the application establishes on the basis of the record of the arbitral tribunal that—\n"
            "(i) a party was under some incapacity, or\n"
            "(ii) the arbitration agreement is not valid under the law to which the parties have subjected it or, failing any indication thereon, under the law for the time being in force; or\n"
            "(iii) the party making the application was not given proper notice of the appointment of an arbitrator or of the arbitral proceedings or was otherwise unable to present his case; or\n"
            "(iv) the arbitral award deals with a dispute not contemplated by or not falling within the terms of the submission to arbitration, or it contains decisions on matters beyond the scope of the submission to arbitration:\n"
            "Provided that, if the decisions on matters submitted to arbitration can be separated from those not so submitted, only that part of the arbitral award which contains decisions on matters not submitted to arbitration may be set aside; or\n"
            "(v) the composition of the arbitral tribunal or the arbitral procedure was not in accordance with the agreement of the parties, unless such agreement was in conflict with a provision of this Part from which the parties cannot derogate, or, failing such agreement, was not in accordance with this Part; or\n"
            "(b) the Court finds that—\n"
            "(i) the subject-matter of the dispute is not capable of settlement by arbitration under the law for the time being in force, or\n"
            "(ii) the arbitral award is in conflict with the public policy of India.\n"
            "Explanation 1.—For the avoidance of any doubt, it is clarified that an award is in conflict with the public policy of India, only if,—\n"
            "(i) the making of the award was induced or affected by fraud or corruption or was in violation of section 75 or section 81; or\n"
            "(ii) it is in contravention with the fundamental policy of Indian law; or\n"
            "(iii) it is in conflict with the most basic notions of morality or justice.\n"
            "Explanation 2.—For the avoidance of doubt, the test as to whether there is a contravention with the fundamental policy of Indian law shall not entail a review on the merits of the dispute. (2A) An arbitral award arising out of arbitrations other than international commercial arbitrations, may also be set aside by the Court, if the Court finds that the award is vitiated by patent illegality appearing on the face of the award:\n"
            "Provided that an award shall not be set aside merely on the ground of an erroneous application of the law or by reappreciation of evidence.\n"
            "(3) An application for setting aside may not be made after three months have elapsed from the date on which the party making that application had received the arbitral award or, if a request had been made under section 33, from the date on which that request had been disposed of by the arbitral tribunal:\n"
            "Provided that if the Court is satisfied that the applicant was prevented by sufficient cause from making the application within the said period of three months it may entertain the application within a further period of thirty days, but not thereafter.\n"
            "(4) On receipt of an application under sub-section (1), the Court may, where it is appropriate and it is so requested by a party, adjourn the proceedings for a period of time determined by it in order to give the arbitral tribunal an opportunity to resume the arbitral proceedings or to take such other action as in the opinion of arbitral tribunal will eliminate the grounds for setting aside the arbitral award.\n"
            "(5) An application under this section shall be filed by a party only after issuing a prior notice to the other party and such application shall be accompanied by an affidavit by the applicant endorsing compliance with the said requirement.\n"
            "(6) An application under this section shall be disposed of expeditiously, and in any event, within a period of one year from the date on which the notice referred to in sub-section\n"
            "(5) is served upon the other party."
        ),
        "explanation": (
            "Defines the narrow, non-merit grounds for setting aside arbitral awards in India. Under Associate Builders (2015) "
            "and Ssangyong Engineering (2019), courts cannot review the merits of the dispute or re-appreciate evidence."
        ),
        "source_url": "https://indiacode.gov.in/items/99bffa19-c36b-417d-9175-4098ad6a6cf7",
        "effective_date": "22 August 1996"
    }
]

def init_db(db_path: Path) -> sqlite3.Connection:
    """Initializes SQLite tables for Bare Acts and Statutory Provisions with schema evolution."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bare_acts (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                act_number TEXT NOT NULL,
                year INTEGER NOT NULL,
                jurisdiction TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS seed_meta (
                key TEXT PRIMARY KEY,
                value TEXT
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
                source_url TEXT,
                effective_date TEXT,
                FOREIGN KEY (act_id) REFERENCES bare_acts(id) ON DELETE CASCADE
            );
        """)
        # Index on act_id + section_number for high performance statutory lookups
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_provision_lookup 
            ON statutory_provisions(act_id, section_number);
        """)

        # Graceful schema migration for existing databases
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(bare_acts);")
        act_cols = [r[1] for r in cursor.fetchall()]
        if "jurisdiction" not in act_cols:
            cursor.execute("ALTER TABLE bare_acts ADD COLUMN jurisdiction TEXT;")

        cursor.execute("PRAGMA table_info(statutory_provisions);")
        prov_cols = [r[1] for r in cursor.fetchall()]
        if "source_url" not in prov_cols:
            cursor.execute("ALTER TABLE statutory_provisions ADD COLUMN source_url TEXT;")
        if "effective_date" not in prov_cols:
            cursor.execute("ALTER TABLE statutory_provisions ADD COLUMN effective_date TEXT;")
        if "status" not in prov_cols:
            cursor.execute("ALTER TABLE statutory_provisions ADD COLUMN status TEXT DEFAULT 'in_force';")
        if "edition" not in act_cols:
            cursor.execute("ALTER TABLE bare_acts ADD COLUMN edition TEXT;")

    return conn

def seed_database(conn: sqlite3.Connection) -> Tuple[int, int]:
    """Inserts or updates authoritative bare acts and statutory provisions."""
    cursor = conn.cursor()
    
    # 1. Insert bare acts
    acts_inserted = 0
    for act in BARE_ACTS_DATA:
        cursor.execute("""
            INSERT INTO bare_acts (id, title, act_number, year, jurisdiction, edition)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                act_number=excluded.act_number,
                year=excluded.year,
                jurisdiction=excluded.jurisdiction,
                edition=excluded.edition;
        """, (act["id"], act["title"], act["act_number"], act["year"], act.get("jurisdiction", "India"), act.get("edition")))
        acts_inserted += 1

    # 2. Insert statutory provisions (Constitution handled separately from the verified corpus)
    provisions_inserted = 0
    constitution_curated = {}
    for prov in STATUTORY_PROVISIONS_DATA:
        if prov["act_id"] == "constitution-of-india-1950":
            constitution_curated[prov["section_number"].upper()] = prov
            continue
        cursor.execute("""
            INSERT INTO statutory_provisions (id, act_id, section_number, heading, body, explanation, source_url, effective_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                act_id=excluded.act_id,
                section_number=excluded.section_number,
                heading=excluded.heading,
                body=excluded.body,
                explanation=excluded.explanation,
                source_url=excluded.source_url,
                effective_date=excluded.effective_date;
        """, (
            prov["id"],
            prov["act_id"],
            prov["section_number"],
            prov["heading"],
            prov["body"],
            prov["explanation"],
            prov.get("source_url"),
            prov.get("effective_date")
        ))
        provisions_inserted += 1

    # 3. Constitution: replace any prior provisions with the verified corpus
    cursor.execute("DELETE FROM statutory_provisions WHERE act_id = 'constitution-of-india-1950';")
    cursor.execute("UPDATE bare_acts SET edition = ? WHERE id = 'constitution-of-india-1950';", (CONSTITUTION_EDITION,))
    for prov in load_constitution_provisions(constitution_curated):
        cursor.execute("""
            INSERT INTO statutory_provisions (id, act_id, section_number, heading, body, explanation, source_url, effective_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            prov["id"], prov["act_id"], prov["section_number"], prov["heading"],
            prov["body"], prov["explanation"], prov.get("source_url"),
            prov.get("effective_date"), prov.get("status", "in_force"),
        ))
        provisions_inserted += 1

    # 4. Criminal reforms (BNS/BNSS): replace any prior provisions with the verified corpus
    cursor.execute("DELETE FROM statutory_provisions WHERE act_id IN ('bharatiya-nyaya-sanhita-2023', 'bharatiya-nagarik-suraksha-sanhita-2023');")
    for prov in load_criminal_reforms_provisions():
        cursor.execute("""
            INSERT INTO statutory_provisions (id, act_id, section_number, heading, body, explanation, source_url, effective_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            prov["id"], prov["act_id"], prov["section_number"], prov["heading"],
            prov["body"], prov["explanation"], prov.get("source_url"),
            prov.get("effective_date"), prov.get("status", "in_force"),
        ))
        provisions_inserted += 1

    cursor.execute("""
        INSERT INTO seed_meta (key, value) VALUES ('seed_version', ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value;
    """, (SEED_VERSION,))
    conn.commit()
    return acts_inserted, provisions_inserted

def main():
    logger.info("=================================================================")
    logger.info("   JUSTICE Legal Intelligence — Bare Acts & Provisions Seeder    ")
    logger.info(f"   Target SQLite DB: {DB_PATH}")
    logger.info("=================================================================")

    conn = init_db(DB_PATH)
    acts_count, provisions_count = seed_database(conn)
    conn.close()

    print(f"\n[SUCCESS] Seeded Indian Statutory Intelligence Engine:")
    print(f"  * Bare Acts Indexed:       {acts_count} acts")
    print(f"  * Statutory Provisions:   {provisions_count} sections/articles")
    print(f"  * Database Location:      {DB_PATH}\n")

if __name__ == "__main__":
    main()
