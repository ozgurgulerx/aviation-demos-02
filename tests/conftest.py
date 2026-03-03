"""
Shared test fixtures for Aviation Multi-Agent Solver tests.
"""

import pytest
from unittest.mock import AsyncMock


@pytest.fixture
def mock_event_bus():
    """Mock EventBus for tests that don't need Redis."""
    bus = AsyncMock()
    bus.publish = AsyncMock()
    bus.subscribe = AsyncMock(return_value=AsyncMock())
    bus.get_events = AsyncMock(return_value=[])
    return bus


@pytest.fixture
def mock_run_store():
    """Mock RunStore for tests that don't need PostgreSQL."""
    store = AsyncMock()
    store.create_run = AsyncMock()
    store.get_run = AsyncMock(return_value=None)
    store.update_run_status = AsyncMock()
    store.list_runs = AsyncMock(return_value=[])
    return store


@pytest.fixture
def sample_problem():
    """Sample aviation problem for testing."""
    return "Flight AA1234 diverted to ORD due to severe weather at DFW. 200 passengers need rebooking."


@pytest.fixture
def mock_event_callback():
    """Mock event callback for orchestrator tests."""
    return AsyncMock()


class _FakeCitation:
    def __init__(self, source="mock_source", text="mock citation"):
        self.source = source
        self.text = text


@pytest.fixture
def mock_retriever():
    """Mock retriever with all query methods returning ([], [Citation(...)])."""
    r = AsyncMock()
    cit = _FakeCitation()
    for method_name in [
        "query_sql", "query_graph", "query_kql",
        "query_nosql", "query_semantic", "query_fabric_sql",
        "query_multiple",
    ]:
        if method_name == "query_multiple":
            getattr(r, method_name).return_value = {}
        else:
            getattr(r, method_name).return_value = ([], [cit])
    return r


@pytest.fixture
def wire_retriever(mock_retriever):
    """Wire mock_retriever to all RETRIEVER_MODULES and clean up after."""
    from agents.tools import RETRIEVER_MODULES
    originals = {mod: getattr(mod, "_retriever", None) for mod in RETRIEVER_MODULES}
    for mod in RETRIEVER_MODULES:
        mod.set_retriever(mock_retriever)
    yield mock_retriever
    for mod, orig in originals.items():
        mod.set_retriever(orig)


@pytest.fixture
def _set_aoai_endpoint(monkeypatch):
    """Patch the module-level AZURE_OPENAI_ENDPOINT so agent factories don't fail."""
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://dummy.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "dummy-key-for-testing")
    monkeypatch.setenv("AZURE_OPENAI_AUTH_MODE", "api-key")
    monkeypatch.setattr("agents.client.AZURE_OPENAI_ENDPOINT", "https://dummy.openai.azure.com/")
    monkeypatch.setattr("agents.client.AZURE_OPENAI_KEY", "dummy-key-for-testing")
