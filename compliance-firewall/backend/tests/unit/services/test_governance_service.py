from sqlmodel import Session

from app.pipeline.firewall import FirewallContext
from app.services import governance_service


def test_build_when_tokens_missing_reports_warnings_and_rules(
    db_session: Session, firewall_ctx: FirewallContext
) -> None:
    report = governance_service.build(db_session, firewall_ctx.ai, admin_token_set=False, api_token_set=False)

    assert report.rules["latest_version"] == 1
    assert report.ai["model"] == firewall_ctx.ai.model
    assert any("ADMIN_TOKEN is not set" in c for c in report.security_controls)
    assert any("API_TOKEN is not set" in c for c in report.security_controls)
