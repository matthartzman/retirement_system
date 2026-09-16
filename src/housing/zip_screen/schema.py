"""Column names, scoring weights, and tunable constants -- no behavior.

The Neighborhood Stability Score (NSS) is derived from, but is NOT, the
"ZIP-Code Neighborhood Screening Score Framework" Rev 2.1. Only 33 of that
model's 100 points are sourceable at national ZIP granularity (the Stability
component plus Eviction Filing Rate); the Safety component has no national
ZIP-level dataset. Those 33 points are renormalized by 100/33, preserving the
source model's relative weighting among the metrics that survive.

NSS therefore measures stability, not safety. ``NSS_DISCLOSURE`` must appear
wherever a score is displayed.
"""
from __future__ import annotations

from dataclasses import dataclass

SCORE_MODEL_VERSION = 'nss-1.0'
RESPONSE_SCHEMA = 'zip_screen_v2'

NSS_DISCLOSURE = (
    'Measures housing and economic stability. Does not measure crime or safety.'
)

# PDF Rev 2.1 point allocations for the sourceable metrics, renormalized to 100.
_PDF_POINTS = {
    'owner_occupied': 8,
    'poverty': 6,
    'tenure': 5,
    'vacancy': 4,
    'eviction_execution': 4,
    'eviction_filing': 3,
    'median_income': 3,
}
_PDF_SOURCEABLE_POINTS = 33  # sum(_PDF_POINTS.values())

NSS_WEIGHTS = {
    k: v * 100.0 / _PDF_SOURCEABLE_POINTS for k, v in _PDF_POINTS.items()
}

# Each metric's precomputed-percentile column in the snapshot. quality.py reads
# only these, so it needs no distribution data of its own.
PCTL_COLUMN = {
    'owner_occupied': 'pctl_owner_occupied',
    'poverty': 'pctl_poverty',
    'tenure': 'pctl_tenure',
    'vacancy': 'pctl_vacancy_deviation',
    'eviction_execution': 'pctl_eviction_execution',
    'eviction_filing': 'pctl_eviction_filing',
    'median_income': 'pctl_median_income',
}

# True when a HIGHER percentile is the better outcome. The rest use the source
# model's Score = 100 * (1 - Percentile) (PDF section 2.2).
HIGHER_IS_BETTER = {'owner_occupied', 'tenure', 'median_income'}

# Originally calibrated at 70.0 on the assumption that Eviction Lab data
# (eviction_execution + eviction_filing, 21.2 of the 100 NSS weight points
# combined) would usually be present. Task 12's real national ingest found
# Eviction Lab now gates all downloads behind signup, so both eviction
# columns are empty for every ZIP in the shipped snapshot -- a ZIP with all
# other metrics present tops out at 78.8% coverage, and a ZIP ALSO missing
# only median_income (9.09 weight) drops to 69.7%, just under the old 70.0
# floor. That excluded ~6.7% of ZCTAs nationally over one missing metric
# rather than genuine data sparsity. 60.0 keeps the floor meaningful --
# still rejects rows missing 2+ of the 5 currently-available metrics -- while
# admitting the 69.7% near-miss tier.
COVERAGE_FLOOR_PCT = 60.0

# "Balanced market vacancy scored higher" (PDF section 2.3) made concrete: the
# metric is scored on the percentile of the ABSOLUTE DEVIATION from this rate,
# so both a starved and a glutted market are penalized.
VACANCY_IDEAL_RATE = 0.06

# University Presence Index threshold (PDF section 5).
UPI_THRESHOLD = 0.15

# De-duplication rule (spec section 5.2).
DEDUP_RADIUS_MILES = 5.0
DEDUP_SCORE_POINTS = 5.0

ALLOWED_RADII_MILES = (5, 10, 25, 50)

# PDF section 2.4, read as stability bands.
BANDS = (
    (90.0, 'Exceptional'),
    (80.0, 'Very Favorable'),
    (70.0, 'Generally Favorable'),
    (60.0, 'Mixed'),
    (50.0, 'Below Average'),
    (0.0, 'Relatively Unfavorable'),
)

COLUMNS = (
    'zcta', 'state', 'state_abbrev', 'primary_place', 'place_population',
    'zcta_population', 'land_area_sqmi', 'lat', 'lon',
    'median_home_value', 'state_median_home_value', 'upi',
    'pctl_owner_occupied', 'pctl_poverty', 'pctl_non_student_poverty',
    'pctl_tenure', 'pctl_tenure_nonstudent', 'pctl_vacancy_deviation',
    'pctl_eviction_execution', 'pctl_eviction_filing', 'pctl_median_income',
)


def band_for(score: float) -> str:
    """The PDF section 2.4 band a 0-100 NSS falls in."""
    for threshold, label in BANDS:
        if score >= threshold:
            return label
    return BANDS[-1][1]


@dataclass(frozen=True)
class ZipRecord:
    """One ZCTA row of the bundled snapshot.

    Every ``pctl_*`` field is ``None`` when that metric has no data for this
    ZCTA. quality.py renormalizes over what is present rather than zero-filling
    -- zero-filling would penalize a rural ZIP for a dataset gap instead of for
    any property of the place.
    """
    zcta: str
    state: str
    lat: float
    lon: float
    state_abbrev: str = ''
    primary_place: str = ''
    place_population: int = 0
    zcta_population: int = 0
    land_area_sqmi: float = 0.0
    median_home_value: float | None = None
    state_median_home_value: float | None = None
    upi: float = 0.0
    pctl_owner_occupied: float | None = None
    pctl_poverty: float | None = None
    pctl_non_student_poverty: float | None = None
    pctl_tenure: float | None = None
    pctl_tenure_nonstudent: float | None = None
    pctl_vacancy_deviation: float | None = None
    pctl_eviction_execution: float | None = None
    pctl_eviction_filing: float | None = None
    pctl_median_income: float | None = None

    @property
    def density(self) -> float:
        """People per square mile, 0.0 when land area is unknown."""
        if self.land_area_sqmi <= 0:
            return 0.0
        return self.zcta_population / self.land_area_sqmi
