"""Pre-execution validation of API key availability for web run/backtest.

Before a hedge-fund run or backtest is started, this module checks that every
API key required by the selected models (global + per-agent overrides) and by
financial-data access is actually available. Key availability mirrors
``src/llm/models.py:get_model`` exactly: a key counts as present if it is in the
request's injected ``api_keys`` dict OR in ``os.environ`` (env-only keys ignore
the dict). This avoids false positives that would block runs whose keys are
configured purely via environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, Optional

from pydantic import BaseModel

from src.llm.models import ModelProvider
from src.utils.analysts import ANALYST_CONFIG
from app.backend.services.graph import extract_base_agent_key

# Tickers for which financial data is available without an API key.
# Source: docker/README.md (free tickers documented for the data provider).
FREE_TICKERS = frozenset({"AAPL", "GOOGL", "MSFT", "NVDA", "TSLA"})

FINANCIAL_DATASETS_API_KEY = "FINANCIAL_DATASETS_API_KEY"

# portfolio_manager is not part of ANALYST_CONFIG but always calls the LLM.
PORTFOLIO_MANAGER_KEY = "portfolio_manager"
PORTFOLIO_MANAGER_DISPLAY = "Portfolio Manager"


@dataclass(frozen=True)
class KeyRequirement:
    """A single requirement: at least one of ``any_of`` must be present.

    When ``env_only`` is True the injected request ``api_keys`` dict is ignored
    and only ``os.environ`` is consulted (mirrors providers like Azure OpenAI
    whose ``get_model`` branch reads exclusively from the environment).
    """

    any_of: tuple[str, ...]
    env_only: bool = False


# Provider -> requirement groups. Mirrors src/llm/models.py:get_model (the
# resolution order and key names there are the source of truth). Providers with
# no usable get_model branch (Alibaba, Meta, Mistral) are intentionally absent;
# they have no selectable models and get_model would raise "Unsupported".
PROVIDER_KEY_REQUIREMENTS: dict[ModelProvider, tuple[KeyRequirement, ...]] = {
    ModelProvider.OPENAI: (KeyRequirement(("OPENAI_API_KEY",)),),
    ModelProvider.ANTHROPIC: (KeyRequirement(("ANTHROPIC_API_KEY",)),),
    ModelProvider.GROQ: (KeyRequirement(("GROQ_API_KEY",)),),
    ModelProvider.DEEPSEEK: (KeyRequirement(("DEEPSEEK_API_KEY",)),),
    ModelProvider.GOOGLE: (KeyRequirement(("GOOGLE_API_KEY",)),),
    ModelProvider.OPENROUTER: (KeyRequirement(("OPENROUTER_API_KEY",)),),
    ModelProvider.XAI: (KeyRequirement(("XAI_API_KEY",)),),
    ModelProvider.KIMI: (KeyRequirement(("MOONSHOT_API_KEY", "KIMI_API_KEY")),),
    ModelProvider.GIGACHAT: (
        KeyRequirement(
            ("GIGACHAT_API_KEY", "GIGACHAT_CREDENTIALS", "GIGACHAT_USER", "GIGACHAT_PASSWORD")
        ),
    ),
    ModelProvider.AZURE_OPENAI: (
        KeyRequirement(("AZURE_OPENAI_API_KEY",), env_only=True),
        KeyRequirement(("AZURE_OPENAI_ENDPOINT",), env_only=True),
        KeyRequirement(("AZURE_OPENAI_DEPLOYMENT_NAME",), env_only=True),
    ),
    # Ollama needs no API key (local base URL) -> no requirement entry.
}


class MissingApiKey(BaseModel):
    """A required-but-absent key requirement, surfaced to the frontend."""

    provider: str
    key_names: list[str]
    required_by: list[str]


def _is_present(requirement: KeyRequirement, api_keys: Optional[dict]) -> bool:
    """True if any key in the requirement is available (api_keys dict ∪ env)."""
    keys = api_keys or {}
    for name in requirement.any_of:
        if not requirement.env_only and keys.get(name):
            return True
        if os.environ.get(name):
            return True
    return False


def _coerce_provider(provider) -> Optional[ModelProvider]:
    """Normalize a provider (enum, enum value, or name) to ModelProvider."""
    if provider is None:
        return None
    if isinstance(provider, ModelProvider):
        return provider
    text = getattr(provider, "value", provider)
    try:
        return ModelProvider(text)
    except ValueError:
        pass
    try:
        return ModelProvider[str(text).upper()]
    except KeyError:
        return None


def _agent_uses_llm(base_key: str) -> tuple[bool, str]:
    """Return (uses_llm, display_name) for a base agent key."""
    if base_key == PORTFOLIO_MANAGER_KEY:
        return True, PORTFOLIO_MANAGER_DISPLAY
    config = ANALYST_CONFIG.get(base_key)
    if not config:
        return False, base_key
    return bool(config.get("uses_llm", True)), config.get("display_name", base_key)


def _collect_required_providers(request) -> dict[ModelProvider, list[str]]:
    """Map each required provider to the display names of the agents needing it."""
    required: dict[ModelProvider, list[str]] = {}
    for node in request.graph_nodes:
        base_key = extract_base_agent_key(node.id)
        uses_llm, display = _agent_uses_llm(base_key)
        if not uses_llm:
            continue
        _, provider = request.get_agent_model_config(node.id)
        provider_enum = _coerce_provider(provider)
        if provider_enum is None:
            continue
        agents = required.setdefault(provider_enum, [])
        if display not in agents:
            agents.append(display)
    return required


def _non_free_tickers(tickers: Iterable[str]) -> list[str]:
    """Return the subset of tickers that require a financial-data API key."""
    return [t for t in tickers if t and t.strip().upper() not in FREE_TICKERS]


def validate_request_api_keys(request) -> list[MissingApiKey]:
    """Validate that all keys required to start the run/backtest are present.

    Returns a list of missing requirements (empty means the run may proceed).
    """
    api_keys = request.api_keys
    missing: list[MissingApiKey] = []

    for provider, required_by in _collect_required_providers(request).items():
        for requirement in PROVIDER_KEY_REQUIREMENTS.get(provider, ()):  # noqa: B007
            if not _is_present(requirement, api_keys):
                missing.append(
                    MissingApiKey(
                        provider=provider.value,
                        key_names=list(requirement.any_of),
                        required_by=sorted(required_by),
                    )
                )

    non_free = _non_free_tickers(request.tickers)
    if non_free:
        financial_requirement = KeyRequirement((FINANCIAL_DATASETS_API_KEY,))
        if not _is_present(financial_requirement, api_keys):
            missing.append(
                MissingApiKey(
                    provider="Financial Data",
                    key_names=[FINANCIAL_DATASETS_API_KEY],
                    required_by=[f"Tickers without free data: {', '.join(non_free)}"],
                )
            )

    return missing


def collect_used_key_names(request) -> set[str]:
    """Names of request-supplied keys actually used by this run.

    Only keys present in ``request.api_keys`` are returned (env-only keys are
    excluded) because ``last_used`` is meaningful only for keys stored in the
    database / injected via the request.
    """
    api_keys = request.api_keys or {}
    used: set[str] = set()

    for provider in _collect_required_providers(request):
        for requirement in PROVIDER_KEY_REQUIREMENTS.get(provider, ()):
            if requirement.env_only:
                continue
            for name in requirement.any_of:
                if api_keys.get(name):
                    used.add(name)

    if _non_free_tickers(request.tickers) and api_keys.get(FINANCIAL_DATASETS_API_KEY):
        used.add(FINANCIAL_DATASETS_API_KEY)

    return used
