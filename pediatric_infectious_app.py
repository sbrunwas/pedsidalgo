"""
Streamlit application for pediatric infectious disease differential.

This app allows clinicians to enter patient details—age, duration of fever,
symptoms and physical exam findings—and receive a suggested differential
diagnosis and next steps.  The logic is based on guidelines compiled from
Children’s Hospital of Philadelphia pathways, UCSF consensus guidelines and
CDC recommendations.  For example, bronchiolitis management comes from
CHOP’s bronchiolitis pathway where supportive care, suctioning and oxygen
are recommended【109856319218224†L220-L307】, and pneumonia treatment follows
UCSF guidelines recommending amoxicillin for typical bacterial pneumonia
【806213690256861†L168-L199】.  Kawasaki criteria are drawn from CHOP’s
Kawasaki disease pathway【65725433074396†L236-L347】.

Disclaimer: this tool is for educational purposes only and should not be
used as a substitute for clinical judgement.  Always consult local
protocols and specialists when managing pediatric patients.
"""

import streamlit as st


def get_differential(age_years: float, fever_days: int, symptoms: list, exam: list, immunocompromised: bool):
    """Generate a differential diagnosis and management recommendations.

    Parameters
    ----------
    age_years : float
        Age of the patient in years.  Three months ≈ 0.25 years.
    fever_days : int
        Number of consecutive days with fever.
    symptoms : list of str
        List of selected symptoms.
    exam : list of str
        List of selected physical exam findings.
    immunocompromised : bool
        Whether the patient is known to be immunocompromised or has other high‑risk factors.

    Returns
    -------
    conditions : list of str
        Differential diagnoses to consider.
    recommendations : list of str
        Suggested next steps based on guidelines.
    """

    conditions = []
    recommendations = []

    # Normalize features to lower case for easier matching
    features = [f.lower() for f in (symptoms + exam)]

    # Age thresholds
    age_months = age_years * 12.0
    # Very young infants (< 3 months) – high risk for SBI
    if age_months < 3:
        conditions.append("Serious bacterial infection (sepsis, UTI, meningitis)")
        recommendations.append(
            "Infants under 3 months with fever require full sepsis work‑up (blood, urine and CSF cultures) and hospital admission for empiric IV antibiotics【507335888327708†L69-L72】."
        )

    # Sepsis or septic shock
    if immunocompromised:
        conditions.append("Sepsis or septic shock")
        recommendations.append(
            "High‑risk patients should be screened for sepsis; obtain blood cultures and begin IV fluids and broad‑spectrum antibiotics within one hour【140001994586765†L194-L203】."
        )

    # Bronchiolitis
    if ("cough" in features or "wheeze" in features) and age_years < 2:
        conditions.append("Bronchiolitis (viral lower respiratory infection)")
        recommendations.append(
            "Most cases are viral.  Provide supportive care: nasal suctioning, hydration, fever control and supplemental oxygen if SpO₂ < 90 %【109856319218224†L220-L307】.  Bronchodilators and steroids are rarely beneficial.  Consider high‑flow nasal cannula therapy if persistent increased work of breathing."
        )

    # Pneumonia / lower respiratory tract infection
    if "difficulty breathing" in features or ("cough" in features and age_years >= 2):
        conditions.append("Pneumonia or lower respiratory tract infection")
        recommendations.append(
            "Assess for respiratory distress.  For outpatients, avoid routine imaging; if typical bacterial pneumonia is suspected, treat with high‑dose amoxicillin (45 mg/kg/dose twice daily for 5 days)【806213690256861†L168-L199】.  Admit if hypoxic, dehydrated or failing outpatient therapy【806213690256861†L157-L163】.  For hospitalized children, obtain PA and lateral chest radiograph and start IV ampicillin【806213690256861†L330-L389】."
        )

    # Viral upper respiratory infection / influenza
    if "runny or stuffy nose" in features and fever_days < 5 and "cough" in features:
        conditions.append("Viral upper respiratory infection / influenza")
        recommendations.append(
            "Provide symptomatic care (fluids, antipyretics).  During influenza season, test for influenza and SARS‑CoV‑2 if results will influence management【599095123826586†L159-L170】.  Antiviral treatment with oseltamivir is recommended for hospitalized or high‑risk patients【599095123826586†L141-L171】."
        )

    # Acute bacterial sinusitis
    if ("runny or stuffy nose" in features or "nasal discharge" in features) and fever_days >= 10:
        conditions.append("Acute bacterial sinusitis")
        recommendations.append(
            "Diagnosis is clinical: persistent nasal discharge or cough >10 days, or worsening symptoms, or abrupt onset of fever ≥39 °C with purulent nasal discharge for ≥3 days【356009382797648†L35-L56】.  Treat with amoxicillin or amoxicillin‑clavulanate【356009382797648†L68-L96】; consider cephalosporin or levofloxacin for penicillin allergy【356009382797648†L78-L96】."
        )

    # Group A streptococcal pharyngitis
    if "sore throat" in features and "swollen lymph nodes" in features and "cough" not in features:
        conditions.append("Group A streptococcal (GAS) pharyngitis")
        recommendations.append(
            "Obtain rapid antigen detection test or throat culture.  If positive, treat with penicillin or amoxicillin for 10 days【420852390700442†L236-L290】.  Consider cephalexin or azithromycin for penicillin allergy【420852390700442†L270-L296】."
        )

    # Urinary tract infection
    if "burning or frequent urination" in features or "burning/frequent urination" in features:
        conditions.append("Urinary tract infection (UTI)")
        recommendations.append(
            "Obtain urinalysis and urine culture via catheterized or clean‑catch specimen; start empiric antibiotics if UA is positive and adjust based on culture【983498909858577†L220-L311】.  Admit if ill appearing, dehydrated or unable to tolerate oral therapy【983498909858577†L220-L311】."
        )

    # Meningitis
    if "neck stiffness" in features or "seizure" in features or ("headache" in features and fever_days >= 1):
        conditions.append("Meningitis")
        recommendations.append(
            "Perform blood cultures and lumbar puncture unless contraindicated.  Obtain head CT before LP if there is altered mental status, focal neurologic deficits, papilledema, recent head trauma, intracranial mass or coagulopathy【404628699029728†L208-L244】.  Start empiric IV antibiotics immediately after cultures."
        )

    # Cellulitis / abscess
    if "fluctuant lesion" in features or "fluctuant skin lesion" in features or ("rash" in features and "tender" in features):
        conditions.append("Cellulitis or abscess")
        recommendations.append(
            "Evaluate for drainable collection; use ultrasound if needed.  Incise and drain abscesses and begin antibiotics covering staphylococci and streptococci.  Admit if systemic signs or failure to improve【241280290133427†L253-L305】."
        )

    # Septic arthritis or osteomyelitis
    if "joint pain" in features or "limp" in features:
        conditions.append("Septic arthritis or osteomyelitis")
        recommendations.append(
            "Urgent evaluation by orthopedics; obtain blood cultures and imaging (ultrasound or MRI).  Start empiric IV antibiotics covering Staphylococcus aureus and streptococci."
        )

    # Kawasaki disease
    # Count principal clinical features: oral changes, conjunctival injection, extremity changes, cervical lymphadenopathy, rash
    kd_features = 0
    if "conjunctival injection" in features:
        kd_features += 1
    if "oral mucosal changes" in features or "strawberry tongue" in features:
        kd_features += 1
    if "extremity changes" in features:
        kd_features += 1
    if "swollen lymph nodes" in features:
        kd_features += 1
    if "rash" in features:
        kd_features += 1
    if fever_days >= 5:
        if kd_features >= 4:
            conditions.append("Complete Kawasaki disease")
            recommendations.append(
                "Consult cardiology and rheumatology.  Initiate IVIG (2 g/kg) and high‑dose aspirin (30–50 mg/kg/day in divided doses) followed by low‑dose aspirin after defervescence【65725433074396†L236-L347】.  Obtain baseline echocardiogram and repeat to monitor coronary arteries."
            )
        elif 2 <= kd_features <= 3:
            conditions.append("Incomplete Kawasaki disease")
            recommendations.append(
                "Consider incomplete Kawasaki disease; obtain inflammatory markers and echocardiogram.  Consult cardiology and rheumatology for guidance on IVIG therapy【65725433074396†L236-L347】."
            )

    # Fever of unknown origin / FUO
    if fever_days >= 8 and not conditions:
        conditions.append("Fever of unknown origin")
        recommendations.append(
            "Daily fever ≥38.3 °C for ≥8 days qualifies as fever of unknown origin【995604675643215†L212-L226】.  Obtain a detailed history (travel, exposures), complete physical exam and targeted laboratory work‑up.  Consider referral to infectious disease and rheumatology."
        )

    # If no specific conditions matched
    if not conditions:
        conditions.append("Non‑specific viral illness")
        recommendations.append(
            "Most short‑duration febrile illnesses in children are viral.  Provide symptomatic care and reassess if fever persists or new symptoms develop."
        )

    return conditions, recommendations


