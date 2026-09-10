"""CSV -> reconstructed threads. BUILD_SPEC.md §3.

Runs alone: `python -m cordon.ingest --help`.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
from rich.console import Console

from config import INTERIM_DIR, MIN_THREADS_FOR_BRAND, RAW_CSV_PATH
from cordon.schemas import Thread, Turn

console = Console()

LEADING_MENTION_RE = re.compile(r"^(?:@\w+\s+)+")
MENTION_RE = re.compile(r"(?<!\w)@\w+")
URL_RE = re.compile(r"https?://\S+")
EMAIL_RE = re.compile(r"(?<!\w)[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")
ORDER_ID_RE = re.compile(r"\b\d{6,}\b|\b[A-Z0-9]{2,}-[A-Z0-9]{4,}\b")
DM_LINK_RE = re.compile(r"twitter\.com/messages")

MAX_WALK = 50  # defensive cap against malformed cyclic response_tweet_id data


def clean_text(text: str) -> tuple[str, dict]:
    """Normalise a raw tweet body. Strips the leading @mention (brand or customer handle,
    whichever opens the tweet — both are label leakage), masks URLs, keeps emoji and casing.
    """
    normalized = unicodedata.normalize("NFKC", html.unescape(text))
    flags = {
        "had_url": bool(URL_RE.search(normalized)),
        "has_order_id_like": bool(ORDER_ID_RE.search(normalized)),
        "has_email": bool(EMAIL_RE.search(normalized)),
        "has_phone": bool(PHONE_RE.search(normalized)),
        "has_dm_link": bool(DM_LINK_RE.search(normalized)),
    }
    stripped = LEADING_MENTION_RE.sub("", normalized, count=1)
    masked = URL_RE.sub("<url>", stripped)
    cleaned = MENTION_RE.sub("@user", masked)
    return cleaned, flags


def load_raw(path: Path, chunksize: int = 200_000, limit: int | None = None) -> dict[str, tuple]:
    """Stream the CSV in chunks and build tweet_id -> (author_id, inbound, created_at, text,
    children, in_response_to). Chunked to bound peak memory (BUILD_SPEC.md §3 step 1)."""
    cols = ["tweet_id", "author_id", "inbound", "created_at", "text",
            "response_tweet_id", "in_response_to_tweet_id"]
    rows: dict[str, tuple] = {}
    for chunk in pd.read_csv(path, usecols=cols, dtype=str, chunksize=chunksize):
        chunk["created_at"] = pd.to_datetime(
            chunk["created_at"], format="%a %b %d %H:%M:%S %z %Y", errors="coerce"
        )
        for row in chunk.itertuples(index=False):
            children = row.response_tweet_id.split(",") if pd.notna(row.response_tweet_id) else []
            in_response_to = row.in_response_to_tweet_id if pd.notna(row.in_response_to_tweet_id) else None
            rows[row.tweet_id] = (
                row.author_id, row.inbound == "True", row.created_at, row.text,
                children, in_response_to,
            )
            if limit and len(rows) >= limit:
                return rows
    return rows


def reconstruct_threads(rows: dict[str, tuple]) -> tuple[list[Thread], dict]:
    """Walk forward from each inbound root, following the earliest child on a branch.
    BUILD_SPEC.md §3 steps 2-6."""
    dropped_stats = defaultdict(int)
    threads: list[Thread] = []

    for tid, (_, inbound, _, _, _, in_response_to) in rows.items():
        if not inbound:
            continue
        if in_response_to is not None and in_response_to in rows:
            continue  # not a root: its parent is present in this data

        turns: list[Turn] = []
        n_branches = 0
        cur = tid
        for _ in range(MAX_WALK):
            author_id, cur_inbound, created_at, text, children, _ = rows[cur]
            if pd.isna(created_at):
                break
            cleaned, _ = clean_text(text)
            turns.append(Turn(role="customer" if cur_inbound else "agent", text=cleaned,
                               created_at=created_at.to_pydatetime(), tweet_id=cur))

            valid_children = [c for c in children if c in rows]
            if not valid_children:
                break
            if len(valid_children) > 1:
                n_branches += 1
            cur = min(valid_children, key=lambda c: rows[c][2])

        agent_turns = [t for t in turns if t.role == "agent"]
        if not agent_turns:
            dropped_stats["no_agent_turn"] += 1
            continue

        brand = next(rows[t.tweet_id][0] for t in turns if t.role == "agent")
        customer_turns = [t for t in turns if t.role == "customer"]
        threads.append(Thread(
            thread_id=tid, brand=brand, turns=turns, n_turns=len(turns), n_branches=n_branches,
            first_customer_msg=turns[0].text, first_agent_reply=agent_turns[0].text,
            last_customer_msg=customer_turns[-1].text, created_at_root=turns[0].created_at,
        ))

    return threads, dict(dropped_stats)


def write_threads_by_brand(threads: list[Thread], out_dir: Path,
                            min_threads: int = MIN_THREADS_FOR_BRAND) -> dict:
    by_brand: dict[str, list[Thread]] = defaultdict(list)
    for t in threads:
        by_brand[t.brand].append(t)

    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    skipped_small_brands = 0
    for brand, brand_threads in by_brand.items():
        if len(brand_threads) < min_threads:
            skipped_small_brands += 1
            continue
        path = out_dir / f"threads_{brand}.jsonl"
        with open(path, "w") as f:
            for t in brand_threads:
                f.write(t.model_dump_json() + "\n")
        written[brand] = len(brand_threads)

    return {"brands_written": written, "brands_skipped_below_min": skipped_small_brands}


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconstruct threads from the raw twcs.csv")
    parser.add_argument("--raw-path", type=Path, default=RAW_CSV_PATH)
    parser.add_argument("--out-dir", type=Path, default=INTERIM_DIR)
    parser.add_argument("--min-threads", type=int, default=MIN_THREADS_FOR_BRAND)
    parser.add_argument("--limit", type=int, default=None, help="cap rows read, for a quick run")
    args = parser.parse_args()

    if not args.raw_path.exists():
        raise FileNotFoundError(
            f"{args.raw_path} not found. Download twcs.csv per SETUP.md §5 "
            "(Kaggle: thoughtvector/customer-support-on-twitter) before running ingest."
        )

    console.log(f"Loading {args.raw_path} ...")
    rows = load_raw(args.raw_path, limit=args.limit)
    console.log(f"Loaded {len(rows)} tweets. Reconstructing threads ...")
    threads, dropped_stats = reconstruct_threads(rows)
    console.log(f"Reconstructed {len(threads)} threads. dropped_stats={dropped_stats}")

    write_stats = write_threads_by_brand(threads, args.out_dir, args.min_threads)
    console.log(f"Wrote {len(write_stats['brands_written'])} brand files to {args.out_dir}")

    stats_path = args.out_dir / "ingest_stats.json"
    with open(stats_path, "w") as f:
        json.dump({"dropped_stats": dropped_stats, **write_stats}, f, indent=2)
    console.log(f"Stats written to {stats_path}")


if __name__ == "__main__":
    main()
