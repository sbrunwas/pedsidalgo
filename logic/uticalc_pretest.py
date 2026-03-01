"""UTICalc pretest lookup for children 2-24 months."""

from __future__ import annotations

from typing import Optional


# Table values are percentages from the provided eFigure-derived lookup table.
_TABLE = {
    "female_or_uncirc_male": {
        "ge_39_other": {"ge_12": 2.14, "lt_12": 6.46},
        "ge_39_no_other": {"ge_12": 8.05, "lt_12": 21.51},
        "lt_39_other": {"ge_12": 0.91, "lt_12": 2.82},
        "lt_39_no_other": {"ge_12": 3.54, "lt_12": 10.41},
    },
    "circ_male": {
        "ge_39_other": {"ge_12": 0.19, "lt_12": 0.62},
        "ge_39_no_other": {"ge_12": 0.79, "lt_12": 2.45},
        "lt_39_other": {"ge_12": 0.08, "lt_12": 0.26},
        "lt_39_no_other": {"ge_12": 0.33, "lt_12": 1.04},
    },
}


def uticalc_pretest_percent(
    *,
    age_months: float,
    sex: str,
    circumcised: Optional[bool],
    other_source: bool,
    tmax_ge_39: Optional[bool] = None,
    tmax_c: Optional[float] = None,
) -> Optional[float]:
    """Return UTICalc pretest risk percent for 2-24 months inclusive, else None."""
    if age_months < 2 or age_months > 24:
        return None

    sex_norm = sex.strip().lower()
    if sex_norm == "female":
        sex_group = "female_or_uncirc_male"
    elif sex_norm == "male":
        if circumcised is None:
            raise ValueError("circumcised must be provided for male sex")
        sex_group = "circ_male" if circumcised else "female_or_uncirc_male"
    else:
        raise ValueError("sex must be 'female' or 'male'")

    if tmax_ge_39 is None:
        fever_ge_39 = bool(tmax_c is not None and tmax_c >= 39.0)
    else:
        fever_ge_39 = bool(tmax_ge_39)

    temp_key = "ge_39" if fever_ge_39 else "lt_39"
    source_key = "other" if other_source else "no_other"
    row_key = f"{temp_key}_{source_key}"

    age_key = "lt_12" if age_months < 12 else "ge_12"
    return float(_TABLE[sex_group][row_key][age_key])
