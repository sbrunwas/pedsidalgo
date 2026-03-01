from logic.centor import compute_centor_score


def test_age_band_3_to_14_gets_plus_one():
    r = compute_centor_score(
        age_years=3,
        tonsillar_exudate_or_swelling=False,
        tender_anterior_cervical_nodes=False,
        fever_gt_38=False,
        cough_absent=False,
    )
    age_row = next(x for x in r["breakdown"] if x["name"] == "Age")
    assert age_row["points"] == 1


def test_age_band_15_to_44_gets_zero():
    r = compute_centor_score(
        age_years=15,
        tonsillar_exudate_or_swelling=False,
        tender_anterior_cervical_nodes=False,
        fever_gt_38=False,
        cough_absent=False,
    )
    age_row = next(x for x in r["breakdown"] if x["name"] == "Age")
    assert age_row["points"] == 0


def test_age_band_45_plus_gets_minus_one():
    r = compute_centor_score(
        age_years=45,
        tonsillar_exudate_or_swelling=False,
        tender_anterior_cervical_nodes=False,
        fever_gt_38=False,
        cough_absent=False,
    )
    age_row = next(x for x in r["breakdown"] if x["name"] == "Age")
    assert age_row["points"] == -1


def test_age_under_three_gets_zero_points():
    r = compute_centor_score(
        age_years=1,
        tonsillar_exudate_or_swelling=False,
        tender_anterior_cervical_nodes=False,
        fever_gt_38=False,
        cough_absent=False,
    )
    age_row = next(x for x in r["breakdown"] if x["name"] == "Age")
    assert age_row["points"] == 0


def test_total_score_not_negative():
    r = compute_centor_score(
        age_years=50,
        tonsillar_exudate_or_swelling=False,
        tender_anterior_cervical_nodes=False,
        fever_gt_38=False,
        cough_absent=False,
    )
    assert r["score"] == 0


def test_score_gte_four_uses_highest_probability_row():
    r = compute_centor_score(
        age_years=10,
        tonsillar_exudate_or_swelling=True,
        tender_anterior_cervical_nodes=True,
        fever_gt_38=True,
        cough_absent=True,
    )
    assert r["score"] >= 4
    assert r["probability_range"] == "51-53%"
    assert "Empiric antibiotics may be appropriate depending on the specific scenario." in r["recommendation"]


def test_score_two_mapping():
    r = compute_centor_score(
        age_years=25,
        tonsillar_exudate_or_swelling=True,
        tender_anterior_cervical_nodes=True,
        fever_gt_38=False,
        cough_absent=False,
    )
    assert r["score"] == 2
    assert r["probability_range"] == "11-17%"
    assert r["recommendation"] == "Optional rapid strep testing and/or culture."
