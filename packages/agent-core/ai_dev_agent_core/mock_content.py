"""Helpers shared by the mock executors (domain-free, content generation).

These are stand-ins for real requirement understanding / research that a
future LLM runtime would perform.
"""

from __future__ import annotations

import re

from ai_dev_shared import Task

# Phase 4.1: the real intent contract lives in `intents.py`. This module
# re-exports it so existing importers keep working; the legacy 4-way mock
# classifier below is only retained for the mock doc-subject demo content.
from .intents import classify_intent  # noqa: F401  (re-export)

_DOC_SUBJECT = {
    "auth": "NextAuth.js",
    "deploy": "Serverless deployment",
    "bug": "Next.js runtime errors",
    "feature": "React Server Components",
}


def _legacy_mock_intent(task: Task) -> str:
    """Very cheap stand-in for requirement understanding (mock demos only)."""
    text = f"{task.title} {task.description}".lower()
    if re.search(r"deploy|ci/cd|release|docker|pipeline|production", text):
        return "deploy"
    if re.search(r"auth|login|session|jwt|oauth|credential|password", text):
        return "auth"
    if re.search(r"bug|fix|error|crash|fail|regress|broken", text):
        return "bug"
    return "feature"


def doc_subject_for(task: Task) -> str:
    """Which documentation SCOUT pretends to read."""
    return _DOC_SUBJECT.get(_legacy_mock_intent(task), "React Server Components")


def repo_name_for(task: Task) -> str:
    return "nextjs-app"