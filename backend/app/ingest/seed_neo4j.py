"""
JUSTICE Legal AI Backend - Neo4j Article 141 Graph Seeder
Builds the real citation-treatment graph in Neo4j from the verified
Section 27 / Article 141 corpus. Nodes are Case vertices; edges are the
documented judicial treatment relationships (AFFIRMS, DISTINGUISHES,
APPLIES, OVERRULES, RELIES_ON).

All statements use MERGE, so the seeder is idempotent and safe to re-run.

Usage:
    python -m app.ingest.seed_neo4j            # seed into live Neo4j
    python -m app.ingest.seed_neo4j --dry-run  # print the Cypher plan only
"""

import argparse
import json
import logging
from typing import Any, Dict, List

from app.config import settings
from app.ingest.seed_qdrant import load_corpus

logger = logging.getLogger("justice.ingest.neo4j")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Verified treatment relationships between the corpus cases.
# (citing_case_id, cited_case_id, relationship, note)
TREATMENT_EDGES = [
    ("sc-2006-percept", "sc-1980-superintendence", "REAFFIRMS",
     "Percept D'Mark reaffirms Krishan Murgai: post-termination restraints are void under Section 27."),
    ("sc-2006-percept", "sc-1967-niranjan", "DISTINGUISHES",
     "Niranjan Golikari limited to restraints operating during the subsistence of employment."),
    ("sc-1995-gujaratbottling", "sc-1967-niranjan", "APPLIES",
     "Franchise negative covenant valid only because it operated during the agreement period."),
    ("hc-2006-wipro", "sc-2006-percept", "FOLLOWS",
     "Delhi HC applies Percept D'Mark: no reasonableness balancing for post-termination non-competes."),
    ("hc-2005-ambiance", "sc-2006-percept", "APPLIES",
     "Non-solicitation of customers distinguished from a void general non-compete."),
    ("hc-2009-desiccant", "sc-2006-percept", "FOLLOWS",
     "Injunction enforcing post-service non-compete refused, relying on Percept D'Mark."),
    ("hc-2016-stellar", "sc-1967-niranjan", "DISTINGUISHES",
     "Confidentiality wording cannot be stretched into a post-employment non-compete."),
    ("sc-2017-puttaswamy", "sc-1976-admjabalpur", "OVERRULES",
     "Nine-judge bench overruled ADM Jabalpur on the status of Article 21 during emergency."),
]

NODE_CYPHER = """
MERGE (c:Case {id: $id})
SET c.title = $title,
    c.citation = $citation,
    c.court = $court,
    c.benchType = $benchType,
    c.benchSize = $benchSize,
    c.decisionYear = $decisionYear,
    c.status = $status,
    c.statusLabel = $statusLabel,
    c.ratioSummary = $ratioSummary,
    c.sourceUrl = $sourceUrl
"""

EDGE_CYPHER = """
MATCH (a:Case {id: $citing}), (b:Case {id: $cited})
MERGE (a)-[r:TREATS {kind: $kind}]->(b)
SET r.note = $note
"""


def build_plan() -> Dict[str, Any]:
    cases = {c["id"]: c for c in load_corpus()}
    missing = [e for e in TREATMENT_EDGES if e[0] not in cases or e[1] not in cases]
    if missing:
        raise RuntimeError(f"Treatment edges reference unknown case ids: {missing}")
    return {"nodes": list(cases.values()), "edges": TREATMENT_EDGES}


def seed_neo4j(dry_run: bool = False) -> Dict[str, Any]:
    plan = build_plan()
    report: Dict[str, Any] = {
        "uri": settings.NEO4J_URI,
        "nodes": len(plan["nodes"]),
        "edges": len(plan["edges"]),
        "dry_run": dry_run,
    }
    if dry_run:
        logger.info("Dry run OK: %d Case nodes, %d TREATS edges", len(plan["nodes"]), len(plan["edges"]))
        return report

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    with driver.session() as session:
        for case in plan["nodes"]:
            session.run(
                NODE_CYPHER,
                id=case["id"],
                title=case["title"],
                citation=case["citation"],
                court=case["court"],
                benchType=case["benchType"],
                benchSize=case["benchSize"],
                decisionYear=case["decisionYear"],
                status=case["status"],
                statusLabel=case["statusLabel"],
                ratioSummary=case.get("ratioSummary", ""),
                sourceUrl=case.get("source", {}).get("url", ""),
            )
        for citing, cited, kind, note in plan["edges"]:
            session.run(EDGE_CYPHER, citing=citing, cited=cited, kind=kind, note=note)
    driver.close()
    logger.info("Seeded %d Case nodes and %d TREATS edges into Neo4j", len(plan["nodes"]), len(plan["edges"]))
    return report


def main():
    parser = argparse.ArgumentParser(description="Seed the Article 141 citation graph into Neo4j.")
    parser.add_argument("--dry-run", action="store_true", help="Print the seeding plan without touching Neo4j")
    args = parser.parse_args()
    report = seed_neo4j(dry_run=args.dry_run)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
