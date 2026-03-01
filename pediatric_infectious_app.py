"""Streamlit app for pediatric infectious disease differential and next steps.

Educational support tool only. Outputs are framed as considerations and rule-outs,
not definitive diagnoses. Always follow local pathways and clinician judgment.
"""

from __future__ import annotations

from typing import Dict, List

try:
    import streamlit as st
except ModuleNotFoundError:  # Enables logic testing in environments without Streamlit installed.
    st = None


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


def main() -> None:
    if st is None:
        raise RuntimeError("Streamlit is not installed. Install dependencies from requirements.txt.")
    st.set_page_config(page_title="Pediatric Infectious Disease Differential", layout="centered")
    st.title("Pediatric Infectious Disease Differential Tool")
    st.caption(
        "Educational decision support only. Use to broaden differential and prioritize rule-outs; "
        "final decisions require clinician judgment and local pathways."
    )

    if "last_assessment" not in st.session_state:
        st.session_state["last_assessment"] = None
    if "generation_count" not in st.session_state:
        st.session_state["generation_count"] = 0

    with st.form("patient_form"):
        st.subheader("Patient details")
        col1, col2, col3 = st.columns(3)
        with col1:
            age_years = st.number_input("Age (years)", min_value=0, max_value=18, value=1, step=1)
        with col2:
            age_month_remainder = st.number_input("Additional months", min_value=0, max_value=11, value=0, step=1)
        with col3:
            fever_days = st.number_input("Fever duration (days)", min_value=0, max_value=60, value=1, step=1)

        computed_age_months = int(age_years * 12 + age_month_remainder)
        st.write(f"Computed age: **{computed_age_months} months** ({computed_age_months / 12:.2f} years)")

        st.subheader("Symptoms")
        symptom_options = [
            "Cough",
            "Wheeze",
            "Runny or stuffy nose",
            "Sore throat",
            "Ear pain",
            "Difficulty breathing",
            "Vomiting or diarrhea",
            "Abdominal pain",
            "Burning/Frequent urination",
            "Rash",
            "Poor feeding or irritability",
            "Headache",
            "Joint pain",
            "Limp",
            "Neck stiffness",
            "Seizure",
            "Altered mental status",
            "Rapidly progressive severe pain",
            "Pain out of proportion",
        ]
        symptoms = st.multiselect("Select symptoms", symptom_options)

        st.subheader("Exam findings")
        exam_options = [
            "Conjunctival injection",
            "Oral mucosal changes",
            "Swollen lymph nodes",
            "Extremity changes",
            "Rash",
            "Tachypnea or increased work of breathing",
            "Hypoxia (SpO2 < 90%)",
            "Signs of dehydration",
            "Fluctuant skin lesion",
            "Tender skin",
        ]
        exam = st.multiselect("Select exam findings", exam_options)

        st.subheader("Risk flags")
        col_a, col_b = st.columns(2)
        with col_a:
            toxic = st.checkbox("Toxic / ill-appearing")
            unstable = st.checkbox("Hemodynamic instability (e.g., hypotension/poor perfusion)")
        with col_b:
            high_risk = st.checkbox("Immunocompromised / high risk")
            fever_without_source = st.checkbox("Fever without obvious source")

        submitted = st.form_submit_button("Generate assessment")

    if submitted:
        st.session_state["last_assessment"] = generate_assessment(
            age_months=computed_age_months,
            fever_days=int(fever_days),
            symptoms=symptoms,
            exam=exam,
            high_risk=high_risk,
            toxic=toxic,
            unstable=unstable,
            fever_without_source=fever_without_source,
        )
        st.session_state["generation_count"] += 1

    if st.session_state["last_assessment"] is not None:
        assessment = st.session_state["last_assessment"]
        st.subheader("Assessment")
        st.caption(f"Generated assessment run #{st.session_state['generation_count']}")
        with st.expander("Cannot miss / rule out now", expanded=True):
            _render_list(assessment["cannot_miss"], "No immediate red-flag diagnoses triggered from current inputs.")

        with st.expander("Common considerations", expanded=True):
            _render_list(assessment["common"], "No specific common etiology flagged from entered features.")

        with st.expander("If prolonged/worsening", expanded=True):
            _render_list(
                assessment["prolonged_or_special"],
                "No prolonged-fever pathway triggered yet; reassess if fever persists or new features emerge.",
            )

        with st.expander("Suggested workup", expanded=True):
            _render_list(assessment["recommended_workup"], "Use local pathway-guided targeted workup.")

        with st.expander("Initial management (high level)", expanded=True):
            _render_list(
                assessment["recommended_initial_management"],
                "Provide supportive care, monitor closely, and escalate based on trajectory.",
            )

        with st.expander("Consults / disposition tips", expanded=True):
            st.markdown("**Consults**")
            _render_list(assessment["consults"], "No immediate specialty consult triggered by current inputs.")
            st.markdown("**Admit considerations**")
            _render_list(assessment["admit_considerations"], "Consider outpatient management only if low risk and reliable follow-up.")
            st.markdown("**Discharge considerations**")
            _render_list(assessment["discharge_considerations"], "Use strict return precautions and timely follow-up.")


if __name__ == "__main__":
    main()
