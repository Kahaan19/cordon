"""Tests 4-5 from BUILD_SPEC.md §13."""
from __future__ import annotations

import pytest

from cordon import llm


def test_cache_hit_returns_identical_text_and_is_free(tmp_path, monkeypatch):
    cache_path = tmp_path / "cache.sqlite"
    monkeypatch.setattr(llm, "LLM_CACHE_PATH", cache_path)

    conn = llm._init_cache(cache_path)
    key = llm._cache_key("gemini-flash-latest", "", "hello", 0.0, 1024, None)
    llm._cache_put(conn, key, "gemini-flash-latest", "hi there", None, 5, 2, 0.0)
    conn.close()

    def boom(*_args, **_kwargs):
        raise AssertionError("backend must not be called on a cache hit")

    monkeypatch.setattr(llm.GeminiBackend, "generate", boom)

    result = llm.complete("hello", model="gemini-flash-latest")

    assert result.text == "hi there"
    assert result.cache_hit is True
    assert result.cost_usd == 0.0


def test_offline_cache_miss_raises_without_calling_a_backend(tmp_path, monkeypatch):
    cache_path = tmp_path / "cache.sqlite"
    monkeypatch.setattr(llm, "LLM_CACHE_PATH", cache_path)
    monkeypatch.setenv("CORDON_OFFLINE", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def boom(*_args, **_kwargs):
        raise AssertionError("offline cache miss must never reach a backend")

    monkeypatch.setattr(llm.GeminiBackend, "generate", boom)

    with pytest.raises(llm.CacheMiss):
        llm.complete("a prompt never cached before", model="gemini-flash-latest")
