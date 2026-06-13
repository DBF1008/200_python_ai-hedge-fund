"""
API Key pre-execution validator.

Validates that all required API keys (LLM provider keys and financial data keys)
are available before starting a hedge fund run or backtest. Returns structured
information about any missing keys so the frontend can display actionable errors.
"""

import os
from dataclasses import dataclass, field
from typing import Optional

from src.llm.models import ModelProvider
from src.utils.analysts import ANALYST_CONFIG
from app.backend.services.graph import extract_base_agent_key


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maps each ModelProvider to the API key env-var name(s) it requires.
# - A single string means exactly one key is needed.
# - A list means *any one* of the listed keys suffices (e.g. KIMI).
# - None means no API key is required (local / self-hosted providers).
PROVIDER_KEY_MAP: dict[ModelProvider, Optional[str | list[str]]] = {
    ModelProvider.OPENAI: "OPENAI_API_KEY",
    ModelProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
    ModelProvider.GROQ: "GROQ_API_KEY",
    ModelProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
    ModelProvider.GOOGLE: "GOOGLE_API_KEY",
    ModelProvider.OLLAMA: None,  # local, no key
    ModelProvider.OPENROUTER: "OPENROUTER_API_KEY",
    ModelProvider.KIMI: ["MOONSHOT_API_KEY", "KIMI_API_KEY"],
    ModelProvider.XAI: "XAI_API_KEY",
    ModelProvider.GIGACHAT: "GIGACHAT_API_KEY",
    ModelProvider.AZURE_OPENAI: "AZURE_OPENAI_API_KEY",
    # ALIBABA / META / MISTRAL models are typically served through Ollama
    # locally. If they are used with a cloud endpoint in the future, extend
    # this map with the appropriate key names.
    ModelProvider.ALIBABA: None,
    ModelProvider.META: None,
    ModelProvider.MISTRAL: None,
}

# Analyst keys whose agents are purely algorithmic and never call the LLM.
AGENTS_NOT_USING_LLM: set[str] = {
    "technical_analyst",
    "fundamentals_analyst",
    "growth_analyst",
    "sentiment_analyst",
    "valuation_analyst",
}

# The single financial-data key required by every agent that fetches market data.
FINANCIAL_DATA_KEY = "FINANCIAL_DATASETS_API_KEY"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MissingKeyInfo:
    """Describes a single missing API key."""
    key_name: str            # e.g. "ANTHROPIC_API_KEY"
    provider: str            # e.g. "Anthropic"
    required_by: list[str] = field(default_factory=list)  # display names of agents
    reason: str = ""         # human-readable explanation


@dataclass
class ApiKeyValidationResult:
    """Result of the pre-execution API key validation."""
    is_valid: bool
    missing_keys: list[MissingKeyInfo] = field(default_factory=list)
    used_key_names: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _display_name_for_agent(base_key: str) -> str:
    """Return a human-readable display name for an agent base key."""
    config = ANALYST_CONFIG.get(base_key)
    if config:
        return config["display_name"]
    # Well-known non-analyst agents
    if base_key == "portfolio_manager":
        return "Portfolio Manager"
    if base_key == "risk_management":
        return "Risk Manager"
    return base_key


def _is_key_available(key_name: str, available_keys: dict[str, str] | None) -> bool:
    """Check whether *key_name* is present in the supplied dict or in env vars."""
    if available_keys and available_keys.get(key_name):
        return True
    if os.environ.get(key_name):
        return True
    return False


def _resolve_provider_key(
    provider: ModelProvider,
    available_keys: dict[str, str] | None,
) -> tuple[Optional[str], bool]:
    """
    Determine the API key name for *provider* and whether it is available.

    Returns ``(key_name_or_first, is_available)``.  When the provider maps to
    a **list** of acceptable key names, the *first* name is returned as the
    canonical label and availability is ``True`` if **any** of the alternatives
    is found.  Returns ``(None, True)`` for providers that need no key.
    """
    key_spec = PROVIDER_KEY_MAP.get(provider)

    # No key required (Ollama, local models, etc.)
    if key_spec is None:
        return None, True

    # Single key
    if isinstance(key_spec, str):
        return key_spec, _is_key_available(key_spec, available_keys)

    # List of alternative keys – any one suffices
    for alt_key in key_spec:
        if _is_key_available(alt_key, available_keys):
            # Return the specific key that was actually found
            return alt_key, True
    # None found – return the first as the canonical label
    return key_spec[0], False


# ---------------------------------------------------------------------------
# Main validation entry point
# ---------------------------------------------------------------------------

