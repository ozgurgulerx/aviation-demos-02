"""
Shared test fixtures for Aviation Multi-Agent Solver tests.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


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
