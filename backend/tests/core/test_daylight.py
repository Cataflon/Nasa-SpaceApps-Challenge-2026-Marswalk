import pytest

from app.core.daylight import (
    MARS_HOUR_S,
    ltst_hours,
    mars_ls_deg,
    mst_hours,
    solar_declination_deg,
    sunrise_sunset_min,
)

JEZERO = (18.44, 77.45)  # meta.json center (lat N, lon E)
MARS_HOUR_MIN = MARS_HOUR_S / 60.0


def test_declination_at_solstice_and_equinoxes():
    assert solar_declination_deg(90.0) == pytest.approx(25.2, abs=0.3)
    assert solar_declination_deg(270.0) == pytest.approx(-25.2, abs=0.3)
    assert solar_declination_deg(0.0) == pytest.approx(0.0, abs=1e-9)
    assert solar_declination_deg(180.0) == pytest.approx(0.0, abs=1e-9)


def test_ls_matches_mars24_worked_example():
    # Exemplul din pagina Mars24: 2000-01-06 00:00 UTC → Ls = 277,18758° (cu perturbații).
    assert mars_ls_deg("2000-01-06T00:00:00Z") == pytest.approx(277.18758, abs=0.05)


def test_mst_matches_mars24_worked_example():
    # Același exemplu Mars24: MST = 23,99425 h la meridianul 0.
    assert mst_hours("2000-01-06T00:00:00Z") == pytest.approx(23.99425, abs=0.01)


def test_ls_and_local_time_at_perseverance_landing():
    # Aterizarea Perseverance, 18 februarie 2021: anul marțian 36 abia început (Ls ≈ 5°),
    # după-amiaza la Jezero (≈ 15:53 ora locală medie).
    landing = "2021-02-18T20:55:00Z"
    assert mars_ls_deg(landing) == pytest.approx(5.2, abs=1.0)
    assert 14.5 <= ltst_hours(JEZERO[1], landing) <= 17.0


@pytest.mark.parametrize(
    "start",
    ["2021-02-18T20:55:00Z", "2022-01-01T00:00:00Z", "2023-06-15T12:00:00+00:00", "2024-03-03T07:30:00"],
)
def test_sunrise_before_sunset_and_day_length(start):
    sunrise, sunset = sunrise_sunset_min(*JEZERO, start)

    assert sunrise < sunset
    assert 0.0 <= sunset < 24 * MARS_HOUR_MIN  # primul apus de după start
    assert 10.0 <= (sunset - sunrise) / MARS_HOUR_MIN <= 14.0
    assert 0.0 <= ltst_hours(JEZERO[1], start) < 24.0


def test_same_input_same_result():
    start = "2022-01-01T00:00:00Z"
    assert len({sunrise_sunset_min(*JEZERO, start) for _ in range(10)}) == 1
