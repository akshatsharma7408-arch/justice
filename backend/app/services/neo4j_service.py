"""
JUSTICE Legal AI Backend - Neo4j Knowledge Graph Service
Article 141 bench hierarchies and precedent treatment DAGs.

Data source is explicit on every response via the "dataSource" field:
  - "neo4j":              live Cypher reads from the seeded graph
                          (seed with: python -m app.ingest.seed_neo4j)
  - "in_memory_fallback": the verified static graph below (labeled)

BUG FIX (2026-10-17): get_citator_case previously returned the Percept
D'Mark entry for ANY unknown case id. It now returns None for unknown ids
and the router answers 404, so no case is ever silently mislabeled.
"""

import logging
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger("justice.neo4j")

# Verified static citation network (fallback + citator listing).
# Sources for every case are recorded in backend/app/data/section27_precedents.json.
ARTICLE_141_GRAPH_DATA: Dict[str, Dict[str, Any]] = {
    "sc-2006-percept": {
        "id": "sc-2006-percept",
        "title": "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan",
        "citation": "(2006) 4 SCC 227",
        "court": "Supreme Court of India",
        "benchType": "Division Bench",
        "benchSize": 2,
        "decisionYear": 2006,
        "status": "GREEN",
        "statusLabel": "GOOD LAW (ARTICLE 141 BINDING)",
        "citationCount": 34,
        "statusDescription": (
            "Binding precedent under Article 141. Co-ordinate and subordinate benches "
            "are bound. Establishes that Section 27 invalidates restrictive covenants "
            "operating after termination of the contract."
        ),
        "overruledCases": [],
        "treatmentHistory": [
            {
                "case": "Wipro Limited v. Beckman Coulter International S.A.",
                "year": 2006,
                "court": "Delhi High Court",
                "treatment": "FOLLOWS",
                "note": "Applied Percept: no judicial balancing or reasonableness test for post-termination non-competes."
            },
            {
                "case": "Desiccant Rotors International Pvt. Ltd. v. Bappaditya Sarkar",
                "year": 2009,
                "court": "Delhi High Court",
                "treatment": "FOLLOWS",
                "note": "Refused injunction enforcing a post-service non-compete against a former manager."
            },
            {
                "case": "Stellar Information Technology v. Rakesh Kumar",
                "year": 2016,
                "court": "Delhi High Court",
                "treatment": "RELIED_ON",
                "note": "Confidentiality wording cannot be stretched into a post-employment non-compete."
            }
        ],
        "graphNodes": [
            {"id": "sc-2006-percept", "label": "Percept D'Mark (2006)", "type": "TARGET", "bench": 2},
            {"id": "sc-1980-superintendence", "label": "Krishan Murgai (1980)", "type": "REAFFIRMED", "bench": 3},
            {"id": "sc-1967-niranjan", "label": "Niranjan Golikari (1967)", "type": "DISTINGUISHED", "bench": 2},
            {"id": "hc-2006-wipro", "label": "Wipro v. Beckman (2006)", "type": "FOLLOWS", "bench": 2},
            {"id": "hc-2009-desiccant", "label": "Desiccant Rotors (2009)", "type": "FOLLOWS", "bench": 1}
        ],
        "graphEdges": [
            {"source": "sc-2006-percept", "target": "sc-1980-superintendence", "relationship": "REAFFIRMS"},
            {"source": "sc-2006-percept", "target": "sc-1967-niranjan", "relationship": "DISTINGUISHES"},
            {"source": "hc-2006-wipro", "target": "sc-2006-percept", "relationship": "FOLLOWS"},
            {"source": "hc-2009-desiccant", "target": "sc-2006-percept", "relationship": "FOLLOWS"}
        ]
    },
    "sc-1980-superintendence": {
        "id": "sc-1980-superintendence",
        "title": "Superintendence Company of India (P) Ltd. v. Krishan Murgai",
        "citation": "(1981) 2 SCC 246",
        "court": "Supreme Court of India",
        "benchType": "Three-Judge Bench",
        "benchSize": 3,
        "decisionYear": 1980,
        "status": "GREEN",
        "statusLabel": "GOOD LAW (ARTICLE 141 BINDING)",
        "citationCount": 58,
        "statusDescription": (
            "Three-judge bench authority reaffirmed in Percept D'Mark (2006). During-employment "
            "negative covenants are valid; post-service restraints are void under Section 27."
        ),
        "overruledCases": [],
        "treatmentHistory": [
            {
                "case": "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan",
                "year": 2006,
                "court": "Supreme Court of India",
                "treatment": "REAFFIRMED",
                "note": "Division bench reaffirmed the void post-service restraint rule."
            }
        ],
        "graphNodes": [
            {"id": "sc-1980-superintendence", "label": "Krishan Murgai (1980)", "type": "TARGET", "bench": 3},
            {"id": "sc-2006-percept", "label": "Percept D'Mark (2006)", "type": "REAFFIRMED", "bench": 2}
        ],
        "graphEdges": [
            {"source": "sc-2006-percept", "target": "sc-1980-superintendence", "relationship": "REAFFIRMS"}
        ]
    },
    "sc-1967-niranjan": {
        "id": "sc-1967-niranjan",
        "title": "Niranjan Shankar Golikari v. The Century Spinning & Mfg. Co. Ltd.",
        "citation": "AIR 1967 SC 1098",
        "court": "Supreme Court of India",
        "benchType": "Division Bench",
        "benchSize": 2,
        "decisionYear": 1967,
        "status": "YELLOW",
        "statusLabel": "GOOD LAW, NARROW: DURING-EMPLOYMENT RESTRAINTS ONLY",
        "citationCount": 71,
        "statusDescription": (
            "Good law confined to its facts: negative covenants operating during the subsistence of "
            "employment are outside Section 27. Consistently distinguished in post-termination cases."
        ),
        "overruledCases": [],
        "treatmentHistory": [
            {
                "case": "Percept D'Mark (India) (P) Ltd. v. Zaheer Khan",
                "year": 2006,
                "court": "Supreme Court of India",
                "treatment": "DISTINGUISHED",
                "note": "Limited to restraints operating during the contract term."
            },
            {
                "case": "Gujarat Bottling Co. Ltd. v. The Coca Cola Co.",
                "year": 1995,
                "court": "Supreme Court of India",
                "treatment": "APPLIED",
                "note": "Franchise restraint valid only because it operated during the agreement period."
            }
        ],
        "graphNodes": [
            {"id": "sc-1967-niranjan", "label": "Niranjan Golikari (1967)", "type": "TARGET", "bench": 2},
            {"id": "sc-2006-percept", "label": "Percept D'Mark (2006)", "type": "DISTINGUISHED", "bench": 2},
            {"id": "sc-1995-gujaratbottling", "label": "Gujarat Bottling (1995)", "type": "APPLIED", "bench": 2}
        ],
        "graphEdges": [
            {"source": "sc-2006-percept", "target": "sc-1967-niranjan", "relationship": "DISTINGUISHES"},
            {"source": "sc-1995-gujaratbottling", "target": "sc-1967-niranjan", "relationship": "APPLIES"}
        ]
    },
    "sc-1995-gujaratbottling": {
        "id": "sc-1995-gujaratbottling",
        "title": "Gujarat Bottling Co. Ltd. v. The Coca Cola Co.",
        "citation": "(1995) 5 SCC 545",
        "court": "Supreme Court of India",
        "benchType": "Division Bench",
        "benchSize": 2,
        "decisionYear": 1995,
        "status": "GREEN",
        "statusLabel": "GOOD LAW (ARTICLE 141 BINDING)",
        "citationCount": 96,
        "statusDescription": (
            "Binding authority that a franchise negative covenant operating during the agreement "
            "period is not a restraint of trade under Section 27."
        ),
        "overruledCases": [],
        "treatmentHistory": [],
        "graphNodes": [
            {"id": "sc-1995-gujaratbottling", "label": "Gujarat Bottling (1995)", "type": "TARGET", "bench": 2},
            {"id": "sc-1967-niranjan", "label": "Niranjan Golikari (1967)", "type": "APPLIED", "bench": 2}
        ],
        "graphEdges": [
            {"source": "sc-1995-gujaratbottling", "target": "sc-1967-niranjan", "relationship": "APPLIES"}
        ]
    },
    "sc-2017-puttaswamy": {
        "id": "sc-2017-puttaswamy",
        "title": "Justice K.S. Puttaswamy (Retd.) v. Union of India",
        "citation": "(2017) 10 SCC 1",
        "court": "Supreme Court of India",
        "benchType": "Constitution Bench",
        "benchSize": 9,
        "decisionYear": 2017,
        "status": "GREEN",
        "statusLabel": "GOOD LAW (9-JUDGE CONSTITUTION BENCH)",
        "citationCount": 182,
        "statusDescription": (
            "Plenary authority under Article 141. Explicitly overruled ADM Jabalpur (1976) and "
            "M.P. Sharma (1954). Governs Indian privacy and Article 21 jurisprudence."
        ),
        "overruledCases": ["ADM Jabalpur v. Shivkant Shukla (1976)", "M.P. Sharma v. Satish Chandra (1954)"],
        "treatmentHistory": [
            {
                "case": "Navtej Singh Johar v. Union of India",
                "year": 2018,
                "court": "Supreme Court of India",
                "treatment": "APPLIED",
                "note": "Decriminalized Section 377 relying on autonomy and privacy protections anchored in Puttaswamy."
            },
            {
                "case": "Joseph Shine v. Union of India",
                "year": 2018,
                "court": "Supreme Court of India",
                "treatment": "APPLIED",
                "note": "Struck down Section 497 IPC (adultery) citing Puttaswamy privacy and dignity doctrine."
            }
        ],
        "graphNodes": [
            {"id": "sc-2017-puttaswamy", "label": "Puttaswamy (2017)", "type": "TARGET", "bench": 9},
            {"id": "sc-1976-admjabalpur", "label": "ADM Jabalpur (1976)", "type": "OVERRULED", "bench": 5},
            {"id": "sc-2018-navtej", "label": "Navtej Johar (2018)", "type": "APPLIED", "bench": 5}
        ],
        "graphEdges": [
            {"source": "sc-2017-puttaswamy", "target": "sc-1976-admjabalpur", "relationship": "OVERRULES"},
            {"source": "sc-2018-navtej", "target": "sc-2017-puttaswamy", "relationship": "APPLIES"}
        ]
    },
    "sc-1976-admjabalpur": {
        "id": "sc-1976-admjabalpur",
        "title": "ADM Jabalpur v. Shivkant Shukla",
        "citation": "(1976) 2 SCC 521",
        "court": "Supreme Court of India",
        "benchType": "Constitution Bench",
        "benchSize": 5,
        "decisionYear": 1976,
        "status": "RED",
        "statusLabel": "OVERRULED / BAD LAW",
        "citationCount": 41,
        "statusDescription": (
            "Overruled by the nine-judge bench in Puttaswamy (2017). No longer good law; "
            "cited today only to record its overruling and Justice Khanna's dissent."
        ),
        "overruledCases": [],
        "treatmentHistory": [
            {
                "case": "Justice K.S. Puttaswamy (Retd.) v. Union of India",
                "year": 2017,
                "court": "Supreme Court of India",
                "treatment": "OVERRULED",
                "note": "Nine-judge bench held ADM Jabalpur was wrongly decided on Article 21."
            }
        ],
        "graphNodes": [
            {"id": "sc-1976-admjabalpur", "label": "ADM Jabalpur (1976)", "type": "TARGET", "bench": 5},
            {"id": "sc-2017-puttaswamy", "label": "Puttaswamy (2017)", "type": "OVERRULED", "bench": 9}
        ],
        "graphEdges": [
            {"source": "sc-2017-puttaswamy", "target": "sc-1976-admjabalpur", "relationship": "OVERRULES"}
        ]
    }
}

