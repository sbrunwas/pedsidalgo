"""Master router logic for pathway activation and prioritization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from logic.uticalc_pretest import uticalc_pretest_percent
from yaml_compat import safe_load


ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "source" / "sources.yaml"
MASTER_ROUTER_PATH = ROOT / "pathways" / "master_router.yaml"


@dataclass
class Activation:
    id: str
    name: str
    status: str  # ACTIVE | CONSIDER
    priority: str  # CRITICAL | HIGH | NORMAL
    reason: str
    source: str  # chop | non_chop | note


def load_sources() -> List[Dict[str, Any]]:
    data = safe_load(SOURCES_PATH.read_text())
    return data.get("pathways", [])


def load_router_spec() -> Dict[str, Any]:
    return safe_load(MASTER_ROUTER_PATH.read_text())


def _age_months_from_days(age_days: int) -> float:
    return age_days / 30.4375


def _corrected_days(age_days: int, ga_weeks: Optional[int]) -> int:
    if ga_weeks is None or ga_weeks >= 37:
        return age_days
    corrected = age_days - (37 - ga_weeks) * 7
    return max(0, corrected)


def _infant_band(age_days_corrected: int) -> Optional[str]:
    if 0 <= age_days_corrected <= 21:
        return "0-21"
    if 22 <= age_days_corrected <= 28:
        return "22-28"
    if 29 <= age_days_corrected <= 60:
        return "29-60"
    return None


def _priority_rank(priority: str, spec: Dict[str, Any]) -> int:
    order = spec.get("sort_order", {}).get("priority", ["CRITICAL", "HIGH", "NORMAL"])
    return order.index(priority) if priority in order else len(order)


def _status_rank(status: str, spec: Dict[str, Any]) -> int:
    order = spec.get("sort_order", {}).get("status", ["ACTIVE", "CONSIDER"])
    return order.index(status) if status in order else len(order)


def _build_force_critical_flags(patient: Dict[str, Any]) -> Dict[str, bool]:
    return {
        "hemodynamic_instability": bool(patient.get("hemodynamic_instability")),
        "altered_mental_status": bool(patient.get("altered_mental_status")),
        "hypoxia": bool(patient.get("hypoxia")),
        "neck_stiffness": bool(patient.get("neck_stiffness")),
        "refusal_to_bear_weight": bool(patient.get("refusal_to_bear_weight")),
        "eye_swelling_and_pain_with_eom": bool(patient.get("eye_swelling") and patient.get("pain_with_eom")),
        "drooling_and_muffled_voice_or_trismus": bool(
            patient.get("drooling") and (patient.get("muffled_voice") or patient.get("trismus"))
        ),
    }


def _register(
    acc: Dict[str, Activation],
    *,
    pathway_id: str,
    name: str,
    status: str,
    priority: str,
    reason: str,
    source: str,
) -> None:
    existing = acc.get(pathway_id)
    if existing is None:
        acc[pathway_id] = Activation(pathway_id, name, status, priority, reason, source)
        return

    status = "ACTIVE" if (existing.status == "ACTIVE" or status == "ACTIVE") else "CONSIDER"
    p_order = {"CRITICAL": 3, "HIGH": 2, "NORMAL": 1}
    priority = existing.priority if p_order[existing.priority] >= p_order[priority] else priority
    reason = f"{existing.reason}; {reason}"
    acc[pathway_id] = Activation(pathway_id, name, status, priority, reason, source)


def route_patient(patient: Dict[str, Any]) -> Dict[str, Any]:
    sources = load_sources()
    spec = load_router_spec()
    by_id = {item["id"]: item for item in sources}

    activations: Dict[str, Activation] = {}
    notes: List[Dict[str, str]] = []
    rule_trace: List[Dict[str, Any]] = []

    def trace(rule_id: str, fired: bool, details: str) -> None:
        rule_trace.append({"rule_id": rule_id, "fired": fired, "details": details})

    age_days = int(patient.get("age_days", 0))
    age_months = patient.get("age_months")
    if age_months is None:
        age_months = _age_months_from_days(age_days)

    ga_weeks = patient.get("ga_weeks")
    ill_appearing = bool(patient.get("ill_appearing"))

    if age_days < int(spec["age_cutoffs"]["infant_days_max"]):
        corrected = _corrected_days(age_days, ga_weeks)
        band = _infant_band(corrected)
        target_id = spec["infant_split"]["targets"]["ill_appearing" if ill_appearing else "well_appearing"]
        entry = by_id[target_id]
        _register(
            activations,
            pathway_id=target_id,
            name=entry["title"],
            status="ACTIVE",
            priority="HIGH" if ill_appearing else "NORMAL",
            reason=(
                f"Infant pathway: age {age_days} days"
                + (f", corrected {corrected} days (GA {ga_weeks}w)" if ga_weeks and ga_weeks < 37 else "")
                + (f", band {band}" if band else "")
                + (", ill-appearing" if ill_appearing else ", well-appearing")
            ),
            source="chop" if entry.get("publisher") == "chop" else "non_chop",
        )
        trace("infant_split", True, f"Infant split applied (band={band or 'n/a'})")
    else:
        trace("infant_split", False, "Age >= 60 days")

    if ill_appearing or patient.get("hemodynamic_instability") or patient.get("altered_mental_status"):
        sepsis = by_id["sepsis"]
        elevated = any(
            bool(patient.get(flag))
            for flag in ["hypoxia", "respiratory_distress", "altered_mental_status", "hemodynamic_instability"]
        )
        _register(
            activations,
            pathway_id="sepsis",
            name=sepsis["title"],
            status="ACTIVE",
            priority="HIGH" if elevated else "NORMAL",
            reason="Activated because ill_appearing OR hemodynamic_instability OR altered_mental_status",
            source="chop",
        )
        trace("sepsis_rule", True, "ill_appearing OR hemodynamic_instability OR altered_mental_status")
    else:
        trace("sepsis_rule", False, "No sepsis trigger flags")

    if patient.get("immunocompromised_or_onc"):
        p = by_id["fever_onc_patient"]
        _register(
            activations,
            pathway_id="fever_onc_patient",
            name=p["title"],
            status="ACTIVE",
            priority="HIGH",
            reason="Activated because immunocompromised_or_onc",
            source="chop",
        )
        trace("onc_fever_rule", True, "immunocompromised_or_onc")
    else:
        trace("onc_fever_rule", False, "No onc trigger")

    if patient.get("seizure"):
        fs = by_id["febrile_seizure"]
        _register(
            activations,
            pathway_id="febrile_seizure",
            name=fs["title"],
            status="ACTIVE",
            priority="NORMAL",
            reason="Activated because seizure",
            source="chop",
        )
        men = by_id["meningitis"]
        men_pri = "HIGH" if (patient.get("neck_stiffness") or patient.get("altered_mental_status")) else "NORMAL"
        _register(
            activations,
            pathway_id="meningitis",
            name=men["title"],
            status="ACTIVE",
            priority=men_pri,
            reason="Activated because seizure (parallel meningitis activation)",
            source="chop",
        )
        trace("seizure_rule", True, "Activated febrile_seizure + meningitis")
    else:
        trace("seizure_rule", False, "No seizure")

    if patient.get("neck_stiffness") or patient.get("altered_mental_status"):
        men = by_id["meningitis"]
        _register(
            activations,
            pathway_id="meningitis",
            name=men["title"],
            status="ACTIVE",
            priority="HIGH",
            reason="Activated because neck_stiffness OR altered_mental_status",
            source="chop",
        )
        trace("meningitis_direct_rule", True, "neck_stiffness OR altered_mental_status")
    elif patient.get("severe_headache"):
        men = by_id["meningitis"]
        _register(
            activations,
            pathway_id="meningitis",
            name=men["title"],
            status="CONSIDER",
            priority="NORMAL",
            reason="Consider because severe headache alone",
            source="chop",
        )
        trace("meningitis_headache_consider_rule", True, "severe_headache only")
    else:
        trace("meningitis_rules", False, "No meningitis direct/consider trigger")

    if patient.get("influenza_like_illness"):
        for pid in ["influenza", "covid"]:
            p = by_id[pid]
            _register(
                activations,
                pathway_id=pid,
                name=p["title"],
                status="ACTIVE",
                priority="NORMAL",
                reason="Activated because influenza-like illness",
                source="chop",
            )
        trace("ili_rule", True, "Activated influenza + covid")
    else:
        trace("ili_rule", False, "No influenza-like illness")

    # Respiratory pathway support so distressing respiratory presentations surface core airway/lung pathways.
    if patient.get("respiratory_distress") or patient.get("hypoxia") or (patient.get("cough") and patient.get("wheeze")):
        p = by_id["bronchiolitis"]
        _register(
            activations,
            pathway_id="bronchiolitis",
            name=p["title"],
            status="ACTIVE",
            priority="HIGH" if (patient.get("respiratory_distress") or patient.get("hypoxia")) else "NORMAL",
            reason="Activated because respiratory_distress OR hypoxia OR (cough and wheeze)",
            source="chop",
        )
        trace("bronchiolitis_rule", True, "respiratory_distress OR hypoxia OR cough+wheeze")
    else:
        trace("bronchiolitis_rule", False, "No bronchiolitis trigger")

    if patient.get("respiratory_distress") or patient.get("hypoxia") or patient.get("cough"):
        p = by_id["pneumonia"]
        _register(
            activations,
            pathway_id="pneumonia",
            name=p["title"],
            status="CONSIDER" if not patient.get("hypoxia") else "ACTIVE",
            priority="HIGH" if patient.get("hypoxia") else "NORMAL",
            reason="Activated/considered because respiratory distress, hypoxia, or cough",
            source="chop",
        )
        trace("pneumonia_rule", True, "respiratory_distress OR hypoxia OR cough")
    else:
        trace("pneumonia_rule", False, "No pneumonia trigger")

    if patient.get("stridor") or patient.get("barky_cough") or (patient.get("respiratory_distress") and age_days <= 6 * 365):
        p = by_id["croup"]
        _register(
            activations,
            pathway_id="croup",
            name=p["title"],
            status="ACTIVE" if (patient.get("stridor") or patient.get("barky_cough")) else "CONSIDER",
            priority="HIGH" if patient.get("respiratory_distress") else "NORMAL",
            reason="Activated/considered because stridor, barky cough, or respiratory distress in younger child",
            source="chop",
        )
        trace("croup_rule", True, "stridor OR barky_cough OR respiratory_distress in younger child")
    else:
        trace("croup_rule", False, "No croup trigger")

    if patient.get("eye_swelling") or patient.get("periorbital_erythema"):
        p = by_id["orbital_preseptal_cellulitis"]
        pri = "HIGH" if (patient.get("eye_swelling") and patient.get("pain_with_eom")) else "NORMAL"
        _register(
            activations,
            pathway_id="orbital_preseptal_cellulitis",
            name=p["title"],
            status="ACTIVE",
            priority=pri,
            reason="Activated because eye_swelling OR periorbital_erythema",
            source="chop",
        )
        trace("orbital_preseptal_rule", True, "eye_swelling OR periorbital_erythema")
    else:
        trace("orbital_preseptal_rule", False, "No orbital/preseptal trigger")

    if (patient.get("vomiting") or patient.get("diarrhea")) and not patient.get("severe_focal_abdominal_pain"):
        p = by_id["gastroenteritis"]
        _register(
            activations,
            pathway_id="gastroenteritis",
            name=p["title"],
            status="ACTIVE",
            priority="NORMAL",
            reason="Activated because vomiting OR diarrhea and no severe focal abdominal pain",
            source="non_chop",
        )
        trace("gastro_rule", True, "vomiting OR diarrhea without severe focal abdominal pain")
    else:
        trace("gastro_rule", False, "No gastro trigger or severe focal abdominal pain present")
    if patient.get("severe_focal_abdominal_pain"):
        notes.append(
            {
                "id": "consider_surgical_abdomen",
                "name": "Consider Surgical Abdomen",
                "status": "CONSIDER",
                "priority": "HIGH",
                "reason": "Consider because severe focal abdominal pain",
                "source": "note",
            }
        )

    if patient.get("localized_erythema") and (
        patient.get("warmth_or_tenderness") or patient.get("fluctuance_or_purulence") or patient.get("localized_swelling")
    ):
        p = by_id["cellulitis_abscess"]
        _register(
            activations,
            pathway_id="cellulitis_abscess",
            name=p["title"],
            status="ACTIVE",
            priority="NORMAL",
            reason="Activated because localized_erythema with warmth/tenderness or fluctuance/purulence or localized_swelling",
            source="chop",
        )
        trace("cellulitis_abscess_rule", True, "localized_erythema + associated local signs")
    else:
        trace("cellulitis_abscess_rule", False, "No cellulitis/abscess trigger pattern")

    if patient.get("joint_pain") or patient.get("limp") or patient.get("refusal_to_bear_weight"):
        p = by_id["osteomyelitis"]
        _register(
            activations,
            pathway_id="osteomyelitis",
            name=p["title"],
            status="ACTIVE",
            priority="HIGH" if patient.get("refusal_to_bear_weight") else "NORMAL",
            reason="Activated because joint_pain OR limp OR refusal_to_bear_weight",
            source="chop",
        )
        trace("osteomyelitis_rule", True, "joint_pain OR limp OR refusal_to_bear_weight")
    else:
        trace("osteomyelitis_rule", False, "No osteomyelitis trigger")

    if age_days >= int(spec["age_cutoffs"]["kawasaki_min_days"]) and int(patient.get("fever_days", 0)) >= 5:
        kd_features = int(patient.get("kd_features", 0))
        p = by_id["kawasaki"]
        if kd_features >= 4:
            _register(
                activations,
                pathway_id="kawasaki",
                name=p["title"],
                status="ACTIVE",
                priority="HIGH",
                reason="Activated because age>=60d, fever>=5d, KD features >=4",
                source="chop",
            )
            trace("kawasaki_rule", True, "ACTIVE (KD features >=4)")
        elif 2 <= kd_features <= 3:
            _register(
                activations,
                pathway_id="kawasaki",
                name=p["title"],
                status="CONSIDER",
                priority="NORMAL",
                reason="Consider incomplete Kawasaki because age>=60d, fever>=5d, KD features 2-3",
                source="chop",
            )
            trace("kawasaki_rule", True, "CONSIDER (KD features 2-3)")
        else:
            trace("kawasaki_rule", False, "Criteria window met but KD features <2")
    else:
        trace("kawasaki_rule", False, "Requires age>=60d and fever_days>=5")

    if patient.get("dysuria") or patient.get("flank_pain") or patient.get("fever_without_source"):
        p = by_id["uti"]
        _register(
            activations,
            pathway_id="uti",
            name=p["title"],
            status="ACTIVE",
            priority="NORMAL",
            reason="Activated because dysuria OR flank_pain OR fever_without_source",
            source="chop",
        )
        trace("uti_symptom_rule", True, "dysuria OR flank_pain OR fever_without_source")
    else:
        trace("uti_symptom_rule", False, "No UTI symptom trigger")

    uticalc = patient.get("uticalc")
    uticalc_risk: Optional[float] = None
    if isinstance(uticalc, dict) and uticalc:
        uticalc_risk = uticalc_pretest_percent(
            age_months=age_months,
            sex=uticalc.get("sex", "female"),
            circumcised=uticalc.get("circumcised"),
            other_source=bool(uticalc.get("other_source", True)),
            tmax_ge_39=uticalc.get("tmax_ge_39"),
            tmax_c=uticalc.get("tmax_c"),
        )

    if uticalc_risk is not None and uticalc_risk >= 2.0:
        p = by_id["uti"]
        _register(
            activations,
            pathway_id="uti",
            name=p["title"],
            status="ACTIVE",
            priority="NORMAL",
            reason=f"Activated because UTICalc >=2% (pretest): {uticalc_risk:.2f}%",
            source="chop",
        )
        trace("uticalc_rule", True, f"UTICalc {uticalc_risk:.2f}% >= 2%")
    elif uticalc is None or uticalc == {}:
        trace("uticalc_rule", False, "UTICalc inputs not provided")
    elif uticalc_risk is None:
        trace("uticalc_rule", False, "Age outside 2-24 months")
    else:
        trace("uticalc_rule", False, f"UTICalc {uticalc_risk:.2f}% < 2%")

    force_flags = _build_force_critical_flags(patient)
    any_force = any(force_flags.values())
    forced_paths = set(spec.get("critical_overrides", {}).get("forced_critical_pathways", []))
    if any_force:
        for pid, item in list(activations.items()):
            if pid in forced_paths:
                item.priority = "CRITICAL"
                item.reason = f"{item.reason}; Critical override applied"
        trace("critical_overrides", True, "At least one critical flag set")
    else:
        trace("critical_overrides", False, "No critical override flags set")

    results = [a.__dict__ for a in activations.values()]
    results.extend(notes)

    chop_first = bool(spec.get("sort_order", {}).get("chop_first", True))

    def sort_key(item: Dict[str, Any]) -> Any:
        chop_rank = 0 if item.get("source") == "chop" else 1
        if not chop_first:
            chop_rank = 0
        return (
            _priority_rank(item["priority"], spec),
            _status_rank(item["status"], spec),
            chop_rank,
            item["name"].lower(),
        )

    results.sort(key=sort_key)
    return {
        "pathways": results,
        "uticalc_pretest_percent": uticalc_risk,
        "critical_flags": force_flags,
        "rule_trace": rule_trace,
    }
