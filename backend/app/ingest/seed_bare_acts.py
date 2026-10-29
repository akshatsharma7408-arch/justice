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
SEED_VERSION = "2026-10-29.v4"  # bump on any seed content/corpus correction; self-heal reseeds on mismatch

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
        "edition": "Repealed by the Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS) w.e.f. 1 July 2024, subject to savings: proceedings initiated before that date generally continue under the CrPC, while matters arising on or after it fall under the BNSS. The BNSS is not yet in our verified database, so current criminal-procedure coverage is a gap. Which text applies depends on when the proceeding arose."
    },
    {
        "id": "ipc-1860",
        "title": "The Indian Penal Code, 1860",
        "act_number": "Act No. 45 of 1860",
        "year": 1860,
        "jurisdiction": "India",
        "edition": "Repealed by the Bharatiya Nyaya Sanhita, 2023 (BNS) w.e.f. 1 July 2024, subject to savings: offences committed before that date are generally still governed by the IPC, while offences on or after it fall under the BNS. The BNS is not yet in our verified database, so current criminal-law coverage for recent offences is a gap. Which text applies depends on the date of the offence."
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
            "(1) Notwithstanding anything contained in this Act or in any other law for the time being in force or instrument having the force of law, "
            "the owner of the motor vehicle or the authorised insurer shall be liable to pay in the case of death or grievous hurt due to any accident "
            "arising out of the use of the motor vehicle, a compensation, of a sum of five lakh rupees in case of death or of two and a half lakh rupees in case of grievous hurt "
            "to the legal heirs or the victim, as the case may be.\n"
            "(2) In any claim for compensation under sub-section (1), the claimant shall not be required to plead or establish that the death or grievous hurt in respect of which the claim has been made was due to any wrongful act or neglect or default of the owner or of the vehicle."
        ),
        "explanation": (
            "Provides statutory structured compensation on a no-fault basis where the offending vehicle is identified/traced. "
            "The claimant is not required to plead or prove wrongful act, neglect, or default."
        ),
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/15390/1/the_motor_vehicles_act%2C_1988.pdf",
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
            "(c) where death has resulted from the accident, by all or any of the legal representatives of the deceased;\n"
            "(d) by any agent duly authorised by the person injured or all or any of the legal representatives of the deceased..."
        ),
        "explanation": (
            "Governs fault-based adjudication before the Motor Accident Claims Tribunal (MACT) against the owner, driver, and insurance company "
            "of an identified offending vehicle. Compensation is calculated judicially under the structured multiplier system (Sarla Verma (2009) 6 SCC 121 "
            "and National Insurance Co. v. Pranay Sethi (2017) 16 SCC 680) based on age, verified monthly income, future prospects, dependency, and permanent disability percentage."
        ),
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/15390/1/the_motor_vehicles_act%2C_1988.pdf",
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
            "Every agreement, by which any party thereto is restricted absolutely from enforcing his rights under or in respect "
            "of any contract, by the usual legal proceedings in the ordinary tribunals, or which limits the time within which "
            "he may thus enforce his rights, is void to that extent.\n\n"
            "Exception 1.—Saving of contract to refer to arbitration dispute that may arise.\n"
            "Exception 2.—Saving of contract to refer questions that have already arisen."
        ),
        "explanation": (
            "Agreements that extinguish rights or curtail statutory limitation periods are void. "
            "Arbitration agreements are expressly protected under Exceptions 1 and 2."
        ),
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2187/2/A187209.pdf",
        "effective_date": "1 September 1872"
    },
    {
        "id": "contract-1872-sec-56",
        "act_id": "contract-act-1872",
        "section_number": "56",
        "heading": "Agreement to do impossible act / Contract to do act afterwards becoming impossible or unlawful",
        "body": (
            "An agreement to do an act impossible in itself is void.\n\n"
            "Contract to do act afterwards becoming impossible or unlawful.—A contract to do an act which, after the contract is made, "
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
            "(1) Any police officer may without an order from a Magistrate and without a warrant, arrest any person—\n"
            "(a) who commits, in the presence of a police officer, a cognizable offence;\n"
            "(b) against whom a reasonable complaint has been made, or credible information has been received, or a reasonable suspicion exists "
            "that he has committed a cognizable offence punishable with imprisonment for a term which may be less than seven years or which may extend to seven years..."
        ),
        "explanation": (
            "Governs arrest without warrant. Under Arnesh Kumar v. State of Bihar (2014) 8 SCC 273 and D.K. Basu (1997) 1 SCC 416, "
            "police cannot arrest mechanically for offences punishable up to 7 years without satisfying the statutory checklist of necessity and recording reasons."
        ),
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/15272/1/the_code_of_criminal_procedure%2C_1973.pdf",
        "effective_date": "1 April 1974"
    },
    {
        "id": "crpc-1973-sec-41a",
        "act_id": "crpc-1973",
        "section_number": "41A",
        "heading": "Notice of appearance before police officer",
        "body": (
            "(1) The police officer shall, in all cases where the arrest of a person is not required under the provisions of sub-section (1) of section 41, "
            "issue a notice directing the person against whom a reasonable complaint has been made, or credible information has been received, "
            "or a reasonable suspicion exists that he has committed a cognizable offence, to appear before him or at such other place as may be specified in the notice."
        ),
        "explanation": (
            "Mandates issuance of a notice of appearance instead of arrest for offences punishable up to 7 years where arrest is not strictly necessary."
        ),
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/15272/1/the_code_of_criminal_procedure%2C_1973.pdf",
        "effective_date": "1 November 2010 (inserted by Act 5 of 2009)"
    },
    {
        "id": "crpc-1973-sec-56",
        "act_id": "crpc-1973",
        "section_number": "56",
        "heading": "Person arrested to be taken before Magistrate or officer in charge of police station",
        "body": (
            "A police officer making an arrest without warrant shall, without unnecessary delay and subject to the provisions herein contained "
            "as to bail, take or send the person arrested before a Magistrate having jurisdiction in the case, or before the officer in charge of a police station."
        ),
        "explanation": (
            "Statutory procedural mandate giving effect to Article 22(2) of the Constitution: every person arrested without a warrant must be brought "
            "before a Magistrate or police station officer in charge without unnecessary delay."
        ),
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/15272/1/the_code_of_criminal_procedure%2C_1973.pdf",
        "effective_date": "1 April 1974"
    },
    {
        "id": "crpc-1973-sec-161",
        "act_id": "crpc-1973",
        "section_number": "161",
        "heading": "Examination of witnesses by police",
        "body": (
            "(1) Any police officer making an investigation under this Chapter, or any police officer not below such rank as the State Government may, "
            "by general or special order, prescribe in this behalf, acting on the requisition of such officer, may examine orally any person supposed "
            "to be acquainted with the facts and circumstances of the case.\n"
            "(2) Such person shall be bound to answer truly all questions relating to such case put to him by such officer, other than questions "
            "the answers to which would have a tendency to expose him to a criminal charge or to a penalty or forfeiture.\n"
            "(3) The police officer may reduce into writing any statement made to him in the course of an examination under this section; "
            "and if he does so, he shall make a separate and true record of the statement of each such person whose statement he records."
        ),
        "explanation": (
            "Governs oral examination of witnesses by investigating police officers during criminal investigations. "
            "Statements recorded under Section 161 cannot be signed by the witness and cannot be used as substantive evidence at trial; "
            "they may only be used to contradict the witness under Section 162 CrPC and Section 145 Evidence Act."
        ),
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/15272/1/the_code_of_criminal_procedure%2C_1973.pdf",
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
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/4219/1/THE-INDIAN-PENAL-CODE-1860.pdf",
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
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/4219/1/THE-INDIAN-PENAL-CODE-1860.pdf",
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
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/4219/1/THE-INDIAN-PENAL-CODE-1860.pdf",
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
        "source_url": "https://www.indiacode.nic.in/handle/123456789/1583",
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
            "(i) when the conduct of the plaintiff or his agents has been such as to disentitle him to the assistance of the court;\n"
            "(j) when the plaintiff has no personal interest in the matter."
        ),
        "explanation": (
            "Clause (e) bars an injunction to restrain the breach of a contract whose specific performance is barred under Section 14 "
            "(such as contracts for personal services or post-service non-compete agreements)."
        ),
        "source_url": "https://www.indiacode.nic.in/handle/123456789/1583",
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
        "source_url": "https://www.indiacode.nic.in/handle/123456789/1583",
        "effective_date": "1 March 1964"
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
        ),
        "source_url": "https://www.indiacode.nic.in/handle/123456789/1978",
        "effective_date": "22 August 1996"
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
        ),
        "source_url": "https://www.indiacode.nic.in/handle/123456789/1978",
        "effective_date": "22 August 1996"
    },
    {
        "id": "arbitration-1996-sec-11",
        "act_id": "arbitration-act-1996",
        "section_number": "11",
        "heading": "Appointment of arbitrators",
        "body": (
            "A person of any nationality may be an arbitrator, unless otherwise agreed by the parties...\n"
            "The Supreme Court or, as the case may be, the High Court or any person or institution designated by such Court, "
            "in an application under this section, shall examine whether there is an arbitration agreement, "
            "and nothing more."
        ),
        "explanation": (
            "Governs judicial appointment of arbitrators. Under Vidya Drolia (2021) and SBI General Insurance (2024), "
            "the referral court's examination is strictly confined to the prima facie existence of the arbitration agreement."
        ),
        "source_url": "https://www.indiacode.nic.in/handle/123456789/1978",
        "effective_date": "22 August 1996"
    },
    {
        "id": "arbitration-1996-sec-34",
        "act_id": "arbitration-act-1996",
        "section_number": "34",
        "heading": "Application for setting aside arbitral award",
        "body": (
            "Recourse to a Court against an arbitral award may be made only by an application for setting aside such award in accordance with sub-section (2) and sub-section (3)...\n"
            "An arbitral award may be set aside by the Court only if—\n"
            "(b) the Court finds that—\n"
            "(i) the subject-matter of the dispute is not capable of settlement by arbitration under the law for the time being in force, or\n"
            "(ii) the arbitral award is in conflict with the public policy of India."
        ),
        "explanation": (
            "Defines the narrow, non-merit grounds for setting aside arbitral awards in India. Under Associate Builders (2015) "
            "and Ssangyong Engineering (2019), courts cannot review the merits of the dispute or re-appreciate evidence."
        ),
        "source_url": "https://www.indiacode.nic.in/handle/123456789/1978",
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