def validate_api_keys(
    request,
    available_keys: dict[str, str] | None = None,
) -> ApiKeyValidationResult:
    """
    Validate that all API keys required for execution are available.

    Parameters
    ----------
    request :
        The incoming ``HedgeFundRequest`` or ``BacktestRequest`` (anything
        that inherits from ``BaseHedgeFundRequest``).
    available_keys :
        A ``{provider_name: key_value}`` dict.  Typically this is the hydrated
        ``request.api_keys`` dict.

    Returns
    -------
    ApiKeyValidationResult
        ``is_valid=True`` when every required key is present.  Otherwise
        ``missing_keys`` contains one entry per missing key with human-readable
        context.
    """
    # provider_key -> set of agent display names that depend on it
    provider_deps: dict[str, tuple[str, set[str]]] = {}
    # Keys we confirmed are available (for last_used tracking)
    used_key_names: set[str] = set()

    # ------------------------------------------------------------------
    # 1. Collect LLM providers required by agents in the graph
    # ------------------------------------------------------------------
    agent_ids = [node.id for node in request.graph_nodes]

    for agent_id in agent_ids:
        base_key = extract_base_agent_key(agent_id)

        # Skip non-LLM agents
        if base_key in AGENTS_NOT_USING_LLM:
            continue
        # portfolio_manager is handled separately below (it may have
        # multiple instances with different suffixes)
        if base_key == "portfolio_manager":
            continue
        # risk_management never uses LLM
        if base_key == "risk_management":
            continue
        # Skip unknown agents not in config
        if base_key not in ANALYST_CONFIG:
            continue

        # Resolve the model provider for this agent
        _model_name, model_provider = request.get_agent_model_config(agent_id)

        # Skip custom models (model_name == "-")
        if _model_name == "-":
            continue

        # Ensure model_provider is the enum
        if isinstance(model_provider, str):
            try:
                model_provider = ModelProvider(model_provider)
            except ValueError:
                continue  # unknown provider, skip

        key_name, is_available = _resolve_provider_key(model_provider, available_keys)

        if key_name is None:
            # No key needed for this provider
            continue

        if is_available:
            used_key_names.add(key_name)
        else:
            # Record the dependency for later reporting
            display_name = _display_name_for_agent(base_key)
            if key_name in provider_deps:
                provider_deps[key_name][1].add(display_name)
            else:
                provider_deps[key_name] = (model_provider.value, {display_name})

    # ------------------------------------------------------------------
    # 2. Portfolio Manager – always present, always uses LLM
    # ------------------------------------------------------------------
    # Resolve using the portfolio_manager base key.  If there is a
    # per-agent override for portfolio_manager, get_agent_model_config
    # will pick it up.
    _pm_model_name, pm_provider = request.get_agent_model_config("portfolio_manager")
    if _pm_model_name != "-":
        if isinstance(pm_provider, str):
            try:
                pm_provider = ModelProvider(pm_provider)
            except ValueError:
                pm_provider = ModelProvider.OPENAI

        pm_key_name, pm_available = _resolve_provider_key(pm_provider, available_keys)
        if pm_key_name is not None:
            if pm_available:
                used_key_names.add(pm_key_name)
            else:
                pm_display = "Portfolio Manager"
                if pm_key_name in provider_deps:
                    provider_deps[pm_key_name][1].add(pm_display)
                else:
                    provider_deps[pm_key_name] = (pm_provider.value, {pm_display})

    # ------------------------------------------------------------------
    # 3. Financial data key – always required
    # ------------------------------------------------------------------
    if _is_key_available(FINANCIAL_DATA_KEY, available_keys):
        used_key_names.add(FINANCIAL_DATA_KEY)
    else:
        # All agents in the graph need financial data
        all_agent_displays: set[str] = set()
        for agent_id in agent_ids:
            base_key = extract_base_agent_key(agent_id)
            if base_key in ANALYST_CONFIG:
                all_agent_displays.add(_display_name_for_agent(base_key))
        all_agent_displays.add("Portfolio Manager")
        provider_deps[FINANCIAL_DATA_KEY] = (
            "Financial Datasets",
            all_agent_displays,
        )

    # ------------------------------------------------------------------
    # 4. Build result
    # ------------------------------------------------------------------
    missing_keys: list[MissingKeyInfo] = []
    for key_name, (provider_value, agent_displays) in provider_deps.items():
        sorted_agents = sorted(agent_displays)
        if key_name == FINANCIAL_DATA_KEY:
            reason = (
                f"Required for fetching financial market data "
                f"(used by: {', '.join(sorted_agents)})"
            )
        else:
            reason = (
                f"Required for LLM provider '{provider_value}' "
                f"(used by agents: {', '.join(sorted_agents)})"
            )
        missing_keys.append(MissingKeyInfo(
            key_name=key_name,
            provider=provider_value,
            required_by=sorted_agents,
            reason=reason,
        ))

    return ApiKeyValidationResult(
        is_valid=len(missing_keys) == 0,
        missing_keys=missing_keys,
        used_key_names=used_key_names,
    )
