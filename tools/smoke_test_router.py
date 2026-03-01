#!/usr/bin/env python3
"""Smoke tests for master router behavior."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.router import route_patient


def get_pathway(result: Dict[str, Any], pathway_id: str) -> Dict[str, Any] | None:
    for item in result.get("pathways", []):
        if item.get("id") == pathway_id:
            return item
    return None


def print_result(label: str, result: Dict[str, Any]) -> None:
    print(f"\n=== {label} ===")
    for i, item in enumerate(result.get("pathways", []), start=1):
        print(f"{i:02d}. {item['priority']:<8} {item['status']:<8} {item['id']:<30} | {item['reason']}")


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def scenario_kawasaki() -> None:
    result = route_patient({"age_days": 3 * 365, "fever_days": 6, "kd_features": 4})
    print_result("3yo fever 6d KD features 4", result)
    k = get_pathway(result, "kawasaki")
    assert_true(k is not None, "kawasaki should be present")
    assert_true(k["status"] == "ACTIVE", "kawasaki should be ACTIVE")
    assert_true(k["priority"] == "HIGH", "kawasaki should be HIGH priority")


def scenario_uticalc() -> None:
    result = route_patient(
        {
            "age_days": int(18 * 30.4375),
            "fever_days": 2,
            "fever_without_source": True,
            "uticalc": {
                "sex": "female",
                "circumcised": None,
                "tmax_c": 39.5,
                "tmax_ge_39": None,
                "other_source": False,
            },
        }
    )
    print_result("18mo fever no source tmax 39.5 female", result)
    u = get_pathway(result, "uti")
    assert_true(u is not None, "uti should be present")
    assert_true(u["status"] == "ACTIVE", "uti should be ACTIVE")
    assert_true("UTICalc" in u["reason"], "uti should activate via uticalc")


def scenario_seizure_meningitis() -> None:
    base = route_patient({"age_days": 5 * 365, "seizure": True})
    print_result("5yo seizure", base)
    fs = get_pathway(base, "febrile_seizure")
    men = get_pathway(base, "meningitis")
    assert_true(fs is not None and fs["status"] == "ACTIVE", "febrile seizure should be ACTIVE")
    assert_true(men is not None and men["status"] == "ACTIVE", "meningitis should be ACTIVE")

    elevated = route_patient({"age_days": 5 * 365, "seizure": True, "neck_stiffness": True})
    print_result("5yo seizure + neck stiffness", elevated)
    men2 = get_pathway(elevated, "meningitis")
    assert_true(men2 is not None and men2["priority"] in {"HIGH", "CRITICAL"}, "meningitis should be elevated")


def scenario_orbital() -> None:
    base = route_patient({"age_days": 10 * 365, "eye_swelling": True, "periorbital_erythema": True})
    print_result("10yo eye swelling + periorbital erythema", base)
    orb = get_pathway(base, "orbital_preseptal_cellulitis")
    assert_true(orb is not None and orb["status"] == "ACTIVE", "orbital pathway should be ACTIVE")

    critical = route_patient(
        {
            "age_days": 10 * 365,
            "eye_swelling": True,
            "periorbital_erythema": True,
            "pain_with_eom": True,
        }
    )
    print_result("10yo eye swelling + periorbital erythema + pain with EOM", critical)
    orb2 = get_pathway(critical, "orbital_preseptal_cellulitis")
    assert_true(orb2 is not None and orb2["priority"] == "CRITICAL", "orbital pathway should be CRITICAL with pain EOM")


def scenario_sepsis() -> None:
    base = route_patient({"age_days": 8 * 365, "ill_appearing": True})
    print_result("Ill-appearing", base)
    s = get_pathway(base, "sepsis")
    assert_true(s is not None and s["status"] == "ACTIVE", "sepsis should be ACTIVE")

    critical = route_patient({"age_days": 8 * 365, "ill_appearing": True, "hypoxia": True})
    print_result("Ill-appearing + hypoxia", critical)
    s2 = get_pathway(critical, "sepsis")
    assert_true(s2 is not None and s2["priority"] == "CRITICAL", "sepsis should be CRITICAL with hypoxia")


def scenario_wheeze_bronchiolitis() -> None:
    result = route_patient({"age_days": int(14 * 30.4375), "wheeze": True})
    print_result("14mo wheeze alone", result)
    b = get_pathway(result, "bronchiolitis")
    assert_true(b is not None and b["status"] == "ACTIVE", "bronchiolitis should be ACTIVE with wheeze alone")


def scenario_dysuria_uti() -> None:
    result = route_patient({"age_days": 7 * 365, "dysuria": True})
    print_result("7yo dysuria alone", result)
    u = get_pathway(result, "uti")
    assert_true(u is not None and u["status"] == "ACTIVE", "uti should be ACTIVE with dysuria")


def scenario_cellulitis_findings() -> None:
    result = route_patient({"age_days": 6 * 365, "localized_erythema": True, "warmth_or_tenderness": True})
    print_result("6yo localized erythema + warmth", result)
    c = get_pathway(result, "cellulitis_abscess")
    assert_true(c is not None and c["status"] == "ACTIVE", "cellulitis/abscess should be ACTIVE with erythema + warmth")


def scenario_neck_space_drooling() -> None:
    result = route_patient({"age_days": 4 * 365, "drooling": True})
    print_result("4yo drooling", result)
    n = get_pathway(result, "neck_space_infection")
    assert_true(n is not None and n["status"] == "ACTIVE", "neck space infection should be ACTIVE with drooling")


def scenario_fever_without_source_uticalc() -> None:
    result = route_patient(
        {
            "age_days": int(18 * 30.4375),
            "fever_without_source": True,
            "uticalc": {
                "sex": "female",
                "circumcised": None,
                "tmax_c": 39.5,
                "other_source": False,
            },
        }
    )
    print_result("18mo fever without source + UTICalc inputs", result)
    u = get_pathway(result, "uti")
    assert_true(u is not None and u["status"] == "ACTIVE", "uti should be ACTIVE when UTICalc >=2%")
    assert_true(
        "Active – UA/UCx recommended (UTICalc ≥2%)" in u["reason"],
        "UTI reason should include exact UTICalc activation label",
    )
    fired = [r for r in result.get("rule_trace", []) if r.get("fired")]
    assert_true(any(r.get("rule_id") == "uticalc_rule" for r in fired), "uticalc_rule should fire in trace")


def main() -> int:
    scenario_wheeze_bronchiolitis()
    scenario_dysuria_uti()
    scenario_cellulitis_findings()
    scenario_neck_space_drooling()
    scenario_fever_without_source_uticalc()
    scenario_kawasaki()
    scenario_uticalc()
    scenario_seizure_meningitis()
    scenario_orbital()
    scenario_sepsis()
    print("\nAll smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
