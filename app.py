from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import re

import streamlit as st

try:
    import requests
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    requests = None
    BeautifulSoup = None

from logic.router import route_patient
from yaml_compat import safe_load


ROOT = Path(__file__).resolve().parent
PATHWAYS_DIR = ROOT / "pathways"
SOURCES_PATH = ROOT / "source" / "sources.yaml"


def _add_unique(items: List[str], entry: str) -> None:
    if entry not in items:
        items.append(entry)


def generate_assessment(
    age_months: int,
    fever_days: int,
    symptoms: List[str],
    exam: List[str],
    high_risk: bool,
    toxic: bool,
    unstable: bool,
    fever_without_source: bool,
) -> Dict[str, List[str]]:
    """Return structured, safety-first clinical considerations.

    The function is deterministic and prioritizes urgent rule-outs first.
    """

    features = {*(s.lower() for s in symptoms), *(e.lower() for e in exam)}

    cannot_miss: List[str] = []
    common: List[str] = []
    prolonged_or_special: List[str] = []
    recommended_workup: List[str] = []
    recommended_initial_management: List[str] = []
    consults: List[str] = []
    admit_considerations: List[str] = []
    discharge_considerations: List[str] = []

    age_years = age_months / 12.0
    infant_under_90d = age_months < 3

    def _score_candidate(
        base: float,
        supports: List[str] | None = None,
        opposes: List[str] | None = None,
        min_age_months: int | None = None,
        max_age_months: int | None = None,
        min_fever_days: int | None = None,
        max_fever_days: int | None = None,
        required_any: List[str] | None = None,
    ) -> float:
        score = base
        if min_age_months is not None and age_months < min_age_months:
            score -= 3.0
        if max_age_months is not None and age_months > max_age_months:
            score -= 3.0
        if min_fever_days is not None and fever_days < min_fever_days:
            score -= 2.0
        if max_fever_days is not None and fever_days > max_fever_days:
            score -= 2.0

        if required_any and not features.intersection(set(required_any)):
            score -= 2.5

        for item in supports or []:
            if item in features:
                score += 1.8
        for item in opposes or []:
            if item in features:
                score -= 1.0
        return score

    # Core safety net and immediate threats.
    if unstable or toxic:
        _add_unique(cannot_miss, "Sepsis/shock with potential end-organ hypoperfusion")
        _add_unique(
            recommended_workup,
            "Immediate sepsis evaluation: CBC, CMP, lactate, blood cultures, UA/urine culture, consider VBG/ABG and coagulation panel.",
        )
        _add_unique(
            recommended_initial_management,
            "Stabilize ABCs, establish IV/IO access, give fluid resuscitation as indicated, and start empiric broad-spectrum IV antibiotics per local pathway.",
        )
        _add_unique(admit_considerations, "PICU/monitored admission for unstable or ill-appearing child.")

    if high_risk:
        _add_unique(cannot_miss, "Invasive bacterial infection in immunocompromised/high-risk host")
        _add_unique(
            recommended_workup,
            "Lower threshold for blood cultures, broad infectious workup, and early source imaging based on exam.",
        )
        _add_unique(
            recommended_initial_management,
            "Start empiric antimicrobials early after cultures when feasible; tailor quickly to local antibiogram and host risk.",
        )
        _add_unique(consults, "Early infectious diseases consultation for high-risk host.")
        _add_unique(admit_considerations, "Admission favored in immunocompromised/high-risk patients with fever.")

    if infant_under_90d:
        _add_unique(cannot_miss, "Serious bacterial infection in febrile infant <90 days (bacteremia/UTI/meningitis)")
        _add_unique(
            recommended_workup,
            "Age-stratified febrile infant pathway: blood culture, inflammatory markers, catheterized UA + urine culture, and CSF studies when indicated.",
        )
        _add_unique(
            recommended_initial_management,
            "Use local febrile infant risk stratification; start empiric IV antibiotics when high-risk criteria are met.",
        )
        _add_unique(admit_considerations, "Hospital admission is commonly indicated for infants <28 days and many 29-60 day infants.")

    neuro_red_flags = {
        "headache",
        "neck stiffness",
        "seizure",
        "altered mental status",
        "ams",
    }
    if features.intersection(neuro_red_flags):
        _add_unique(cannot_miss, "Meningitis/encephalitis")
        _add_unique(
            recommended_workup,
            "Obtain blood cultures and urgent LP when safe; neuroimaging first if signs of increased ICP/focal deficits.",
        )
        _add_unique(
            recommended_initial_management,
            "Do not delay empiric IV antimicrobials for suspected CNS infection in unstable patients.",
        )
        _add_unique(admit_considerations, "Admit for close neurologic monitoring and definitive infectious evaluation.")

    respiratory_distress_flags = {
        "hypoxia (spo2 < 90%)",
        "tachypnea or increased work of breathing",
        "difficulty breathing",
    }
    if features.intersection(respiratory_distress_flags):
        _add_unique(cannot_miss, "Impending respiratory failure / severe lower respiratory tract infection")
        _add_unique(
            recommended_workup,
            "Continuous pulse oximetry and respiratory assessment; consider chest radiograph if severe illness/admission likely.",
        )
        _add_unique(
            recommended_initial_management,
            "Provide oxygen/supportive respiratory care and escalate support per local respiratory pathway.",
        )
        _add_unique(admit_considerations, "Admit if hypoxic, significant work of breathing, apnea risk, or poor oral intake.")

    if "rapidly progressive severe pain" in features or "pain out of proportion" in features:
        _add_unique(cannot_miss, "Necrotizing soft tissue infection")
        _add_unique(
            recommended_workup,
            "Urgent surgical evaluation plus broad labs/cultures; avoid delay for definitive imaging if unstable.",
        )
        _add_unique(recommended_initial_management, "Begin broad-spectrum IV antibiotics and emergent source control.")
        _add_unique(consults, "Immediate surgery consultation for possible necrotizing infection.")

    # Always consider UTI/pyelo for young children/febrile without source.
    uri_focus = {"runny or stuffy nose", "cough", "wheeze", "sore throat", "ear pain"}
    clear_uri_focus = bool(features.intersection(uri_focus))
    uti_trigger = (
        (age_months < 24 and fever_days >= 2 and (fever_without_source or not clear_uri_focus))
        or fever_without_source
        or "burning/frequent urination" in features
    )
    if uti_trigger:
        target_bucket = cannot_miss if age_months < 24 or fever_without_source else common
        _add_unique(target_bucket, "UTI/pyelonephritis (including without urinary symptoms)")
        _add_unique(
            recommended_workup,
            "Obtain urinalysis and urine culture (catheterized specimen in non-toilet-trained child) before antibiotics when feasible.",
        )

    # Broad-to-narrow common differential:
    # start with a wide age/fever-informed list, then rerank as evidence is added.
    common_candidates = [
        (
            "Viral URI (including influenza/COVID depending on season and circulation)",
            _score_candidate(
                base=2.8,
                supports=["runny or stuffy nose", "cough", "sore throat"],
                opposes=["neck stiffness", "seizure", "altered mental status"],
            ),
        ),
        (
            "Community-acquired pneumonia (viral or bacterial)",
            _score_candidate(
                base=2.1,
                supports=["cough", "difficulty breathing", "tachypnea or increased work of breathing", "hypoxia (spo2 < 90%)"],
                min_fever_days=1,
            ),
        ),
        (
            "Bronchiolitis / viral lower respiratory tract infection",
            _score_candidate(
                base=2.2,
                supports=["wheeze", "cough", "tachypnea or increased work of breathing"],
                max_age_months=23,
            ),
        ),
        (
            "Group A streptococcal pharyngitis",
            _score_candidate(
                base=1.6,
                supports=["sore throat", "swollen lymph nodes"],
                opposes=["cough", "runny or stuffy nose"],
                min_age_months=36,
                required_any=["sore throat"],
            ),
        ),
        (
            "Acute bacterial sinusitis",
            _score_candidate(
                base=1.2,
                supports=["runny or stuffy nose", "nasal discharge", "cough"],
                min_fever_days=10,
            ),
        ),
        (
            "Acute otitis media",
            _score_candidate(
                base=1.7,
                supports=["ear pain", "runny or stuffy nose"],
                max_age_months=144,
            ),
        ),
        (
            "Viral gastroenteritis / enteric infection",
            _score_candidate(
                base=1.5,
                supports=["vomiting or diarrhea", "abdominal pain"],
            ),
        ),
        (
            "Cellulitis/abscess",
            _score_candidate(
                base=1.1,
                supports=["fluctuant skin lesion", "tender skin", "rash"],
                required_any=["fluctuant skin lesion", "tender skin", "rash"],
            ),
        ),
    ]

    # Keep UTI in the broad differential even when not in cannot-miss bucket.
    if "UTI/pyelonephritis (including without urinary symptoms)" not in cannot_miss:
        common_candidates.append(
            (
                "UTI/pyelonephritis (including without urinary symptoms)",
                _score_candidate(
                    base=1.8,
                    supports=["burning/frequent urination", "abdominal pain"],
                    min_fever_days=1,
                ),
            )
        )

    scored_common = sorted(
        ((name, score) for name, score in common_candidates if score >= 0.7),
        key=lambda item: (-item[1], item[0]),
    )
    # Narrow list as user adds more details, while always keeping a meaningful breadth.
    detail_count = len(features) + int(high_risk) + int(toxic) + int(unstable) + int(fever_without_source)
    common_limit = max(3, 7 - detail_count)
    for name, _ in scored_common[:common_limit]:
        _add_unique(common, name)

    if "Bronchiolitis / viral lower respiratory tract infection" in common:
        _add_unique(
            recommended_initial_management,
            "Bronchiolitis care is mainly supportive: suctioning, hydration, antipyretics, oxygen if hypoxic.",
        )

    if "Community-acquired pneumonia (viral or bacterial)" in common:
        _add_unique(
            recommended_workup,
            "Consider chest radiograph when severe illness, hypoxia, or admission is being considered.",
        )

    if "Viral URI (including influenza/COVID depending on season and circulation)" in common:
        _add_unique(
            recommended_workup,
            "Consider influenza/COVID testing when result will change treatment, isolation, or disposition.",
        )

    if "Group A streptococcal pharyngitis" in common:
        _add_unique(recommended_workup, "Obtain rapid strep test ± throat culture per local testing protocol.")

    if "Acute bacterial sinusitis" in common and fever_days >= 10:
        _add_unique(
            recommended_initial_management,
            "If persistent/worsening bacterial sinusitis pattern is present, consider amoxicillin-clavulanate per local guideline.",
        )

    if "Cellulitis/abscess" in common:
        _add_unique(
            recommended_workup,
            "Evaluate for drainable collection; bedside ultrasound can help when fluctuance is uncertain.",
        )

    if "joint pain" in features or "limp" in features:
        _add_unique(cannot_miss, "Septic arthritis / osteomyelitis")
        _add_unique(recommended_workup, "Send ESR/CRP, blood cultures, and targeted imaging; urgent orthopedic evaluation.")
        _add_unique(consults, "Orthopedics consult for suspected septic joint or osteomyelitis.")

    # Fever-duration based pathways.
    kd_feature_labels = {
        "conjunctival injection",
        "oral mucosal changes",
        "oral mucosal changes (e.g., strawberry tongue, red or cracked lips)",
        "strawberry tongue",
        "extremity changes",
        "extremity changes (erythema, edema or peeling)",
        "swollen lymph nodes",
        "rash",
    }
    kd_count = len(features.intersection(kd_feature_labels))

    if fever_days >= 5:
        if kd_count >= 4:
            _add_unique(cannot_miss, "Kawasaki disease (high clinical suspicion)")
            _add_unique(
                prolonged_or_special,
                "MIS-C and other inflammatory syndromes should still be considered with persistent fever.",
            )
            _add_unique(
                recommended_workup,
                "Kawasaki-focused workup: CRP/ESR, CBC, CMP, UA, and echocardiogram per pathway.",
            )
            _add_unique(
                recommended_initial_management,
                "Consult cardiology urgently and treat per local Kawasaki pathway (e.g., IVIG/aspirin decisions by treating team).",
            )
            _add_unique(consults, "Cardiology consultation for suspected Kawasaki disease.")
            _add_unique(consults, "Consider rheumatology consultation per local Kawasaki/MIS-C pathway.")
        elif kd_count >= 2:
            _add_unique(prolonged_or_special, "Incomplete Kawasaki disease (fever >=5 days with compatible features)")
            _add_unique(prolonged_or_special, "MIS-C and other inflammatory syndromes")
            _add_unique(
                recommended_workup,
                "Evaluate incomplete Kawasaki pathway: CRP/ESR, CBC, CMP, UA, echocardiogram; trend inflammatory markers.",
            )
            _add_unique(consults, "Cardiology/rheumatology discussion for prolonged fever with Kawasaki features.")
        else:
            _add_unique(prolonged_or_special, "Kawasaki disease")
            _add_unique(prolonged_or_special, "MIS-C and other inflammatory syndromes")
            _add_unique(
                recommended_workup,
                "Persistent fever >=5 days should trigger inflammatory evaluation (CRP/ESR, CBC, CMP, UA) and reassessment for evolving Kawasaki signs.",
            )

    if fever_days >= 8:
        _add_unique(prolonged_or_special, "Fever of unknown origin framework")
        _add_unique(
            recommended_workup,
            "If fever persists >=8 days, broaden evaluation: exposure/travel history, weight loss/night sweats, malignancy/autoimmune considerations.",
        )
        _add_unique(consults, "Consider infectious diseases and rheumatology consultation for persistent unexplained fever.")

    # Disposition guidance.
    _add_unique(
        discharge_considerations,
        "Discharge only if hemodynamically stable, oxygenating adequately, tolerating fluids, and with reliable follow-up/return precautions.",
    )
    _add_unique(
        discharge_considerations,
        "Re-evaluation is needed for persistent fever, worsening work of breathing, decreased urine output, new neurologic signs, or clinical deterioration.",
    )

    if not common and not prolonged_or_special and not cannot_miss:
        _add_unique(common, "Self-limited viral syndrome (diagnosis of exclusion after safety screen)")

    return {
        "cannot_miss": cannot_miss,
        "common": common,
        "prolonged_or_special": prolonged_or_special,
        "recommended_workup": recommended_workup,
        "recommended_initial_management": recommended_initial_management,
        "consults": consults,
        "admit_considerations": admit_considerations,
        "discharge_considerations": discharge_considerations,
    }


