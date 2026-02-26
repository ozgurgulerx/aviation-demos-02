"""
Intent graph for evidence-to-tool mapping.
Adapted from demos-01 intent_graph_provider.py.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Default intent graph — maps aviation intents to evidence types and tools
# ---------------------------------------------------------------------------

DEFAULT_INTENT_GRAPH: Dict[str, Any] = {
    "intents": {
        "Disruption.Assess": {
            "description": "Assess the scope and impact of an operational disruption",
            "evidence": ["FlightSchedule", "WeatherHazard", "CrewStatus", "AircraftStatus", "NOTAMs"],
        },
        "Disruption.Recover": {
            "description": "Generate recovery plans for disrupted operations",
            "evidence": ["FlightSchedule", "AircraftStatus", "CrewStatus", "PassengerImpact", "HistoricalDelays"],
        },
        "Maintenance.Predict": {
            "description": "Predict maintenance needs from MEL/techlog trends",
            "evidence": ["MELTechlog", "SafetyReports", "RegulatoryDocs"],
        },
        "Diversion.Decide": {
            "description": "Support diversion decision with alternate evaluation",
            "evidence": ["LivePositions", "WeatherHazard", "AirportOps", "NOTAMs", "RouteAlternatives"],
        },
        "Crew.FatigueRisk": {
            "description": "Assess crew fatigue risk against FAR 117",
            "evidence": ["CrewStatus", "RegulatoryDocs", "SafetyReports"],
        },
        "Safety.Compliance": {
            "description": "Check compliance against regulations and safety standards",
            "evidence": ["RegulatoryDocs", "SafetyReports", "MELTechlog"],
        },
        "Network.Impact": {
            "description": "Model delay propagation across the network",
            "evidence": ["FlightSchedule", "HistoricalDelays", "GraphConnectivity"],
        },
        "Weather.Brief": {
            "description": "Weather briefing for operations",
            "evidence": ["WeatherHazard", "NOTAMs", "SafetyReports"],
        },
        "Passenger.Impact": {
            "description": "Assess passenger rebooking and connection risks",
            "evidence": ["FlightSchedule", "PassengerImpact", "GraphConnectivity"],
        },
        "Route.Optimize": {
            "description": "Find optimal route alternatives",
            "evidence": ["RouteAlternatives", "WeatherHazard", "LivePositions", "GraphConnectivity"],
        },
    },
    "evidence": {
        "FlightSchedule": {"description": "Flight legs, schedules, delays"},
        "CrewStatus": {"description": "Crew rosters, duty hours, legality"},
        "AircraftStatus": {"description": "Aircraft availability, MEL items"},
        "MELTechlog": {"description": "MEL/techlog events, deferred items"},
        "WeatherHazard": {"description": "SIGMETs, PIREPs, weather hazards"},
        "NOTAMs": {"description": "Active NOTAMs for airports/routes"},
        "SafetyReports": {"description": "ASRS safety reports, incident narratives"},
        "RegulatoryDocs": {"description": "FAA/EASA regulations, advisory circulars"},
        "HistoricalDelays": {"description": "BTS on-time performance data"},
        "PassengerImpact": {"description": "Passenger counts, connections, baggage"},
        "GraphConnectivity": {"description": "Airport/flight connectivity graph"},
        "LivePositions": {"description": "Real-time ADS-B flight positions"},
        "AirportOps": {"description": "Airport operational data, gates, turnaround"},
        "RouteAlternatives": {"description": "Alternative routes and segments"},
    },
    "authoritative_in": {
        "FlightSchedule": [
            {"tool": "SQL", "priority": 1, "hint_tables": ["ops_flight_legs"]},
            {"tool": "GRAPH", "priority": 2},
        ],
        "CrewStatus": [
            {"tool": "SQL", "priority": 1, "hint_tables": ["ops_crew_rosters"]},
        ],
        "AircraftStatus": [
            {"tool": "SQL", "priority": 1, "hint_tables": ["ops_flight_legs", "ops_mel_techlog_events"]},
        ],
        "MELTechlog": [
            {"tool": "SQL", "priority": 1, "hint_tables": ["ops_mel_techlog_events"]},
            {"tool": "VECTOR_OPS", "priority": 2},
        ],
        "WeatherHazard": [
            {"tool": "KQL", "priority": 1},
            {"tool": "VECTOR_OPS", "priority": 2},
        ],
        "NOTAMs": [
            {"tool": "NOSQL", "priority": 1},
            {"tool": "KQL", "priority": 2},
        ],
        "SafetyReports": [
            {"tool": "VECTOR_OPS", "priority": 1},
        ],
        "RegulatoryDocs": [
            {"tool": "VECTOR_REG", "priority": 1},
        ],
        "HistoricalDelays": [
            {"tool": "FABRIC_SQL", "priority": 1},
        ],
        "PassengerImpact": [
            {"tool": "SQL", "priority": 1, "hint_tables": ["ops_flight_legs", "ops_baggage_events"]},
        ],
        "GraphConnectivity": [
            {"tool": "GRAPH", "priority": 1},
        ],
        "LivePositions": [
            {"tool": "KQL", "priority": 1},
        ],
        "AirportOps": [
            {"tool": "SQL", "priority": 1, "hint_tables": ["ops_turnaround_milestones"]},
            {"tool": "VECTOR_AIRPORT", "priority": 2},
        ],
        "RouteAlternatives": [
            {"tool": "GRAPH", "priority": 1},
            {"tool": "SQL", "priority": 2, "hint_tables": ["ops_flight_legs"]},
        ],
    },
}


def tools_for_evidence(evidence_name: str) -> List[Dict[str, Any]]:
    """Return prioritized list of tools for an evidence type."""
    return DEFAULT_INTENT_GRAPH.get("authoritative_in", {}).get(evidence_name, [])


def evidence_for_intent(intent_name: str) -> List[str]:
    """Return required evidence types for an intent."""
    intent = DEFAULT_INTENT_GRAPH.get("intents", {}).get(intent_name, {})
    return intent.get("evidence", [])
