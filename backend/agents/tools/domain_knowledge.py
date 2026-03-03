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

# ── Fleet Recovery Guidance ──────────────────────────────────────
FLEET_RECOVERY_GUIDANCE = {
    "mel_categories": {
        "A": "Must be repaired within time specified in MEL (varies per item)",
        "B": "Must be repaired within 3 consecutive calendar days",
        "C": "Must be repaired within 10 consecutive calendar days",
        "D": "Must be repaired within 120 consecutive calendar days",
    },
    "tail_swap_evaluation_criteria": [
        "1. MEL status: verify no open Category A items on swap aircraft",
        "2. Range/payload: confirm swap aircraft can serve the route (fuel, distance, pax capacity)",
        "3. Crew qualification: verify flight crew is type-rated for swap aircraft",
        "4. Gate compatibility: confirm swap aircraft fits the assigned gate/jetbridge",
        "5. Downstream impact: assess how removing swap aircraft affects its original schedule",
        "6. Ground time: ensure sufficient turnaround time for servicing swap aircraft",
    ],
    "fleet_availability_estimation": {
        "spare_ratio_narrow_body": "5-8% of fleet held as operational spares",
        "spare_ratio_wide_body": "3-5% of fleet held as operational spares",
        "typical_ground_time_turnaround": "45-60 minutes domestic, 90-120 minutes international",
        "overnight_maintenance_window": "2300-0500 local time typical",
        "average_daily_utilization": "10-12 block hours narrow-body, 14-16 block hours wide-body",
    },
    "ground_time_minimums": {
        "narrow_body_domestic": "35-45 minutes",
        "narrow_body_international": "60-75 minutes",
        "wide_body_domestic": "60-90 minutes",
        "wide_body_international": "90-150 minutes",
    },
    "regulatory_refs": {
        "FAR 121.135": "MEL — each operator must have a minimum equipment list",
        "FAR 121.628": "Inoperable instruments and equipment — dispatch conditions",
        "AC 91-67": "Minimum equipment requirements for general aviation",
    },
}

# ── Network Impact Guidance ──────────────────────────────────────
NETWORK_IMPACT_GUIDANCE = {
    "propagation_model": {
        "reactionary_delay_ratio": "Each minute of primary delay generates ~0.8 minutes of reactionary delay",
        "decay_per_hop": "Delay attenuates ~30-40% per downstream hop if buffers exist",
        "hub_amplification": "Hub airports amplify delays: 1 cancelled hub flight affects ~1.8 downstream flights",
        "time_of_day_factors": {
            "morning_bank_0600_1000": "Highest cascade risk — feeds entire day's connections",
            "midday_1000_1400": "Moderate — some recovery buffer available",
            "afternoon_bank_1400_1800": "High — evening connections at risk, limited recovery",
            "evening_1800_2200": "Lower cascade but overnight recovery more difficult",
        },
        "recovery_time_estimates": {
            "minor_disruption_5_10_flights": "2-4 hours to recover 90% schedule integrity",
            "moderate_disruption_10_30_flights": "4-8 hours to recover 80% schedule integrity",
            "major_disruption_30_plus_flights": "12-24 hours; may require next-day schedule adjustments",
        },
    },
    "bts_benchmarks_by_cause": {
        "carrier": {"avg_delay_minutes": 20, "frequency_pct": 5.5, "description": "Mechanical, crew, fueling, baggage"},
        "weather": {"avg_delay_minutes": 55, "frequency_pct": 6.2, "description": "Significant weather at origin/destination/en-route"},
        "nas": {"avg_delay_minutes": 35, "frequency_pct": 7.8, "description": "National Aviation System — ATC, runway closures, volume"},
        "security": {"avg_delay_minutes": 15, "frequency_pct": 0.03, "description": "Terminal/concourse evacuation, re-screening"},
        "late_aircraft": {"avg_delay_minutes": 30, "frequency_pct": 5.8, "description": "Previous flight arrived late"},
    },
    "cascade_estimation_rules": [
        "Count connecting flights within 2x MCT window of affected arrivals",
        "Apply 60% misconnect probability for delays > MCT",
        "Apply 30% misconnect probability for delays between 0.5*MCT and MCT",
        "Weight by passenger load factor and connection ratio at hub",
    ],
}

