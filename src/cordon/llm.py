"""The one place any model gets called from. Two backends (Gemini generator, Ollama judge)
behind one `complete()` signature, a committed sqlite cache keyed on the exact call, and the
`CORDON_OFFLINE` guard that makes `make reproduce` free and deterministic.

Contract: BUILD_SPEC.md §11.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel
from rich.console import Console

from config import GEN_MODEL, JUDGE_MODEL, LLM_CACHE_PATH, OLLAMA_HOST_DEFAULT

load_dotenv()
console = Console()


PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    """Prompts live as readable markdown in src/cordon/prompts/, never inlined (CLAUDE.md style)."""
    return (PROMPTS_DIR / f"{name}.md").read_text()


class CacheMiss(Exception):
    """Raised instead of calling any API when CORDON_OFFLINE=1 and the exact call isn't cached."""


class LLMResult(BaseModel):
    text: str
    parsed: dict | None = None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    cache_hit: bool


def _cache_key(model: str, system: str, prompt: str, temperature: float, max_tokens: int,
               schema: dict | None) -> str:
    canonical = "|".join([
        model, system, prompt, repr(temperature), repr(max_tokens),
        json.dumps(schema, sort_keys=True) if schema else "",
    ])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _init_cache(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS llm_cache ("
        " key TEXT PRIMARY KEY, model TEXT, text TEXT, parsed TEXT,"
        " input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL, created_at TEXT)"
    )
    conn.commit()
    return conn


def _cache_get(conn: sqlite3.Connection, key: str) -> dict | None:
    row = conn.execute(
        "SELECT text, parsed, input_tokens, output_tokens, cost_usd FROM llm_cache WHERE key = ?",
        (key,),
    ).fetchone()
    if row is None:
        return None
    text, parsed, input_tokens, output_tokens, cost_usd = row
    return {
        "text": text,
        "parsed": json.loads(parsed) if parsed else None,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
    }


def _cache_put(conn: sqlite3.Connection, key: str, model: str, text: str, parsed: dict | None,
               input_tokens: int, output_tokens: int, cost_usd: float) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO llm_cache VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        (key, model, text, json.dumps(parsed) if parsed is not None else None,
         input_tokens, output_tokens, cost_usd),
    )
    conn.commit()


class GeminiBackend:
    """Free-tier Gemini. 429s are expected (BUILD_SPEC.md §2, CLAUDE.md rule 3a) — retry with
    exponential backoff rather than surfacing them as pipeline failures. 503s (transient
    server-side overload, observed in practice on gemini-flash-latest) get the same treatment:
    both are "the server is busy," neither is a pipeline bug."""

    MAX_RETRIES = 10
    RETRYABLE_MARKERS = ("429", "503", "UNAVAILABLE", "RESOURCE_EXHAUSTED")

    def generate(self, prompt: str, system: str, temperature: float, max_tokens: int,
                 schema: dict | None, model: str) -> tuple[str, dict | None, int, int]:
        # DECISION: google-generativeai is dead ("all support has ended", per its own
        # deprecation warning) and its auth path no longer works reliably against the current
        # API — migrated to google-genai. See docs/DECISION_LOG.md.
        from google import genai
        from google.genai import types

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set — required for a live Gemini call")
        client = genai.Client(api_key=api_key)

        config = types.GenerateContentConfig(temperature=temperature, max_output_tokens=max_tokens,
                                              system_instruction=system or None)
        if schema is not None:
            config.response_mime_type = "application/json"
            config.response_schema = schema

        for attempt in range(self.MAX_RETRIES):
            try:
                response = client.models.generate_content(model=model, contents=prompt, config=config)
                break
            except Exception as exc:  # DECISION: broad catch is deliberate here — the google
                # SDK raises different exception types across versions for the same transient
                # condition, and every one of them must retry, never surface as a pipeline
                # failure (rule 3a).
                retryable = any(marker in str(exc) for marker in self.RETRYABLE_MARKERS)
                if not retryable or attempt == self.MAX_RETRIES - 1:
                    raise
                wait = min(2 ** attempt, 60)
                console.log(f"[yellow]Gemini transient error, retry {attempt + 1}/"
                            f"{self.MAX_RETRIES} in {wait}s[/yellow]")
                time.sleep(wait)

        text = response.text
        parsed = json.loads(text) if schema is not None else None
        usage = response.usage_metadata
        input_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0
        return text, parsed, input_tokens, output_tokens


