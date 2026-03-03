"""Shared domain-knowledge constants for tool no-data fallbacks.

When retriever queries return zero rows, tools use these constants to give
agents substantive material so they can still produce a complete analysis.
"""

# ── FAR 117 Flight Duty Period Limits ──────────────────────────────
FAR_117_LIMITS = {
    "flight_duty_period": {
        "1_segment_start_0500_1959": "9 hours",
        "2_segments_start_0500_1959": "8.5 hours",
        "3_segments_start_0500_1959": "8 hours",
        "4_segments_start_0500_1959": "7.5 hours",
        "5_segments_start_0500_1959": "7 hours",
        "6_segments_start_0500_1959": "6.5 hours",
        "7plus_segments_start_0500_1959": "6 hours",
        "augmented_3_pilot_max": "13 hours",
        "augmented_4_pilot_max": "17 hours",
    },
    "rest_requirements": {
        "minimum_rest_period": "10 consecutive hours (must include 8-hour uninterrupted sleep opportunity)",
        "reduced_rest_minimum": "8 hours (only with airline fatigue policy approval)",
        "weekly_rest": "30 consecutive hours free from duty per 168-hour period",
        "cumulative_duty_limit_168h": "60 flight-duty hours",
        "cumulative_duty_limit_672h": "190 flight-duty hours",
        "cumulative_flight_time_365d": "1000 hours",
    },
    "extensions": {
        "unforeseen_operational_max": "2 hours beyond FDP table value",
        "commander_authority_condition": "Must not adversely affect safety; requires fatigue assessment",
    },
}

# ── SAFTE/FAST Fatigue Model Factors ───────────────────────────────
FATIGUE_RISK_FACTORS = {
    "high_risk_indicators": [
        "Duty period exceeds 10 hours without augmented crew",
        "Less than 10 hours rest in preceding rest period",
        "Window of Circadian Low (WOCL) duty: 0200-0559 local time",
        "Cumulative sleep debt exceeding 8 hours over 3 days",
        "More than 3 time-zone crossings in 24 hours",
        "4+ consecutive early starts (report before 0600)",
    ],
    "scoring_guidance": {
        "low": "Score 1-3: Crew well-rested, within all FDP limits, no circadian disruption",
        "medium": "Score 4-6: Approaching FDP limit, minor sleep debt, or WOCL overlap",
        "high": "Score 7-10: Exceeds FDP without augmentation, significant sleep debt, or multiple risk factors",
    },
    "analysis_template": (
        "For each crew member assess: (1) hours since last rest period, "
        "(2) cumulative duty in last 168h vs 60h limit, "
        "(3) WOCL exposure, (4) time-zone crossings, "
        "(5) consecutive early/late starts."
    ),
}

# ── Crew Scheduling SOPs ──────────────────────────────────────────
CREW_SCHEDULING_SOPS = {
    "minimum_complement": {
        "narrow_body": {"captain": 1, "first_officer": 1, "flight_attendant": "1 per 50 pax (min 1)"},
        "wide_body_domestic": {"captain": 1, "first_officer": 1, "flight_attendant": "1 per 50 pax (min 2)"},
        "wide_body_international": {"captain": 1, "first_officer": 1, "relief_pilot": "1 for FDP > 12h", "flight_attendant": "1 per 50 pax (min 3)"},
    },
    "reserve_crew": {
        "airport_standby_response": "2 hours from call to report",
        "home_standby_response": "3-4 hours from call to report",
        "short_call_reserve_window": "Typically 0500-2200 local",
    },
    "pairing_guidelines": {
        "priority_order": [
            "1. Airport standby reserves at affected base",
            "2. Home-based reserves within call-out window",
            "3. Deadheading crew from nearby base",
            "4. Voluntary extension of current crew (if within FDP)",
        ],
        "duty_verification": "Verify remaining FDP before any assignment; check 168h/672h cumulative limits",
    },
}

# ── Disruption Assessment Framework ────────────────────────────────
DISRUPTION_FRAMEWORK = {
    "assessment_dimensions": [
        "Scope: number of flights, airports, passengers affected",
        "Duration: expected length of disruption (hours/days)",
        "Cascade risk: downstream connection impacts at hub",
        "Resource impact: aircraft, crew, gates, ground handling",
        "Passenger impact: misconnections, stranded pax, rebooking needs",
    ],
    "typical_hub_metrics": {
        "major_hub_daily_departures": "200-400 flights",
        "average_connection_ratio": "40-60% connecting passengers",
        "minimum_connection_time": "45-90 minutes domestic, 90-120 minutes international",
        "gate_utilization": "85-95% during peak hours (0600-1000, 1600-2000)",
        "crew_base_coverage": "Typically 3-5 reserve crews per aircraft type on standby",
    },
    "estimation_heuristics": {
        "delay_cascade": "Each cancelled hub flight affects ~1.8 downstream flights on average",
        "crew_disruption": "Each crew timeout typically affects 2-4 subsequent flights",
        "recovery_time": "Major hub disruption: 4-8 hours to recover 80% schedule integrity",
    },
}

# ── Key Regulatory References ─────────────────────────────────────
REGULATORY_REFERENCES = {
    "crew_fatigue": {
        "FAR 117": "Flight crew member duty/rest requirements (14 CFR Part 117)",
        "FAR 117.11": "Flight duty period limits table",
        "FAR 117.25": "Rest period requirements (10h minimum)",
        "FAR 117.27": "Consecutive nighttime operations limits",
        "AC 120-103A": "Fatigue Risk Management Systems advisory circular",
    },
    "operations": {
        "FAR 91.3": "Pilot-in-command authority and responsibility",
        "FAR 91.11": "Prohibition on interference with crewmembers",
        "FAR 121.533": "Operational control responsibilities",
        "FAR 121.535": "Dispatch release authority",
        "FAR 121.542": "Sterile cockpit rule",
    },
    "safety": {
        "FAR 121.135": "Minimum equipment list (MEL) requirements",
        "FAR 121.153": "Aircraft airworthiness requirements for operations",
        "FAR 121.557": "Domestic emergency operations — duty to report",
        "AC 120-16G": "Air carrier maintenance programs",
    },
    "passenger_rights": {
        "14 CFR 259.5": "Tarmac delay contingency plan requirements",
        "DOT_2024_IDB": "Denied boarding compensation and rebooking obligations",
    },
}
