"""Offline ingest: build src/housing/zip_screen/data/zip_metrics.csv.gz.

NOT imported at runtime -- nothing under src/ may import this module. Run it by
hand when refreshing the snapshot:

    python scripts/build_zip_metrics.py --states IL,FL,CO
    python scripts/build_zip_metrics.py --all-states

Sources (all keyless, all fetched over plain HTTPS with stdlib urllib):

  * ACS 5-year, vintage ACS_VINTAGE_YEAR, via the Census *table-based Summary
    File* rather than api.census.gov.  As of the 2024 vintage the Census data
    API rejects every unkeyed request with an HTML "Missing Key" page, and this
    build must stay runnable without a per-developer credential.  The Summary
    File carries the identical estimates for the identical vintage, is a plain
    pipe-delimited national extract keyed by GEO_ID, and needs no key:

        https://www2.census.gov/programs-surveys/acs/summary_file/
            {YEAR}/table-based-SF/data/5YRData/acsdt5y{YEAR}-{table}.dat

    Tables used: B25003 (tenure/owner-occupied), B25002 (vacancy),
    B19013 (median household income), B25038 (tenure by year moved in),
    B25077 (median home value), B14007 (school enrollment),
    B14006 (poverty by enrollment status), B01003 (total population).

  * Census Gazetteer {YEAR}: ZCTA centroids + land area, and place internal
    points + USPS state code for top_cities.csv.

  * Census 2020 geographic relationship files: ZCTA <-> county (for the state
    assignment the Gazetteer ZCTA file omits) and ZCTA <-> place (for
    primary_place).  Both carry AREALAND_PART, so a ZCTA that straddles a
    boundary is assigned to whichever county/place holds the most of its land.

  * Eviction Lab: NOT INGESTED.  See EVICTION_NOTE below.

Percentiles are computed against the FULL set of rows in this run and written
into the snapshot, so the runtime never needs distribution data. When building
a pilot subset, percentiles are therefore pilot-relative -- pass --all-states
before shipping a snapshot users will act on.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import math
import os
import sys
import tempfile
import urllib.request
import zipfile

# `src` depends on nothing in this script (this script is NOT imported at
# runtime -- see the module docstring), so the reverse import is safe: pull
# COLUMNS/VACANCY_IDEAL_RATE from schema.py instead of hand-duplicating them
# here, where they could silently drift out of sync on a future schema change.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.housing.zip_screen.schema import COLUMNS, VACANCY_IDEAL_RATE  # noqa: E402

ACS_VINTAGE_YEAR = 2024
ACS_SF_BASE = (
    f'https://www2.census.gov/programs-surveys/acs/summary_file/'
    f'{ACS_VINTAGE_YEAR}/table-based-SF/data/5YRData'
)
GAZETTEER_ZCTA_URL = (
    f'https://www2.census.gov/geo/docs/maps-data/data/gazetteer/'
    f'{ACS_VINTAGE_YEAR}_Gazetteer/{ACS_VINTAGE_YEAR}_Gaz_zcta_national.zip'
)
GAZETTEER_PLACE_URL = (
    f'https://www2.census.gov/geo/docs/maps-data/data/gazetteer/'
    f'{ACS_VINTAGE_YEAR}_Gazetteer/{ACS_VINTAGE_YEAR}_Gaz_place_national.zip'
)
REL_BASE = 'https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520'
REL_ZCTA_COUNTY = f'{REL_BASE}/tab20_zcta520_county20_natl.txt'
REL_ZCTA_PLACE = f'{REL_BASE}/tab20_zcta520_place20_natl.txt'

EVICTION_NOTE = """\
Eviction Lab's tract-level filing/judgment extracts are no longer served from a
public URL: evictionlab.org gates every download behind a signup + data-use
agreement form (the site returns 403 to a plain fetch, and the historical
s3 `.../{ST}/tracts.csv` objects 404).  Accepting terms and creating an account
is not something this build script may do unattended, so BOTH eviction columns
are written empty for every row.  quality.py renormalizes the remaining weights
and coverage_pct reports the reduction honestly (26 of 33 sourceable PDF points
=> ~78.8% coverage).  To restore them: obtain the tract-level file by hand,
drop it beside this script, and join it through REL_ZCTA_TRACT (the Census
ZCTA<->tract relationship file) weighting each tract by AREALAND_PART.
"""

SQ_METERS_PER_SQ_MILE = 2_589_988.11

# GEO_ID prefixes in the table-based Summary File.
P_ZCTA = '860Z200US'
P_STATE = '0400000US'
P_PLACE = '1600000US'

OUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'src', 'housing', 'zip_screen', 'data', 'zip_metrics.csv.gz',
)

PILOT_STATES = ('IL', 'FL', 'CO')

STATE_FIPS = {
    '01': ('AL', 'Alabama'), '02': ('AK', 'Alaska'), '04': ('AZ', 'Arizona'),
    '05': ('AR', 'Arkansas'), '06': ('CA', 'California'), '08': ('CO', 'Colorado'),
    '09': ('CT', 'Connecticut'), '10': ('DE', 'Delaware'),
    '11': ('DC', 'District of Columbia'), '12': ('FL', 'Florida'),
    '13': ('GA', 'Georgia'), '15': ('HI', 'Hawaii'), '16': ('ID', 'Idaho'),
    '17': ('IL', 'Illinois'), '18': ('IN', 'Indiana'), '19': ('IA', 'Iowa'),
    '20': ('KS', 'Kansas'), '21': ('KY', 'Kentucky'), '22': ('LA', 'Louisiana'),
    '23': ('ME', 'Maine'), '24': ('MD', 'Maryland'), '25': ('MA', 'Massachusetts'),
    '26': ('MI', 'Michigan'), '27': ('MN', 'Minnesota'), '28': ('MS', 'Mississippi'),
    '29': ('MO', 'Missouri'), '30': ('MT', 'Montana'), '31': ('NE', 'Nebraska'),
    '32': ('NV', 'Nevada'), '33': ('NH', 'New Hampshire'), '34': ('NJ', 'New Jersey'),
    '35': ('NM', 'New Mexico'), '36': ('NY', 'New York'),
    '37': ('NC', 'North Carolina'), '38': ('ND', 'North Dakota'), '39': ('OH', 'Ohio'),
    '40': ('OK', 'Oklahoma'), '41': ('OR', 'Oregon'), '42': ('PA', 'Pennsylvania'),
    '44': ('RI', 'Rhode Island'), '45': ('SC', 'South Carolina'),
    '46': ('SD', 'South Dakota'), '47': ('TN', 'Tennessee'), '48': ('TX', 'Texas'),
    '49': ('UT', 'Utah'), '50': ('VT', 'Vermont'), '51': ('VA', 'Virginia'),
    '53': ('WA', 'Washington'), '54': ('WV', 'West Virginia'),
    '55': ('WI', 'Wisconsin'), '56': ('WY', 'Wyoming'),
    '72': ('PR', 'Puerto Rico'),
}
ABBREV_TO_FIPS = {ab: f for f, (ab, _) in STATE_FIPS.items()}

# ACS jam/annotation values (-666666666, -999999999, ...) are sentinels, not data.
_ACS_NULL_FLOOR = -100_000_000

# B25038 "year householder moved in" buckets, expressed as tenure-years ranges
# relative to the vintage year, shortest tenure first.
_TENURE_BOUNDS = ((0.0, 2.0), (2.0, 5.0), (5.0, 15.0),
                  (15.0, 25.0), (25.0, 35.0), (35.0, 55.0))


# --------------------------------------------------------------------------
# fetch helpers
# --------------------------------------------------------------------------

def _cache_dir() -> str:
    d = os.path.join(tempfile.gettempdir(), f'zip_metrics_cache_{ACS_VINTAGE_YEAR}')
    os.makedirs(d, exist_ok=True)
    return d


def _open_url(url: str):
    req = urllib.request.Request(url, headers={'User-Agent': 'zip-screen-ingest/1.0'})
    return urllib.request.urlopen(req, timeout=600)


def _download(url: str, name: str) -> bytes:
    """Fetch `url` once, caching the raw bytes in the OS temp dir."""
    path = os.path.join(_cache_dir(), name)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, 'rb') as fh:
            return fh.read()
    with _open_url(url) as resp:
        data = resp.read()
    with open(path, 'wb') as fh:
        fh.write(data)
    return data


def _acs_table(table: str, prefixes: tuple[str, ...]) -> dict[str, dict[str, float | None]]:
    """Stream one Summary File table, keeping only rows under `prefixes`.

    Returns ``{GEO_ID: {'001': value_or_None, ...}}`` -- estimate cells only,
    ACS sentinels mapped to None.  Filtered rows are cached so a re-run does not
    re-pull ~300 MB.
    """
    cache = os.path.join(_cache_dir(), f'{table}-{"_".join(prefixes)}.psv')
    if os.path.exists(cache) and os.path.getsize(cache) > 0:
        with open(cache, 'r', encoding='utf-8') as fh:
            lines = fh.read().splitlines()
    else:
        url = f'{ACS_SF_BASE}/acsdt5y{ACS_VINTAGE_YEAR}-{table.lower()}.dat'
        lines = []
        with _open_url(url) as resp:
            stream = io.TextIOWrapper(resp, encoding='utf-8', errors='replace')
            header = stream.readline().rstrip('\n')
            lines.append(header)
            for line in stream:
                if line.startswith(prefixes):
                    lines.append(line.rstrip('\n'))
        with open(cache, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines))

    head = lines[0].split('|')
    # header cells look like B14007_E017 (estimate) / B14007_M017 (margin)
    cells = {}
    for idx, name in enumerate(head):
        if '_E' in name:
            cells[name.split('_E')[1]] = idx

    out: dict[str, dict[str, float | None]] = {}
    for line in lines[1:]:
        if not line:
            continue
        parts = line.split('|')
        row: dict[str, float | None] = {}
        for key, idx in cells.items():
            raw = parts[idx] if idx < len(parts) else ''
            if raw == '' or raw == '.':
                row[key] = None
                continue
            try:
                val = float(raw)
            except ValueError:
                row[key] = None
                continue
            row[key] = None if val <= _ACS_NULL_FLOOR else val
        out[parts[0]] = row
    return out


def _gazetteer(url: str, name: str) -> list[dict[str, str]]:
    """Parse a zipped, tab-delimited national Gazetteer file."""
    raw = _download(url, name)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        text = zf.read(zf.namelist()[0]).decode('utf-8', 'replace')
    lines = text.splitlines()
    head = [h.strip() for h in lines[0].split('\t')]
    rows = []
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split('\t')]
        rows.append(dict(zip(head, parts)))
    return rows


def _relationship(url: str, name: str) -> tuple[list[str], list[list[str]]]:
    text = _download(url, name).decode('utf-8-sig', 'replace')
    lines = text.splitlines()
    return lines[0].split('|'), [l.split('|') for l in lines[1:] if l]


# --------------------------------------------------------------------------
# derivations
# --------------------------------------------------------------------------

def percentile_ranks(values: dict[str, float]) -> dict[str, float]:
    """Fractional rank in [0, 1] of each key's value among all present values.

    Ties share the midpoint rank. Keys absent here stay absent in the snapshot
    (an empty cell), which quality.py renormalizes over.
    """
    if not values:
        return {}
    ordered = sorted(values.items(), key=lambda kv: kv[1])
    n = len(ordered)
    ranks: dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and ordered[j + 1][1] == ordered[i][1]:
            j += 1
        mid = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[ordered[k][0]] = mid / (n - 1) if n > 1 else 0.5
        i = j + 1
    return ranks


def _median_from_buckets(counts: list[float]) -> float | None:
    """Linear-interpolated median tenure (years) from ordered bucket counts."""
    total = sum(counts)
    if total <= 0:
        return None
    target = total / 2.0
    cumulative = 0.0
    for count, (lo, hi) in zip(counts, _TENURE_BOUNDS):
        if count <= 0:
            continue
        if cumulative + count >= target:
            return lo + (target - cumulative) / count * (hi - lo)
        cumulative += count
    return _TENURE_BOUNDS[-1][1]


def _ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den <= 0:
        return None
    return num / den


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

def build(states: tuple[str, ...], out_path: str) -> int:
    """Fetch, join, rank, and write the snapshot. Returns the row count."""
    wanted_fips = (set(ABBREV_TO_FIPS[s] for s in states)
                   if states else set(STATE_FIPS) - {'72'})

    # --- geography: ZCTA -> state (via county), ZCTA -> primary place --------
    print('fetching ZCTA<->county relationship ...', flush=True)
    _, county_rows = _relationship(REL_ZCTA_COUNTY, 'rel_zcta_county.txt')
    best_county: dict[str, tuple[float, str]] = {}
    for r in county_rows:
        zcta, county, area = r[1], r[9], r[16]
        if not zcta or not county:
            continue
        try:
            a = float(area or 0)
        except ValueError:
            a = 0.0
        if a >= best_county.get(zcta, (-1.0, ''))[0]:
            best_county[zcta] = (a, county)
    zcta_state = {z: c[:2] for z, (_, c) in best_county.items()}
    zctas = {z for z, f in zcta_state.items() if f in wanted_fips}
    print(f'  {len(zctas)} ZCTAs in scope', flush=True)

    print('fetching ZCTA<->place relationship ...', flush=True)
    _, place_rows = _relationship(REL_ZCTA_PLACE, 'rel_zcta_place.txt')
    best_place: dict[str, tuple[float, str, str]] = {}
    for r in place_rows:
        zcta, place, label, area = r[1], r[9], r[10], r[16]
        if not zcta or not place or zcta not in zctas:
            continue
        try:
            a = float(area or 0)
        except ValueError:
            a = 0.0
        if a >= best_place.get(zcta, (-1.0, '', ''))[0]:
            best_place[zcta] = (a, place, label)

    print('fetching Gazetteer ZCTA centroids ...', flush=True)
    gaz = {}
    for r in _gazetteer(GAZETTEER_ZCTA_URL, 'gaz_zcta.zip'):
        gaz[r['GEOID']] = r

    # --- ACS ----------------------------------------------------------------
    prefixes = (P_ZCTA, P_STATE, P_PLACE)
    acs: dict[str, dict[str, dict[str, float | None]]] = {}
    for table in ('B25003', 'B25002', 'B19013', 'B25038',
                  'B25077', 'B14007', 'B14006', 'B01003'):
        print(f'fetching ACS {ACS_VINTAGE_YEAR} 5-year {table} ...', flush=True)
        acs[table] = _acs_table(table, prefixes)

    state_home_value = {
        fips: (acs['B25077'].get(f'{P_STATE}{fips}') or {}).get('001')
        for fips in wanted_fips
    }
    place_pop = {
        gid[len(P_PLACE):]: (row.get('001') or 0.0)
        for gid, row in acs['B01003'].items() if gid.startswith(P_PLACE)
    }

    # --- per-ZCTA rows ------------------------------------------------------
    rows: dict[str, dict[str, object]] = {}
    raw: dict[str, dict[str, float]] = {
        'owner_occupied': {}, 'poverty': {}, 'non_student_poverty': {},
        'tenure': {}, 'tenure_nonstudent': {}, 'vacancy_deviation': {},
        'median_income': {},
    }

    for zcta in sorted(zctas):
        g = gaz.get(zcta)
        if not g:
            continue  # no centroid -> unusable for a radius search
        gid = f'{P_ZCTA}{zcta}'
        pop = (acs['B01003'].get(gid) or {}).get('001')
        if pop is None:
            continue
        fips = zcta_state[zcta]
        abbrev, name = STATE_FIPS[fips]

        b25003 = acs['B25003'].get(gid) or {}
        b25002 = acs['B25002'].get(gid) or {}
        b25038 = acs['B25038'].get(gid) or {}
        b14007 = acs['B14007'].get(gid) or {}
        b14006 = acs['B14006'].get(gid) or {}

        owner = _ratio(b25003.get('002'), b25003.get('001'))
        vacancy = _ratio(b25002.get('003'), b25002.get('001'))
        vac_dev = None if vacancy is None else abs(vacancy - VACANCY_IDEAL_RATE)

        pov_total = b14006.get('001')
        pov_below = b14006.get('002')
        poverty = _ratio(pov_below, pov_total)

        # Students excluded = college undergrad + grad/professional enrollees.
        col_below = (b14006.get('009') or 0.0) + (b14006.get('010') or 0.0)
        col_above = (b14006.get('019') or 0.0) + (b14006.get('020') or 0.0)
        ns_poverty = None
        if pov_total is not None and pov_below is not None:
            ns_total = pov_total - col_below - col_above
            ns_below = pov_below - col_below
            if ns_total > 0 and ns_below >= 0:
                ns_poverty = ns_below / ns_total

        owner_buckets = [b25038.get(f'{i:03d}') or 0.0 for i in range(3, 9)]
        renter_buckets = [b25038.get(f'{i:03d}') or 0.0 for i in range(10, 16)]
        tenure = _median_from_buckets(
            [o + r for o, r in zip(owner_buckets, renter_buckets)])
        # No ACS table breaks tenure out by student status; owner-occupied
        # tenure is the student-excluded proxy (students are near-universally
        # renters, and the PDF's UPI adjustment exists to stop annual student
        # leases from reading as instability).
        tenure_ns = _median_from_buckets(owner_buckets)

        income = (acs['B19013'].get(gid) or {}).get('001')
        home_value = (acs['B25077'].get(gid) or {}).get('001')

        # UPI (University Presence Index) exists to flag genuine university
        # towns for the PDF methodology's student-population adjustment (see
        # schema.UPI_THRESHOLD = 0.15). It deliberately uses only college and
        # graduate/professional enrollment (B14007 categories 017-018), not
        # total school enrollment: K-12 enrollment is near-universal across
        # nearly every ZCTA, so folding it into the numerator would push
        # almost all ZCTAs over the threshold and destroy the index's ability
        # to tell an actual college town (e.g. DeKalb, home to NIU) apart
        # from an ordinary suburb. College/grad enrollment is the signal that
        # actually discriminates.
        college = (b14007.get('017') or 0.0) + (b14007.get('018') or 0.0)
        upi = (college / pop) if pop > 0 else 0.0

        area_m2 = float(g.get('ALAND') or 0.0)
        place_gid = best_place.get(zcta, (0.0, '', ''))[1]
        place_label = best_place.get(zcta, (0.0, '', ''))[2]

        rows[zcta] = {
            'zcta': zcta,
            'state': name,
            'state_abbrev': abbrev,
            'primary_place': _place_name(place_label),
            'place_population': int(place_pop.get(place_gid, 0.0)),
            'zcta_population': int(pop),
            'land_area_sqmi': round(area_m2 / SQ_METERS_PER_SQ_MILE, 4),
            'lat': float(g['INTPTLAT']),
            'lon': float(g['INTPTLONG']),
            'median_home_value': home_value,
            'state_median_home_value': state_home_value.get(fips),
            'upi': round(upi, 6),
        }
        for key, value in (('owner_occupied', owner), ('poverty', poverty),
                           ('non_student_poverty', ns_poverty),
                           ('tenure', tenure), ('tenure_nonstudent', tenure_ns),
                           ('vacancy_deviation', vac_dev),
                           ('median_income', income)):
            if value is not None:
                raw[key][zcta] = float(value)

    # --- percentiles --------------------------------------------------------
    ranks = {metric: percentile_ranks(vals) for metric, vals in raw.items()}
    print(EVICTION_NOTE, flush=True)

    # --- write --------------------------------------------------------------
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with gzip.open(out_path, 'wt', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for zcta in sorted(rows):
            row = rows[zcta]
            row['pctl_eviction_execution'] = None
            row['pctl_eviction_filing'] = None
            for metric in raw:
                row[f'pctl_{metric}'] = ranks[metric].get(zcta)
            writer.writerow([_cell(row.get(c)) for c in COLUMNS])
    return len(rows)


_PLACE_SUFFIXES = (' city', ' village', ' town', ' CDP', ' borough',
                   ' municipality', ' (balance)')


def _place_name(label: str) -> str:
    name = label.strip()
    changed = True
    while changed:
        changed = False
        for suffix in _PLACE_SUFFIXES:
            if name.endswith(suffix):
                name = name[: -len(suffix)].strip()
                changed = True
    return name


def _cell(value: object) -> str:
    """None is an EMPTY cell -- never a zero. See table.py's _opt_float."""
    if value is None:
        return ''
    if isinstance(value, float):
        # Fixed-point, never %g: %g renders 1032800.0 as "1.0328e+06".
        return f'{value:.6f}'.rstrip('0').rstrip('.') or '0'
    return str(value)


