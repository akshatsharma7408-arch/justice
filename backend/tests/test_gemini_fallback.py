import os
from types import SimpleNamespace as NS
import pytest
import app.services.groq_client as g


class Resp:
    def __init__(self, code, js=None, text=""):
        self.status_code, self._js, self.text = code, js or {}, text
    def json(self):
        return self._js


def _models(monkeypatch, groq_code, gemini_code=200, seen=None):
    def post(url, headers=None, json=None, timeout=None):
        if "groq" in url:
            return Resp(groq_code, {"choices": [{"message": {"content": "groq ok"}}]}, "limit")
        if seen is not None:
            seen.append((url, dict(headers)))
        return Resp(gemini_code, {"candidates": [{"content": {"parts": [{"text": "gemini ok"}]}}]}, "x")
    monkeypatch.setattr(g.httpx, "post", post)
    return g._Models("groqkey")


def _env(monkeypatch, **kw):
    for k in ["GEMINI_FALLBACK_ENABLED", "GEMINI_FALLBACK_API_KEY", "GEMINI_FALLBACK_MODEL", "GEMINI_FALLBACK_DAILY_CAP"]:
        monkeypatch.delenv(k, raising=False)
    for k, v in kw.items():
        monkeypatch.setenv(k, v)
    g._GEMINI_CALLS.update({"day": None, "n": 0})


FULL = dict(GEMINI_FALLBACK_ENABLED="1", GEMINI_FALLBACK_API_KEY="SECRETKEY", GEMINI_FALLBACK_MODEL="test-model", GEMINI_FALLBACK_DAILY_CAP="2")


def test_off_by_default_even_when_groq_down(monkeypatch):
    _env(monkeypatch)
    tok = g.ALLOW_EXTERNAL_FALLBACK.set(True)
    try:
        with pytest.raises(RuntimeError):
            _models(monkeypatch, 429).generate_content(contents="q", config=NS())
    finally:
        g.ALLOW_EXTERNAL_FALLBACK.reset(tok)


def test_not_used_for_documents_context(monkeypatch):
    _env(monkeypatch, **FULL)
    with pytest.raises(RuntimeError):
        _models(monkeypatch, 429).generate_content(contents="q", config=NS())


def test_used_when_groq_down_key_in_header_not_url(monkeypatch):
    _env(monkeypatch, **FULL)
    seen = []
    tok = g.ALLOW_EXTERNAL_FALLBACK.set(True)
    try:
        out = _models(monkeypatch, 429, seen=seen).generate_content(contents="q", config=NS(system_instruction="s", temperature=0.1, max_output_tokens=50))
    finally:
        g.ALLOW_EXTERNAL_FALLBACK.reset(tok)
    assert out.text == "gemini ok"
    url, headers = seen[0]
    assert "SECRETKEY" not in url and headers["x-goog-api-key"] == "SECRETKEY"


def test_daily_cap_and_non_transient_errors(monkeypatch):
    _env(monkeypatch, **FULL)
    tok = g.ALLOW_EXTERNAL_FALLBACK.set(True)
    try:
        m = _models(monkeypatch, 429)
        assert m.generate_content(contents="q", config=NS()).text == "gemini ok"
        assert m.generate_content(contents="q", config=NS()).text == "gemini ok"
        with pytest.raises(RuntimeError):
            m.generate_content(contents="q", config=NS())  # cap of 2 reached
        _env(monkeypatch, **FULL)
        with pytest.raises(RuntimeError):
            _models(monkeypatch, 400).generate_content(contents="q", config=NS())  # not transient
    finally:
        g.ALLOW_EXTERNAL_FALLBACK.reset(tok)


def test_error_text_never_contains_key(monkeypatch):
    _env(monkeypatch, **FULL)
    tok = g.ALLOW_EXTERNAL_FALLBACK.set(True)
    try:
        m = _models(monkeypatch, 429, gemini_code=500)
        with pytest.raises(RuntimeError) as ei:
            m.generate_content(contents="q", config=NS())
        assert "SECRETKEY" not in str(ei.value)
    finally:
        g.ALLOW_EXTERNAL_FALLBACK.reset(tok)


def test_flag_default_off_and_only_search_routes_enable_it():
    import pathlib, re
    assert g.ALLOW_EXTERNAL_FALLBACK.get() is False
    root = pathlib.Path(g.__file__).resolve().parents[1]
    users = sorted(str(p.relative_to(root)) for p in root.rglob("*.py")
                   if "ALLOW_EXTERNAL_FALLBACK" in p.read_text() or "_allow_question_only_fallback" in p.read_text())
    assert users == ["routers/search.py", "services/groq_client.py"], users
    src = (root / "routers" / "search.py").read_text()
    assert len(re.findall(r"^\s+_allow_question_only_fallback\(\)", src, re.M)) == 2


def test_only_one_module_talks_to_a_model_provider():
    import pathlib
    root = pathlib.Path(g.__file__).resolve().parents[1]
    hits = sorted(str(p.relative_to(root)) for p in root.rglob("*.py")
                  if "api.groq.com" in p.read_text() or "generativelanguage.googleapis" in p.read_text())
    assert hits == ["services/groq_client.py"], hits


def test_flag_does_not_leak_between_requests_or_into_other_routes():
    """A search request sets the flag; later requests (any route, same server) must still see it off."""
    import asyncio
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import app.routers.search as s
    probe = FastAPI()

    @probe.get("/search-like")
    async def search_like():
        s._allow_question_only_fallback()
        await asyncio.sleep(0.05)
        return {"flag": g.ALLOW_EXTERNAL_FALLBACK.get()}

    @probe.get("/doc-like")
    async def doc_like():
        await asyncio.sleep(0.01)
        return {"flag": g.ALLOW_EXTERNAL_FALLBACK.get()}

    @probe.get("/doc-like-thread")
    def doc_like_thread():
        return {"flag": g.ALLOW_EXTERNAL_FALLBACK.get()}

    c = TestClient(probe)
    assert c.get("/search-like").json() == {"flag": True}
    assert c.get("/doc-like").json() == {"flag": False}
    assert c.get("/doc-like-thread").json() == {"flag": False}

    async def both():
        async def a():
            s._allow_question_only_fallback(); await asyncio.sleep(0.05); return g.ALLOW_EXTERNAL_FALLBACK.get()
        async def b():
            await asyncio.sleep(0.02); return g.ALLOW_EXTERNAL_FALLBACK.get()
        return await asyncio.gather(asyncio.create_task(a()), asyncio.create_task(b()))
    assert asyncio.run(both()) == [True, False]  # concurrent requests do not see each other's flag
