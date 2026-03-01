from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from logic.router import route_patient
from logic.uticalc_pretest import uticalc_pretest_percent
from logic.centor import compute_centor_score
from yaml_compat import safe_load


ROOT = Path(__file__).resolve().parent
PATHWAYS_DIR = ROOT / "pathways"
SOURCES_PATH = ROOT / "source" / "sources.yaml"
st.set_page_config(page_title="Pediatric Infectious Pathway Router", layout="wide")


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


def _priority_sort_value(priority: str) -> int:
    order = {"CRITICAL": 0, "HIGH": 1, "NORMAL": 2}
    return order.get(priority, 3)


def _badge_css_class(item: Dict[str, Any]) -> str:
    priority = str(item.get("priority", "NORMAL")).upper()
    status = str(item.get("status", "CONSIDER")).upper()
    if priority == "CRITICAL":
        return "badge-critical"
    if priority == "HIGH":
        return "badge-high"
    if status == "CONSIDER":
        return "badge-consider"
    return "badge-normal"


def _render_pathway_card(item: Dict[str, Any], source_catalog: Dict[str, Dict[str, Any]]) -> None:
    reason_text = str(item.get("reason", "")).strip()
    reasons = [r.strip() for r in reason_text.split(";") if r.strip()]
    if not reasons:
        reasons = ["No activation reason provided."]
    badge_class = _badge_css_class(item)
    status_line = f"{item.get('priority', 'NORMAL')} | {item.get('status', 'CONSIDER')}"
    critical_class = " router-card-critical" if str(item.get("priority", "")).upper() == "CRITICAL" else ""
    src = source_catalog.get(str(item.get("id")))

    reasons_html = "".join(f"<li>{reason}</li>" for reason in reasons)
    link_html = ""
    if src and src.get("url"):
        link_html = f"<a class='router-link' href='{src['url']}' target='_blank'>Open pathway</a>"

    st.markdown(
        f"""
        <div class="router-card{critical_class}">
          <div class="router-card-header">
            <div class="router-card-title">{item.get("name", "Untitled Pathway")}</div>
            <span class="router-badge {badge_class}">{status_line}</span>
          </div>
          <ul class="router-reasons">{reasons_html}</ul>
          {link_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def age_months_from_days(age_days: int) -> float:
    return age_days / 30.4375


def c_to_f(celsius: float) -> float:
    return (celsius * 9.0 / 5.0) + 32.0


def f_to_c(fahrenheit: float) -> float:
    return (fahrenheit - 32.0) * 5.0 / 9.0


def sync_tmax_from_c() -> None:
    st.session_state["tmax_f"] = round(c_to_f(float(st.session_state["tmax_c"])), 1)


def sync_tmax_from_f() -> None:
    st.session_state["tmax_c"] = round(f_to_c(float(st.session_state["tmax_f"])), 1)


@st.cache_data
def load_source_catalog() -> Dict[str, Dict[str, Any]]:
    data = safe_load(SOURCES_PATH.read_text()) or {}
    pathways = data.get("pathways", [])
    return {p["id"]: p for p in pathways if "id" in p}


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg-main: #eef3f9;
            --bg-panel: #f5f8fc;
            --card-bg: #ffffff;
            --text-main: #1e2a3a;
            --text-muted: #607086;
            --border-soft: #d8e1ec;
            --accent: #295b8f;
            --accent-soft: #e8f0fa;
            --critical-bg: #f2e8ea;
            --critical-text: #6b3a43;
            --high-bg: #efeaf7;
            --high-text: #4f3f72;
            --normal-bg: #e8eef6;
            --normal-text: #314a68;
            --consider-bg: #ecf1f7;
            --consider-text: #4f6379;
        }
        .stApp {
            background: linear-gradient(180deg, #f2f6fb 0%, var(--bg-main) 100%);
            color: var(--text-main);
            font-family: "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        }
        .main .block-container {
            max-width: 1120px;
            padding-top: 1.2rem;
        }
        .stMarkdown, .stText, .stCaption, p, label, div {
            color: var(--text-main);
        }
        .router-title {
            margin: 0 0 0.6rem 0;
            font-size: clamp(1.5rem, 2.2vw, 2.2rem);
            line-height: 1.1;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            color: #18314f;
            letter-spacing: 0.15px;
            font-weight: 700;
            text-align: center;
            width: 100%;
        }
        [data-testid="stMarkdownContainer"] h2 {
            color: #1e3a59;
            font-weight: 700;
        }
        [data-testid="stCaptionContainer"] {
            color: var(--text-muted);
        }
        [data-testid="stNumberInput"] input,
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
        [data-testid="stCheckbox"] label,
        [data-testid="stMultiSelect"] div[data-baseweb="select"] > div,
        [data-testid="stTextInput"] input {
            border: 1px solid var(--border-soft);
            background: var(--card-bg);
            border-radius: 10px;
        }
        [data-testid="stNumberInput"] input:focus,
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div:focus-within,
        [data-testid="stMultiSelect"] div[data-baseweb="select"] > div:focus-within,
        [data-testid="stTextInput"] input:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 2px rgba(41, 91, 143, 0.18);
        }
        [data-testid="stVerticalBlock"] > [data-testid="stContainer"] {
            border: 1px solid var(--border-soft) !important;
            background: var(--card-bg);
            border-radius: 15px;
            box-shadow: 0 6px 18px rgba(26, 44, 67, 0.07);
            padding: 0.15rem 0.2rem;
        }
        [data-testid="stSidebar"] > div {
            background: var(--bg-panel);
            border-right: 1px solid var(--border-soft);
        }
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            background: transparent;
            padding: 0.4rem 0.35rem;
        }
        .router-card {
            background: var(--card-bg);
            border: 1px solid var(--border-soft);
            border-radius: 15px;
            box-shadow: 0 4px 14px rgba(25, 42, 62, 0.06);
            padding: 0.8rem 0.95rem 0.75rem 0.95rem;
            margin: 0 0 0.65rem 0;
        }
        .router-card-critical {
            border-left: 5px solid #8a5a66;
        }
        .router-card-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 0.6rem;
            margin-bottom: 0.35rem;
        }
        .router-card-title {
            font-size: 0.99rem;
            font-weight: 650;
            color: var(--text-main);
            line-height: 1.25;
        }
        .router-badge {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 0.16rem 0.56rem;
            font-size: 0.71rem;
            letter-spacing: 0.02em;
            font-weight: 600;
            white-space: nowrap;
            border: 1px solid transparent;
        }
        .badge-critical {
            background: var(--critical-bg);
            color: var(--critical-text);
            border-color: #d9c4c9;
        }
        .badge-high {
            background: var(--high-bg);
            color: var(--high-text);
            border-color: #d6cbe9;
        }
        .badge-normal {
            background: var(--normal-bg);
            color: var(--normal-text);
            border-color: #cfdaea;
        }
        .badge-consider {
            background: var(--consider-bg);
            color: var(--consider-text);
            border-color: #d4deea;
        }
        .router-reasons {
            margin: 0.2rem 0 0.5rem 0;
            padding-left: 1rem;
            color: var(--text-muted);
        }
        .router-reasons li {
            margin: 0.12rem 0;
            line-height: 1.3;
        }
        .router-link {
            font-size: 0.84rem;
            color: var(--accent);
            text-decoration: none;
            font-weight: 550;
        }
        .router-link:hover {
            text-decoration: underline;
        }
        .router-note {
            color: var(--text-muted);
            margin: 0.1rem 0 0.5rem 0;
            font-size: 0.9rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    apply_theme()
    st.markdown('<h1 class="router-title">Pediatric Infectious Pathway Router</h1>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        years = int(st.number_input("Years", min_value=0, max_value=21, value=1))
    with col2:
        months = int(st.number_input("Months", min_value=0, max_value=11, value=0))
    age_days = years * 365 + months * 30

    st.caption(f"Computed age_days: {age_days}")
    age_months = age_months_from_days(age_days)
    sex_col, circ_col = st.columns(2)
    with sex_col:
        sex = st.radio("Sex", ["female", "male"], horizontal=True)
    with circ_col:
        circumcised: Optional[bool] = None
        if sex == "male":
            circumcised = st.checkbox("Circumcised", value=True)

    ga_weeks = None
    if age_days < 60:
        ga_preterm = st.checkbox("Gestational age <37 weeks", value=False)
        if ga_preterm:
            ga_weeks = int(st.number_input("Gestational age at birth (weeks)", min_value=22, max_value=36, value=35))
        ill_infant = st.checkbox("Ill-appearing infant", value=False)
    else:
        ill_infant = False

    fever_days = int(st.number_input("Fever duration (days)", min_value=0, max_value=30, value=1))
    immunization_status = st.selectbox(
        "Immunization Status",
        ["Up To Date", "Underimmunized", "Unknown"],
        index=0,
    )
    if "tmax_c" not in st.session_state and "tmax_f" not in st.session_state:
        st.session_state["tmax_c"] = 38.5
        st.session_state["tmax_f"] = round(c_to_f(38.5), 1)
    elif "tmax_c" not in st.session_state and "tmax_f" in st.session_state:
        st.session_state["tmax_c"] = round(f_to_c(float(st.session_state["tmax_f"])), 1)
    elif "tmax_f" not in st.session_state and "tmax_c" in st.session_state:
        st.session_state["tmax_f"] = round(c_to_f(float(st.session_state["tmax_c"])), 1)

    tcol1, tcol2 = st.columns(2)
    with tcol1:
        st.number_input(
            "Tmax (C)",
            min_value=35.0,
            max_value=43.0,
            step=0.1,
            key="tmax_c",
            on_change=sync_tmax_from_c,
        )
    with tcol2:
        st.number_input(
            "Tmax (F)",
            min_value=95.0,
            max_value=109.4,
            step=0.1,
            key="tmax_f",
            on_change=sync_tmax_from_f,
        )
    tmax_c = float(st.session_state["tmax_c"])
    ill_appearing = st.checkbox("Ill appearing", value=ill_infant)
    hemodynamic_instability = st.checkbox("Hemodynamic instability", value=False)
    altered_mental_status = st.checkbox("Altered mental status", value=False)
    immunocompromised_or_onc = st.checkbox("Immunocompromised or oncology patient", value=False)

    st.subheader("Clinical Findings")
    findings_map = {
        "Cough": "cough",
        "Nasal Congestion": "nasal_congestion",
        "Sore Throat": "sore_throat",
        "Vomiting": "vomiting",
        "Diarrhea": "diarrhea",
        "Rash": "rash",
        "Hypoxia": "hypoxia",
        "Respiratory Distress": "respiratory_distress",
        "Wheeze": "wheeze",
        "Stridor": "stridor",
        "Barky Cough": "barky_cough",
        "Seizure": "seizure",
        "Neck Stiffness": "neck_stiffness",
        "Severe Headache": "severe_headache",
        "Drooling": "drooling",
        "Muffled Voice": "muffled_voice",
        "Trismus": "trismus",
        "Neck Swelling": "neck_swelling",
        "Eye Swelling": "eye_swelling",
        "Periorbital Erythema": "periorbital_erythema",
        "Pain With EOM": "pain_with_eom",
        "Dysuria": "dysuria",
        "Flank Pain": "flank_pain",
        "Fever Without Source": "fever_without_source",
        "Localized Erythema": "localized_erythema",
        "Warmth Or Tenderness": "warmth_or_tenderness",
        "Fluctuance Or Purulence": "fluctuance_or_purulence",
        "Localized Swelling": "localized_swelling",
        "Joint Pain": "joint_pain",
        "Limp": "limp",
        "Refusal To Bear Weight": "refusal_to_bear_weight",
        "Conjunctivitis": "conjunctivitis",
        "Coryza": "coryza",
        "Myalgias": "myalgias",
        "Chills": "chills",
        "Fatigue": "fatigue",
        "Koplik Spots": "koplik_spots",
        "Strawberry Tongue": "strawberry_tongue",
        "Fissured Lips": "fissured_lips",
        "Cervical Lymphadenopathy": "cervical_lymphadenopathy",
        "Swelling Of Hands And Feet": "extremity_changes",
        "Severe Focal Abdominal Pain": "severe_focal_abdominal_pain",
    }
    finding_labels = list(findings_map.keys())
    selected_labels = st.multiselect("Select findings", finding_labels)
    selected_keys = [findings_map[label] for label in selected_labels]
    sore_throat_selected = "sore_throat" in selected_keys
    rash_detail_features: List[str] = []
    rash_morphology = "none"
    rash_head_to_toes = False
    rash_trunk_to_face_ext = False
    rash_sandpaper = False
    rash_herald_patch = False
    rash_slapped_cheek = False
    rash_posterior_nodes = False
    rash_vesicular = False
    if "rash" in selected_keys:
        st.caption("Rash features (shown only when rash is selected)")
        rash_morphology = st.selectbox("Rash Morphology", ["none", "scaly", "maculopapular", "vesicular"], index=0)
        c1, c2 = st.columns(2)
        with c1:
            rash_sandpaper = st.checkbox("Sandpaper-like rash", value=False)
            rash_herald_patch = st.checkbox("Herald patch / Christmas-tree distribution", value=False)
            rash_slapped_cheek = st.checkbox("Slapped-cheek appearance", value=False)
        with c2:
            rash_head_to_toes = st.checkbox("Head-to-toes spread", value=False)
            rash_trunk_to_face_ext = st.checkbox("Trunk to face/extremities spread", value=False)
            rash_posterior_nodes = st.checkbox("Posterior auricular lymphadenopathy", value=False)
            rash_vesicular = st.checkbox("Vesicular lesions", value=False)

        if rash_sandpaper:
            rash_detail_features.append("Sandpaper Rash")
        if rash_slapped_cheek:
            rash_detail_features.append("Slapped Cheek")
        if rash_posterior_nodes:
            rash_detail_features.append("Posterior Auricular Lymphadenopathy")
        if rash_herald_patch:
            rash_detail_features.append("Herald Patch / Christmas Tree Distribution")
        if rash_vesicular:
            rash_detail_features.append("Vesicular Lesions")
    bloody_diarrhea = False
    if "diarrhea" in selected_keys:
        bloody_diarrhea = st.checkbox("Bloody Diarrhea", value=False)

    kd_features = 0

    patient = {
        "age_days": age_days,
        "age_months": age_months,
        "ga_weeks": ga_weeks,
        "fever_days": fever_days,
        "immunization_status": immunization_status,
        "ill_appearing": ill_appearing,
        "hemodynamic_instability": hemodynamic_instability,
        "altered_mental_status": altered_mental_status,
        "immunocompromised_or_onc": immunocompromised_or_onc,
        "kd_features": kd_features,
        "uticalc": {
            "sex": sex,
            "circumcised": circumcised,
            "tmax_ge_39": None,
            "tmax_c": tmax_c,
            "other_source": True,  # computed from feature selection below
        },
    }

    all_flags = list(findings_map.values())
    for flag in all_flags:
        patient[flag] = False
    for flag in selected_keys:
        patient[flag] = True
    flu_like_count = sum(
        int(bool(patient.get(k)))
        for k in ["cough", "sore_throat", "coryza", "nasal_congestion", "myalgias", "chills", "fatigue"]
    )
    patient["influenza_like_illness"] = bool((flu_like_count >= 2) or (fever_days > 0 and flu_like_count >= 1))
    patient["high_fever"] = bool(tmax_c >= 40.0)  # ~104F threshold for rash logic.
    patient["high_fever_3_4_days_before_rash"] = bool(tmax_c >= 40.0 and fever_days in {3, 4})
    patient["sandpaper_rash"] = "Sandpaper Rash" in rash_detail_features
    patient["slapped_cheek"] = "Slapped Cheek" in rash_detail_features
    patient["posterior_auricular_lymphadenopathy"] = "Posterior Auricular Lymphadenopathy" in rash_detail_features
    patient["herald_patch_christmas_tree"] = "Herald Patch / Christmas Tree Distribution" in rash_detail_features
    patient["vesicular_lesions"] = ("Vesicular Lesions" in rash_detail_features) or (rash_morphology == "vesicular")
    patient["rash_morphology"] = rash_morphology
    patient["head_to_toes_spread"] = bool(rash_head_to_toes)
    patient["trunk_to_face_extremities_spread"] = bool(rash_trunk_to_face_ext)
    patient["bloody_diarrhea"] = bool(bloody_diarrhea)
    patient["uticalc"]["other_source"] = not bool(patient.get("fever_without_source"))

    # Robust KD principal-feature counting to support fever+feature consideration logic.
    kd_conjunctivitis = bool(patient.get("conjunctivitis"))
    kd_oral_changes = bool(patient.get("strawberry_tongue") or patient.get("fissured_lips"))
    kd_rash = bool(patient.get("rash"))
    kd_extremity = bool(patient.get("extremity_changes"))
    kd_nodes = bool(patient.get("cervical_lymphadenopathy"))
    kd_features = sum([kd_conjunctivitis, kd_oral_changes, kd_rash, kd_extremity, kd_nodes])
    patient["kd_features"] = kd_features

    show_centor_module = sore_throat_selected
    centor_result: Optional[Dict[str, object]] = None
    if show_centor_module:
        st.subheader("Centor / McIsaac risk estimate")
        centor_fever_gt_38 = bool(tmax_c > 38.0)
        c1, c2 = st.columns(2)
        with c1:
            centor_exudate_or_swelling = st.checkbox("Tonsillar exudate or swelling", value=False)
            centor_tender_anterior_cervical_nodes = st.checkbox("Tender/swollen anterior cervical lymph nodes", value=False)
        with c2:
            st.checkbox(
                "Temperature >38C / 100.4F (auto from Tmax)",
                value=centor_fever_gt_38,
                disabled=True,
            )
            centor_cough_absent = st.checkbox("Cough absent", value=not bool(patient.get("cough")))

        centor_result = compute_centor_score(
            age_years=age_days / 365.0,
            tonsillar_exudate_or_swelling=centor_exudate_or_swelling,
            tender_anterior_cervical_nodes=centor_tender_anterior_cervical_nodes,
            fever_gt_38=centor_fever_gt_38,
            cough_absent=centor_cough_absent,
        )

        patient["centor_exudate_or_swelling"] = centor_exudate_or_swelling
        patient["centor_tender_anterior_cervical_nodes"] = centor_tender_anterior_cervical_nodes
        patient["centor_fever_gt_38"] = centor_fever_gt_38
        patient["centor_cough_absent"] = centor_cough_absent

        st.markdown("**Interpretation Table**")
        st.table(
            [
                {"Score": "0", "Probability": "1-2.5%", "Recommendation": "No further testing or antibiotics."},
                {
                    "Score": "1",
                    "Probability": "5-10%",
                    "Recommendation": "No further testing or antibiotics.",
                },
                {
                    "Score": "2",
                    "Probability": "11-17%",
                    "Recommendation": "Optional rapid strep testing and/or culture.",
                },
                {
                    "Score": "3",
                    "Probability": "28-35%",
                    "Recommendation": "Consider rapid strep testing and/or culture.",
                },
                {
                    "Score": ">=4",
                    "Probability": "51-53%",
                    "Recommendation": "Consider rapid strep testing and/or culture. Empiric antibiotics may be appropriate depending on the specific scenario.",
                },
            ]
        )

        st.markdown("**Breakdown**")
        st.table(centor_result["breakdown"])
        st.markdown(f"**Total score: {centor_result['score']}**")
        st.markdown(
            f"**Selected row:** Score {centor_result['score'] if int(centor_result['score']) < 4 else '>=4'} "
            f"-> Probability {centor_result['probability_range']} -> Recommendation: {centor_result['recommendation']}"
        )
        st.caption(f"Probability: {centor_result['probability_range']} | Recommendation: {centor_result['recommendation']}")
        st.caption("Centor / McIsaac risk estimate does not replace clinical judgment.")
    else:
        patient["centor_exudate_or_swelling"] = False
        patient["centor_tender_anterior_cervical_nodes"] = False
        patient["centor_fever_gt_38"] = False
        patient["centor_cough_absent"] = False

    # Explicit live UTICalc recomputation on every rerun using current inputs.
    live_uticalc_pretest = uticalc_pretest_percent(
        age_months=age_months,
        sex=sex,
        circumcised=circumcised,
        other_source=bool(patient["uticalc"]["other_source"]),
        tmax_c=tmax_c,
    )

    # Real-time update on every rerun.
    result = route_patient(patient)
    source_catalog = load_source_catalog()

    with st.expander("Debug: triggered rules", expanded=False):
        for row in result.get("rule_trace", []):
            prefix = "FIRED" if row.get("fired") else "NOPE"
            st.write(f"- {prefix} | {row.get('rule_id')}: {row.get('details')}")

    differential_items: List[Dict[str, Any]] = result.get("pathways", [])
    uti_item = next((p for p in differential_items if p.get("id") == "uti"), None)

    uti_symptom_triggered = bool(patient.get("dysuria") or patient.get("flank_pain") or patient.get("fever_without_source"))
    visible_items = [p for p in differential_items if (p.get("id") != "uti" or uti_symptom_triggered)]
    visible_items = sorted(
        visible_items,
        key=lambda item: (
            _priority_sort_value(str(item.get("priority", "NORMAL"))),
            0 if str(item.get("status", "CONSIDER")).upper() == "ACTIVE" else 1,
            str(item.get("name", "")).lower(),
        ),
    )

    st.subheader("Differential To Consider")
    with st.container(border=True):
        fever_general = source_catalog.get("fever_general")
        if fever_days > 0 or tmax_c >= 38.0:
            if fever_general:
                st.markdown(
                    f"- **Baseline consideration:** Most pediatric febrile illnesses are viral/self-limited. "
                    f"Continue red-flag screening and reassessment. "
                    f"[Fever General Pathway]({fever_general['url']})"
                )
            else:
                st.markdown(
                    "- **Baseline consideration:** Most pediatric febrile illnesses are viral/self-limited. "
                    "Continue red-flag screening and reassessment."
                )
        st.markdown("<div class='router-note'>Pathways are ranked by urgency and confidence.</div>", unsafe_allow_html=True)
        if immunization_status in {"Underimmunized", "Unknown"}:
            st.markdown(
                "- **Immunization-related consideration:** Underimmunized/unknown status may increase concern for "
                "vaccine-preventable etiologies and broader serious bacterial infection differential."
            )
        if 2 <= age_months <= 24 and live_uticalc_pretest is not None:
            uti_text = f"UTICalc pretest (embedded): {live_uticalc_pretest:.2f}%"
            if uti_item and uti_item.get("status") == "ACTIVE":
                uti_text += " -> UTI considered"
            st.markdown(f"- **{uti_text}**")
        if centor_result is not None and int(centor_result["score"]) <= 1:
            pharyngitis_src = source_catalog.get("pharyngitis")
            if pharyngitis_src:
                st.markdown(
                    f"- **Centor score {centor_result['score']} (no auto-activation):** Manual pathway access - "
                    f"[Pharyngitis Pathway]({pharyngitis_src['url']})"
                )
        if not visible_items:
            st.write("No differential items generated yet.")
        else:
            for item in visible_items:
                _render_pathway_card(item, source_catalog)

    assessment = generate_assessment(
        age_months=int(round(age_months)),
        fever_days=fever_days,
        symptoms=selected_labels,
        exam=[],
        high_risk=immunocompromised_or_onc,
        toxic=ill_appearing,
        unstable=hemodynamic_instability,
        fever_without_source=bool(patient.get("fever_without_source")),
    )

    st.subheader("Next Steps To Consider")
    with st.container(border=True):
        step_items: List[str] = []
        if immunization_status in {"Underimmunized", "Unknown"}:
            step_items.append(
                "Testing/Imaging: Consider expanded evaluation for vaccine-preventable and invasive bacterial causes per local protocol."
            )
            step_items.append(
                "Supportive Care/Treatment: Use lower threshold for reassessment and escalation if clinical course worsens."
            )
        for entry in assessment.get("recommended_workup", []):
            step_items.append(f"Testing/Imaging: {entry}")
        for entry in assessment.get("recommended_initial_management", []):
            step_items.append(f"Supportive Care/Treatment: {entry}")
        for entry in assessment.get("consults", []):
            step_items.append(f"Consults: {entry}")
        for entry in assessment.get("admit_considerations", []):
            step_items.append(f"Disposition: {entry}")
        if centor_result is not None:
            step_items.append(
                f"Testing/Imaging: Centor total {centor_result['score']} with probability {centor_result['probability_range']}. {centor_result['recommendation']}"
            )

        if not step_items:
            st.write("No specific next-step suggestions generated for this input set.")
        else:
            for item in step_items:
                st.markdown(f"- {item}")

if __name__ == "__main__":
    main()
