"""
Agent Registry — 20-agent pool with scenario-based selection.
Each agent has icon, color, data_sources, and scenario mappings for the canvas UI.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel


class AgentDefinition(BaseModel):
    """Definition of an agent in the registry."""
    id: str
    name: str
    short_name: str
    category: str  # "specialist", "coordinator", "placeholder"
    description: str
    default_include: bool = False
    priority: int = 50
    icon: str = ""
    color: str = ""
    data_sources: List[str] = []
    scenarios: List[str] = []
    phase: int = 1  # implementation phase


class AgentSelectionResult(BaseModel):
    """Result of agent selection process."""
    agent_id: str
    agent_name: str
    short_name: str
    category: str
    included: bool
    reason: str
    conditions_evaluated: List[str]
    priority: int
    icon: str = ""
    color: str = ""
    data_sources: List[str] = []


# ═══════════════════════════════════════════════════════════════════
# FULL 20-AGENT REGISTRY
# ═══════════════════════════════════════════════════════════════════

AGENT_REGISTRY: List[AgentDefinition] = [
    # ── Hub Disruption Recovery (7 agents) ─────────────────────────
    AgentDefinition(
        id="situation_assessment", name="Situation Assessment", short_name="Situation",
        category="specialist", description="Maps disruption scope via GRAPH + SQL + KQL",
        icon="Radar", color="#3b82f6", data_sources=["GRAPH", "SQL", "KQL"],
        scenarios=["hub_disruption", "diversion", "crew_fatigue", "safety_incident"],
        priority=10, phase=1,
    ),
    AgentDefinition(
        id="fleet_recovery", name="Fleet Recovery", short_name="Fleet",
        category="specialist", description="Finds available tails, evaluates swaps via SQL + GRAPH",
        icon="PlaneTakeoff", color="#22c55e", data_sources=["SQL", "GRAPH"],
        scenarios=["hub_disruption", "predictive_maintenance"],
        priority=20, phase=1,
    ),
    AgentDefinition(
        id="crew_recovery", name="Crew Recovery", short_name="Crew",
        category="specialist", description="Crew availability and duty limit checks via SQL + AI Search",
        icon="Users", color="#06b6d4", data_sources=["SQL", "VECTOR_REG"],
        scenarios=["hub_disruption", "crew_fatigue"],
        priority=30, phase=1,
    ),
    AgentDefinition(
        id="network_impact", name="Network Impact", short_name="Network",
        category="specialist", description="Delay propagation modeling via Fabric SQL + GRAPH",
        icon="Network", color="#8b5cf6", data_sources=["FABRIC_SQL", "GRAPH"],
        scenarios=["hub_disruption", "predictive_maintenance", "delay_analysis"],
        priority=40, phase=1,
    ),
    AgentDefinition(
        id="weather_safety", name="Weather & Safety", short_name="Weather",
        category="specialist", description="SIGMETs/PIREPs, NOTAMs, ASRS search via KQL + Cosmos + AI Search",
        icon="CloudLightning", color="#f59e0b", data_sources=["KQL", "NOSQL", "VECTOR_OPS"],
        scenarios=["hub_disruption", "diversion", "weather_brief", "safety_incident"],
        priority=50, phase=1,
    ),
    AgentDefinition(
        id="passenger_impact", name="Passenger Impact", short_name="Passenger",
        category="specialist", description="Connection risks and rebooking load via SQL + GRAPH",
        icon="UserCheck", color="#ec4899", data_sources=["SQL", "GRAPH"],
        scenarios=["hub_disruption", "gate_reassignment", "turnaround"],
        priority=60, phase=1,
    ),
    AgentDefinition(
        id="recovery_coordinator", name="Recovery Coordinator", short_name="Coordinator",
        category="coordinator", description="Multi-objective scoring and recovery plan synthesis",
        icon="Brain", color="#6366f1", data_sources=[],
        scenarios=["hub_disruption"],
        priority=100, phase=1,
    ),

    # ── Cross-scenario agents ─────────────────────────────────────
    AgentDefinition(
        id="maintenance_predictor", name="Maintenance Predictor", short_name="Maintenance",
        category="specialist", description="MEL trend analysis, similar incident search via SQL + AI Search",
        icon="Wrench", color="#f97316", data_sources=["SQL", "VECTOR_OPS"],
        scenarios=["predictive_maintenance"],
        priority=25, phase=1,
    ),
    AgentDefinition(
        id="crew_fatigue_assessor", name="Crew Fatigue Assessor", short_name="Fatigue",
        category="specialist", description="FAR 117 compliance, fatigue risk scoring via SQL + AI Search",
        icon="Moon", color="#0ea5e9", data_sources=["SQL", "VECTOR_REG"],
        scenarios=["crew_fatigue"],
        priority=35, phase=1,
    ),
    AgentDefinition(
        id="diversion_advisor", name="Diversion Advisor", short_name="Diversion",
        category="specialist", description="Alternate airport evaluation via KQL + SQL + Cosmos",
        icon="Navigation", color="#ef4444", data_sources=["KQL", "SQL", "NOSQL"],
        scenarios=["diversion"],
        priority=15, phase=1,
    ),
    AgentDefinition(
        id="regulatory_compliance", name="Regulatory Compliance", short_name="Regulatory",
        category="specialist", description="Safety gate — regulation search via AI Search",
        icon="Shield", color="#64748b", data_sources=["VECTOR_REG", "VECTOR_OPS"],
        scenarios=["predictive_maintenance", "crew_fatigue", "safety_incident"],
        priority=90, phase=1,
    ),
    AgentDefinition(
        id="route_planner", name="Route Planner", short_name="Route",
        category="specialist", description="Route alternatives via GRAPH + SQL + KQL",
        icon="Route", color="#2dd4bf", data_sources=["GRAPH", "SQL", "KQL"],
        scenarios=["diversion", "fuel_optimization", "atc_flow"],
        priority=45, phase=1,
    ),
    AgentDefinition(
        id="real_time_monitor", name="Real-Time Monitor", short_name="Monitor",
        category="specialist", description="Live ADS-B positions + active NOTAMs via KQL + Cosmos",
        icon="Satellite", color="#fb923c", data_sources=["KQL", "NOSQL"],
        scenarios=["diversion", "atc_flow"],
        priority=55, phase=1,
    ),
    AgentDefinition(
        id="decision_coordinator", name="Decision Coordinator", short_name="Decision",
        category="coordinator", description="General decision synthesis for non-hub scenarios",
        icon="Cpu", color="#818cf8", data_sources=[],
        scenarios=["predictive_maintenance", "diversion", "crew_fatigue", "safety_incident"],
        priority=100, phase=1,
    ),

    # ── Placeholder agents (stub tools) ───────────────────────────
    AgentDefinition(
        id="fuel_optimizer", name="Fuel Optimizer", short_name="Fuel",
        category="placeholder", description="Fuel optimization analysis (placeholder)",
        icon="Fuel", color="#14b8a6", data_sources=["KQL", "SQL", "FABRIC_SQL"],
        scenarios=["fuel_optimization"],
        priority=65, phase=2,
    ),
    AgentDefinition(
        id="gate_optimizer", name="Gate Optimizer", short_name="Gate",
        category="placeholder", description="Gate/stand reassignment optimization (placeholder)",
        icon="DoorOpen", color="#a855f7", data_sources=["SQL", "GRAPH"],
        scenarios=["gate_reassignment"],
        priority=66, phase=2,
    ),
    AgentDefinition(
        id="atc_flow_advisor", name="ATC Flow Advisor", short_name="ATC",
        category="placeholder", description="ATC flow management advisory (placeholder)",
        icon="Radio", color="#84cc16", data_sources=["KQL", "FABRIC_SQL"],
        scenarios=["atc_flow"],
        priority=67, phase=2,
    ),
    AgentDefinition(
        id="historical_analyst", name="Historical Analyst", short_name="Historical",
        category="placeholder", description="BTS historical delay analysis (placeholder)",
        icon="History", color="#d946ef", data_sources=["FABRIC_SQL", "VECTOR_OPS"],
        scenarios=["delay_analysis"],
        priority=68, phase=2,
    ),
    AgentDefinition(
        id="airport_ops_advisor", name="Airport Ops Advisor", short_name="Airport",
        category="placeholder", description="Airport operations advisory (placeholder)",
        icon="Building", color="#78716c", data_sources=["SQL", "VECTOR_AIRPORT"],
        scenarios=["turnaround", "gate_reassignment"],
        priority=69, phase=2,
    ),
    AgentDefinition(
        id="cost_analyst", name="Cost Analyst", short_name="Cost",
        category="placeholder", description="Cost impact analysis (placeholder)",
        icon="DollarSign", color="#fbbf24", data_sources=["FABRIC_SQL", "SQL"],
        scenarios=["turnaround", "fuel_optimization"],
        priority=70, phase=2,
    ),
]


# ═══════════════════════════════════════════════════════════════════
# SCENARIO → AGENT MAPPING
# ═══════════════════════════════════════════════════════════════════

SCENARIO_AGENTS = {
    "hub_disruption": {
        "agents": ["situation_assessment", "fleet_recovery", "crew_recovery",
                    "network_impact", "weather_safety", "passenger_impact"],
        "coordinator": "recovery_coordinator",
    },
    "predictive_maintenance": {
        "agents": ["fleet_recovery", "maintenance_predictor", "regulatory_compliance", "network_impact"],
        "coordinator": "decision_coordinator",
    },
    "diversion": {
        "agents": ["situation_assessment", "weather_safety", "diversion_advisor",
                    "route_planner", "real_time_monitor"],
        "coordinator": "decision_coordinator",
    },
    "crew_fatigue": {
        "agents": ["crew_recovery", "crew_fatigue_assessor", "regulatory_compliance",
                    "situation_assessment"],
        "coordinator": "decision_coordinator",
    },
}

# Keywords for scenario detection
SCENARIO_KEYWORDS = {
    "hub_disruption": [
        "disruption", "hub", "ground stop", "thunderstorm", "grounded", "runway closure",
        "terminal closure", "multiple flights", "gate hold", "delay recovery",
        "recovery plan", "mass cancellation",
    ],
    "predictive_maintenance": [
        "maintenance", "mel", "techlog", "minimum equipment", "deferred",
        "jasc", "predictive", "component failure", "fleet health",
    ],
    "diversion": [
        "diversion", "divert", "alternate", "fuel critical", "emergency",
        "medical emergency", "go-around", "missed approach",
    ],
    "crew_fatigue": [
        "fatigue", "duty limit", "far 117", "crew rest", "red-eye",
        "cumulative duty", "legality", "crew scheduling",
    ],
}


def detect_scenario(problem: str) -> str:
    """Detect which scenario a problem maps to based on keywords."""
    problem_lower = problem.lower()
    scores: Dict[str, int] = {}
    for scenario, keywords in SCENARIO_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in problem_lower)
        if score > 0:
            scores[scenario] = score
    if scores:
        return max(scores, key=lambda k: scores[k])
    return "hub_disruption"  # default


def get_agent_registry() -> List[AgentDefinition]:
    return AGENT_REGISTRY


def get_agent_by_id(agent_id: str) -> Optional[AgentDefinition]:
    for agent in AGENT_REGISTRY:
        if agent.id == agent_id:
            return agent
    return None


def select_agents_for_problem(
    problem: str = "",
) -> tuple[List[AgentSelectionResult], List[AgentSelectionResult]]:
    """
    Select agents for a problem. Returns (included, excluded) with full metadata.
    All 20 agents are returned — the coordinator's LLM makes final handoff decisions.
    """
    scenario = detect_scenario(problem)
    scenario_config = SCENARIO_AGENTS.get(scenario, SCENARIO_AGENTS["hub_disruption"])
    active_ids = set(scenario_config["agents"] + [scenario_config["coordinator"]])

    included: List[AgentSelectionResult] = []
    excluded: List[AgentSelectionResult] = []

    for agent in AGENT_REGISTRY:
        is_included = agent.id in active_ids
        result = AgentSelectionResult(
            agent_id=agent.id,
            agent_name=agent.name,
            short_name=agent.short_name,
            category=agent.category,
            included=is_included,
            reason=f"Required for {scenario} scenario" if is_included else f"Not needed for {scenario}",
            conditions_evaluated=[scenario, "keyword_match"],
            priority=agent.priority,
            icon=agent.icon,
            color=agent.color,
            data_sources=agent.data_sources,
        )
        if is_included:
            included.append(result)
        else:
            excluded.append(result)

    included.sort(key=lambda x: x.priority)
    return included, excluded
