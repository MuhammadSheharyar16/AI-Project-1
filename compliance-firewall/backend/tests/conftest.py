"""Shared fixtures: temp SQLite per test, FakeLLM injected via deps, and a TestClient."""

import asyncio
import json
import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.governance import AIBudget, AIGateway, AIPolicy
from app.ai.prompts import CLAIM_END, CLAIM_START, EXTRACT_TASK, POLICIES_MARKER, PROMPT_VERSION
from app.api.deps import get_llm
from app.core.config import Settings
from app.main import create_app
from app.rules.seed import SEED_RULES
from app.schemas.rules import Rules


TEST_MODEL = "test-model"


def make_settings(**overrides: Any) -> Settings:
    """Settings for tests: explicit values, never the real `.env`."""
    values: dict[str, Any] = {
        "groq_api_key": "test-key",
        "groq_model": TEST_MODEL,
        "database_url": "sqlite:///:memory:",
    }
    return Settings(_env_file=None, **(values | overrides))


def parse_prompt(prompt: str) -> tuple[list[dict[str, Any]], str]:
    policies_part = prompt.split(POLICIES_MARKER, 1)[1].split(CLAIM_START, 1)[0]
    claim = prompt.split(CLAIM_START, 1)[1].split(CLAIM_END, 1)[0].strip()
    return json.loads(policies_part), claim


class FakeLLM:
    """Judges by topic keywords and quotes a real sentence from the matching policy."""

    TOPICS = {
        "refund": ("refund", "money back"),
        "trial": ("trial",),
        "cancel": ("cancel",),
    }
    CONTRADICTION_CUES = ("no refund", "cannot", "can't", "never", "not available")

    def __init__(self) -> None:
        self.calls = 0

    async def llm_json(self, prompt: str, timeout: float) -> dict[str, Any]:
        self.calls += 1
        if prompt.startswith(EXTRACT_TASK):
            return {"facts": []}  # the pattern rules already found everything in test answers
        policies, claim = parse_prompt(prompt)
        lowered = claim.lower()
        for policy in policies:
            if not any(k in lowered for k in self.TOPICS.get(policy["id"], ())):
                continue
            if any(cue in lowered for cue in self.CONTRADICTION_CUES):
                return {"verdict": "contradicted", "policy_id": policy["id"], "quote": "",
                        "reason": f"conflicts with the {policy['title']}"}
            first_sentence = re.split(r"(?<=\.)\s+", policy["text"])[0]
            return {"verdict": "supported", "policy_id": policy["id"], "quote": first_sentence,
                    "reason": f"matches the {policy['title']}"}
        return {"verdict": "not_covered", "policy_id": None, "quote": "",
                "reason": "no policy covers this claim"}


class InventedQuoteLLM:
    """Says 'supported' but quotes text that does not exist in the policy."""

    def __init__(self) -> None:
        self.calls = 0

    async def llm_json(self, prompt: str, timeout: float) -> dict[str, Any]:
        self.calls += 1
        return {"verdict": "supported", "policy_id": "refund",
                "quote": "Refunds are available at any time, no matter what.",
                "reason": "looks fine"}


class SlowLLM:
    async def llm_json(self, prompt: str, timeout: float) -> dict[str, Any]:
        await asyncio.sleep(timeout + 5)
        return {}


class CrashingLLM:
    async def llm_json(self, prompt: str, timeout: float) -> dict[str, Any]:
        raise RuntimeError("provider exploded")


@pytest.fixture
def rules() -> Rules:
    return Rules.model_validate(SEED_RULES)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return make_settings(
        database_url=f"sqlite:///{tmp_path.as_posix()}/test.db",
        check_timeout_s=0.2,
        debug=True,
        cors_origins="*",
    )


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def app(settings: Settings, fake_llm: FakeLLM) -> FastAPI:
    application = create_app(settings)
    application.dependency_overrides[get_llm] = lambda: fake_llm
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def use_llm(app: FastAPI, llm: Any) -> None:
    app.dependency_overrides[get_llm] = lambda: llm


def gateway(llm: Any, timeout: float = 1.0, *, enabled: bool = True, per_minute: int = 1000) -> AIGateway:
    policy = AIPolicy(enabled=enabled, budget=AIBudget(per_minute), timeout_s=timeout,
                      model="test-model", prompt_version=PROMPT_VERSION)
    return AIGateway(llm, policy)
