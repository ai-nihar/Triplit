"""Trip domain operations.

This module holds DB access + business rules for trips, selections, and itinerary.
Routes should parse HTTP and serialize responses only.

Important: keep behavior and messages identical to existing API.
"""

from __future__ import annotations

from collections import OrderedDict
from difflib import SequenceMatcher
import json

from app.helpers.db import execute_db, query_db
from app.services.osrm import fetch_table_matrix
from app.services.optimizer import optimize_order_from_durations


def get_user_trips(user_id: int) -> dict:
    all_trips = query_db(
        '''SELECT trip_id, trip_name, start_region, end_region, pace,
                  companion_type, season, planning_mode, trip_days,
                  trip_status, created_at
           FROM trips
           WHERE user_id = %s
           ORDER BY created_at DESC''',
        (user_id,),
    )

    if not all_trips:
        all_trips = []

    for trip in all_trips:
        if trip.get('created_at'):
            trip['created_at'] = str(trip['created_at'])

    drafts = [t for t in all_trips if t['trip_status'] != 'finalized']
    finals = [t for t in all_trips if t['trip_status'] == 'finalized']
    return {'draft_trips': drafts, 'final_trips': finals}


def create_trip(
    *,
    user_id: int,
    trip_name: str,
    start_region: str,
    end_region: str | None,
    focus_mode: str,
    diversity_mode: int,
    pace: str,
    companion: str,
    season: str,
    planning_mode: str,
    trip_days: int,
) -> int:
    return execute_db(
        '''INSERT INTO trips
           (user_id, trip_name, start_region, end_region, focus_mode,
            diversity_mode, pace, companion_type, season, planning_mode,
            trip_status, trip_days)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
        (
            user_id,
            trip_name,
            start_region,
            end_region,
            focus_mode,
            diversity_mode,
            pace,
            companion,
            season,
            planning_mode,
            'draft',
            trip_days,
        ),
    )


def insert_trip_regions(trip_id: int, travelling_regions: list[str]) -> None:
    for region_name in travelling_regions:
        execute_db(
            'INSERT INTO trip_regions (trip_id, region_name) VALUES (%s, %s)',
            (trip_id, region_name),
        )


def get_trip_for_user(trip_id: int | str, user_id: int, *, full: bool = True) -> dict | None:
    if full:
        return query_db('SELECT * FROM trips WHERE trip_id = %s AND user_id = %s', (trip_id, user_id), one=True)
    return query_db('SELECT trip_id FROM trips WHERE trip_id = %s AND user_id = %s', (trip_id, user_id), one=True)


def get_trip_regions(trip_id: int | str) -> list[str]:
    regions = query_db('SELECT region_name FROM trip_regions WHERE trip_id = %s', (trip_id,))
    return [r['region_name'] for r in regions] if regions else []


def get_selected_locations(trip_id: int | str) -> list[dict]:
    rows = query_db(
        '''
        SELECT l.location_id, l.name, l.locality, l.region, l.category, l.image_url, l.description
        FROM trip_locations tl
        JOIN locations l ON tl.location_id = l.location_id
        WHERE tl.trip_id = %s AND tl.status = 'selected'
        ORDER BY tl.visit_order ASC
        ''',
        (trip_id,),
    )
    return rows or []


def enforce_region_constraint(*, trip_id: int | str, location_id: int | str) -> tuple[bool, str | None]:
    """Return (allowed, error_message)."""
    trip_regions = query_db('SELECT region_name FROM trip_regions WHERE trip_id = %s', (trip_id,))
    allowed_regions = [r['region_name'].lower() for r in trip_regions] if trip_regions else []

    loc_info = query_db('SELECT locality, region FROM locations WHERE location_id = %s', (location_id,), one=True)
    if not loc_info:
        return True, None

    loc_region = (loc_info.get('region') or '').lower()
    loc_locality = (loc_info.get('locality') or '').lower()
    if not allowed_regions:
        return True, None

    match_found = False
    for ar in allowed_regions:
        if loc_region and (ar in loc_region or loc_region in ar):
            match_found = True
            break
        if loc_region and SequenceMatcher(None, ar, loc_region).ratio() > 0.8:
            match_found = True
            break

        # Also allow matches against locality so trips scoped to cities still work
        # even when the stored "region" is the state.
        if loc_locality and (ar in loc_locality or loc_locality in ar):
            match_found = True
            break
        if loc_locality and SequenceMatcher(None, ar, loc_locality).ratio() > 0.8:
            match_found = True
            break

    if match_found:
        return True, None

    r_str = ", ".join([r['region_name'] for r in trip_regions])
    return False, f'Location is in "{loc_info["region"]}", but trip is limited to: {r_str}'


def add_location_to_trip(*, trip_id: int | str, location_id: int | str) -> dict:
    """Add location to trip as selected.

    Returns the exact response payload used by the current API.
    Caller is responsible for ownership validation.
    """
    existing = query_db(
        'SELECT trip_location_id FROM trip_locations WHERE trip_id = %s AND location_id = %s',
        (trip_id, location_id),
        one=True,
    )
    if existing:
        execute_db(
            "UPDATE trip_locations SET status = 'selected' WHERE trip_id = %s AND location_id = %s",
            (trip_id, location_id),
        )
        return {'success': True, 'message': 'Location status updated to selected'}

    max_order = query_db(
        'SELECT COALESCE(MAX(visit_order), 0) as mx FROM trip_locations WHERE trip_id = %s',
        (trip_id,),
        one=True,
    )
    next_order = (max_order['mx'] or 0) + 1

    execute_db(
        'INSERT INTO trip_locations (trip_id, location_id, status, visit_order) VALUES (%s, %s, %s, %s)',
        (trip_id, location_id, 'selected', next_order),
    )

    return {'success': True, 'message': 'Location added to trip'}


def remove_location_from_trip(*, trip_id: int | str, location_id: int | str) -> dict:
    execute_db(
        "UPDATE trip_locations SET status = 'suggested', visit_order = NULL WHERE trip_id = %s AND location_id = %s",
        (trip_id, location_id),
    )
    return {'success': True, 'message': 'Location removed from trip'}


def build_trip_itinerary(*, trip_id: int | str, pace: str) -> dict:
    pace_key = (pace or 'balanced').strip().lower()

    # Realistic daily time budgets (minutes). Includes travel + visit time.
    # Goal: avoid impractical 12–14 hour "Day 1" plans.
    day_budget_min_map = {
        'relaxed': 360,   # 6 hours
        'balanced': 480,  # 8 hours
        'packed': 600,    # 10 hours
    }
    day_budget_min = day_budget_min_map.get(pace_key, 480)

    # Keep old locs_per_day for backward-compatible payload fields.
    pace_map = {'relaxed': 2, 'balanced': 3, 'packed': 5}
    locs_per_day = pace_map.get(pace_key, 3)

    def _estimate_visit_min(category: str | None) -> int:
        base_by_category = {
            'heritage': 90,
            'museum': 90,
            'religious': 75,
            'nature': 120,
            'beach': 120,
            'adventure': 180,
            'food': 60,
            'shopping': 75,
            'viewpoint': 45,
            'entertainment': 90,
            'wellness': 120,
            'local-experience': 90,
        }
        c = (category or '').strip().lower()
        minutes = int(base_by_category.get(c, 75))

        # Pace adjustment: packed tends to spend less time per stop; relaxed more.
        mult = 1.0
        if pace_key == 'relaxed':
            mult = 1.1
        elif pace_key == 'packed':
            mult = 0.85
        minutes = int(round(minutes * mult))
        return max(30, minutes)

    all_locs = query_db(
        '''SELECT tl.visit_order, l.location_id, l.name, l.locality,
                  l.region, l.category, l.image_url
           FROM trip_locations tl
           JOIN locations l ON tl.location_id = l.location_id
           WHERE tl.trip_id = %s AND tl.status IN ('selected', 'confirmed')
           ORDER BY tl.visit_order ASC''',
        (trip_id,),
    )

    if not all_locs:
        all_locs = []

    # Travel time (minutes) between consecutive optimized stops.
    # If no snapshot exists yet, we fall back to 0 travel time.
    segments = query_db(
        '''SELECT from_location_id, to_location_id, duration_min
           FROM trip_route_segments
           WHERE trip_id = %s AND region = %s''',
        (trip_id, 'ALL'),
    ) or []
    seg_map: dict[tuple[int, int], float] = {}
    for s in segments:
        try:
            seg_map[(int(s['from_location_id']), int(s['to_location_id']))] = float(s.get('duration_min') or 0.0)
        except Exception:
            continue

    # Build global days in strict visit_order sequence.
    days_global: list[dict] = []
    current_day_locs: list[dict] = []
    current_day_travel = 0.0
    current_day_visit = 0.0
    current_day_total = 0.0

    prev_loc_id: int | None = None

    def _flush_day() -> None:
        nonlocal current_day_locs, current_day_travel, current_day_visit, current_day_total
        if not current_day_locs:
            return
        day_number = len(days_global) + 1
        days_global.append({
            'day_number': day_number,
            'locations': current_day_locs,
            'travel_min': round(current_day_travel, 1),
            'visit_min': round(current_day_visit, 1),
            'total_min': round(current_day_total, 1),
        })
        current_day_locs = []
        current_day_travel = 0.0
        current_day_visit = 0.0
        current_day_total = 0.0

    for loc in all_locs:
        loc_id = int(loc.get('location_id'))

        travel_min = 0.0
        if prev_loc_id is not None:
            travel_min = float(seg_map.get((prev_loc_id, loc_id), 0.0))

        visit_min = float(_estimate_visit_min(loc.get('category')))
        add_total = travel_min + visit_min

        # Start a new day if adding this stop would exceed the budget
        # (but never split before placing at least one location).
        if current_day_locs and (current_day_total + add_total) > float(day_budget_min):
            _flush_day()

        # Attach estimated times to location payload (safe extra fields)
        loc_aug = dict(loc)
        loc_aug['estimated_visit_min'] = int(visit_min)
        loc_aug['estimated_travel_from_prev_min'] = round(travel_min, 1)

        current_day_locs.append(loc_aug)
        current_day_travel += travel_min
        current_day_visit += visit_min
        current_day_total += (travel_min + visit_min)
        prev_loc_id = loc_id

    _flush_day()

    # Group days under a region header for UI consistency.
    # We assign a day to the region of its first location.
    region_groups: "OrderedDict[str, list[dict]]" = OrderedDict()
    for day in days_global:
        first_loc = (day.get('locations') or [{}])[0]
        region_name = first_loc.get('region') or 'Other'
        region_groups.setdefault(region_name, []).append(day)

    regions_output: list[dict] = []
    for region_name, days in region_groups.items():
        regions_output.append({'name': region_name, 'days': days})

    return {
        'regions': regions_output,
        'pace': pace_key,
        'locs_per_day': locs_per_day,
        'day_budget_min': day_budget_min,
        'total_locations': len(all_locs),
    }


def finalize_trip(*, trip_id: int | str, user_id: int) -> None:
    execute_db(
        "UPDATE trips SET trip_status = 'finalized' WHERE trip_id = %s AND user_id = %s",
        (trip_id, user_id),
    )

    # Mark selected locations as confirmed for finalized trips.
    execute_db(
        "UPDATE trip_locations SET status = 'confirmed' WHERE trip_id = %s AND status = 'selected'",
        (trip_id,),
    )

    # Cleanup: once finalized, discard remaining AI suggestions for this trip.
    execute_db(
        "DELETE FROM trip_locations WHERE trip_id = %s AND status = 'suggested'",
        (trip_id,),
    )


def optimize_trip_route(
    *,
    trip_id: int | str,
    user_id: int,
    start_location_id: int | str | None = None,
    end_location_id: int | str | None = None,
) -> dict:
    """Optimize selected locations order for a trip.

    - Uses OSRM /table once for all selected locations.
    - Runs NN + 2-Opt on durations.
    - Writes optimized order into trip_locations.visit_order.
    - Stores snapshot into trip_route_plan + trip_route_segments.
    """
    trip = query_db(
        'SELECT trip_id, trip_status, start_region, end_region FROM trips WHERE trip_id = %s AND user_id = %s',
        (trip_id, user_id),
        one=True,
    )
    if not trip:
        raise LookupError('Trip not found')

    if (trip.get('trip_status') or 'draft') == 'finalized':
        raise PermissionError('Trip is finalized')

    rows = query_db(
        '''
        SELECT tl.location_id, tl.visit_order, l.name, l.locality, l.region,
               l.latitude, l.longitude
        FROM trip_locations tl
        JOIN locations l ON tl.location_id = l.location_id
        WHERE tl.trip_id = %s AND tl.status IN ('selected', 'confirmed')
        ORDER BY tl.visit_order ASC
        ''',
        (trip_id,),
    ) or []

    if len(rows) <= 1:
        # Still store a trivial snapshot for consistency.
        location_ids = [r['location_id'] for r in rows]
        _store_route_snapshot(
            trip_id=int(trip_id),
            region='ALL',
            ordered_location_ids=location_ids,
            distances_m=[],
            durations_s=[],
        )
        return {
            'optimized_order': location_ids,
            'total_distance_km': 0.0,
            'total_duration_min': 0.0,
            'total_locations': len(rows),
        }

    # Validate coordinates
    coordinates: list[tuple[float, float]] = []
    for r in rows:
        lat = r.get('latitude')
        lon = r.get('longitude')
        if lat is None or lon is None:
            raise ValueError(f"Missing coordinates for location_id={r.get('location_id')}")
        coordinates.append((float(lon), float(lat)))

    table = fetch_table_matrix(coordinates=coordinates)

    # Mapping from location_id to index in `rows`/matrix
    id_to_index: dict[int, int] = {int(r['location_id']): i for i, r in enumerate(rows)}

    hard_start_idx: int | None = None
    hard_end_idx: int | None = None

    # Explicit selectors (hard constraints)
    try:
        if start_location_id is not None and str(start_location_id).strip() != '':
            hard_start_idx = id_to_index.get(int(start_location_id))
    except Exception:
        hard_start_idx = None

    try:
        if end_location_id is not None and str(end_location_id).strip() != '':
            hard_end_idx = id_to_index.get(int(end_location_id))
    except Exception:
        hard_end_idx = None

    if hard_start_idx is not None and hard_end_idx is not None and hard_start_idx == hard_end_idx:
        hard_end_idx = None

    def _region_match(user_text: str, value: str) -> bool:
        ut = (user_text or '').strip().lower()
        vv = (value or '').strip().lower()
        if not ut or not vv:
            return False
        if ut in vv or vv in ut:
            return True
        return SequenceMatcher(None, ut, vv).ratio() > 0.8

    start_pref = (trip.get('start_region') or '').strip()
    end_pref = (trip.get('end_region') or '').strip()

    # Soft preferences (only if they don't significantly worsen the route)
    start_candidates = [
        i for i, r in enumerate(rows)
        if _region_match(start_pref, (r.get('locality') or '')) or _region_match(start_pref, (r.get('region') or ''))
    ] if (start_pref and hard_start_idx is None) else []

    end_candidates = [
        i for i, r in enumerate(rows)
        if _region_match(end_pref, (r.get('locality') or '')) or _region_match(end_pref, (r.get('region') or ''))
    ] if (end_pref and hard_end_idx is None) else []

    # Baseline: best route subject to hard constraints only
    base = optimize_order_from_durations(
        table.durations_s,
        fixed_start_index=hard_start_idx,
        fixed_end_index=hard_end_idx,
    )

    # Try applying soft constraints; accept only if cost stays close to baseline.
    SOFT_MAX_DEGRADATION = 0.12  # allow up to +12% travel time to respect start/end preferences

    start_options = [None] + start_candidates
    end_options = [None] + end_candidates

    best_soft = None
    for s in start_options:
        for e in end_options:
            # Skip the baseline and invalid combos
            if s is None and e is None:
                continue
            if s is not None and e is not None and s == e:
                continue
            # If hard constraints exist, keep them.
            fs = hard_start_idx if hard_start_idx is not None else s
            fe = hard_end_idx if hard_end_idx is not None else e
            if fs is not None and fe is not None and fs == fe:
                continue
            cand = optimize_order_from_durations(
                table.durations_s,
                fixed_start_index=fs,
                fixed_end_index=fe,
            )
            if best_soft is None or cand.total_cost < best_soft.total_cost:
                best_soft = cand

    if best_soft is not None and base.total_cost > 0:
        if best_soft.total_cost <= base.total_cost * (1.0 + SOFT_MAX_DEGRADATION):
            result = best_soft
        else:
            result = base
    else:
        result = base

    ordered_rows = [rows[i] for i in result.order]
    ordered_location_ids = [r['location_id'] for r in ordered_rows]

    # Persist visit_order so existing itinerary endpoint reflects the optimized sequence.
    for idx, loc_id in enumerate(ordered_location_ids, start=1):
        execute_db(
            'UPDATE trip_locations SET visit_order = %s WHERE trip_id = %s AND location_id = %s',
            (idx, trip_id, loc_id),
        )

    # Compute totals based on the ordered path
    total_distance_m = 0.0
    total_duration_s = 0.0
    for a, b in zip(result.order, result.order[1:]):
        d_m = table.distances_m[a][b]
        t_s = table.durations_s[a][b]
        if d_m is None or t_s is None:
            raise ValueError('OSRM matrix contains unreachable pairs')
        total_distance_m += float(d_m)
        total_duration_s += float(t_s)

    _store_route_snapshot(
        trip_id=int(trip_id),
        region='ALL',
        ordered_location_ids=ordered_location_ids,
        distances_m=table.distances_m,
        durations_s=table.durations_s,
        order_indices=result.order,
    )

    return {
        'optimized_order': ordered_location_ids,
        'total_distance_km': round(total_distance_m / 1000.0, 3),
        'total_duration_min': round(total_duration_s / 60.0, 1),
        'total_locations': len(rows),
    }


def get_trip_route_plan(*, trip_id: int | str) -> dict | None:
    plan = query_db(
        '''SELECT optimized_order_json, total_distance_km, total_duration_min
           FROM trip_route_plan
           WHERE trip_id = %s AND region = %s''',
        (trip_id, 'ALL'),
        one=True,
    )
    if not plan:
        return None

    try:
        order = json.loads(plan.get('optimized_order_json') or '[]')
    except Exception:
        order = []

    return {
        'optimized_order': order,
        'total_distance_km': plan.get('total_distance_km'),
        'total_duration_min': plan.get('total_duration_min'),
    }


def _store_route_snapshot(
    *,
    trip_id: int,
    region: str,
    ordered_location_ids: list[int],
    distances_m: list[list[float | None]],
    durations_s: list[list[float | None]],
    order_indices: list[int] | None = None,
) -> None:
    """Upsert snapshot into trip_route_plan and replace segments."""
    total_distance_km = None
    total_duration_min = None

    if order_indices is not None and len(order_indices) > 1:
        dist_m = 0.0
        dur_s = 0.0
        for a, b in zip(order_indices, order_indices[1:]):
            d = distances_m[a][b]
            t = durations_s[a][b]
            if d is None or t is None:
                d = 0.0
                t = 0.0
            dist_m += float(d)
            dur_s += float(t)
        total_distance_km = dist_m / 1000.0
        total_duration_min = dur_s / 60.0

    order_json = json.dumps(ordered_location_ids)

    existing = query_db(
        'SELECT plan_id FROM trip_route_plan WHERE trip_id = %s AND region = %s',
        (trip_id, region),
        one=True,
    )
    if existing:
        execute_db(
            '''UPDATE trip_route_plan
               SET optimized_order_json = %s,
                   total_distance_km = %s,
                   total_duration_min = %s
               WHERE plan_id = %s''',
            (order_json, total_distance_km, total_duration_min, existing['plan_id']),
        )
    else:
        execute_db(
            '''INSERT INTO trip_route_plan
               (trip_id, region, optimized_order_json, total_distance_km, total_duration_min)
               VALUES (%s, %s, %s, %s, %s)''',
            (trip_id, region, order_json, total_distance_km, total_duration_min),
        )

    # Replace segments snapshot for this region
    execute_db('DELETE FROM trip_route_segments WHERE trip_id = %s AND region = %s', (trip_id, region))
    if order_indices is None or len(order_indices) <= 1:
        return

    # Insert segments using ordered_location_ids (already ordered)
    for from_loc, to_loc, a, b in zip(
        ordered_location_ids,
        ordered_location_ids[1:],
        order_indices,
        order_indices[1:],
    ):
        d = distances_m[a][b]
        t = durations_s[a][b]
        if d is None or t is None:
            continue
        execute_db(
            '''INSERT INTO trip_route_segments
               (trip_id, region, from_location_id, to_location_id, distance_km, duration_min)
               VALUES (%s, %s, %s, %s, %s, %s)''',
            (trip_id, region, from_loc, to_loc, float(d) / 1000.0, float(t) / 60.0),
        )


def delete_draft_trips(*, user_id: int, trip_ids: list) -> dict:
    deleted = 0
    for tid in trip_ids:
        trip = query_db(
            "SELECT trip_id FROM trips WHERE trip_id = %s AND user_id = %s AND trip_status != 'finalized'",
            (tid, user_id),
            one=True,
        )
        if trip:
            execute_db('DELETE FROM trip_locations WHERE trip_id = %s', (tid,))
            execute_db('DELETE FROM trip_regions WHERE trip_id = %s', (tid,))
            execute_db('DELETE FROM trips WHERE trip_id = %s', (tid,))
            deleted += 1

    return {'success': True, 'deleted': deleted, 'message': f'{deleted} trip(s) deleted'}
