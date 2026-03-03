"""
Aviation agent tools — module exports for retriever wiring.
"""

import asyncio
from typing import Any, Coroutine, Dict, List, Tuple
import structlog

_rq_logger = structlog.get_logger()


async def retriever_query(
    coro: Coroutine[Any, Any, Tuple[List, List]], timeout: int = 50
) -> Tuple[List, List]:
    """Wrap a retriever coroutine with a hard timeout. Returns ([], []) on failure."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except (TimeoutError, asyncio.TimeoutError) as e:
        _rq_logger.warning("retriever_query_timeout", error=str(e), timeout=timeout)
        return [], []
    except Exception as e:
        _rq_logger.warning("retriever_query_error", error=str(e))
        return [], []


async def retriever_query_multi(
    coro: Coroutine[Any, Any, Dict[str, Tuple[List, List]]], timeout: int = 60
) -> Dict[str, Tuple[List, List]]:
    """Wrap a retriever query_multiple coroutine with a hard timeout. Returns {} on failure."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except (TimeoutError, asyncio.TimeoutError) as e:
        _rq_logger.warning("retriever_query_multi_timeout", error=str(e), timeout=timeout)
        return {}
    except Exception as e:
        _rq_logger.warning("retriever_query_multi_error", error=str(e))
        return {}


from agents.tools import (
    crew_tools,
    diversion_tools,
    fatigue_tools,
    fleet_tools,
    flight_tools,
    maintenance_tools,
    monitor_tools,
    network_tools,
    operations_tools,
    passenger_tools,
    regulatory_tools,
    route_tools,
    safety_tools,
    situation_tools,
    weather_safety_tools,
)

# All modules that support set_retriever()
RETRIEVER_MODULES = [
    crew_tools,
    diversion_tools,
    fatigue_tools,
    fleet_tools,
    flight_tools,
    maintenance_tools,
    monitor_tools,
    network_tools,
    operations_tools,
    passenger_tools,
    regulatory_tools,
    route_tools,
    safety_tools,
    situation_tools,
    weather_safety_tools,
]
