"""Terminal golden-set labeller. BUILD_SPEC.md §9.1, docs/ANNOTATION_GUIDE.md §2.

Keyboard-driven, one item per screen, autosaves after every item (appends to
data/golden/golden_v1.jsonl and flushes -- safe to Ctrl+C anytime, resumes on restart by
skipping already-labelled item_ids). Structurally enforces the hindsight rule (docs/
ANNOTATION_GUIDE.md §5): the brand's actual reply stays hidden until every judgement field is
captured, so seeing it can't bias the labels.

Runs alone: `python -m cordon.labeler --help`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from config import GOLDEN_DIR, TAXONOMY_DIR

console = Console()

SEVERITY = {"l": "low", "m": "med", "h": "high"}


def load_intents() -> list[str]:
    data = yaml.safe_load((TAXONOMY_DIR / "intents.yaml").read_text())
    return [i["id"] for i in data["intents"]]


def load_jsonl(path) -> list[dict]:
    if not path.exists():
        return []
    with open(path) as f:
        return [json.loads(line) for line in f]


SKIP = object()  # sentinel: fast-path this item as other/hard_case (docs/ANNOTATION_GUIDE.md §4.6)


def menu_select(intents: list[str], label: str, allow_none: bool, allow_skip: bool = False):
    console.print(f"\n[bold]{label}[/bold]")
    for i, name in enumerate(intents, 1):
        console.print(f"  {i}. {name}")
    hints = []
    if allow_none:
        hints.append("Enter for none")
    if allow_skip:
        hints.append("'skip' to fast-path as other/hard_case")
    hint = f" ({', '.join(hints)})" if hints else ""
    while True:
        raw = Prompt.ask(f"Choice [1-{len(intents)}]{hint}", default="" if allow_none else None).strip()
        if allow_skip and raw.lower() == "skip":
            return SKIP
        if allow_none and raw == "":
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(intents):
            return intents[int(raw) - 1]
        console.print("[red]Invalid choice.[/red]")


def ask_choice(prompt: str, mapping: dict[str, str]) -> str:
    keys = "/".join(mapping)
    while True:
        raw = Prompt.ask(f"{prompt} ({keys})").strip().lower()
        if raw in mapping:
            return mapping[raw]
        console.print("[red]Invalid choice.[/red]")


def ask_text(prompt: str, max_words: int | None = None, max_chars: int | None = None) -> str:
    text = Prompt.ask(prompt).strip()
    if max_words and len(text.split()) > max_words:
        console.print(f"[yellow]({len(text.split())} words, guide says <= {max_words} -- kept anyway)[/yellow]")
    if max_chars and len(text) > max_chars:
        console.print(f"[yellow]({len(text)} chars, guide says <= {max_chars} -- kept anyway)[/yellow]")
    return text


def label_item(item: dict, intents: list[str], index: int, total: int) -> dict:
    console.clear()
    console.print(Panel(f"[{index}/{total}] stratum={item['stratum']}"
                         f"{' [red](synthetic)[/red]' if item.get('synthetic') else ''}",
                         title="Golden set labeller"))
    console.print(f"\n[bold cyan]Customer message:[/bold cyan] {item['customer_message']}")

    record: dict = {
        "item_id": item["item_id"], "thread_id": item["thread_id"], "stratum": item["stratum"],
    }

    intent = menu_select(intents, "Intent", allow_none=False, allow_skip=True)
    if intent is SKIP:
        record.update(intent="other", secondary_intent=None, needs_account_access=False,
                      severity="low", anger=0, contains_pii=False, multi_intent=False,
                      should_escalate=False, escalate_reason=None, hard_case=True,
                      human_reference_reply=None, brand_reply_score=None)
        return _finalize(record, item)

    record["intent"] = intent
    record["secondary_intent"] = menu_select(intents, "Secondary intent", allow_none=True)
    record["multi_intent"] = record["secondary_intent"] is not None
    record["needs_account_access"] = Confirm.ask("Needs account access?")
    record["severity"] = ask_choice("Severity", SEVERITY)
    record["anger"] = int(ask_choice("Anger", {"0": "0", "1": "1", "2": "2"}))
    record["contains_pii"] = Confirm.ask("Contains PII?")
    record["should_escalate"] = Confirm.ask("Should escalate?")
    record["escalate_reason"] = (ask_text("Escalate reason (<=15 words)", max_words=15)
                                  if record["should_escalate"] else None)
    record["hard_case"] = False

    if item.get("needs_reference_reply"):
        record["human_reference_reply"] = ask_text(
            "Human reference reply -- what you'd actually send (<=280 chars, write BLIND)",
            max_chars=280)
    else:
        record["human_reference_reply"] = None

    console.print(f"\n[bold green]Brand's actual reply:[/bold green] "
                  f"{item['brand_reply'] or '(none -- synthetic item)'}")

    record["brand_reply_score"] = (
        int(ask_choice("Brand reply quality (1=worst..5=best)", {str(n): str(n) for n in range(1, 6)}))
        if item.get("needs_reference_reply") else None
    )
    return _finalize(record, item)


def _finalize(record: dict, item: dict) -> dict:
    record["customer_message"] = item["customer_message"]
    record["brand_reply"] = item["brand_reply"]
    record["synthetic"] = item.get("synthetic", False)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Label the golden set, one item per screen")
    parser.add_argument("--sampled", default=str(GOLDEN_DIR / "sampled_items.jsonl"))
    parser.add_argument("--out", default=str(GOLDEN_DIR / "golden_v1.jsonl"))
    args = parser.parse_args()

    items = load_jsonl(Path(args.sampled))
    already = {r["item_id"] for r in load_jsonl(Path(args.out))}
    remaining = [i for i in items if i["item_id"] not in already]
    intents = load_intents()

    console.print(f"{len(already)} already labelled, {len(remaining)} remaining.")
    total = len(items)
    try:
        for i, item in enumerate(remaining, 1):
            record = label_item(item, intents, len(already) + i, total)
            with open(args.out, "a") as f:
                f.write(json.dumps(record) + "\n")
                f.flush()
            console.print(f"[green]Saved {record['item_id']}.[/green]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped. Progress is saved -- rerun to resume.[/yellow]")


if __name__ == "__main__":
    main()