class OllamaBackend:
    """Local judge, no key, no rate limit. Requires `ollama pull qwen3:8b` once (SETUP.md)."""

    def generate(self, prompt: str, system: str, temperature: float, max_tokens: int,
                 schema: dict | None, model: str) -> tuple[str, dict | None, int, int]:
        import ollama

        client = ollama.Client(host=os.environ.get("OLLAMA_HOST", OLLAMA_HOST_DEFAULT))
        messages = [{"role": "system", "content": system}] if system else []
        messages.append({"role": "user", "content": prompt})
        response = client.chat(
            model=model,
            messages=messages,
            format=schema if schema is not None else None,
            options={"temperature": temperature, "num_predict": max_tokens},
        )
        text = response["message"]["content"]
        parsed = json.loads(text) if schema is not None else None
        input_tokens = response.get("prompt_eval_count", 0) or 0
        output_tokens = response.get("eval_count", 0) or 0
        return text, parsed, input_tokens, output_tokens


def _select_provider(model: str, provider: str | None):
    if provider == "gemini" or (provider is None and model.startswith("gemini")):
        return GeminiBackend()
    if provider == "ollama" or (provider is None and model == JUDGE_MODEL):
        return OllamaBackend()
    raise ValueError(f"Cannot infer provider for model={model!r}; pass provider= explicitly")


def complete(prompt: str, *, system: str = "", model: str = GEN_MODEL, temperature: float = 0.0,
             max_tokens: int = 1024, schema: dict | None = None, cache: bool = True,
             provider: str | None = None) -> LLMResult:
    start = time.perf_counter()
    key = _cache_key(model, system, prompt, temperature, max_tokens, schema)
    conn = _init_cache(LLM_CACHE_PATH)
    try:
        if cache:
            hit = _cache_get(conn, key)
            if hit is not None:
                return LLMResult(**hit, latency_ms=(time.perf_counter() - start) * 1000,
                                  cache_hit=True)

        if os.environ.get("CORDON_OFFLINE") == "1":
            raise CacheMiss(
                f"CORDON_OFFLINE=1 and no cached entry for key={key[:12]}... "
                f"(model={model}). Refusing to call a live API."
            )

        backend = _select_provider(model, provider)
        text, parsed, input_tokens, output_tokens = backend.generate(
            prompt, system, temperature, max_tokens, schema, model
        )
        cost_usd = 0.0  # DECISION: both backends are free tier / local by construction
        # (CLAUDE.md rule 2) — cost accounting exists for the ops table, and the honest number
        # for this pipeline is $0.00, not an estimated paid-tier rate never actually charged.

        if cache:
            _cache_put(conn, key, model, text, parsed, input_tokens, output_tokens, cost_usd)

        return LLMResult(text=text, parsed=parsed, input_tokens=input_tokens,
                          output_tokens=output_tokens, cost_usd=cost_usd,
                          latency_ms=(time.perf_counter() - start) * 1000, cache_hit=False)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Cached LLM client smoke test")
    parser.add_argument("--prompt", default="Say hello in five words.")
    parser.add_argument("--model", default=GEN_MODEL)
    parser.add_argument("--provider", default=None, choices=["gemini", "ollama"])
    args = parser.parse_args()

    result = complete(args.prompt, model=args.model, provider=args.provider)
    console.print(f"text={result.text!r}")
    console.print(f"cache_hit={result.cache_hit} cost_usd={result.cost_usd} "
                  f"latency_ms={result.latency_ms:.1f} "
                  f"tokens_in={result.input_tokens} tokens_out={result.output_tokens}")


if __name__ == "__main__":
    main()
