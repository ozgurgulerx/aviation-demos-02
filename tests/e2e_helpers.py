"""
Shared helpers for end-to-end scenario tests.

Provides:
- SCENARIOS: canonical prompts + expected agent mappings for all 4 scenario cards
- EventCollector: async callback that records (event_type, payload) tuples
- Validation helpers for agent activations, event ordering, etc.

Validators are written for the LLM-directed orchestration mode where the
coordinator is the start agent in a HandoffBuilder star topology and
dynamically delegates to specialists via tool-based handoff calls.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


# ═══════════════════════════════════════════════════════════════════════════
# Scenario definitions — mirror frontend/components/av/scenario-cards.tsx
# ═══════════════════════════════════════════════════════════════════════════

SCENARIOS: Dict[str, Dict[str, Any]] = {
    "hub_disruption": {
        "prompt": (
            "Severe thunderstorm at Chicago O'Hare (ORD) has caused a ground stop. "
            "47 flights are delayed or cancelled, affecting approximately 6,800 passengers. "
            "12 aircraft are grounded, 3 runways closed. Develop a recovery plan to minimize "
            "total delay and passenger impact while maintaining crew legality and safety compliance."
        ),
        "expected_agents": [
            "situation_assessment", "fleet_recovery", "crew_recovery",
            "network_impact", "weather_safety", "passenger_impact",
        ],
        "expected_coordinator": "recovery_coordinator",
        "scenario_id": "hub_disruption",
    },
    "predictive_maintenance": {
        "prompt": (
            "The Boeing 737-800 fleet is showing a trending increase in MEL deferrals "
            "for JASC code 7200 (engine) items over the past 30 days. Three aircraft "
            "(N738AA, N739AA, N741AA) have repeat deferrals. Analyze the MEL trends, "
            "search for similar historical incidents, and recommend whether to escalate "
            "inspections or adjust dispatch procedures."
        ),
        "expected_agents": [
            "fleet_recovery", "maintenance_predictor", "regulatory_compliance",
            "network_impact",
        ],
        "expected_coordinator": "decision_coordinator",
        "scenario_id": "predictive_maintenance",
    },
    "diversion": {
        "prompt": (
            "Flight AA1847 (B737-800, N735AA) en route from JFK to ORD is encountering "
            "severe weather at the destination. Current position is 80nm east of Detroit (DTW). "
            "Fuel remaining is 90 minutes. ORD is reporting visibility below minimums with "
            "thunderstorms. Evaluate diversion alternates and recommend the best course of action."
        ),
        "expected_agents": [
            "situation_assessment", "weather_safety", "diversion_advisor",
            "route_planner", "real_time_monitor",
        ],
        "expected_coordinator": "decision_coordinator",
        "scenario_id": "diversion",
    },
    "crew_fatigue": {
        "prompt": (
            "The crew operating red-eye flights from LAX hub are showing elevated fatigue "
            "indicators. Captain J. Smith (crew ID CR-4421) has accumulated 11.5 hours of "
            "duty time with a red-eye departure at 23:45. Three first officers on the same "
            "rotation are approaching FAR 117 cumulative duty limits. Assess fatigue risk "
            "and recommend mitigation measures."
        ),
        "expected_agents": [
            "crew_recovery", "crew_fatigue_assessor", "regulatory_compliance",
            "situation_assessment",
        ],
        "expected_coordinator": "decision_coordinator",
        "scenario_id": "crew_fatigue",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# Event Collector
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class EventCollector:
    """Async callback that captures (event_type, payload) tuples for assertions."""

    events: List[Tuple[str, Dict[str, Any]]] = field(default_factory=list)

    async def __call__(self, event_type: str, payload: Dict[str, Any]):
        self.events.append((event_type, payload))

    # -- query helpers -------------------------------------------------------

    def get_events_by_type(self, event_type: str) -> List[Dict[str, Any]]:
        return [p for t, p in self.events if t == event_type]

    def has_event(self, event_type: str) -> bool:
        return any(t == event_type for t, _ in self.events)

    def get_activated_agent_ids(self) -> List[str]:
        return [
            p.get("agentId") or p.get("agent_id", "")
            for t, p in self.events
            if t == "agent.activated"
        ]

    def get_invoked_agent_ids(self) -> Set[str]:
        ids: Set[str] = set()
        for t, p in self.events:
            if t == "executor.invoked":
                eid = p.get("executor_id") or p.get("agentId") or p.get("agent_id") or ""
                if eid:
                    ids.add(eid)
        return ids

    def get_completed_agent_ids(self) -> Set[str]:
        ids: Set[str] = set()
        for t, p in self.events:
            if t in ("executor.completed", "agent.completed"):
                eid = (
                    p.get("executor_id")
                    or p.get("agentId")
                    or p.get("agent_id")
                    or ""
                )
                if eid:
                    ids.add(eid)
        return ids

    # -- diagnostics ---------------------------------------------------------

    def dump_timeline(self, max_lines: int = 200) -> str:
        lines: List[str] = []
        for i, (etype, payload) in enumerate(self.events):
            agent = (
                payload.get("agentId")
                or payload.get("agent_id")
                or payload.get("executor_id")
                or ""
            )
            msg = (
                payload.get("message")
                or payload.get("status")
                or payload.get("error")
                or payload.get("stage_name")
                or payload.get("currentStep")
                or ""
            )
            # Skip noisy streaming/progress events in timeline dumps
            if etype in ("agent.streaming", "agent.progress", "progress_update"):
                continue
            if isinstance(msg, str) and len(msg) > 80:
                msg = msg[:77] + "..."
            lines.append(f"[{i:03d}] {etype:<40s} agent={agent:<25s} {msg}")
            if len(lines) >= max_lines:
                lines.append(f"  ... ({len(self.events)} total events)")
                break
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Validation helpers
# ═══════════════════════════════════════════════════════════════════════════

def validate_scenario_detected(engine: Any, expected_scenario: str, collector: EventCollector):
    """Assert the engine detected the correct scenario."""
    assert engine.scenario == expected_scenario, (
        f"Expected scenario '{expected_scenario}', got '{engine.scenario}'\n"
        f"Timeline:\n{collector.dump_timeline()}"
    )


def validate_agent_activations(
    collector: EventCollector,
    expected_agents: List[str],
    expected_coordinator: str,
):
    """Assert coordinator + at least N-1 expected specialists were activated.

    In LLM-directed mode the coordinator always runs (it is the start agent)
    and gpt-5-mini selects which specialists to recruit.  The LLM may
    reasonably exclude one specialist, so we require at least len-1 matches.
    """
    activated = set(collector.get_activated_agent_ids())

    # Coordinator MUST always be activated
    assert expected_coordinator in activated, (
        f"Coordinator '{expected_coordinator}' was not activated\n"
        f"Activated: {sorted(activated)}\n"
        f"Timeline:\n{collector.dump_timeline()}"
    )

    # At least N-1 expected specialists must be activated
    seen_specialists = set(expected_agents) & activated
    min_required = max(1, len(expected_agents) - 1)
    assert len(seen_specialists) >= min_required, (
        f"Too few specialists activated: need >= {min_required}, "
        f"got {len(seen_specialists)} {sorted(seen_specialists)}\n"
        f"Missing: {sorted(set(expected_agents) - activated)}\n"
        f"Activated: {sorted(activated)}\n"
        f"Timeline:\n{collector.dump_timeline()}"
    )

    # Warn if any were excluded
    missing = set(expected_agents) - activated
    if missing:
        warnings.warn(
            f"LLM excluded {sorted(missing)} from selection "
            f"(this is acceptable — LLM-directed mode allows selective recruitment)",
            stacklevel=2,
        )


def validate_specialists_invoked(
    collector: EventCollector,
    expected_agents: List[str],
):
    """Assert at least one specialist was invoked via coordinator handoff.

    In LLM-directed mode the coordinator delegates to specialists through
    handoff tool calls. The LLM may skip some specialists it deems
    irrelevant, so we require at least one to have been invoked or completed.
    """
    invoked = collector.get_invoked_agent_ids()
    completed = collector.get_completed_agent_ids()
    all_seen = invoked | completed

    seen_specialists = all_seen & set(expected_agents)
    assert seen_specialists, (
        f"No specialists were invoked at all\n"
        f"Expected at least one of: {sorted(expected_agents)}\n"
        f"Invoked: {sorted(invoked)}\n"
        f"Completed: {sorted(completed)}\n"
        f"Timeline:\n{collector.dump_timeline()}"
    )

    # Warn (but don't fail) if the LLM skipped some specialists
    missing = set(expected_agents) - all_seen
    if missing:
        warnings.warn(
            f"LLM-directed coordinator skipped specialists: {sorted(missing)}, "
            f"invoked {sorted(seen_specialists)} "
            f"(acceptable — LLM selectively recruits agents)",
            stacklevel=2,
        )


def validate_coordinator_invoked(
    collector: EventCollector,
    expected_coordinator: str,
):
    """Assert the coordinator was invoked.

    In LLM-directed mode the coordinator is the start agent in the
    HandoffBuilder star topology, so it must always be invoked.
    """
    invoked = collector.get_invoked_agent_ids()
    completed = collector.get_completed_agent_ids()
    all_seen = invoked | completed
    coordinator_ids = {expected_coordinator, "coordinator"}
    assert coordinator_ids & all_seen, (
        f"Coordinator '{expected_coordinator}' was never invoked. "
        f"In LLM-directed mode the coordinator is the start agent and "
        f"must always run.\n"
        f"Invoked: {sorted(invoked)}\n"
        f"Completed: {sorted(completed)}\n"
        f"Timeline:\n{collector.dump_timeline()}"
    )


def validate_no_run_failed(collector: EventCollector):
    """Assert no orchestrator.run_failed events."""
    run_failed = [
        p for t, p in collector.events
        if t == "orchestrator.run_failed"
    ]
    assert not run_failed, (
        f"Run failed with errors: {[p.get('error', '') for p in run_failed]}\n"
        f"Timeline:\n{collector.dump_timeline()}"
    )


def validate_run_completed(collector: EventCollector):
    """Assert orchestrator.run_completed was emitted."""
    assert collector.has_event("orchestrator.run_completed"), (
        f"orchestrator.run_completed never emitted\n"
        f"Timeline:\n{collector.dump_timeline()}"
    )


def validate_coordinator_output(collector: EventCollector):
    """Assert the coordinator completed. Warn if no structured artifacts."""
    has_coordinator_done = any(
        t in ("executor.completed", "agent.completed")
        and ("coordinator" in (p.get("executor_id", "") or p.get("agent_id", "")))
        for t, p in collector.events
    )
    assert has_coordinator_done, (
        "Coordinator never completed. In LLM-directed mode the coordinator "
        "is the start agent and must always complete.\n"
        f"Timeline:\n{collector.dump_timeline()}"
    )

    artifact_types = {"recovery.option", "coordinator.scoring", "coordinator.plan"}
    has_artifact = any(t in artifact_types for t, _ in collector.events)
    if not has_artifact:
        warnings.warn(
            "Coordinator completed but produced no structured artifacts "
            "(recovery.option / coordinator.scoring / coordinator.plan). "
            "The LLM may have synthesised its response in free-form text.",
            stacklevel=2,
        )


def validate_llm_selection_trace(collector: EventCollector):
    """Assert that the LLM agent-selection trace event was emitted.

    In LLM-directed mode, gpt-5-mini selects which agents to recruit and
    emits an ``orchestrator.decision`` event with
    ``decisionType == "llm_agent_selection"`` containing its reasoning.
    """
    decisions = collector.get_events_by_type("orchestrator.decision")
    llm_selections = [
        d for d in decisions
        if d.get("decisionType") == "llm_agent_selection"
    ]
    assert llm_selections, (
        "No orchestrator.decision event with decisionType='llm_agent_selection' "
        "was emitted. LLM-directed mode should always emit this trace.\n"
        f"All decision events: {decisions}\n"
        f"Timeline:\n{collector.dump_timeline()}"
    )

    # Validate payload structure
    sel = llm_selections[0]
    assert sel.get("reason"), (
        f"LLM selection trace is missing 'reason': {sel}"
    )
