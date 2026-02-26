"""
Async data source layer for aviation multi-agent system.
Adapted from demos-01 UnifiedRetriever — all sources async for FastAPI.
"""

from data_sources.unified_retriever import AsyncUnifiedRetriever, get_retriever
from data_sources.shared_utils import Citation

__all__ = [
    "AsyncUnifiedRetriever",
    "get_retriever",
    "Citation",
]
