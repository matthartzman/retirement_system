"""Housing optimizer bench: run a real optimization from the command line.

Exists so refining ``src/housing/`` does not require writing throwaway
scripts or scratch tests. It loads a plan folder's CSVs the same way the
build does, runs ``src.housing.optimize_housing`` against it, and prints the
ranked candidates -- with the search settings, the candidate count, and the
wall time each phase took, so a change can be judged on both answer and cost.

v2 (design 2026-09-16, §5.1): the original home's sale is decoupled from any
purchase. A run now needs a ``--sale-window`` for the original home (ignored
when ``--dispositions`` never includes ``sell``) plus a separate
``--move1-window`` for when the first acquisition happens.

Examples
--------
Two candidate locations for move 1, sold within a window and bought within
a separate one, against the frozen sample plan::

    python tools/housing_lab.py --location Texas --location Florida \\
        --sale-window 2027 2029 --move1-window 2027 2029

The same search with a second, later move and a CSV export::

    python tools/housing_lab.py --plan input --location Texas --location Florida \\
        --sale-window 2027 2029 --move1-window 2027 2032 \\
        --move2-window 2033 2040 --search-mode narrowed \\
        --objective lifetime_cost --csv out.csv

A location is ``STATE[:city_type[:population[:price_lo-price_hi]]]``, e.g.
``"North Carolina:urban:300000:600000-750000"``. Locations built this way
never carry a ZIP code, so ``--family-presence`` will fail closed for them
(the underlying rule requires a resolvable ZIP on both ends); it is meant for
locations produced by the real ZIP screen, not this harness's manual mode.
``--objective``, ``--search-mode`` and ``--move2-strategy`` accept exactly
the values ``src.housing`` accepts; anything it rejects is reported as an
error here rather than a traceback.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The committed, self-contained plan the engine-backed housing tests run
# against, and the date they pin it to (tests/conftest.py's
# FROZEN_PLAN_TODAY). Defaulting here means a bare invocation is reproducible
# and never touches the user's real, gitignored input/ plan.
DEFAULT_PLAN = 'tests/fixtures/sample_plan_frozen'
FROZEN_PLAN_TODAY = '2026-08-04'


def _parse_location(spec: str):
    """``STATE[:city_type[:population[:lo-hi]]]`` -> ``Location``."""
    from src.housing import Location

    parts = [p.strip() for p in spec.split(':')]
    if not parts or not parts[0]:
        raise argparse.ArgumentTypeError(f"--location needs a state: {spec!r}")
    state = parts[0]
    city_type = parts[1].lower() if len(parts) > 1 and parts[1] else 'suburban'
    try:
        population = int(parts[2]) if len(parts) > 2 and parts[2] else 20000
    except ValueError:
        raise argparse.ArgumentTypeError(f"population must be an integer: {spec!r}")
    price_range = None
    if len(parts) > 3 and parts[3]:
        try:
            lo, hi = parts[3].split('-')
            price_range = (float(lo), float(hi))
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"price range must look like 600000-750000: {spec!r}")
    return Location(state=state, city_type=city_type, population_size=population,
                    target_purchase_price_range=price_range)


def _parse_family_presence(spec: str):
    """``ZIP:RADIUS_MILES:FROM_YEAR:THROUGH_YEAR`` -> ``FamilyPresence``."""
    from src.housing import FamilyPresence

    parts = [p.strip() for p in spec.split(':')]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            f"--family-presence wants ZIP:RADIUS_MILES:FROM_YEAR:THROUGH_YEAR, got {spec!r}")
    zip_code, radius, from_year, through_year = parts
    try:
        return FamilyPresence(zip_code=zip_code, radius_miles=int(radius),
                              from_year=int(from_year), through_year=int(through_year))
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"radius/from/through year must be integers: {spec!r}")


def _parse_dispositions(spec: str) -> tuple[str, ...]:
    parts = tuple(p.strip().lower() for p in spec.split(',') if p.strip())
    return parts or ('sell',)


def _family_coords(family_presence) -> dict[str, tuple[float, float]]:
    """Every ZCTA's coordinates, for the ``family_presence_ok`` check.

    Only loaded when ``--family-presence`` is given, since it means reading
    the whole bundled ZIP snapshot. Locations from ``--location`` carry no
    ZIP code, so this will only ever satisfy family presence for a candidate
    whose ``Location`` was built with one (not this harness's manual mode).
    """
    if family_presence is None:
        return {}
    from src.housing.zip_screen.table import load_table

    table = load_table()
    return {zcta: (rec.lat, rec.lon) for zcta, rec in table.items()}


def _resolve_plan_csv(plan: str) -> Path:
    """Accept a folder or the client_data.csv inside it."""
    p = (ROOT / plan) if not Path(plan).is_absolute() else Path(plan)
    if p.is_dir():
        p = p / 'client_data.csv'
    if not p.exists():
        raise SystemExit(f"No plan CSV at {p} -- pass --plan pointing at a folder "
                         f"containing client_data.csv, e.g. --plan {DEFAULT_PLAN}.")
    return p


def _load_config(plan_csv: Path, skip_live_pricing: bool) -> dict:
    from src.data_io import load_csv, parse_client
    from src.plan_config import ensure_engine_config

    c = parse_client(load_csv(plan_csv), "", skip_live_pricing=skip_live_pricing)
    return ensure_engine_config(dict(c), source='housing_lab')


def _location_label(loc: dict) -> str:
    if loc.get('city'):
        where = f"{loc['city']}, {loc['state']}"
        if loc.get('zip_code'):
            where += f" {loc['zip_code']}"
    else:
        where = f"{loc['state']}/{loc['area_type']}"
    if loc.get('est_price') is not None:
        where += f" ${loc['est_price']:,.0f}"
    if loc.get('distance_miles') is not None:
        where += f" ({loc['distance_miles']:.1f}mi)"
    return where


def _move_label(move: dict | None) -> str:
    if not move:
        return '—'
    flag = ' [121?]' if move.get('sec121_exclusion_lost') else ''
    return (f"{move['action'].capitalize()} {move['acquisition_year']} "
            f"{_location_label(move['location'])}{flag}")


def _original_home_label(home: dict) -> str:
    if home['disposition'] == 'keep':
        return 'Keep'
    return f"Sell {home['sale_year']}"


def _rows(result: dict) -> list[dict]:
    out = []
    for cand in result['candidates']:
        moves = cand['moves']
        out.append({
            'rank': cand['rank'],
            'original_home': _original_home_label(cand['original_home']),
            'move_1': _move_label(moves[0] if moves else None),
            'move_2': _move_label(moves[1] if len(moves) > 1 else None),
            'net_worth': cand['net_worth'],
            'lifetime_cost': cand['lifetime_cost'],
            'mc_success_rate': cand['mc_success_rate'],
            'objective_value': cand['objective_value'],
            'notes': '; '.join(cand['notes']),
        })
    return out


def _print_table(rows: list[dict], objective: str) -> None:
    if not rows:
        print("No candidate survived the filters.")
        return
    header = (f"{'#':>2}  {'ORIGINAL HOME':<12} {'MOVE 1':<42} {'MOVE 2':<42} "
              f"{'NET WORTH':>14} {'LIFETIME COST':>14} {'MC':>6}")
    print(header)
    print('-' * len(header))
    for r in rows:
        mc = '' if r['mc_success_rate'] is None else f"{r['mc_success_rate'] * 100:5.1f}%"
        print(f"{r['rank']:>2}  {r['original_home']:<12} {r['move_1']:<42} {r['move_2']:<42} "
              f"{r['net_worth']:>14,.0f} {r['lifetime_cost']:>14,.0f} {mc:>6}")
        if r['notes']:
            print(f"      notes: {r['notes']}")
    print(f"\nRanked by {objective}. MC success rate is computed for the shortlist only.")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog='housing_lab',
        description=__doc__.split('Examples')[0].strip(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument('--plan', default=DEFAULT_PLAN,
                    help=f"Folder holding client_data.csv (default: {DEFAULT_PLAN} -- the "
                         "committed, self-contained plan the engine-backed tests use).")
    ap.add_argument('--today', default=None, metavar='YYYY-MM-DD',
                    help=f"Pin the projection's 'today' (default: {FROZEN_PLAN_TODAY} when "
                         "running the frozen sample plan, so repeated runs are comparable; "
                         "the real clock otherwise).")
    ap.add_argument('--location', action='append', required=True, metavar='SPEC',
                    dest='locations1',
                    help="Repeat 1+ times. Move-1 candidate locations: "
                         "STATE[:city_type[:population[:lo-hi]]].")
    ap.add_argument('--location2', action='append', metavar='SPEC',
                    dest='locations2',
                    help="Repeat 1+ times. Move-2 candidate locations (same SPEC "
                         "format). Only used when --move2-window is given; defaults "
                         "to the --location list if omitted.")
    ap.add_argument('--dispositions', type=_parse_dispositions, default=('sell',),
                    help="Comma-separated: sell, keep, and/or auto (default: sell).")
    ap.add_argument('--sale-window', nargs=2, type=int, required=True,
                    metavar=('EARLIEST_SALE', 'LATEST_SALE'),
                    help="Window for the original home's sale year (ignored unless "
                         "--dispositions includes sell/auto).")
    ap.add_argument('--move1-window', nargs=2, type=int, required=True,
                    metavar=('EARLIEST_ACQUIRE', 'LATEST_ACQUIRE'),
                    help="Window for move 1's acquisition year.")
    ap.add_argument('--move2-window', nargs=2, type=int, default=None,
                    metavar=('EARLIEST_ACQUIRE_2', 'LATEST_ACQUIRE_2'),
                    help="Window for move 2's acquisition year. Omit for a "
                         "move-1-only search.")
    ap.add_argument('--move1-action', default='auto', choices=('auto', 'buy', 'rent'))
    ap.add_argument('--move2-action', default='auto', choices=('auto', 'buy', 'rent'))
    ap.add_argument('--move2-concurrent', action='store_true',
                    help="Move 2 is a simultaneous second residence rather than a "
                         "later relocation. Not supported with --search-mode narrowed.")
    ap.add_argument('--objective', default='net_worth',
                    help="net_worth | lifetime_cost | mc_success_rate.")
    ap.add_argument('--search-mode', default='full', help="full | narrowed.")
    ap.add_argument('--move2-strategy', default='anchored', help="anchored | cross_product.")
    ap.add_argument('--anchor-count', type=int, default=5)
    ap.add_argument('--shortlist-size', type=int, default=5,
                    help="Candidates that get a Monte Carlo run (clamped to 3-5).")
    ap.add_argument('--allow-dual-ownership', action='store_true',
                    help="Permit buying before selling (default: not allowed).")
    ap.add_argument('--family-presence', type=_parse_family_presence, default=None,
                    metavar='ZIP:RADIUS_MILES:FROM_YEAR:THROUGH_YEAR')
    ap.add_argument('--down-payment-pct', type=float, default=0.20)
    ap.add_argument('--mortgage-rate-pct', type=float, default=None,
                    help="Override the engine's default mortgage rate assumption.")
    ap.add_argument('--skip-live-pricing', action='store_true',
                    help="Skip the per-symbol live price fetch when loading the plan "
                         "(faster startup; holdings are valued from cache).")
    ap.add_argument('--csv', metavar='PATH', help="Write the ranked table to a CSV file.")
    ap.add_argument('--json', metavar='PATH',
                    help="Write the raw housing_optimize_v2 payload to a JSON file.")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        locations1 = [_parse_location(spec) for spec in args.locations1]
        locations2 = ([_parse_location(spec) for spec in args.locations2]
                      if args.locations2 else None)
    except argparse.ArgumentTypeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    today = args.today or (FROZEN_PLAN_TODAY if args.plan == DEFAULT_PLAN else None)
    if today:
        # Read at import time by the engine's date handling, so this has to be
        # set before src.housing (and the modules it pulls in) is imported.
        os.environ['RETIREMENT_SYSTEM_FROZEN_TODAY'] = today

    from src.housing import MoveWindow, SaleWindow, optimize_housing

    plan_csv = _resolve_plan_csv(args.plan)
    t0 = time.perf_counter()
    c0 = _load_config(plan_csv, args.skip_live_pricing)
    t_load = time.perf_counter() - t0

    if args.move2_window and locations2 is None:
        locations2 = locations1

    print(f"plan            {plan_csv.relative_to(ROOT) if plan_csv.is_relative_to(ROOT) else plan_csv}")
    print(f"dispositions    {', '.join(args.dispositions)}")
    print(f"locations (m1)  {', '.join(f'{l.state}/{l.city_type}' for l in locations1)}")
    if locations2:
        print(f"locations (m2)  {', '.join(f'{l.state}/{l.city_type}' for l in locations2)}")
    print(f"sale window     {args.sale_window[0]}-{args.sale_window[1]}")
    print(f"move-1 window   {args.move1_window[0]}-{args.move1_window[1]} "
          f"(action={args.move1_action})")
    if args.move2_window:
        print(f"move-2 window   {args.move2_window[0]}-{args.move2_window[1]} "
              f"(action={args.move2_action}, concurrent={args.move2_concurrent})")
    print(f"settings        objective={args.objective} search_mode={args.search_mode} "
          f"move2_strategy={args.move2_strategy} anchors={args.anchor_count} "
          f"no_dual_ownership={not args.allow_dual_ownership}")
    if today:
        print(f"today pinned to {today}")
    print(f"plan loaded in  {t_load:.1f}s\n")

    t1 = time.perf_counter()
    try:
        result = optimize_housing(
            c0,
            locations1=locations1,
            locations2=locations2,
            sale_window=SaleWindow(*args.sale_window),
            move1_window=MoveWindow(*args.move1_window),
            move2_window=MoveWindow(*args.move2_window) if args.move2_window else None,
            dispositions=args.dispositions,
            move1_action=args.move1_action,
            move2_action=args.move2_action,
            move2_concurrent=args.move2_concurrent,
            no_dual_ownership=not args.allow_dual_ownership,
            family_presence=args.family_presence,
            family_coords=_family_coords(args.family_presence),
            anchor_count=args.anchor_count,
            objective=args.objective,
            search_mode=args.search_mode,
            move2_strategy=args.move2_strategy,
            down_payment_pct=args.down_payment_pct,
            mortgage_rate_pct=args.mortgage_rate_pct,
            shortlist_size=args.shortlist_size,
        )
    except ValueError as exc:
        # Every guard in optimize_housing (unknown objective/mode, location
        # count, the cross-product cap) raises ValueError with a message
        # meant for a caller -- show it as one, not as a traceback.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - t1

    rows = _rows(result)
    _print_table(rows, result['objective'])
    print(f"{result['candidates_evaluated']} candidates evaluated in {elapsed:.1f}s "
          f"({elapsed / max(1, result['candidates_evaluated']):.2f}s per candidate).")
    if result.get('rejections'):
        rejected = {k: v for k, v in result['rejections'].items() if v}
        if rejected:
            print(f"rejected        {rejected}")
    if result.get('message'):
        print(f"message         {result['message']}")

    if args.csv:
        path = Path(args.csv)
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ['rank'])
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {path}")
    if args.json:
        path = Path(args.json)
        path.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(f"wrote {path}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
