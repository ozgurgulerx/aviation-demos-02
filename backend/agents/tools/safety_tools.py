"""
Safety tools for the Safety Inspector Agent.
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
async def check_compliance(
    solution_description: Annotated[
        str,
        Field(description="Description of the proposed solution to check for compliance")
    ],
    regulations: Annotated[
        List[str],
        Field(description="Regulatory frameworks to check against (e.g., ['FAA', 'ICAO', 'EASA'])", default=["FAA", "ICAO"])
    ] = ["FAA", "ICAO"],
) -> Dict[str, Any]:
    """Check compliance of a proposed solution against aviation regulations.

    Returns compliance assessment for each regulatory framework including
    pass/fail status, specific violations, and remediation recommendations.
    """
    results = {}
    all_compliant = True

    for reg in regulations:
        num_checks = random.randint(3, 8)
        violations = []

        for i in range(num_checks):
            if random.random() < 0.15:  # 15% chance of violation per check
                violations.append({
                    "check_id": f"{reg}-{i+1:03d}",
                    "rule": f"{reg} Part {random.randint(91, 135)}.{random.randint(100, 999)}",
                    "description": random.choice([
                        "Minimum crew rest requirements not met",
                        "Aircraft maintenance interval exceeded",
                        "Duty time limitation violation",
                        "Required crew qualification missing",
                        "Fuel reserve requirements not satisfied",
                    ]),
                    "severity": random.choice(["warning", "violation", "critical"]),
                })

        compliant = len(violations) == 0
        if not compliant:
            all_compliant = False

        results[reg] = {
            "framework": reg,
            "compliant": compliant,
            "checks_performed": num_checks,
            "violations": violations,
            "violation_count": len(violations),
        }

    logger.info("compliance_checked", regulations=regulations, compliant=all_compliant)
    return {
        "solution": solution_description[:100],
        "overall_compliant": all_compliant,
        "frameworks": results,
    }


@ai_function(approval_mode="never_require")
async def assess_risk_factors(
    scenario_description: Annotated[
        str,
        Field(description="Description of the scenario to assess for risk factors")
    ],
    risk_categories: Annotated[
        List[str],
        Field(
            description="Risk categories to assess (e.g., ['operational', 'safety', 'financial', 'reputational'])",
            default=["operational", "safety", "financial", "reputational"],
        )
    ] = ["operational", "safety", "financial", "reputational"],
) -> Dict[str, Any]:
    """Assess risk factors for an operational scenario.

    Returns risk assessment across multiple categories with likelihood,
    impact severity, and overall risk scores.
    """
    risks = {}
    for category in risk_categories:
        likelihood = round(random.uniform(0.05, 0.8), 2)
        impact = round(random.uniform(1, 10), 1)
        risk_score = round(likelihood * impact, 2)

        risks[category] = {
            "category": category,
            "likelihood": likelihood,
            "impact_severity": impact,
            "risk_score": risk_score,
            "risk_level": "low" if risk_score < 2 else "medium" if risk_score < 5 else "high" if risk_score < 8 else "critical",
            "mitigations": [
                random.choice([
                    "Additional crew standby",
                    "Backup aircraft pre-positioned",
                    "Enhanced monitoring protocols",
                    "Passenger communication plan",
                    "Coordination with ATC",
                    "Maintenance team on standby",
                ])
                for _ in range(random.randint(1, 3))
            ],
        }

    overall_score = round(sum(r["risk_score"] for r in risks.values()) / len(risks), 2)

    logger.info("risk_assessed", categories=risk_categories, overall_score=overall_score)
    return {
        "scenario": scenario_description[:100],
        "risks": risks,
        "overall_risk_score": overall_score,
        "overall_risk_level": "low" if overall_score < 2 else "medium" if overall_score < 5 else "high",
        "recommendation": "proceed" if overall_score < 5 else "proceed_with_caution" if overall_score < 7 else "reconsider",
    }


@ai_function(approval_mode="never_require")
async def validate_solution(
    solution_description: Annotated[
        str,
        Field(description="Description of the complete solution to validate")
    ],
    validation_criteria: Annotated[
        List[str],
        Field(
            description="Criteria to validate against (e.g., ['safety', 'feasibility', 'efficiency', 'passenger_impact'])",
            default=["safety", "feasibility", "efficiency", "passenger_impact"],
        )
    ] = ["safety", "feasibility", "efficiency", "passenger_impact"],
) -> Dict[str, Any]:
    """Validate a proposed solution against safety and operational criteria.

    Returns a comprehensive validation result with pass/fail for each criterion,
    overall recommendation, and any conditions for approval.
    """
    validations = {}
    all_passed = True

    for criterion in validation_criteria:
        score = round(random.uniform(0.5, 1.0), 2)
        passed = score >= 0.7

        if not passed:
            all_passed = False

        validations[criterion] = {
            "criterion": criterion,
            "passed": passed,
            "score": score,
            "threshold": 0.7,
            "notes": random.choice([
                "Meets all requirements",
                "Marginal compliance - monitor closely",
                "Exceeds expectations",
                "Requires additional review",
                "Acceptable with conditions",
            ]),
        }

    logger.info("solution_validated", criteria=validation_criteria, all_passed=all_passed)
    return {
        "solution": solution_description[:100],
        "validations": validations,
        "overall_passed": all_passed,
        "approval_status": "approved" if all_passed else "conditional",
        "conditions": [] if all_passed else [
            f"Remediate {k} (score: {v['score']})"
            for k, v in validations.items()
            if not v["passed"]
        ],
    }
