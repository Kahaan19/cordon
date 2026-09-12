"""The one place any model gets called from. Two backends (Gemini generator, Ollama judge, in
llm_backends.py) behind one `complete()` signature, a committed sqlite cache keyed on the exact
call, and the `CORDON_OFFLINE` guard that makes `make reproduce` free and deterministic.

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

from config import GEN_MODEL, JUDGE_MODEL, LLM_CACHE_PATH  # noqa: F401 (re-exported for callers)
from cordon.llm_backends import select_provider

load_dotenv()
console = Console()

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    """Prompts live as readable markdown in src/cordon/prompts/, never inlined (CLAUDE.md style)."""
    return (PROMPTS_DIR / f"{name}.md").read_text()


# DECISION: a minimal, opt-in call log for ops metrics (§9.3: cache hit-rate, tokens/ticket) --
# a module-level accumulator here is far less invasive than threading a log parameter through
# every classify/draft/claim_check call site in agent.py and verify.py. reset_call_log() before
# processing one item, get_call_log() after, to see exactly the calls that one item made.
_CALL_LOG: list[dict] = []


def reset_call_log() -> None:
    _CALL_LOG.clear()


def get_call_log() -> list[dict]:
    return list(_CALL_LOG)


def _log_call(model: str, result: "LLMResult") -> None:
    _CALL_LOG.append({"model": model, "cache_hit": result.cache_hit,
                       "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
                       "cost_usd": result.cost_usd})


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
                result = LLMResult(**hit, latency_ms=(time.perf_counter() - start) * 1000,
                                    cache_hit=True)
                _log_call(model, result)
                return result

        if os.environ.get("CORDON_OFFLINE") == "1":
            raise CacheMiss(
                f"CORDON_OFFLINE=1 and no cached entry for key={key[:12]}... "
                f"(model={model}). Refusing to call a live API."
            )

        backend = select_provider(model, provider)
        text, parsed, input_tokens, output_tokens = backend.generate(
            prompt, system, temperature, max_tokens, schema, model
        )
        cost_usd = 0.0  # DECISION: both backends are free tier / local by construction
        # (CLAUDE.md rule 2) — cost accounting exists for the ops table, and the honest number
        # for this pipeline is $0.00, not an estimated paid-tier rate never actually charged.

        if cache:
            _cache_put(conn, key, model, text, parsed, input_tokens, output_tokens, cost_usd)

        result = LLMResult(text=text, parsed=parsed, input_tokens=input_tokens,
                            output_tokens=output_tokens, cost_usd=cost_usd,
                            latency_ms=(time.perf_counter() - start) * 1000, cache_hit=False)
        _log_call(model, result)
        return result
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
