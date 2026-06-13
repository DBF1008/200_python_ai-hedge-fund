"""Unit tests for pre-execution API key validation (app/backend/services/api_key_validation.py)."""

import pytest

from app.backend.models.schemas import AgentModelConfig, GraphNode, HedgeFundRequest
from app.backend.services.api_key_validation import (
    FINANCIAL_DATASETS_API_KEY,
    collect_used_key_names,
    validate_request_api_keys,
)
from src.llm.models import ModelProvider

# Node IDs use a 6-char lowercase-alnum suffix so extract_base_agent_key strips it.
BUFFETT = "warren_buffett_abc123"
TECHNICAL = "technical_analyst_abc123"
PORTFOLIO_MANAGER = "portfolio_manager_abc123"

# Every provider/financial key the validator may consult. Cleared before each
# test so results never depend on the developer's real environment.
_ALL_KEY_ENV_VARS = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GROQ_API_KEY",
    "DEEPSEEK_API_KEY",
    "GOOGLE_API_KEY",
    "OPENROUTER_API_KEY",
    "XAI_API_KEY",
    "MOONSHOT_API_KEY",
    "KIMI_API_KEY",
    "GIGACHAT_API_KEY",
    "GIGACHAT_CREDENTIALS",
    "GIGACHAT_USER",
    "GIGACHAT_PASSWORD",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT_NAME",
    FINANCIAL_DATASETS_API_KEY,
]


@pytest.fixture(autouse=True)
def _clear_key_env(monkeypatch):
    """Make every test hermetic by removing all key-related env vars."""
    for name in _ALL_KEY_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _make_request(
    node_ids,
    *,
    tickers=None,
    api_keys=None,
    agent_models=None,
    model_provider=ModelProvider.OPENAI,
    model_name="gpt-4.1",
):
    return HedgeFundRequest(
        tickers=tickers if tickers is not None else ["AAPL"],
        graph_nodes=[GraphNode(id=node_id) for node_id in node_ids],
        graph_edges=[],
        agent_models=agent_models,
        model_name=model_name,
        model_provider=model_provider,
        api_keys=api_keys,
    )


def _by_provider(missing, provider):
    return next((m for m in missing if m.provider == provider), None)


def test_missing_openai_key_when_persona_agent_selected():
    request = _make_request([BUFFETT])
    missing = validate_request_api_keys(request)

    openai_missing = _by_provider(missing, "OpenAI")
    assert openai_missing is not None
    assert openai_missing.key_names == ["OPENAI_API_KEY"]
    assert "Warren Buffett" in openai_missing.required_by


def test_satisfied_via_api_keys_dict():
    request = _make_request([BUFFETT], api_keys={"OPENAI_API_KEY": "sk-test"})
    assert validate_request_api_keys(request) == []


def test_satisfied_via_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    request = _make_request([BUFFETT])
    assert validate_request_api_keys(request) == []


def test_deterministic_agent_needs_no_key():
    # A graph containing only a deterministic analyst (no LLM, no PM) is valid.
    request = _make_request([TECHNICAL])
    assert validate_request_api_keys(request) == []


def test_portfolio_manager_always_requires_key():
    request = _make_request([PORTFOLIO_MANAGER])
    missing = validate_request_api_keys(request)

    openai_missing = _by_provider(missing, "OpenAI")
    assert openai_missing is not None
    assert "Portfolio Manager" in openai_missing.required_by


def test_kimi_satisfied_by_either_alternate_key():
    agent_models = [
        AgentModelConfig(agent_id=BUFFETT, model_name="kimi-k2", model_provider=ModelProvider.KIMI)
    ]

    # Missing when neither Kimi key is present.
    missing = validate_request_api_keys(_make_request([BUFFETT], agent_models=agent_models))
    kimi_missing = _by_provider(missing, "Kimi")
    assert kimi_missing is not None
    assert set(kimi_missing.key_names) == {"MOONSHOT_API_KEY", "KIMI_API_KEY"}

    # Satisfied by KIMI_API_KEY alone.
    via_kimi = _make_request([BUFFETT], agent_models=agent_models, api_keys={"KIMI_API_KEY": "x"})
    assert validate_request_api_keys(via_kimi) == []

    # Satisfied by MOONSHOT_API_KEY alone.
    via_moonshot = _make_request(
        [BUFFETT], agent_models=agent_models, api_keys={"MOONSHOT_API_KEY": "x"}
    )
    assert validate_request_api_keys(via_moonshot) == []


def test_non_free_ticker_requires_financial_key():
    request = _make_request(
        [BUFFETT], tickers=["NFLX"], api_keys={"OPENAI_API_KEY": "sk-test"}
    )
    missing = validate_request_api_keys(request)

    financial_missing = _by_provider(missing, "Financial Data")
    assert financial_missing is not None
    assert financial_missing.key_names == [FINANCIAL_DATASETS_API_KEY]
    assert any("NFLX" in entry for entry in financial_missing.required_by)


def test_free_only_tickers_do_not_require_financial_key():
    request = _make_request(
        [BUFFETT], tickers=["AAPL", "MSFT"], api_keys={"OPENAI_API_KEY": "sk-test"}
    )
    assert _by_provider(validate_request_api_keys(request), "Financial Data") is None


def test_non_free_ticker_satisfied_by_financial_key_in_env(monkeypatch):
    monkeypatch.setenv(FINANCIAL_DATASETS_API_KEY, "fin-key")
    request = _make_request(
        [BUFFETT], tickers=["NFLX"], api_keys={"OPENAI_API_KEY": "sk-test"}
    )
    assert _by_provider(validate_request_api_keys(request), "Financial Data") is None


def test_collect_used_key_names_returns_only_request_supplied_names():
    request = _make_request(
        [BUFFETT],
        tickers=["NFLX"],
        api_keys={"OPENAI_API_KEY": "sk-test", FINANCIAL_DATASETS_API_KEY: "fin-key"},
    )
    assert collect_used_key_names(request) == {"OPENAI_API_KEY", FINANCIAL_DATASETS_API_KEY}


def test_collect_used_key_names_excludes_env_only_keys(monkeypatch):
    # Keys present only in the environment are not "used" for last_used purposes.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    request = _make_request([BUFFETT])
    assert collect_used_key_names(request) == set()
