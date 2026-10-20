"""
Run the 12 landmark validation queries against the backend and record top title + score.
"""
import sys
import os
import base64
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import app

site_pwd = os.getenv("SITE_PASSWORD", "").strip()
headers = {}
if site_pwd:
    token = base64.b64encode(f"user:{site_pwd}".encode()).decode()
    headers["Authorization"] = f"Basic {token}"

client = TestClient(app, headers=headers)

landmark_queries = [
    ("Kesavananda Bharati", "Kesavananda"),
    ("Maneka Gandhi", "Maneka"),
    ("K.S. Puttaswamy", "Puttaswamy"),
    ("Vishaka", "Vishaka"),
    ("Navtej Singh Johar", "Navtej"),
    ("Minerva Mills", "Minerva"),
    ("Golaknath", "Golaknath"),
    ("S.R. Bommai", "Bommai"),
    ("Olga Tellis", "Olga"),
    ("Arnesh Kumar", "Arnesh"),
    ("D.K. Basu", "Basu"),
    ("Shreya Singhal", "Shreya")
]

print("=========================================================================================")
print(f"{'QUERY':<25} | {'TOP RESULT TITLE':<45} | {'SCORE':<6} | {'MATCH'}")
print("=========================================================================================")

for query, expected_sub in landmark_queries:
    resp = client.post("/api/v1/search", json={"query": query, "limit": 5, "enable_hyde": False})
    if resp.status_code == 200:
        data = resp.json()
        results = data.get("results", [])
        if results:
            top = results[0]
            title = top.get("title") or top.get("common_name") or ""
            score = top.get("relevance_score", 0.0)
            score_pct = f"{round(score * 100)}%"
            matched = "YES" if expected_sub.lower() in title.lower() or expected_sub.lower() in (top.get("common_name") or "").lower() else "NO"
            print(f"{query:<25} | {title[:45]:<45} | {score_pct:<6} | {matched}")
        else:
            print(f"{query:<25} | {'<NO RESULTS>':<45} | {'0%':<6} | NO")
    else:
        print(f"{query:<25} | {f'HTTP {resp.status_code}':<45} | {'-':<6} | ERROR")

print("=========================================================================================")
