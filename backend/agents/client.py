"""
Shared Azure OpenAI chat client factory for Agent Framework agents.
Uses DefaultAzureCredential for Azure-native authentication.

Supports separate model deployments for:
- Agents: AZURE_OPENAI_AGENT_DEPLOYMENT (default: gpt-5-nano)
- Orchestrator: AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT (default: gpt-5-mini)
"""

import os
import time
import threading
from typing import Literal, Optional

from azure.identity import DefaultAzureCredential, AzureCliCredential
from agent_framework.azure import AzureOpenAIChatClient
import structlog

logger = structlog.get_logger()

# TTL cache for client instances (replaces @lru_cache to allow credential refresh)
_CLIENT_TTL_SECONDS = 30 * 60  # 30 minutes
_client_cache: dict[str, tuple[AzureOpenAIChatClient, float]] = {}
_cache_lock = threading.Lock()

# Configuration from environment
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")

# Separate deployments for agents vs orchestrator
AZURE_OPENAI_AGENT_DEPLOYMENT = os.getenv("AZURE_OPENAI_AGENT_DEPLOYMENT", "gpt-5-nano")
AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT = os.getenv("AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT", "gpt-5-mini")
COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"


def get_credential():
    """Get Azure credential for authentication."""
    try:
        credential = DefaultAzureCredential()
        logger.info("azure_credential_initialized", method="DefaultAzureCredential")
        return credential
    except Exception as e:
        logger.warning("default_credential_failed", error=str(e), fallback="AzureCliCredential")
        try:
            credential = AzureCliCredential()
            logger.info("azure_credential_initialized", method="AzureCliCredential")
            return credential
        except Exception as e2:
            logger.warning("cli_credential_failed", error=str(e2))
            return None


def get_chat_client(
    endpoint: Optional[str] = None,
    deployment: Optional[str] = None,
    api_version: Optional[str] = None,
    role: Literal["agent", "orchestrator"] = "agent",
) -> AzureOpenAIChatClient:
    """
    Factory for Azure OpenAI chat client.

    Args:
        endpoint: Azure OpenAI endpoint URL
        deployment: Model deployment name
        api_version: API version
        role: "agent" for individual agents, "orchestrator" for manager

    Returns:
        Configured AzureOpenAIChatClient instance
    """
    _endpoint = endpoint or AZURE_OPENAI_ENDPOINT
    if deployment:
        _deployment = deployment
    elif role == "orchestrator":
        _deployment = AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT
    else:
        _deployment = AZURE_OPENAI_AGENT_DEPLOYMENT
    _api_version = api_version or AZURE_OPENAI_API_VERSION

    if not _endpoint:
        raise ValueError(
            "Azure OpenAI endpoint not configured. "
            "Set AZURE_OPENAI_ENDPOINT environment variable."
        )

    credential = get_credential()

    if credential:
        # Use explicit Entra token flow to avoid API-key fallback on key-disabled resources.
        def _ad_token_provider() -> str:
            token = credential.get_token(COGNITIVE_SCOPE)
            return token.token

        saved_key = os.environ.pop("AZURE_OPENAI_API_KEY", None)
        try:
            client = AzureOpenAIChatClient(
                endpoint=_endpoint,
                deployment_name=_deployment,
                api_version=_api_version,
                ad_token_provider=_ad_token_provider,
                env_file_path="",  # Prevent .env-based key fallback.
            )
        finally:
            if saved_key is not None:
                os.environ["AZURE_OPENAI_API_KEY"] = saved_key
        logger.info("chat_client_created", endpoint=_endpoint, deployment=_deployment, auth="entra_token")
    elif AZURE_OPENAI_KEY:
        client = AzureOpenAIChatClient(
            endpoint=_endpoint,
            api_key=AZURE_OPENAI_KEY,
            deployment_name=_deployment,
            api_version=_api_version,
        )
        logger.info("chat_client_created", endpoint=_endpoint, deployment=_deployment, auth="api_key")
    else:
        raise ValueError(
            "No Azure authentication available. "
            "Set up DefaultAzureCredential or AZURE_OPENAI_API_KEY."
        )

    return client


def get_shared_chat_client() -> AzureOpenAIChatClient:
    """Get a cached shared chat client instance for agents (gpt-5-nano).

    Client is cached for _CLIENT_TTL_SECONDS (30 min). When the TTL expires,
    a new client is created with fresh credentials so Entra ID token expiration
    doesn't require a process restart.
    """
    return _get_cached_client("agent")


def get_orchestrator_chat_client() -> AzureOpenAIChatClient:
    """Get a cached chat client for orchestrator/manager agents (gpt-5-mini).

    Same TTL-based caching as get_shared_chat_client().
    """
    return _get_cached_client("orchestrator")


def _get_cached_client(role: Literal["agent", "orchestrator"]) -> AzureOpenAIChatClient:
    """Return a cached client, recreating it when the TTL has expired.

    Client creation (which probes Azure credential providers) happens outside
    the lock so slow credential initialisation doesn't block other threads.
    """
    now = time.monotonic()
    with _cache_lock:
        entry = _client_cache.get(role)
        if entry is not None:
            client, created_at = entry
            if now - created_at < _CLIENT_TTL_SECONDS:
                return client
            logger.info("client_cache_expired", role=role, age_seconds=round(now - created_at))

    # Create outside the lock — two threads may race here on expiry, but both
    # produce a valid client; the last writer wins which is harmless.
    client = get_chat_client(role=role)
    now = time.monotonic()
    with _cache_lock:
        _client_cache[role] = (client, now)
    return client


def clear_client_cache() -> None:
    """Force-clear cached clients so the next call creates fresh credentials.

    Useful when a 401 is detected and we want an immediate credential refresh
    without waiting for the TTL to expire.
    """
    with _cache_lock:
        _client_cache.clear()
    logger.info("client_cache_cleared")
