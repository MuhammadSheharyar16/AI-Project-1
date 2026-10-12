import asyncio

from sqlmodel import Session

from app.pipeline.firewall import FirewallContext
from app.schemas.api import SuiteItem
from app.services.suite_service import load_items, run_suite


def test_load_items_when_default_path_returns_fifty_labelled_answers() -> None:
    items = load_items()

    assert len(items) == 50 and {item.label for item in items} == {"approve", "reject"}


def test_run_suite_when_one_clean_and_one_bad_answer_scores_both(
    db_session: Session, firewall_ctx: FirewallContext
) -> None:
    items = [
        SuiteItem(id="ok", question="q", answer="The Pro plan costs $49 per month.", label="approve", category="price"),
        SuiteItem(id="bad", question="q", answer="The Pro plan is $59 per month.", label="reject", category="price"),
    ]

    report = asyncio.run(run_suite(db_session, firewall_ctx, items))

    assert (report.total, report.leaked, report.caught_rate, report.false_block_rate) == (2, 0, 1.0, 0.0)
    assert [row.correct for row in report.rows] == [True, True]
    assert all(row.audit_id is not None for row in report.rows)