def _render_list(items: List[str], empty_text: str) -> None:
    if items:
        for item in items:
            st.markdown(f"- {item}")
    else:
        st.write(empty_text)


def age_months_from_days(age_days: int) -> float:
    return age_days / 30.4375


def load_pathway(pathway_id: str) -> Dict[str, Any]:
    path = PATHWAYS_DIR / f"{pathway_id}.yaml"
    if not path.exists():
        return {}
    return safe_load(path.read_text()) or {}


@st.cache_data
def load_source_catalog() -> Dict[str, Dict[str, Any]]:
    data = safe_load(SOURCES_PATH.read_text()) or {}
    pathways = data.get("pathways", [])
    return {p["id"]: p for p in pathways if "id" in p}


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@st.cache_data(show_spinner=False, ttl=3600)
def scrape_chop_recommendations(url: str) -> Dict[str, Any]:
    if requests is None or BeautifulSoup is None:
        return {"ok": False, "recommendations": [], "error": "requests/bs4 not installed"}
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        return {"ok": False, "recommendations": [], "error": str(exc)}

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()

    recs: List[str] = []
    for li in soup.find_all("li"):
        txt = _clean_text(li.get_text(" ", strip=True))
        if len(txt) >= 40 and txt not in recs:
            recs.append(txt)
        if len(recs) >= 6:
            break

    if not recs:
        paragraphs = []
        for p in soup.find_all("p"):
            txt = _clean_text(p.get_text(" ", strip=True))
            if len(txt) >= 60:
                paragraphs.append(txt)
            if len(paragraphs) >= 4:
                break
        recs = paragraphs

    return {"ok": True, "recommendations": recs[:6], "error": None}


