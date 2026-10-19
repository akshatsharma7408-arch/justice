"""
Verification script for landmark queries:
Searches for:
1. 'Kesavananda Bharati'
2. 'AIR 1973 SC 1461'
3. '(1973) 4 SCC 225'
4. 'basic structure'
5. 'Maneka Gandhi'
6. 'right to privacy Puttaswamy'
Displays top 3 results (case name only) for each.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.qdrant_service import qdrant_service

queries = [
    "Kesavananda Bharati",
    "AIR 1973 SC 1461",
    "(1973) 4 SCC 225",
    "basic structure",
    "Maneka Gandhi",
    "right to privacy Puttaswamy",
]

print("==================================================================")
print("LANDMARK SEARCH VERIFICATION RESULTS (TOP 3 PER QUERY)")
print("==================================================================")

for q in queries:
    results = qdrant_service.search_precedents(query=q, limit=3)
    print(f"\nQuery: \"{q}\"")
    for idx, r in enumerate(results[:3], 1):
        name = r.get("common_name") or r.get("title") or r.get("case_name")
        score = r.get("relevance_score")
        mode = r.get("retrieval_mode")
        print(f"  {idx}. {name} (score: {score}, mode: {mode})")

print("\n==================================================================")
