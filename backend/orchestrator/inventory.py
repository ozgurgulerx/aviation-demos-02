"""Agent inventory — builds full metadata for the /api/av/inventory endpoint."""

import structlog

from orchestrator.agent_registry import AGENT_REGISTRY, SCENARIO_AGENTS

logger = structlog.get_logger()


def _extract_tool_meta(tool) -> dict:
    """Extract name, description, and parameters from a FunctionTool object."""
    # FunctionTool from agent_framework exposes to_json_schema_spec()
    try:
        schema = tool.to_json_schema_spec()
        func_schema = schema.get("function", {})
        params_schema = func_schema.get("parameters", {})
        properties = params_schema.get("properties", {})
        required = set(params_schema.get("required", []))

        params = []
        for pname, pdef in properties.items():
            params.append({
                "name": pname,
                "type": pdef.get("type", "string"),
                "description": pdef.get("description", ""),
                "default": str(pdef["default"]) if "default" in pdef else None,
                "required": pname in required,
            })

        return {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": params,
        }
    except Exception as exc:
        tool_name = getattr(tool, "name", "unknown")
        logger.warning("tool_meta_extraction_failed", tool=tool_name, error=str(exc))
        return {
            "name": tool_name,
            "description": getattr(tool, "description", ""),
            "parameters": [],
        }


def _build_agent_tools_map() -> dict:
    """Build mapping of agent_id -> {instructions, tools} from agent modules."""
    from agents.tools.situation_tools import (
        map_disruption_scope, query_flight_schedule,
        get_live_positions as sit_get_live_positions,
    )
    from agents.tools.fleet_tools import (
        find_available_tails, check_range_compatibility, evaluate_tail_swap,
    )
    from agents.tools.crew_tools import (
        query_crew_availability, check_duty_limits, propose_crew_pairing,
    )
    from agents.tools.network_tools import simulate_delay_propagation, query_historical_delays
    from agents.tools.weather_safety_tools import (
        check_sigmets_pireps, query_notams, search_asrs_precedent,
    )
    from agents.tools.passenger_tools import assess_connection_risks, estimate_rebooking_load
    from agents.tools.coordinator_tools import score_recovery_option, rank_options, generate_plan
    from agents.tools.maintenance_tools import analyze_mel_trends, search_similar_incidents
    from agents.tools.fatigue_tools import calculate_fatigue_score, check_far117_compliance
    from agents.tools.diversion_tools import evaluate_alternates, check_airport_capability
    from agents.tools.regulatory_tools import check_compliance, search_regulations
    from agents.tools.route_tools import find_route_alternatives, check_route_weather
    from agents.tools.monitor_tools import (
        get_live_positions as mon_get_live_positions, check_active_notams,
    )

    from agents.situation_assessment import INSTRUCTIONS as sit_instr
    from agents.fleet_recovery import INSTRUCTIONS as fleet_instr
    from agents.crew_recovery import INSTRUCTIONS as crew_instr
    from agents.network_impact import INSTRUCTIONS as net_instr
    from agents.weather_safety import INSTRUCTIONS as weather_instr
    from agents.passenger_impact import INSTRUCTIONS as pax_instr
    from agents.recovery_coordinator import INSTRUCTIONS as rc_instr
    from agents.maintenance_predictor import INSTRUCTIONS as maint_instr
    from agents.crew_fatigue_assessor import INSTRUCTIONS as fatigue_instr
    from agents.diversion_advisor import INSTRUCTIONS as div_instr
    from agents.regulatory_compliance import INSTRUCTIONS as reg_instr
    from agents.route_planner import INSTRUCTIONS as route_instr
    from agents.real_time_monitor import INSTRUCTIONS as rtm_instr
    from agents.decision_coordinator import INSTRUCTIONS as dc_instr

    return {
        "situation_assessment": {
            "instructions": sit_instr,
            "tools": [map_disruption_scope, query_flight_schedule, sit_get_live_positions],
        },
        "fleet_recovery": {
            "instructions": fleet_instr,
            "tools": [find_available_tails, check_range_compatibility, evaluate_tail_swap],
        },
        "crew_recovery": {
            "instructions": crew_instr,
            "tools": [query_crew_availability, check_duty_limits, propose_crew_pairing],
        },
        "network_impact": {
            "instructions": net_instr,
            "tools": [simulate_delay_propagation, query_historical_delays],
        },
        "weather_safety": {
            "instructions": weather_instr,
            "tools": [check_sigmets_pireps, query_notams, search_asrs_precedent],
        },
        "passenger_impact": {
            "instructions": pax_instr,
            "tools": [assess_connection_risks, estimate_rebooking_load],
        },
        "recovery_coordinator": {
            "instructions": rc_instr,
            "tools": [score_recovery_option, rank_options, generate_plan],
        },
        "maintenance_predictor": {
            "instructions": maint_instr,
            "tools": [analyze_mel_trends, search_similar_incidents],
        },
        "crew_fatigue_assessor": {
            "instructions": fatigue_instr,
            "tools": [calculate_fatigue_score, check_far117_compliance],
        },
        "diversion_advisor": {
            "instructions": div_instr,
            "tools": [evaluate_alternates, check_airport_capability],
        },
        "regulatory_compliance": {
            "instructions": reg_instr,
            "tools": [check_compliance, search_regulations],
        },
        "route_planner": {
            "instructions": route_instr,
            "tools": [find_route_alternatives, check_route_weather],
        },
        "real_time_monitor": {
            "instructions": rtm_instr,
            "tools": [mon_get_live_positions, check_active_notams],
        },
        "decision_coordinator": {
            "instructions": dc_instr,
            "tools": [score_recovery_option, rank_options, generate_plan],
        },
    }


_cached_inventory = None


def get_inventory() -> dict:
    """Return the full agent inventory with tool metadata, instructions, and scenarios."""
    global _cached_inventory
    if _cached_inventory is not None:
        return _cached_inventory

    tools_map = _build_agent_tools_map()

    # Drift check: every non-placeholder agent must have a tools_map entry
    registry_ids = {a.id for a in AGENT_REGISTRY if a.category != "placeholder"}
    map_ids = set(tools_map.keys())
    missing = registry_ids - map_ids
    if missing:
        logger.error("inventory_registry_drift", missing_agents=sorted(missing))

    agents = []
    for agent_def in AGENT_REGISTRY:
        meta = tools_map.get(agent_def.id, {})
        tools = [_extract_tool_meta(fn) for fn in meta.get("tools", [])]
        instructions = meta.get("instructions", "")

        agents.append({
            "id": agent_def.id,
            "name": agent_def.name,
            "shortName": agent_def.short_name,
            "category": agent_def.category,
            "phase": agent_def.phase,
            "priority": agent_def.priority,
            "icon": agent_def.icon,
            "color": agent_def.color,
            "description": agent_def.description,
            "dataSources": agent_def.data_sources,
            "scenarios": agent_def.scenarios,
            "outputs": agent_def.outputs,
            "instructions": instructions,
            "tools": tools,
            "modelTier": "agent",
        })

    scenarios = {}
    for scenario_id, config in SCENARIO_AGENTS.items():
        scenarios[scenario_id] = {
            "agents": config["agents"],
            "coordinator": config["coordinator"],
        }

    _cached_inventory = {
        "agents": agents,
        "scenarios": scenarios,
        "orchestrationPatterns": ["sequential", "concurrent", "group_chat", "handoff", "magentic"],
    }
    return _cached_inventory