# --------------------------------------------------------------------------
# top_cities.csv
# --------------------------------------------------------------------------

def build_top_cities(out_path: str, snapshot_path: str, limit: int = 200) -> int:
    """Largest places in the snapshot's states, each anchored to a ZCTA.

    The anchor is the ZCTA whose Gazetteer centroid is nearest the Census
    place's internal point, restricted to ZCTAs actually present in the
    snapshot so every anchor resolves.
    """
    with gzip.open(snapshot_path, 'rt', encoding='utf-8', newline='') as fh:
        snap = list(csv.DictReader(fh))
    by_state: dict[str, list[tuple[str, float, float]]] = {}
    for r in snap:
        by_state.setdefault(r['state_abbrev'], []).append(
            (r['zcta'], float(r['lat']), float(r['lon'])))
    states = set(by_state)

    places = _gazetteer(GAZETTEER_PLACE_URL, 'gaz_place.zip')
    pop = {
        gid[len(P_PLACE):]: (row.get('001') or 0.0)
        for gid, row in _acs_table('B01003', (P_PLACE,)).items()
    }

    ranked = []
    for p in places:
        abbrev = p.get('USPS', '')
        if abbrev not in states:
            continue
        population = pop.get(p['GEOID'])
        if not population:
            continue
        ranked.append((population, p, abbrev))
    ranked.sort(key=lambda t: -t[0])
    ranked = ranked[:limit]

    with open(out_path, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['city_id', 'city', 'state', 'state_abbrev',
                         'population', 'anchor_zip'])
        for population, p, abbrev in ranked:
            lat, lon = float(p['INTPTLAT']), float(p['INTPTLONG'])
            anchor = min(by_state[abbrev],
                         key=lambda z: _haversine(lat, lon, z[1], z[2]))[0]
            writer.writerow([p['GEOID'], _place_name(p['NAME']),
                             STATE_FIPS[ABBREV_TO_FIPS[abbrev]][1], abbrev,
                             int(population), anchor])
    return len(ranked)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--states', default=','.join(PILOT_STATES),
                    help='comma-separated USPS state codes')
    ap.add_argument('--all-states', action='store_true')
    ap.add_argument('--out', default=OUT_PATH)
    ap.add_argument('--cities', type=int, default=200,
                    help='rows to write into top_cities.csv')
    args = ap.parse_args(argv)
    states = () if args.all_states else tuple(s.strip().upper()
                                              for s in args.states.split(',') if s.strip())
    rows = build(states, args.out)
    print(f'wrote {rows} rows to {args.out}')
    cities_path = os.path.join(os.path.dirname(args.out), 'top_cities.csv')
    n = build_top_cities(cities_path, args.out, args.cities)
    print(f'wrote {n} cities to {cities_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
