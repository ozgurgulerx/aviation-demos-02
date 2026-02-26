"""
Flight data tools for the Flight Analyst Agent.
Uses @ai_function decorator from Microsoft Agent Framework.
Stub implementations returning mock data.
"""

import random
from typing import Annotated, Any, Dict, List

from agent_framework import tool as ai_function
from pydantic import Field
import structlog

logger = structlog.get_logger()


@ai_function(approval_mode="never_require")
async def analyze_flight_data(
    flight_ids: Annotated[
        List[str],
        Field(description="List of flight IDs to analyze (e.g., ['AA123', 'UA456'])")
    ],
    analysis_type: Annotated[
        str,
        Field(description="Type of analysis: delays, cancellations, diversions, or all", default="all")
    ] = "all",
) -> Dict[str, Any]:
    """Analyze flight data for patterns and anomalies.

    Returns analysis results including delay patterns, on-time performance,
    and disruption statistics for the specified flights.
    """
    results = {}
    for flight_id in flight_ids:
        delay_minutes = random.randint(0, 120)
        results[flight_id] = {
            "flight_id": flight_id,
            "status": random.choice(["on_time", "delayed", "cancelled", "diverted"]),
            "delay_minutes": delay_minutes,
            "delay_reason": random.choice([
                "weather", "maintenance", "crew", "air_traffic", "none"
            ]),
            "on_time_pct": round(random.uniform(0.6, 0.98), 2),
            "passenger_count": random.randint(80, 300),
            "connection_impact": random.randint(0, 50),
        }

    logger.info("flight_data_analyzed", count=len(results), analysis_type=analysis_type)
    return {"flights": results, "analysis_type": analysis_type, "total_analyzed": len(results)}


@ai_function(approval_mode="never_require")
async def check_weather_impact(
    airports: Annotated[
        List[str],
        Field(description="IATA airport codes to check weather for (e.g., ['JFK', 'LAX'])")
    ],
    timeframe_hours: Annotated[
        int,
        Field(description="Hours ahead to forecast weather impact", default=24)
    ] = 24,
) -> Dict[str, Any]:
    """Check weather impact on operations at specified airports.

    Returns weather conditions and their impact on flight operations
    including visibility, wind, precipitation, and operational rating.
    """
    weather = {}
    for airport in airports:
        severity = random.choice(["none", "minor", "moderate", "severe"])
        weather[airport] = {
            "airport": airport,
            "condition": random.choice(["clear", "cloudy", "rain", "snow", "fog", "thunderstorm"]),
            "visibility_miles": round(random.uniform(0.5, 10), 1),
            "wind_speed_knots": random.randint(0, 45),
            "wind_direction": random.randint(0, 360),
            "precipitation": random.choice(["none", "light", "moderate", "heavy"]),
            "impact_severity": severity,
            "operational_rating": random.choice(["green", "yellow", "red"]),
            "expected_delays_minutes": random.randint(0, 90) if severity != "none" else 0,
        }

    logger.info("weather_impact_checked", airports=airports, timeframe=timeframe_hours)
    return {"weather": weather, "timeframe_hours": timeframe_hours}


@ai_function(approval_mode="never_require")
async def query_route_status(
    routes: Annotated[
        List[str],
        Field(description="Route pairs to query (e.g., ['JFK-LAX', 'ORD-SFO'])")
    ],
) -> Dict[str, Any]:
    """Query current status of aviation routes.

    Returns operational status for each route including capacity,
    demand levels, and any active restrictions or NOTAMs.
    """
    statuses = {}
    for route in routes:
        parts = route.split("-")
        origin = parts[0] if len(parts) > 0 else "UNK"
        destination = parts[1] if len(parts) > 1 else "UNK"

        statuses[route] = {
            "route": route,
            "origin": origin,
            "destination": destination,
            "status": random.choice(["normal", "congested", "restricted", "closed"]),
            "capacity_utilization": round(random.uniform(0.4, 1.0), 2),
            "demand_level": random.choice(["low", "moderate", "high", "peak"]),
            "active_notams": random.randint(0, 5),
            "alternate_routes": random.randint(1, 3),
            "avg_transit_time_hours": round(random.uniform(1, 12), 1),
        }

    logger.info("route_status_queried", count=len(statuses))
    return {"routes": statuses}