# ── Weather & Safety Guidance ────────────────────────────────────
WEATHER_SAFETY_GUIDANCE = {
    "sigmet_types": {
        "convective_sigmet": "Thunderstorms, tornadoes, embedded CBs; issued by AWC for CONUS",
        "international_sigmet": "Issued for oceanic/international FIRs: turbulence, volcanic ash, TC",
        "airmet": "Less severe: moderate turbulence, sustained icing, IFR conditions, mountain obscuration",
    },
    "pirep_severity_scales": {
        "turbulence": {
            "light": "Slight erratic changes in altitude/attitude; food service possible",
            "moderate": "Definite strain against seat belts; unsecured objects dislodged",
            "severe": "Large abrupt changes; occupants forced against belts; objects tossed",
            "extreme": "Aircraft practically impossible to control; structural damage possible",
        },
        "icing": {
            "trace": "Rate of accumulation slightly greater than sublimation; not hazardous",
            "light": "Rate allows safe flight but deicing/anti-icing needed occasionally",
            "moderate": "Rate may create a problem; diversion may be necessary",
            "severe": "Rate is such that deicing equipment cannot control; immediate exit required",
            "extreme": "Rate exceeds aircraft capability; immediate exit and diversion required",
        },
    },
    "operational_impact_matrix": {
        "ceiling_below_200ft_vis_below_half_mile": "CAT IIIB or airport closure",
        "ceiling_200_500ft_vis_half_to_1_mile": "CAT II required; significant delays",
        "crosswind_above_30kt": "Possible runway restriction; type-dependent limits apply",
        "windshear_reported": "Pilot discretion; possible missed approaches and go-arounds",
        "thunderstorm_within_5nm": "Ground stop typical; departure/arrival holds",
        "freezing_precipitation": "Deicing required; 30-60 min added ground time per aircraft",
    },
    "notam_categories": [
        "Runway/taxiway closures or restrictions",
        "Navigation aid outages (ILS, VOR, GPS NOTAMs)",
        "Obstacle erection or crane activity near approach paths",
        "Airspace restrictions (TFR, military activity, VIP movement)",
        "Airport facility changes (lighting, fuel, customs)",
        "SID/STAR procedure amendments",
        "Bird/wildlife activity advisories",
        "Snow/ice removal and braking action reports",
    ],
    "asrs_analysis_template": {
        "search_dimensions": [
            "Aircraft type and configuration",
            "Phase of flight (taxi, takeoff, cruise, approach, landing)",
            "Contributing factors (weather, fatigue, maintenance, communication)",
            "Airport/airspace characteristics",
        ],
        "lessons_framework": [
            "What happened (factual sequence of events)",
            "Contributing factors identified by reporters",
            "Mitigations that worked or could have helped",
            "Applicability to current scenario",
        ],
    },
    "severity_levels": {
        "green": "No significant weather impact; normal operations",
        "yellow": "Minor delays possible; monitor conditions; advisory-level hazards",
        "orange": "Moderate operational impact; ground delays, some diversions possible",
        "red": "Severe impact; ground stops, extensive cancellations, diversions required",
    },
}

# ── Passenger Impact Guidance ────────────────────────────────────
PASSENGER_IMPACT_GUIDANCE = {
    "connection_risk_tiers": {
        "critical": "Buffer < 0 min (already misconnected); immediate rebooking required",
        "high": "Buffer < MCT (below minimum connection time); likely misconnect",
        "moderate": "Buffer between MCT and 1.5×MCT; at risk if any further delay",
        "low": "Buffer > 1.5×MCT; likely to make connection",
    },
    "minimum_connection_times": {
        "domestic_to_domestic": "45-60 minutes (varies by airport)",
        "domestic_to_international": "90-120 minutes",
        "international_to_domestic": "90-120 minutes (customs/immigration)",
        "international_to_international": "60-90 minutes (sterile transit) or 120+ (re-clear security)",
    },
    "priority_factors": [
        "1. Number of passengers on the connection",
        "2. Availability of alternative flights within 4 hours",
        "3. Premium cabin vs economy (contractual service guarantees)",
        "4. Unaccompanied minors and passengers needing assistance",
        "5. Passengers with onward international connections",
    ],
    "rebooking_capacity_benchmarks": {
        "load_factor_below_80pct": "Good rebooking capacity — most pax can be accommodated same day",
        "load_factor_80_to_90pct": "Moderate — some pax may need next-day or partner airline rebooking",
        "load_factor_above_90pct": "Tight — significant pax will require next-day; consider hotel vouchers",
    },
    "average_pax_per_flight": {
        "regional_jet": "50-75 passengers",
        "narrow_body_domestic": "140-180 passengers",
        "narrow_body_international": "150-190 passengers",
        "wide_body": "250-400 passengers",
    },
    "rebooking_time_estimates": {
        "automated_rebooking": "5-15 minutes per passenger (via kiosk/app)",
        "agent_assisted": "15-30 minutes per passenger at gate/counter",
        "mass_disruption_queue": "Average wait 45-90 minutes during major events",
    },
    "passenger_rights": {
        "tarmac_delay_rule": "Carrier must offer deplaning after 3 hours domestic / 4 hours international",
        "denied_boarding_compensation": "Up to 400% of one-way fare (max $1,550) for involuntary bumps",
        "eu_261_if_applicable": "€250-600 compensation for cancellations/long delays on EU-connected flights",
    },
    "prioritization_tiers": [
        "Tier 1: Unaccompanied minors, passengers needing medical/mobility assistance",
        "Tier 2: Passengers with tight international connections (< 4 hours)",
        "Tier 3: Premium cabin and loyalty elite passengers",
        "Tier 4: Passengers who can be rebooked same-day on own airline",
        "Tier 5: Passengers requiring partner airline or next-day rebooking",
    ],
}
