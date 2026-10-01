"""Runs the 50 labelled answers through the firewall and scores the result."""

import json
from pathlib import Path

from sqlmodel import Session

from app.pipeline import firewall
from app.pipeline.firewall import FirewallContext
from app.schemas.api import SuiteItem, SuiteReport, SuiteRow

DEFAULT_SUITE_PATH = Path(__file__).resolve().parents[2] / "data" / "test_answers.json"


def load_items(path: Path = DEFAULT_SUITE_PATH) -> list[SuiteItem]:
    return [SuiteItem.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]


def _rate(part: int, whole: int, empty: float) -> float:
    return round(part / whole, 4) if whole else empty


async def run_suite(session: Session, ctx: FirewallContext, items: list[SuiteItem]) -> SuiteReport:
    rows: list[SuiteRow] = []
    ai_calls = 0
    version: int | None = None
    for item in items:
        decision = await firewall.run(item.question, item.answer, session, ctx, source="suite")
        ai_calls += decision.ai_calls
        version = decision.rule_version if decision.rule_version is not None else version
        shown = decision.status == "Approved"  # Rejected and Error both count as blocked
        reasons = [r.reason for r in decision.results if not r.ok and not r.skipped]
        if decision.error:
            reasons.append(decision.error)
        rows.append(SuiteRow(
            id=item.id, category=item.category, label=item.label, decision=decision.status,
            shown_raw_answer=shown, correct=shown == (item.label == "approve"),
            reasons=reasons, ai_used=decision.ai_used, audit_id=decision.audit_id,
        ))

    rejects = [r for r in rows if r.label == "reject"]
    approves = [r for r in rows if r.label == "approve"]
    leaked = sum(r.shown_raw_answer for r in rejects)
    return SuiteReport(
        total=len(rows),
        leaked=leaked,
        caught_rate=_rate(len(rejects) - leaked, len(rejects), 1.0),
        false_block_rate=_rate(sum(not r.shown_raw_answer for r in approves), len(approves), 0.0),
        ai_calls=ai_calls,
        rule_version=version,
        rows=rows,
    )
