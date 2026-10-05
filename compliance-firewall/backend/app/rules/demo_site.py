"""Rewrite the static demo site's prices, discounts and policy wording from the latest rules.

The backend does this on every rules save when DEMO_SITE_DIR is set, and then pushes the pages to
the GitHub Pages repository when DEMO_SITE_REPO is set. To do the same by hand, from `backend/`:

    python -m app.rules.demo_site

Only existing cards are updated in place. A plan, discount or policy that has no matching block in
the HTML is reported, never invented. Publishing uses the GitHub CLI (`gh`) and its saved login.
"""

import base64
import hashlib
import html
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from sqlmodel import Session

from app.core.config import get_settings
from app.core.db import make_engine
from app.pipeline.normalize import Money
from app.rules import repository
from app.schemas.rules import Rules

DEMO_SITE = Path(__file__).resolve().parents[3] / "demo-site"
PRICING_PAGE = Path("pricing/index.html")
POLICIES_PAGE = Path("help/policies/index.html")


def _display(price: Money) -> str:
    """Site style: "Rs 4,999" and "$49"."""
    number = price.label().split(" ", 1)[1]
    return f"${number}" if price.currency == "USD" else f"Rs {number}" if price.currency == "PKR" else price.label()


def _replace(page: str, pattern: str, parts: tuple[str, ...], missing: str, warnings: list[str]) -> str:
    """Swap the text between the pattern's groups for `parts`; note `missing` if nothing matches."""
    def swap(match: re.Match[str]) -> str:
        groups = match.groups()
        return "".join(g + html.escape(p, quote=False) for g, p in zip(groups, parts)) + groups[-1]

    page, count = re.subn(pattern, swap, page, count=1)
    if not count:
        warnings.append(missing)
    return page


def render_pricing(page: str, rules: Rules, warnings: list[str]) -> str:
    for rule in rules.prices:
        name = re.escape(html.escape(rule.product, quote=False))
        page = _replace(
            page,
            rf'(<h2>{name}</h2>\s*<p class="price">)[^<]*(</p>)',
            (_display(rule.official()),), f"pricing page has no card for plan {rule.product!r}", warnings,
        )
    for discount in rules.discounts:
        name = re.escape(html.escape(discount.name, quote=False))
        page = _replace(
            page, rf"(<strong>{name} discount:</strong> save )[\d.]+(%)",
            (f"{discount.percent.normalize():f}",),
            f"pricing page has no notice for discount {discount.name!r}", warnings,
        )
    return page


def render_policies(page: str, rules: Rules, warnings: list[str]) -> str:
    for policy in rules.policies:
        page = _replace(
            page, rf'(<h2 id="{re.escape(policy.id)}">)[^<]*(</h2>\s*<p>)[^<]*(</p>)',
            (policy.title, policy.text), f"policies page has no section for policy {policy.id!r}", warnings,
        )
    return page


def sync(site: Path, rules: Rules) -> tuple[list[Path], list[str]]:
    """Rewrite the pages under `site`. Returns (files changed, warnings)."""
    changed: list[Path] = []
    warnings: list[str] = []
    for relative, render in ((PRICING_PAGE, render_pricing), (POLICIES_PAGE, render_policies)):
        path = site / relative
        before = path.read_bytes().decode("utf-8")  # bytes: keep the file's line endings
        after = render(before, rules, warnings)
        if after != before:
            path.write_bytes(after.encode("utf-8"))
            changed.append(relative)
    return changed, warnings


def _gh_api(args: list[str], body: str | None = None) -> str:
    done = subprocess.run(["gh", "api", *args], input=body, capture_output=True, text=True,
                          encoding="utf-8", timeout=30)
    if done.returncode:
        raise RuntimeError(f"gh api {args[-1]}: {done.stderr.strip() or done.stdout.strip()}")
    return done.stdout.strip()


def publish(site: Path, repo: str, message: str, gh_api: Callable[..., str] = _gh_api) -> list[Path]:
    """Push each page that differs from `repo` ("owner/name", served by GitHub Pages).

    Compares with what is live, so a publish that failed earlier is retried by the next one.
    Returns the files pushed. Raises RuntimeError / OSError if `gh` fails or is not installed.
    """
    pushed: list[Path] = []
    for relative in (PRICING_PAGE, POLICIES_PAGE):
        data = (site / relative).read_bytes().replace(b"\r\n", b"\n")  # the repo stores LF
        endpoint = f"repos/{repo}/contents/{relative.as_posix()}"
        live_sha = gh_api([endpoint, "--jq", ".sha"])
        if live_sha == hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest():  # git blob id
            continue
        body = {"message": message, "content": base64.b64encode(data).decode(), "sha": live_sha}
        gh_api(["-X", "PUT", "--input", "-", endpoint], json.dumps(body))
        pushed.append(relative)
    return pushed


def main() -> None:
    settings = get_settings()
    site = Path(settings.demo_site_dir) if settings.demo_site_dir else DEMO_SITE
    with Session(make_engine(settings.database_url)) as session:
        row = repository.get_latest(session)
    if row is None:
        sys.exit("no rules have been saved")
    changed, warnings = sync(site, Rules.model_validate(row.body))
    print(f"rules v{row.version} -> {site}")
    for path in changed:
        print(f"  updated {path.as_posix()}")
    if not changed:
        print("  already up to date")
    for warning in warnings:
        print(f"  WARNING: {warning}")
    if settings.demo_site_repo:
        pushed = publish(site, settings.demo_site_repo, f"Sync demo site to rules v{row.version}")
        print(f"published to {settings.demo_site_repo}: "
              + (", ".join(p.as_posix() for p in pushed) or "already live"))


if __name__ == "__main__":
    main()
