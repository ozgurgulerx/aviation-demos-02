"""
Evidence collection middleware for Agent Framework agents.
"""

from typing import Any, Dict, List

import structlog

logger = structlog.get_logger()


class EvidenceCollector:
    """Collects and aggregates evidence from multiple agents."""

    def __init__(self):
        self.evidence: List[Dict[str, Any]] = []

    def add_evidence(self, ev: Dict[str, Any]):
        self.evidence.append(ev)

    def get_evidence(self) -> List[Dict[str, Any]]:
        return self.evidence.copy()

    def get_evidence_by_agent(self, agent_id: str) -> List[Dict[str, Any]]:
        return [ev for ev in self.evidence if ev.get("agent_id") == agent_id]

    def clear(self):
        self.evidence = []