def main():
    st.set_page_config(page_title="Pediatric Infectious Disease Differential", layout="centered")
    st.title("Pediatric Infectious Disease Differential Tool")
    st.write(
        "This tool provides a differential diagnosis and suggested next steps based on patient age,\n"
        "duration of fever, symptoms and physical exam findings.  It is intended for educational\n"
        "purposes only and does not replace clinical judgement.  Always consult your local protocols."
    )

    with st.form("patient_form"):
        st.subheader("Patient details")
        col1, col2 = st.columns(2)
        with col1:
            age_years = st.number_input("Age (years)", min_value=0.0, max_value=18.0, value=1.0, step=0.1)
        with col2:
            fever_days = st.number_input("Days of fever", min_value=0, max_value=30, value=1, step=1)

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
            "Neck stiffness",
            "Seizure",
        ]
        symptoms = st.multiselect("Select all that apply", symptom_options)

        st.subheader("Physical exam findings")
        exam_options = [
            "Conjunctival injection",
            "Oral mucosal changes (e.g., strawberry tongue, red or cracked lips)",
            "Swollen lymph nodes",
            "Extremity changes (erythema, edema or peeling)",
            "Rash",
            "Tachypnea or increased work of breathing",
            "Hypoxia (SpO₂ < 90%)",
            "Signs of dehydration",
            "Fluctuant skin lesion",
        ]
        exam = st.multiselect("Select all that apply", exam_options)

        immunocompromised = st.checkbox(
            "Immunocompromised/high‑risk (e.g., central line, asplenia, malignancy)"
        )

        submitted = st.form_submit_button("Get Differential")

    if submitted:
        conditions, recs = get_differential(age_years, int(fever_days), symptoms, exam, immunocompromised)
        st.subheader("Possible diagnoses to consider")
        for cond in conditions:
            st.write(f"• {cond}")
        st.subheader("Recommended next steps")
        for rec in recs:
            st.write(f"• {rec}")


if __name__ == "__main__":
    main()
