"""Pydantic models shared across phases.

Only `Turn`/`Thread` exist yet — `Trace`, `GoldenItem`, `JudgeScore` belong to later phases
(BUILD_SPEC.md §7, §9) and are added when those phases land, not stubbed ahead of need.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Turn(BaseModel):
    role: Literal["customer", "agent"]
    text: str
    created_at: datetime
    tweet_id: str


class Thread(BaseModel):
    thread_id: str
    brand: str
    turns: list[Turn]
    n_turns: int
    n_branches: int
    first_customer_msg: str
    first_agent_reply: str | None
    last_customer_msg: str
    created_at_root: datetime
