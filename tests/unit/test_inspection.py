from datetime import date

import pyarrow as pa

from energy_intelligence.validation.inspection import curtailment_checks, profile_table

DAILY = pa.table({
    "fecha": [date(2024, 1, 1), date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 2)],
    "central_codigo": ["A", "B", "A", "B"],
    "tecnologia": ["Solar", "Eólica", "Solar", "Eólica"],
    "mwh": [0.0, 30.0, 120.0, 0.0],
})
METADATA = pa.table({"central_codigo": ["A", "B"], "potencia_mw": [10.0, 100.0], "match_metodo": ["exacto", "exacto"]})


def test_profile_reports_nulls_ranges_and_distinct():
    table = pa.table({"fecha": [date(2024, 1, 1), None], "central_codigo": ["A", "A"]})

    profile = profile_table("t", table)

    fecha, codigo = profile.columns
    assert profile.rows == 2
    assert fecha.null_pct == 50
    assert (fecha.minimum, fecha.maximum) == (date(2024, 1, 1), date(2024, 1, 1))
    assert codigo.distinct == 1


def test_curtailment_checks_totals_and_zero_share():
    checks = curtailment_checks("daily", DAILY, METADATA)

    assert checks.total_mwh == 150
    assert checks.zero_pct == 50
    assert checks.plants == 2
    assert checks.plant_technology_pairs == 2


def test_curtailment_above_capacity_is_flagged():
    # A tiene 10 MW: como máximo 240 MWh al día. 120 MWh es válido, 300 no.
    over = DAILY.set_column(3, "mwh", pa.array([0.0, 30.0, 300.0, 0.0]))

    checks = curtailment_checks("daily", over, METADATA)

    assert [row["central_codigo"] for row in checks.over_capacity] == ["A"]
    assert checks.max_daily_ratio == 300 / 240


def test_no_flags_when_within_capacity():
    assert curtailment_checks("daily", DAILY, METADATA).over_capacity == []
