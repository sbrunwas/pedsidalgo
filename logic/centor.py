"""Centor / Modified Centor (McIsaac) pharyngitis risk scoring."""

from __future__ import annotations

from typing import Dict, List


def _age_points(age_years: float) -> tuple[int, str]:
    if age_years < 3:
        return 0, "Age <3 years (no age adjustment)"
    if 3 <= age_years <= 14:
        return 1, "Age 3-14 years"
    if 15 <= age_years <= 44:
        return 0, "Age 15-44 years"
    return -1, "Age >=45 years"


def _interpretation(score: int) -> tuple[str, str]:
    if score <= 0:
        return "1-2.5%", "No further testing or antibiotics."
    if score == 1:
        return "5-10%", "No further testing or antibiotics."
    if score == 2:
        return "11-17%", "Optional rapid strep testing and/or culture."
    if score == 3:
        return "28-35%", "Consider rapid strep testing and/or culture."
    return (
        "51-53%",
        "Consider rapid strep testing and/or culture. Empiric antibiotics may be appropriate depending on the specific scenario.",
    )


def compute_centor_score(
    *,
    age_years: float,
    tonsillar_exudate_or_swelling: bool,
    tender_anterior_cervical_nodes: bool,
    fever_gt_38: bool,
    cough_absent: bool,
) -> Dict[str, object]:
    """Compute Modified Centor (McIsaac) score and interpretation."""
    age_pts, age_rationale = _age_points(age_years)

    breakdown: List[Dict[str, object]] = [
        {"name": "Age", "points": age_pts, "rationale": age_rationale},
        {
            "name": "Exudate",
            "points": 1 if tonsillar_exudate_or_swelling else 0,
            "rationale": "Tonsillar exudate or swelling present" if tonsillar_exudate_or_swelling else "Not present",
        },
        {
            "name": "Ant cervical nodes",
            "points": 1 if tender_anterior_cervical_nodes else 0,
            "rationale": "Tender/swollen anterior cervical lymph nodes present"
            if tender_anterior_cervical_nodes
            else "Not present",
        },
        {
            "name": "Fever >38",
            "points": 1 if fever_gt_38 else 0,
            "rationale": "Temperature >38C / 100.4F" if fever_gt_38 else "Not present",
        },
        {
            "name": "Cough absent",
            "points": 1 if cough_absent else 0,
            "rationale": "Cough absent" if cough_absent else "Cough present",
        },
    ]

    raw_score = int(sum(int(row["points"]) for row in breakdown))
    score = max(raw_score, 0)
    probability_range, recommendation = _interpretation(score)

    return {
        "score": score,
        "probability_range": probability_range,
        "recommendation": recommendation,
        "breakdown": breakdown,
    }
