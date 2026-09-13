"""Terminal labeller for bad_to_autosend, blind to which system produced the draft.
docs/ANNOTATION_GUIDE.md §3.

Same style as labeler.py: keyboard-driven, one item per screen, autosaves after every item
(appends + flushes, resumable via Ctrl+C). The queue file carries a `system` field for later
re-association by calibrate.py/evaluate.py/report.py, but this tool never displays it -- the
whole point of blind labelling is that recognizing the system can't bias the label.

Runs alone: `python -m cordon.bad_to_autosend_labeler --help`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from config import GOLDEN_DIR

console = Console()


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path) as f:
        return [json.loads(line) for line in f]


def label_item(item: dict, index: int, total: int) -> dict:
    console.clear()
    console.print(Panel(f"[{index}/{total}]", title="bad_to_autosend -- blind to system"))
    console.print(f"\n[bold cyan]Customer message:[/bold cyan] {item['customer_message']}")
    console.print(f"\n[bold]Evidence:[/bold] {item['evidence'] or '(none given to this system)'}")
    console.print(f"\n[bold green]Draft that was auto-sent:[/bold green] {item['draft']}")
    console.print(
        "\n[dim]Bad to autosend if: factually unsupported, unsafe, requests PII in public, "
        "promises something not promised, or answers a message that needed a human "
        "(docs/ANNOTATION_GUIDE.md §3).[/dim]"
    )
    bad = Confirm.ask("Was sending this publicly a mistake?")
    return {"item_id": item["item_id"], "system": item["system"], "bad_to_autosend": bad}


def main() -> None:
    parser = argparse.ArgumentParser(description="Label bad_to_autosend, one item per screen")
    parser.add_argument("--queue", default=str(GOLDEN_DIR / "bad_to_autosend_queue.jsonl"))
    parser.add_argument("--out", default=str(GOLDEN_DIR / "bad_to_autosend_v1.jsonl"))
    args = parser.parse_args()

    items = load_jsonl(Path(args.queue))
    if not items:
        raise FileNotFoundError(f"{args.queue} not found or empty. Run "
                                 "`python -m cordon.bad_to_autosend_sampler` first.")
    already = {(r["item_id"], r["system"]) for r in load_jsonl(Path(args.out))}
    remaining = [i for i in items if (i["item_id"], i["system"]) not in already]

    console.print(f"{len(already)} already labelled, {len(remaining)} remaining.")
    total = len(items)
    try:
        for i, item in enumerate(remaining, 1):
            record = label_item(item, len(already) + i, total)
            with open(args.out, "a") as f:
                f.write(json.dumps(record) + "\n")
                f.flush()
            console.print(f"[green]Saved {record['item_id']}.[/green]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped. Progress is saved -- rerun to resume.[/yellow]")


if __name__ == "__main__":
    main()