def init_nav_state(pathway: Dict[str, Any]) -> None:
    nodes = pathway.get("nodes", [])
    start_node = next((n for n in nodes if n.get("id") == "start"), nodes[0] if nodes else None)
    st.session_state.nav_current = start_node.get("id") if start_node else None
    st.session_state.nav_history = []


def render_navigator(selected_pathway_id: str) -> None:
    pathway = load_pathway(selected_pathway_id)
    if not pathway:
        st.info(f"No pathway YAML found for `{selected_pathway_id}`")
        return

    if st.session_state.get("nav_pathway") != selected_pathway_id or "nav_current" not in st.session_state:
        init_nav_state(pathway)
        st.session_state.nav_pathway = selected_pathway_id

    nodes = {n["id"]: n for n in pathway.get("nodes", [])}
    edges = pathway.get("edges", [])

    current_id = st.session_state.get("nav_current")
    current = nodes.get(current_id)
    if not current:
        st.warning("Current node missing; restarting at start node.")
        init_nav_state(pathway)
        current_id = st.session_state.get("nav_current")
        current = nodes.get(current_id)
        if not current:
            st.error("Unable to load pathway nodes.")
            return

    st.write(f"**{pathway.get('title', selected_pathway_id)}**")
    st.write(f"Node: `{current['id']}` ({current.get('type', 'unknown')})")
    st.write(current.get("text", ""))

    source_urls = current.get("source_urls", [])
    if source_urls:
        st.caption("Node source(s): " + " | ".join(source_urls))

    next_ids = [e["to"] for e in edges if e.get("from") == current_id]
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Back", key="nav_back"):
            history = st.session_state.get("nav_history", [])
            if history:
                st.session_state.nav_current = history.pop()
                st.session_state.nav_history = history
    with col2:
        if st.button("Restart", key="nav_restart"):
            init_nav_state(pathway)

    if not next_ids:
        st.success("Reached terminal node.")
        return

    st.write("Next step:")
    for nid in next_ids:
        label = nodes.get(nid, {}).get("label", nid)
        if st.button(f"Go to: {label}", key=f"goto_{current_id}_{nid}"):
            history = st.session_state.get("nav_history", [])
            history.append(current_id)
            st.session_state.nav_history = history
            st.session_state.nav_current = nid


