"""
Azure OpenAI client helpers for data source layer.
Async-adapted from demos-01 azure_openai_client.py.
Uses AsyncAzureOpenAI for non-blocking LLM calls in query writers.
"""

from __future__ import annotations

import asyncio
import os
import logging
from typing import Dict, Optional, Tuple

from azure.identity import AzureCliCredential, DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncAzureOpenAI

logger = logging.getLogger(__name__)

AZURE_OPENAI_SCOPE = "https://cognitiveservices.azure.com/.default"

def _resolve_aoai_tenant_id() -> str:
    """Resolve the AOAI tenant from explicit config first, with runtime fallback."""
    aoai_tenant = os.getenv("AZURE_OPENAI_TENANT_ID", "").strip()
    if aoai_tenant:
        return aoai_tenant

    fallback_tenant = os.getenv("EXPECTED_RUNTIME_TENANT_ID", "").strip()
    if fallback_tenant:
        logger.warning(
            "azure_openai_tenant_fallback_used source=EXPECTED_RUNTIME_TENANT_ID tenant_id=%s",
            fallback_tenant,
        )
        return fallback_tenant

    return ""


def client_tuning_kwargs() -> Dict[str, float | int]:
    try:
        timeout_seconds = float(os.getenv("AZURE_OPENAI_TIMEOUT_SECONDS", "45"))
    except Exception:
        timeout_seconds = 45.0
    try:
        max_retries = max(0, int(os.getenv("AZURE_OPENAI_MAX_RETRIES", "1")))
    except Exception:
        max_retries = 1
    return {"timeout": timeout_seconds, "max_retries": max_retries}


def _auth_mode() -> str:
    return (os.getenv("AZURE_OPENAI_AUTH_MODE", "auto") or "auto").strip().lower()


def _build_credential():
    aoai_tenant = _resolve_aoai_tenant_id()
    managed_identity_client_id = os.getenv("AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID", "").strip() or None

    if aoai_tenant:
        logger.info("azure_openai_tenant_from_env", tenant_id=aoai_tenant)
        try:
            cli_credential = AzureCliCredential(tenant_id=aoai_tenant)
            cli_credential.get_token(AZURE_OPENAI_SCOPE)
            logger.info("Using AzureCliCredential with tenant_id=%s", aoai_tenant)
            return cli_credential
        except Exception as exc:
            logger.warning(
                "AzureCliCredential unavailable, falling back to DefaultAzureCredential. "
                "tenant_id=%s error=%s",
                aoai_tenant,
                exc,
            )

    kwargs: Dict[str, str] = {}
    if managed_identity_client_id:
        kwargs["managed_identity_client_id"] = managed_identity_client_id
    return DefaultAzureCredential(**kwargs)


def _token_client(endpoint: str, api_version: str, credential=None) -> AsyncAzureOpenAI:
    cred = credential or _build_credential()
    token_provider = get_bearer_token_provider(cred, AZURE_OPENAI_SCOPE)
    return AsyncAzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token_provider=token_provider,
        api_version=api_version,
        **client_tuning_kwargs(),
    )


def _api_key_client(endpoint: str, api_version: str, api_key: str) -> AsyncAzureOpenAI:
    return AsyncAzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
        **client_tuning_kwargs(),
    )


def init_async_openai_client(
    *,
    endpoint: Optional[str] = None,
    api_version: Optional[str] = None,
) -> Tuple[AsyncAzureOpenAI, str]:
    """Build an async Azure OpenAI client with auth-mode aware behavior."""
    resolved_endpoint = (endpoint or os.getenv("AZURE_OPENAI_ENDPOINT", "")).strip()
    if not resolved_endpoint:
        raise ValueError("Missing AZURE_OPENAI_ENDPOINT")
    resolved_api_version = (api_version or os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")).strip() or "2024-06-01"
    api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    mode = _auth_mode()

    if mode == "api-key":
        if not api_key:
            raise ValueError("AZURE_OPENAI_AUTH_MODE=api-key requires AZURE_OPENAI_API_KEY")
        return _api_key_client(resolved_endpoint, resolved_api_version, api_key), "api-key"

    credential = _build_credential()
    if mode == "token":
        return _token_client(resolved_endpoint, resolved_api_version, credential), "token"

    # auto mode
    try:
        credential.get_token(AZURE_OPENAI_SCOPE)
        return _token_client(resolved_endpoint, resolved_api_version, credential), "token"
    except Exception:
        if api_key:
            return _api_key_client(resolved_endpoint, resolved_api_version, api_key), "api-key"
        return _token_client(resolved_endpoint, resolved_api_version, credential), "token"


# Singleton
_shared_client: Optional[AsyncAzureOpenAI] = None
_shared_auth_mode: str = ""
_shared_lock = asyncio.Lock()


async def get_shared_async_client(
    *,
    api_version: Optional[str] = None,
) -> Tuple[AsyncAzureOpenAI, str]:
    """Process-wide shared AsyncAzureOpenAI client."""
    global _shared_client, _shared_auth_mode

    if _shared_client is not None:
        return _shared_client, _shared_auth_mode

    async with _shared_lock:
        if _shared_client is not None:
            return _shared_client, _shared_auth_mode

        client, auth_mode = init_async_openai_client(api_version=api_version)
        _shared_client = client
        _shared_auth_mode = auth_mode
        logger.info("Shared AsyncAzureOpenAI client initialized (auth=%s)", auth_mode)
        return _shared_client, _shared_auth_mode
