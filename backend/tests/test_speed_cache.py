"""
Tests for TTLLRUCache and Speed & Performance (Item 15)
"""
import sys
import os
import base64
import time
from pathlib import Path
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.routers.search import TTLLRUCache, _SEARCH_CACHE, _ANSWER_CACHE
from fastapi.testclient import TestClient
from app.main import app

site_pwd = os.getenv("SITE_PASSWORD", "").strip()
headers = {}
if site_pwd:
    token = base64.b64encode(f"user:{site_pwd}".encode()).decode()
    headers["Authorization"] = f"Basic {token}"

client = TestClient(app, headers=headers)

def test_ttl_lru_cache_basic_ops():
    cache = TTLLRUCache(capacity=3, ttl_seconds=1.0)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    assert cache.get("a") == 1
    assert cache.get("b") == 2
    assert cache.get("c") == 3
    assert cache.get("d") is None

def test_ttl_lru_cache_capacity_eviction():
    cache = TTLLRUCache(capacity=3, ttl_seconds=10.0)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    
    # Access "a" so "b" becomes the oldest
    _ = cache.get("a")
    
    # Insert "d" -> "b" should be evicted
    cache.set("d", 4)
    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3
    assert cache.get("d") == 4

def test_ttl_lru_cache_expiry():
    cache = TTLLRUCache(capacity=3, ttl_seconds=0.05)
    cache.set("temp", 999)
    assert cache.get("temp") == 999
    time.sleep(0.06)
    assert cache.get("temp") is None

def test_search_cache_endpoint_integration():
    _SEARCH_CACHE.clear()
    _ANSWER_CACHE.clear()

    # Cold search
    start_t = time.perf_counter()
    resp1 = client.post("/api/v1/search", json={"query": "Article 21 privacy", "limit": 5, "enable_hyde": False})
    cold_time = time.perf_counter() - start_t
    assert resp1.status_code == 200

    # Warm search (served from cache in sub-millisecond)
    start_t2 = time.perf_counter()
    resp2 = client.post("/api/v1/search", json={"query": "Article 21 privacy", "limit": 5, "enable_hyde": False})
    warm_time = time.perf_counter() - start_t2
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json()
    assert warm_time < 0.05  # sub-50ms cache response