def main() -> None:
    st.title("Pediatric Infectious Pathway Router")

    age_mode = st.radio("Age Input", ["days", "years/months/days"], horizontal=True)
    if age_mode == "days":
        age_days = int(st.number_input("Age (days)", min_value=0, max_value=8000, value=365))
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            years = int(st.number_input("Years", min_value=0, max_value=21, value=1))
        with col2:
            months = int(st.number_input("Months", min_value=0, max_value=11, value=0))
        with col3:
            days = int(st.number_input("Days", min_value=0, max_value=30, value=0))
        age_days = years * 365 + months * 30 + days

    st.caption(f"Computed age_days: {age_days}")
    age_months = age_months_from_days(age_days)

    ga_weeks = None
    if age_days < 60:
        ga_preterm = st.checkbox("Gestational age <37 weeks", value=False)
        if ga_preterm:
            ga_weeks = int(st.number_input("Gestational age at birth (weeks)", min_value=22, max_value=36, value=35))
        ill_infant = st.checkbox("Ill-appearing infant", value=False)
    else:
        ill_infant = False

    fever_days = int(st.number_input("Fever duration (days)", min_value=0, max_value=30, value=1))
    ill_appearing = st.checkbox("Ill appearing", value=ill_infant)
    hemodynamic_instability = st.checkbox("Hemodynamic instability", value=False)
    altered_mental_status = st.checkbox("Altered mental status", value=False)
    immunocompromised_or_onc = st.checkbox("Immunocompromised or oncology patient", value=False)

    st.subheader("System Findings")
    neuro = st.multiselect("Neuro", ["seizure", "neck_stiffness", "severe_headache"])
    resp = st.multiselect("Respiratory", ["influenza_like_illness", "hypoxia", "respiratory_distress"])
    ent = st.multiselect("HEENT", ["eye_swelling", "periorbital_erythema", "pain_with_eom", "drooling", "muffled_voice", "trismus"])
    gi = st.multiselect("GI", ["vomiting", "diarrhea", "severe_focal_abdominal_pain"])
    gu = st.multiselect("GU", ["dysuria", "flank_pain", "fever_without_source"])
    msk = st.multiselect("MSK", ["joint_pain", "limp", "refusal_to_bear_weight"])
    skin = st.multiselect("Skin", ["localized_erythema", "warmth_or_tenderness", "fluctuance_or_purulence", "localized_swelling"])

    kd_features = int(st.slider("Kawasaki features count", min_value=0, max_value=5, value=0))

    uticalc_payload: Dict[str, Any] = {}
    uticalc_allowed = 2 <= age_months <= 24
    if uticalc_allowed:
        st.subheader("UTI Embedded Assessment (2-24 months)")
        sex = st.radio("Sex", ["female", "male"], horizontal=True)
        circumcised: Optional[bool] = None
        if sex == "male":
            circumcised = st.checkbox("Circumcised", value=True)
        use_tmax_toggle = st.checkbox("Use fever >=39C toggle", value=False)
        if use_tmax_toggle:
            tmax_ge_39 = st.checkbox("Tmax >=39C", value=False)
            tmax_c = None
        else:
            tmax_c = float(st.number_input("Tmax C", min_value=35.0, max_value=43.0, value=38.5, step=0.1))
            tmax_ge_39 = None
        # Default True prevents auto-activating UTI on default 12-month profile.
        other_source = st.checkbox("Other source present", value=True)
        uticalc_payload = {
            "sex": sex,
            "circumcised": circumcised,
            "tmax_ge_39": tmax_ge_39,
            "tmax_c": tmax_c,
            "other_source": other_source,
        }

    patient = {
        "age_days": age_days,
        "age_months": age_months,
        "ga_weeks": ga_weeks,
        "fever_days": fever_days,
        "ill_appearing": ill_appearing,
        "hemodynamic_instability": hemodynamic_instability,
        "altered_mental_status": altered_mental_status,
        "immunocompromised_or_onc": immunocompromised_or_onc,
        "kd_features": kd_features,
        "uticalc": uticalc_payload,
    }

    all_flags = [
        "seizure", "neck_stiffness", "severe_headache", "influenza_like_illness", "hypoxia", "respiratory_distress",
        "eye_swelling", "periorbital_erythema", "pain_with_eom", "drooling", "muffled_voice", "trismus",
        "vomiting", "diarrhea", "severe_focal_abdominal_pain", "dysuria", "flank_pain", "fever_without_source",
        "joint_pain", "limp", "refusal_to_bear_weight", "localized_erythema", "warmth_or_tenderness",
        "fluctuance_or_purulence", "localized_swelling",
    ]
    for flag in all_flags:
        patient[flag] = False
    for flag in neuro + resp + ent + gi + gu + msk + skin:
        patient[flag] = True

    # Real-time update on every rerun.
    result = route_patient(patient)
    source_catalog = load_source_catalog()

    differential_items: List[Dict[str, Any]] = result.get("pathways", [])
    uti_item = next((p for p in differential_items if p.get("id") == "uti"), None)
    if uticalc_allowed and result.get("uticalc_pretest_percent") is not None:
        uti_text = f"UTICalc pretest: {result['uticalc_pretest_percent']:.2f}%"
        if uti_item and uti_item.get("status") == "ACTIVE":
            uti_text += " -> UTI considered (embedded)"
        st.caption(uti_text)

    # UTI is intentionally embedded/hidden from explicit differential cards.
    visible_items = [p for p in differential_items if p.get("id") != "uti"]

    st.subheader("Differential To Consider")
    with st.container(border=True):
        if not visible_items:
            st.write("No differential items generated yet.")
        else:
            for item in visible_items:
                src = source_catalog.get(item["id"])
                status_line = f"{item['priority']} | {item['status']}"
                if src:
                    st.markdown(f"- **{item['name']}** ({status_line}) - [Pathway Link]({src['url']})")
                else:
                    st.markdown(f"- **{item['name']}** ({status_line})")

    st.subheader("Recommendations (Scraped From Relevant CHOP Pathways)")
    with st.container(border=True):
        chop_items = []
        for item in visible_items:
            src = source_catalog.get(item["id"])
            if src and src.get("publisher") == "chop" and "chop.edu" in src.get("url", ""):
                chop_items.append((item, src))

        if not chop_items:
            st.write("No relevant CHOP pathways in the current differential.")
        else:
            shown_urls = set()
            for item, src in chop_items:
                if src["url"] in shown_urls:
                    continue
                shown_urls.add(src["url"])

                st.markdown(f"**{item['name']}**")
                st.markdown(f"[Open CHOP Pathway]({src['url']})")
                scraped = scrape_chop_recommendations(src["url"])
                if not scraped["ok"]:
                    st.caption(f"Could not scrape recommendations: {scraped['error']}")
                    continue
                recs = scraped.get("recommendations", [])
                if not recs:
                    st.caption("No recommendation snippets were detected on this page.")
                    continue
                for rec in recs:
                    st.markdown(f"- {rec}")

    st.subheader("Pathway Navigator (Live)")
    with st.container(border=True):
        candidate_ids = [item["id"] for item in visible_items if (PATHWAYS_DIR / f"{item['id']}.yaml").exists()]
        if not candidate_ids:
            st.write("No navigable pathway available for current selections.")
        else:
            if st.session_state.get("nav_selected_pathway") not in candidate_ids:
                st.session_state.nav_selected_pathway = candidate_ids[0]

            selected_id = st.selectbox(
                "Selected pathway",
                candidate_ids,
                index=candidate_ids.index(st.session_state.nav_selected_pathway),
                key="nav_selected_pathway",
            )
            render_navigator(selected_id)


if __name__ == "__main__":
    main()
