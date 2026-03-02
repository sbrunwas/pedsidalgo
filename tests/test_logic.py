from app import generate_assessment


def _joined(bucket):
    return "\n".join(bucket).lower()


def test_fever_6_days_no_symptoms_includes_kawasaki_misc_and_uti():
    assessment = generate_assessment(
        age_months=24,
        fever_days=6,
        symptoms=[],
        exam=[],
        high_risk=False,
        toxic=False,
        unstable=False,
        fever_without_source=True,
    )

    prolonged_text = _joined(assessment["prolonged_or_special"])
    cannot_miss_text = _joined(assessment["cannot_miss"])
    common_text = _joined(assessment["common"])

    assert "kawasaki" in prolonged_text
    assert "mis-c" in prolonged_text
    assert "uti" in (cannot_miss_text + common_text)


def test_one_month_fever_requires_febrile_infant_sepsis_workup_pathway():
    assessment = generate_assessment(
        age_months=1,
        fever_days=1,
        symptoms=[],
        exam=[],
        high_risk=False,
        toxic=False,
        unstable=False,
        fever_without_source=True,
    )

    cannot_miss_text = _joined(assessment["cannot_miss"])
    workup_text = _joined(assessment["recommended_workup"])

    assert "<90 days" in cannot_miss_text
    assert "blood culture" in workup_text
    assert "urine culture" in workup_text
    assert "csf" in workup_text


def test_sore_throat_without_cough_includes_gas_and_strep_test():
    assessment = generate_assessment(
        age_months=72,
        fever_days=2,
        symptoms=["Sore throat"],
        exam=["Swollen lymph nodes"],
        high_risk=False,
        toxic=False,
        unstable=False,
        fever_without_source=False,
    )

    common_text = _joined(assessment["common"])
    workup_text = _joined(assessment["recommended_workup"])

    assert "group a streptococcal" in common_text
    assert "rapid strep" in workup_text


def test_one_year_old_cough_wheeze_includes_bronchiolitis_supportive_care():
    assessment = generate_assessment(
        age_months=12,
        fever_days=2,
        symptoms=["Cough", "Wheeze"],
        exam=[],
        high_risk=False,
        toxic=False,
        unstable=False,
        fever_without_source=False,
    )

    common_text = _joined(assessment["common"])
    management_text = _joined(assessment["recommended_initial_management"])

    assert "bronchiolitis" in common_text
    assert "supportive" in management_text