_CASE_QUERY = """
MATCH (c:Case {id: $id})
OPTIONAL MATCH (x:Case)-[r:TREATS]->(c)
RETURN c, collect({id: x.id, title: x.title, year: x.decisionYear,
                   court: x.court, kind: r.kind, note: r.note}) AS treatedBy
"""

_ALL_EDGES_QUERY = """
MATCH (a:Case)-[r:TREATS]->(b:Case)
WHERE a.id = $id OR b.id = $id
RETURN a.id AS source, b.id AS target, r.kind AS kind
"""

_NODE_LOOKUP_QUERY = "MATCH (c:Case) WHERE c.id IN $ids RETURN c"


class Neo4jService:
    def __init__(self):
        self.uri = settings.NEO4J_URI
        self.user = settings.NEO4J_USER
        self.password = settings.NEO4J_PASSWORD
        self._driver = None
        self._init_driver()

    def _init_driver(self):
        try:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(
                self.uri, auth=(self.user, self.password), max_connection_lifetime=5
            )
            self._driver.verify_connectivity()
            logger.info("Initialized Neo4j driver for %s", self.uri)
        except Exception as e:
            logger.info("Neo4j inactive at %s; using labeled in-memory Article 141 graph: %s", self.uri, e)
            self._driver = None

    # ------------------------------------------------------------------ #
    # Citator                                                             #
    # ------------------------------------------------------------------ #
    def get_citator_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        """Returns the citator record for case_id, or None if unknown (router answers 404)."""
        if self._driver:
            try:
                live = self._get_citator_case_neo4j(case_id)
                if live:
                    return live
            except Exception as e:
                logger.warning("Live Neo4j read failed, using labeled fallback: %s", e)
        static = ARTICLE_141_GRAPH_DATA.get(case_id)
        if static:
            record = dict(static)
            record["dataSource"] = "in_memory_fallback"
            return record
        return None

    def _get_citator_case_neo4j(self, case_id: str) -> Optional[Dict[str, Any]]:
        with self._driver.session() as session:
            row = session.run(_CASE_QUERY, id=case_id).single()
            if not row:
                return None
            node = dict(row["c"])
            treated_by = [t for t in row["treatedBy"] if t.get("id")]
            edges = session.run(_ALL_EDGES_QUERY, id=case_id).data()
            related_ids = {case_id}
            for e in edges:
                related_ids.add(e["source"])
                related_ids.add(e["target"])
            nodes = {r["c"]["id"]: dict(r["c"]) for r in session.run(_NODE_LOOKUP_QUERY, ids=list(related_ids))}

        return {
            "id": node["id"],
            "title": node.get("title", ""),
            "citation": node.get("citation", ""),
            "court": node.get("court", ""),
            "benchType": node.get("benchType", ""),
            "benchSize": node.get("benchSize", 2),
            "decisionYear": node.get("decisionYear", 0),
            "status": node.get("status", "UNKNOWN"),
            "statusLabel": node.get("statusLabel", ""),
            "citationCount": len(treated_by),
            "statusDescription": node.get("ratioSummary", ""),
            "treatmentHistory": [
                {
                    "case": t.get("title", ""),
                    "year": t.get("year", 0),
                    "court": t.get("court", ""),
                    "treatment": t.get("kind", ""),
                    "note": t.get("note", ""),
                }
                for t in treated_by
            ],
            "graphNodes": [
                {"id": nid, "label": n.get("title", nid), "type": "TARGET" if nid == case_id else "RELATED",
                 "bench": n.get("benchSize", 0)}
                for nid, n in nodes.items()
            ],
            "graphEdges": [
                {"source": e["source"], "target": e["target"], "relationship": e["kind"]}
                for e in edges
            ],
            "dataSource": "neo4j",
        }

    def evaluate_article_141_hierarchy(self, bench_size: int, bench_type: str) -> Dict[str, Any]:
        """Constitutional precedent invalidation criteria (bench hierarchy rules)."""
        return {
            "targetBenchSize": bench_size,
            "targetBenchType": bench_type,
            "rules": [
                {
                    "level": "Smaller / Subordinate Bench",
                    "jurisdiction": "Bindingly bound. Cannot modify or overrule under judicial discipline.",
                    "status": "BOUND"
                },
                {
                    "level": f"Coordinate Bench ({bench_size} Judges)",
                    "jurisdiction": "Cannot overrule. If doubting correctness, must refer to the CJI for a larger bench reference.",
                    "status": "REFERENCE_REQUIRED"
                },
                {
                    "level": f"Larger Bench ({bench_size + 1}+ Judges)",
                    "jurisdiction": "Holds plenary Article 141 competence to review, modify, or overrule this precedent.",
                    "status": "COMPETENT_TO_OVERRULE"
                }
            ]
        }

    def check_health(self) -> Dict[str, Any]:
        if self._driver:
            try:
                self._driver.verify_connectivity()
                with self._driver.session() as session:
                    count = session.run("MATCH (c:Case) RETURN count(c) AS n").single()["n"]
                return {
                    "status": "connected",
                    "uri": self.uri,
                    "case_nodes": count,
                    "hint": None if count else "Run: python -m app.ingest.seed_neo4j",
                }
            except Exception as e:
                return {
                    "status": "local_fallback",
                    "uri": self.uri,
                    "error": str(e),
                    "graph_cached_cases": len(ARTICLE_141_GRAPH_DATA),
                }
        return {
            "status": "in_memory_fallback",
            "uri": self.uri,
            "graph_cached_cases": len(ARTICLE_141_GRAPH_DATA),
            "detail": "Neo4j daemon idle; serving the labeled static Article 141 graph. Start Neo4j and run: python -m app.ingest.seed_neo4j",
        }


neo4j_service = Neo4jService()
