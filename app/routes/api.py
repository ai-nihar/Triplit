"""
JSON API endpoints for frontend integration.
All routes return JSON and are prefixed with /api.
These complement the existing form-based routes.
"""
import json
from flask import Blueprint, request, jsonify, session
from app.helpers.db import query_db, execute_db
from app.helpers.auth_utils import login_required
from app.services.gemini import suggest_places, normalize_location_query, get_display_region
from app.services.osm import verify_place
from app.services.wiki import get_image
from difflib import SequenceMatcher


def get_user_id() -> int | None:
    """Return logged-in user_id from session (or None)."""
    return session.get('user_id')


def get_json_payload() -> dict:
    """Return a JSON body as dict; never raises."""
    return request.get_json(silent=True) or {}
from app.services.locations_service import (
    canonical_place_name,
    dedupe_location_rows,
    is_broad_location_row,
    search_locations_in_db,
    search_or_import_location_from_osm,
)
from app.services.trips_service import (
    add_location_to_trip as add_location_to_trip_service,
    build_trip_itinerary,
    create_trip,
    delete_draft_trips as delete_draft_trips_service,
    enforce_region_constraint,
    finalize_trip as finalize_trip_service,
    get_selected_locations as get_selected_locations_service,
    get_trip_route_plan,
    get_trip_for_user,
    get_user_trips,
    insert_trip_regions,
    optimize_trip_route,
    remove_location_from_trip as remove_location_from_trip_service,
)
from app.services.wishlist_service import (
    get_wishlist_items,
    toggle_wishlist_item,
)

api_bp = Blueprint('api', __name__, url_prefix='/api')


# ──────────────────────────────────────────────────────────────────
#  Helper: get user_id from session (returns None if not logged in)
# ──────────────────────────────────────────────────────────────────
def _user_id():
    # Backward-compatible helper kept for existing debug/route code paths.
    return get_user_id()


# ═══════════════════════════════════════════════════════════════════
#  1. EXPLORE LOCATIONS — paginated, filterable
#     GET /api/explore-locations?page=1&limit=40&search=&region=&category=
# ═══════════════════════════════════════════════════════════════════
@api_bp.route('/explore-locations')
def explore_locations():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 40, type=int)
    search = request.args.get('search', '').strip()
    region = request.args.get('region', '').strip()
    category = request.args.get('category', '').strip()

    # Build dynamic query
    query = 'SELECT location_id, name, locality, region, category, image_url, description FROM locations WHERE 1=1'
    params = []

    if search:
        query += ' AND (name LIKE %s OR locality LIKE %s OR region LIKE %s)'
        term = f'%{search}%'
        params.extend([term, term, term])
    if region:
        query += ' AND region = %s'
        params.append(region)
    if category:
        query += ' AND category = %s'
        params.append(category)

    # Count total
    count_q = query.replace(
        'SELECT location_id, name, locality, region, category, image_url',
        'SELECT COUNT(*) as total'
    )
    total_row = query_db(count_q, tuple(params), one=True)
    total = total_row['total'] if total_row else 0

    # Paginate
    total_pages = max(1, (total + limit - 1) // limit)
    offset = (page - 1) * limit
    query += ' ORDER BY name ASC LIMIT %s OFFSET %s'
    params.extend([limit, offset])

    locations = query_db(query, tuple(params))

    return jsonify({
        'locations': locations,
        'page': page,
        'limit': limit,
        'total': total,
        'total_pages': total_pages
    })


# ═══════════════════════════════════════════════════════════════════
#  2. REGIONS — all distinct regions for filter dropdowns
#     GET /api/regions/all
# ═══════════════════════════════════════════════════════════════════
@api_bp.route('/regions/all')
def regions_all():
    # Pull distinct regions from trip_regions table (user's trips),
    # then match to properly-formatted names from the locations table.
    trip_rows = query_db(
        'SELECT DISTINCT region_name FROM trip_regions WHERE region_name IS NOT NULL ORDER BY region_name'
    )
    if not trip_rows:
        return jsonify({'regions': []})

    # Get all distinct regions from locations for display-name lookup
    loc_rows = query_db(
        'SELECT DISTINCT region FROM locations WHERE region IS NOT NULL AND region != "" ORDER BY region'
    )
    loc_regions = [r['region'] for r in loc_rows] if loc_rows else []

    # Build a lookup: lowercase-no-spaces → proper display name
    display_map = {}
    for lr in loc_regions:
        key = lr.lower().replace(' ', '').replace('-', '')
        display_map[key] = lr

    regions = []
    for tr in trip_rows:
        raw = (tr['region_name'] or '').strip()
        if not raw:
            continue
        key = raw.lower().replace(' ', '').replace('-', '')
        # Use the locations table's display name if found, otherwise title-case
        display = display_map.get(key, raw.title())
        if display not in regions:
            regions.append(display)

    regions.sort()
    return jsonify({'regions': regions})


# ═══════════════════════════════════════════════════════════════════
#  2b. CATEGORIES — all distinct categories for filter dropdowns
#      GET /api/categories/all
# ═══════════════════════════════════════════════════════════════════
@api_bp.route('/categories/all')
def categories_all():
    rows = query_db(
        "SELECT DISTINCT category FROM locations WHERE category IS NOT NULL AND category != '' ORDER BY category"
    )
    categories = [r['category'] for r in rows] if rows else []
    return jsonify({'categories': categories})


# ═══════════════════════════════════════════════════════════════════
#  3. HOME LOCATIONS — 6 random featured locations
#     GET /api/home-locations
# ═══════════════════════════════════════════════════════════════════
@api_bp.route('/home-locations')
def home_locations():
    rows = query_db(
        '''SELECT location_id, name, locality, region, category, image_url, description
           FROM locations
           WHERE image_url IS NOT NULL AND image_url != ''
           ORDER BY RAND() LIMIT 6'''
    )
    return jsonify({'locations': rows or []})


# ═══════════════════════════════════════════════════════════════════
#  4. WISHLIST — get user's wishlist / toggle
#     GET  /api/wishlist
#     POST /api/toggle-wishlist       { location_id }
#     POST /api/wishlist/toggle       { location_id }  (draft.js variant)
# ═══════════════════════════════════════════════════════════════════
@api_bp.route('/wishlist')
@login_required
def get_wishlist():
    user_id = _user_id()
    return jsonify(get_wishlist_items(user_id))


@api_bp.route('/toggle-wishlist', methods=['POST'])
@api_bp.route('/wishlist/toggle', methods=['POST'])
@login_required
def toggle_wishlist():
    user_id = _user_id()
    data = get_json_payload()
    location_id = data.get('location_id')

    if not location_id:
        return jsonify({'error': 'location_id required'}), 400

    return jsonify(toggle_wishlist_item(user_id, location_id))


# ═══════════════════════════════════════════════════════════════════
#  5. MY TRIPS — user's draft + finalized trips
#     GET /api/my-trips
# ═══════════════════════════════════════════════════════════════════
@api_bp.route('/my-trips')
@login_required
def my_trips():
    user_id = _user_id()
    return jsonify(get_user_trips(user_id))


# ═══════════════════════════════════════════════════════════════════
#  6. SUBMIT TRIP — create a new trip from the 8-step form
#     POST /api/submit-trip   (JSON body)
# ═══════════════════════════════════════════════════════════════════
@api_bp.route('/submit-trip', methods=['POST'])
@login_required
def submit_trip():
    user_id = _user_id()
    data = get_json_payload()

    trip_name = data.get('tripName', '').strip()
    start_region = data.get('startRegion', '').strip()
    end_region = data.get('endRegion', '').strip() or None
    travelling_regions = data.get('travellingRegions', [])
    trip_priority = data.get('tripPriority', {})
    pace = data.get('pace', 'balanced')
    companion = data.get('companion', 'couple')
    season = data.get('season', 'anytime')
    planning_mode = data.get('planningMode', 'manual')
    trip_days = data.get('tripDays', 3)

    # Manual trips often send tripDays=0 from the create-trip wizard.
    # Keep trip_days meaningful for AI suggestion capacity.
    try:
        trip_days = int(trip_days)
    except Exception:
        trip_days = 0
    if planning_mode != 'auto' and trip_days < 1:
        trip_days = 3

    focus_mode = trip_priority.get('mode', 'diversity')
    diversity_mode = 1 if focus_mode == 'diversity' else 0

    if not trip_name or not start_region:
        return jsonify({'success': False, 'message': 'Trip name and start region are required'}), 400

    if not travelling_regions:
        return jsonify({'success': False, 'message': 'At least one travel region is required'}), 400

    try:
        trip_id = create_trip(
            user_id=user_id,
            trip_name=trip_name,
            start_region=start_region,
            end_region=end_region,
            focus_mode=focus_mode,
            diversity_mode=diversity_mode,
            pace=pace,
            companion=companion,
            season=season,
            planning_mode=planning_mode,
            trip_days=trip_days,
        )

        insert_trip_regions(trip_id, travelling_regions)

        # Store trip_id in session for the draft page
        session['current_trip_id'] = trip_id

        return jsonify({
            'success': True,
            'trip_id': trip_id,
            'message': 'Trip created successfully!',
            'redirect': f'/trips/{trip_id}/plan'
        })

    except Exception as e:
        print(f'[API] submit-trip error: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


# ═══════════════════════════════════════════════════════════════════
#  6b. AUTO-GENERATE TRIP — create trip + AI suggestions + auto-select
#      POST /api/trips/auto-generate   (JSON body — same as submit-trip)
# ═══════════════════════════════════════════════════════════════════
@api_bp.route('/trips/auto-generate', methods=['POST'])
@login_required
def auto_generate_trip():
    user_id = _user_id()
    data = get_json_payload()

    trip_name = data.get('tripName', '').strip()
    start_region = data.get('startRegion', '').strip()
    end_region = data.get('endRegion', '').strip() or None
    travelling_regions = data.get('travellingRegions', [])
    trip_priority = data.get('tripPriority', {})
    pace = (data.get('pace', 'balanced') or 'balanced').strip().lower()
    companion = data.get('companion', 'couple')
    season = data.get('season', 'anytime')
    trip_days = data.get('tripDays', 3)
    min_days_per_region = data.get('minDaysPerRegion', 2)

    focus_mode = trip_priority.get('mode', 'diversity')
    diversity_mode = 1 if focus_mode == 'diversity' else 0

    if not trip_name or not start_region:
        return jsonify({'success': False, 'message': 'Trip name and start region are required'}), 400
    if not travelling_regions:
        return jsonify({'success': False, 'message': 'At least one travel region is required'}), 400

    if pace not in ('relaxed', 'balanced', 'packed'):
        pace = 'balanced'

    def _norm_region_key(text: str) -> str:
        """Normalize a region string for comparison (strip spaces, lowercase)."""
        return (text or '').strip().lower().replace(' ', '').replace('-', '').replace('_', '')

    def _region_match(user_text: str, value: str) -> bool:
        ut = _norm_region_key(user_text)
        vv = _norm_region_key(value)
        if not ut or not vv:
            return False
        # Exact slug match ("madhyapradesh" == "madhyapradesh")
        if ut == vv:
            return True
        # Substring ("goa" in "northgoa")
        if ut in vv or vv in ut:
            return True
        return SequenceMatcher(None, ut, vv).ratio() > 0.8

    def _matches_any_region(value: str, allowed: list[str]) -> bool:
        for ar in allowed:
            if _region_match(ar, value):
                return True
            # Also try display name comparison
            if _region_match(get_display_region(ar), value):
                return True
        return False

    try:
        trip_days = int(trip_days)
    except Exception:
        return jsonify({'success': False, 'message': 'tripDays must be a number'}), 400
    if trip_days < 1 or trip_days > 30:
        return jsonify({'success': False, 'message': 'tripDays must be between 1 and 30'}), 400

    try:
        min_days_per_region = int(min_days_per_region)
    except Exception:
        return jsonify({'success': False, 'message': 'minDaysPerRegion must be a number'}), 400
    if min_days_per_region < 1 or min_days_per_region > 10:
        return jsonify({'success': False, 'message': 'minDaysPerRegion must be between 1 and 10'}), 400

    # Hard barrier: too many regions for the requested days/region.
    # We fail fast instead of silently dropping regions (more predictable UX).
    regions_count = len([r for r in (travelling_regions or []) if (r or '').strip()])
    max_regions_by_days = (trip_days // min_days_per_region) if (trip_days and min_days_per_region) else 0

    # If max_regions_by_days is 0, it's mathematically impossible to cover even 1 region.
    if regions_count > 0 and max_regions_by_days < 1:
        return jsonify({
            'success': False,
            'message': f'Not enough days. With {trip_days} total days and {min_days_per_region} days/region, you need at least {min_days_per_region} day(s) to cover 1 region.'
        }), 400

    if regions_count > max_regions_by_days:
        return jsonify({
            'success': False,
            'message': f'Too many regions for this duration. With {trip_days} days and {min_days_per_region} days/region, you can cover at most {max_regions_by_days} region(s). Reduce regions or increase days.'
        }), 400

    # Practical caps based on duration and pace
    locs_per_day = {'relaxed': 2, 'balanced': 3, 'packed': 5}[pace]
    max_total_locations = max(1, min(trip_days * locs_per_day, 40))

    # If too many regions for the given days, prioritize a subset.
    extra_regions = {'relaxed': 0, 'balanced': 1, 'packed': 2}[pace]
    max_regions = min(len(travelling_regions), trip_days + extra_regions, max_regions_by_days)

    ordered_regions: list[str] = []
    for r in travelling_regions:
        rr = (r or '').strip()
        if rr and rr not in ordered_regions:
            ordered_regions.append(rr)

    # Prefer start/end in the subset if present
    if start_region and start_region in ordered_regions:
        ordered_regions.remove(start_region)
        ordered_regions.insert(0, start_region)
    if end_region and end_region in ordered_regions:
        ordered_regions.remove(end_region)
        ordered_regions.append(end_region)

    regions_for_ai = ordered_regions[:max_regions]

    display_regions_for_ai = [get_display_region(r) for r in regions_for_ai]

    try:
        # ── Step 1: Create the trip in DB ──
        trip_id = create_trip(
            user_id=user_id,
            trip_name=trip_name,
            start_region=start_region,
            end_region=end_region,
            focus_mode=focus_mode,
            diversity_mode=diversity_mode,
            pace=pace,
            companion=companion,
            season=season,
            planning_mode='auto',
            trip_days=trip_days,
        )

        insert_trip_regions(trip_id, travelling_regions)

        session['current_trip_id'] = trip_id

        # ── Steps 2+3: Generate AI suggestions + verify, with retry loop ──
        # Keep requesting from Gemini until we have enough locations for trip_days.
        trip_data = {
            'travel_regions': display_regions_for_ai,
            'start_region': get_display_region(start_region),
            'end_region': get_display_region(end_region) if end_region else '',
            'pace': pace,
            'companion_type': companion,
            'season': season,
            'diversity_mode': bool(diversity_mode),
            'focus_mode': focus_mode,
            'trip_days': trip_days,
        }
        # Keep requesting from Gemini until we have enough locations for trip_days.
        MAX_AI_ROUNDS = 3
        added_count = 0
        per_region_cap = max(1, int((max_total_locations + len(regions_for_ai) - 1) // max(1, len(regions_for_ai))))
        per_region_selected: dict[str, int] = {}
        excluded_names: list[str] = []  # Track already-added names to avoid duplicates

        for ai_round in range(MAX_AI_ROUNDS):
            # ── Step 2: Generate AI suggestions ──
            raw = suggest_places(trip_data, display_regions_for_ai, excluded_places=excluded_names,
                                 total_override=max_total_locations - added_count)

            if not raw:
                print(f'[API] auto-generate round {ai_round + 1}: Gemini returned 0 suggestions, stopping')
                break

            # ── Step 3: Verify + store + auto-select each suggestion ──
            round_added = 0
            for place in raw:
                if added_count >= max_total_locations:
                    break

                name = canonical_place_name(place.get('name', ''))
                category = place.get('category', 'destination')
                region = place.get('region', '')
                verified_region = None

                # Skip if already added in a previous round
                if name.lower() in [n.lower() for n in excluded_names]:
                    continue

                # Enforce region caps so one region doesn't dominate.
                rkey = (region or '').strip() or 'Other'
                if per_region_selected.get(rkey, 0) >= per_region_cap:
                    continue

                # Do not treat whole cities/regions as a single location.
                if is_broad_location_row({'name': name, 'category': category}):
                    continue

                # Check if location already exists in DB
                loc = query_db(
                    'SELECT location_id, name, category, region, locality FROM locations WHERE name = %s',
                    (name,), one=True
                )

                if not loc:
                    # Verify via OSM
                    osm = verify_place(name, region)
                    if not osm:
                        continue

                    # Use ONLY OSM-verified region — never trust Gemini's region label
                    verified_region = (osm.get('region') or '').strip()
                    # Enforce the trip's regions list so AI doesn't drift.
                    if travelling_regions and verified_region and not _matches_any_region(verified_region, travelling_regions):
                        continue
                    # If OSM returned no region, still reject (we can't verify it)
                    if travelling_regions and not verified_region:
                        continue

                    img = get_image(name) or ''

                    loc_id = execute_db(
                        '''INSERT INTO locations (name, locality, region, category,
                           latitude, longitude, image_url)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                        (name, osm.get('locality', ''), verified_region,
                         category, osm['lat'], osm['lon'], img)
                    )
                else:
                    if is_broad_location_row(loc):
                        continue
                    if travelling_regions and loc.get('region') and not _matches_any_region(loc.get('region'), travelling_regions):
                        continue
                    loc_id = loc['location_id']

                # Link to trip as 'selected' (auto-mode skips manual selection)
                exists = query_db(
                    'SELECT trip_location_id FROM trip_locations WHERE trip_id = %s AND location_id = %s',
                    (trip_id, loc_id), one=True
                )
                if not exists:
                    execute_db(
                        'INSERT INTO trip_locations (trip_id, location_id, status, visit_order) VALUES (%s, %s, %s, %s)',
                        (trip_id, loc_id, 'selected', added_count + 1)
                    )
                    added_count += 1
                    round_added += 1
                    excluded_names.append(name)
                    # Use verified region if available for cap accounting.
                    count_key = (verified_region or (loc.get('region') if loc else region) or rkey or 'Other')
                    per_region_selected[count_key] = per_region_selected.get(count_key, 0) + 1

            print(f'[API] auto-generate round {ai_round + 1}: added {round_added} locations (total: {added_count})')

            # Check if we have enough days — build itinerary to count
            if added_count >= max_total_locations:
                break
            try:
                optimize_trip_route(trip_id=trip_id, user_id=user_id)
                it = build_trip_itinerary(trip_id=trip_id, pace=pace)
                day_count = sum(len(r.get('days') or []) for r in (it.get('regions') or []))
                if day_count >= trip_days:
                    print(f'[API] auto-generate: {day_count} days >= {trip_days} target, stopping')
                    break
                print(f'[API] auto-generate: only {day_count} days vs {trip_days} target, requesting more...')
            except Exception:
                # If itinerary building fails, just continue
                if added_count >= max_total_locations // 2:
                    break

        # Optimize and trim to fit within trip_days (best-effort)
        trimmed = 0
        try:
            optimize_trip_route(trip_id=trip_id, user_id=user_id)

            # If day-splitting still exceeds requested days (due to long travel), drop last stops.
            for _ in range(25):
                it = build_trip_itinerary(trip_id=trip_id, pace=pace)
                day_count = sum(len(r.get('days') or []) for r in (it.get('regions') or []))
                if day_count <= trip_days:
                    break

                # Prefer trimming a "low priority" stop:
                # - avoid POIs matching start/end preferences
                # - avoid start/end regions when possible
                selected_rows = query_db(
                    '''SELECT tl.location_id, tl.visit_order, l.locality, l.region
                       FROM trip_locations tl
                       JOIN locations l ON tl.location_id = l.location_id
                       WHERE tl.trip_id = %s AND tl.status = 'selected'
                       ORDER BY tl.visit_order DESC''',
                    (trip_id,),
                ) or []
                if not selected_rows:
                    break

                protected_ids: set[int] = set()
                if start_region:
                    for r in selected_rows:
                        if _region_match(start_region, (r.get('locality') or '')) or _region_match(start_region, (r.get('region') or '')):
                            protected_ids.add(int(r['location_id']))
                if end_region:
                    for r in selected_rows:
                        if _region_match(end_region, (r.get('locality') or '')) or _region_match(end_region, (r.get('region') or '')):
                            protected_ids.add(int(r['location_id']))

                def _is_start_end_region(rrow: dict) -> bool:
                    rr = (rrow.get('region') or '')
                    return (
                        (start_region and _region_match(start_region, rr))
                        or (end_region and _region_match(end_region, rr))
                    )

                candidate = None
                # 1) last stop not protected and not in start/end regions
                for r in selected_rows:
                    lid = int(r['location_id'])
                    if lid in protected_ids:
                        continue
                    if _is_start_end_region(r):
                        continue
                    candidate = r
                    break
                # 2) last stop not protected
                if candidate is None:
                    for r in selected_rows:
                        lid = int(r['location_id'])
                        if lid in protected_ids:
                            continue
                        candidate = r
                        break
                # 3) fallback: last stop
                if candidate is None:
                    candidate = selected_rows[0]

                execute_db(
                    'DELETE FROM trip_locations WHERE trip_id = %s AND location_id = %s',
                    (trip_id, candidate['location_id']),
                )
                trimmed += 1
                if added_count > 0:
                    added_count -= 1

                # Re-optimize after trimming
                optimize_trip_route(trip_id=trip_id, user_id=user_id)

        except Exception as e:
            print(f'[API] auto-generate optimize/trim warning: {e}')

        finalize_trip_service(trip_id=trip_id, user_id=user_id)

        return jsonify({
            'success': True,
            'trip_id': trip_id,
            'locations_added': added_count,
            'message': f'Trip created with {added_count} AI-picked destinations!' + (f' (Trimmed {trimmed} to fit {trip_days} days.)' if trimmed else ''),
            'redirect': f'/itinerary/{trip_id}'
        })

    except Exception as e:
        print(f'[API] auto-generate error: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


# ═══════════════════════════════════════════════════════════════════
#  7. TRIP SUGGESTIONS — get AI suggestions for a trip
#     GET /api/trips/<trip_id>/suggestions
# ═══════════════════════════════════════════════════════════════════
@api_bp.route('/trips/<int:trip_id>/suggestions', methods=['GET', 'POST'])
@login_required
def trip_suggestions(trip_id):
    user_id = _user_id()

    # Verify ownership
    trip = query_db(
        'SELECT * FROM trips WHERE trip_id = %s AND user_id = %s',
        (trip_id, user_id), one=True
    )
    if not trip:
        return jsonify({'error': 'Trip not found'}), 404

    if request.method == 'POST' and (trip.get('trip_status') or 'draft') == 'finalized':
        return jsonify({'error': 'Trip is finalized and cannot be modified'}), 409

    # Get existing suggestions from DB
    existing_suggestions = query_db(
        '''SELECT l.location_id as suggestion_id, l.name, l.category, l.region,
                  l.locality, l.image_url, l.description
           FROM trip_locations tl
           JOIN locations l ON tl.location_id = l.location_id
           WHERE tl.trip_id = %s AND tl.status = 'suggested' ''',
        (trip_id,)
    ) or []

    # If GET request, return existing (even if empty)
    if request.method == 'GET':
        return jsonify({'suggestions': existing_suggestions})

    # For POST (explicit new generation):
    # 1. Gather all currently known names to exclude them
    excluded_names = []
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        excluded_names = data.get('excluded_names', [])

    planning_mode = (trip.get('planning_mode') or 'manual').strip().lower()
    print(f'[DEBUG] trip_suggestions: trip_id={trip_id}, user_id={user_id}, mode={planning_mode}, POST excluded={len(excluded_names)}')

    # Also exclude what's already in DB for this trip (selected or suggested)
    existing_in_trip = query_db(
        '''SELECT l.name, l.image_url FROM trip_locations tl
           JOIN locations l ON tl.location_id = l.location_id
           WHERE tl.trip_id = %s''',
        (trip_id,)
    )
    
    # If it's already in DB, we rely on name mainly, but could check image too.
    if existing_in_trip:
        excluded_names.extend([row['name'] for row in existing_in_trip])

    # 2. Prepare trip data for AI
    regions = query_db(
        'SELECT region_name FROM trip_regions WHERE trip_id = %s',
        (trip_id,)
    )
    region_list = [r['region_name'] for r in regions] if regions else []

    def _region_match(user_text: str, value: str) -> bool:
        ut = (user_text or '').strip().lower()
        vv = (value or '').strip().lower()
        if not ut or not vv:
            return False
        if ut in vv or vv in ut:
            return True
        return SequenceMatcher(None, ut, vv).ratio() > 0.8

    def _matches_any_trip_region(value: str) -> bool:
        if not region_list:
            return True
        for tr in region_list:
            if _region_match(tr, value):
                return True
        return False

    display_regions = [get_display_region(r) for r in region_list]
    
    trip_data = {
        'travel_regions': display_regions,
        'start_region': get_display_region(trip.get('start_region')),
        'end_region': get_display_region(trip.get('end_region')) if trip.get('end_region') else '',
        'pace': trip.get('pace', 'balanced'),
        'companion_type': trip.get('companion_type'),
        'season': trip.get('season'),
        'diversity_mode': bool(trip.get('diversity_mode')),
        'trip_days': trip.get('trip_days', 3),
        'focus_mode': trip.get('focus_mode')
    }

    try:
        # 3. Call AI with exclusions
        total_override = None
        desired_new = None

        # Manual-mode suggestions should be generous.
        # We over-generate (within caps) so that region filtering + OSM verification
        # still leaves a useful number of suggestions.
        if planning_mode != 'auto':
            try:
                trip_days = int(trip_data.get('trip_days') or 3)
            except Exception:
                trip_days = 3
            trip_days = max(1, min(trip_days, 30))

            pace = (trip_data.get('pace') or 'balanced').strip().lower()
            if pace not in ('relaxed', 'balanced', 'packed'):
                pace = 'balanced'
            locs_per_day = {'relaxed': 2, 'balanced': 3, 'packed': 5}[pace]
            capacity = max(1, trip_days * locs_per_day)

            desired_new = max(15, min(25, capacity * 2))
            total_override = max(capacity * 3, desired_new + 8)
            total_override = max(1, min(int(total_override), 40))

        raw = suggest_places(
            trip_data,
            display_regions,
            excluded_places=excluded_names,
            total_override=total_override,
        )

        verified = []
        skip_counts = {
            'broad': 0,
            'fuzzy_dup': 0,
            'osm_fail': 0,
            'region_mismatch': 0,
            'exists_in_trip': 0,
            'linked': 0,
        }
        
        # Get existing names for fuzzy duplicate checking
        # This includes names already in the trip (selected or suggested)
        existing_names_for_fuzzy = [row['name'].lower() for row in existing_in_trip] if existing_in_trip else []

        for place in raw:
            if desired_new is not None and len(verified) >= desired_new:
                break
            name = canonical_place_name(place.get('name', '').strip())
            category = place.get('category', 'destination')
            region = place.get('region', '')
            
            if not name:
                continue

            # Do not treat whole cities/regions as a single location.
            if is_broad_location_row({'name': name, 'category': category}):
                skip_counts['broad'] += 1
                continue

            # Fuzzy Duplicate Check against existing names in the trip
            is_duplicate = False
            for ex_name in existing_names_for_fuzzy:
                ratio = SequenceMatcher(None, name.lower(), ex_name).ratio()
                if ratio > 0.85: # 85% similarity threshold
                    print(f'[DEBUG] Skipping fuzzy duplicate: {name} (matches {ex_name} {ratio:.2f})')
                    is_duplicate = True
                    break
            
            if is_duplicate:
                skip_counts['fuzzy_dup'] += 1
                continue

            # Check if already in DB
            loc = query_db(
                'SELECT location_id, name, category, region, locality FROM locations WHERE name = %s',
                (name,), one=True
            )

            if not loc:
                # Verify via OSM
                print(f'[DEBUG] Verifying via OSM: {name}')
                osm = verify_place(name, region)
                if not osm:
                    print(f'[DEBUG] OSM failed for: {name}')
                    skip_counts['osm_fail'] += 1
                    continue
                
                # Strict Region Check (Post-Verification)
                verified_region = (osm.get('region') or region or '').strip()
                verified_locality = (osm.get('locality') or '').strip()

                # Accept if either locality OR region matches any trip region.
                if region_list and not (
                    _matches_any_trip_region(verified_region) or
                    _matches_any_trip_region(verified_locality) or
                    _matches_any_trip_region(f"{verified_locality} {verified_region}".strip())
                ):
                    print(f'[DEBUG] Skipped {name}: locality="{verified_locality}" region="{verified_region}" not in {region_list}')
                    skip_counts['region_mismatch'] += 1
                    continue

                img = get_image(name) or ''

                loc_id = execute_db(
                    '''INSERT INTO locations (name, locality, region, category,
                       latitude, longitude, image_url, description)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
                    (name, osm.get('locality', ''), osm.get('region', region),
                     category, osm['lat'], osm['lon'], img, place.get('description', ''))
                )
                print(f'[DEBUG] Inserted new location: {name} ID={loc_id}')
            else:
                if is_broad_location_row(loc):
                    skip_counts['broad'] += 1
                    continue

                # Enforce region constraint even for existing DB rows.
                if region_list:
                    verified_region = (loc.get('region') or '').strip()
                    verified_locality = (loc.get('locality') or '').strip()
                    if not (
                        _matches_any_trip_region(verified_region) or
                        _matches_any_trip_region(verified_locality) or
                        _matches_any_trip_region(f"{verified_locality} {verified_region}".strip())
                    ):
                        print(f'[DEBUG] Skipped {name}: locality="{verified_locality}" region="{verified_region}" not in {region_list}')
                        skip_counts['region_mismatch'] += 1
                        continue

                loc_id = loc['location_id']
                print(f'[DEBUG] Found existing location: {name} ID={loc_id}')

            # Link to trip
            exists = query_db(
                'SELECT trip_location_id FROM trip_locations WHERE trip_id = %s AND location_id = %s',
                (trip_id, loc_id), one=True
            )
            if not exists:
                lid = execute_db(
                    'INSERT INTO trip_locations (trip_id, location_id, status) VALUES (%s, %s, %s)',
                    (trip_id, loc_id, 'suggested')
                )
                print(f'[DEBUG] Linked to trip {trip_id}: {name} (trip_loc_id={lid})')
                skip_counts['linked'] += 1
                
                # Fetch full details for response
                full_loc = query_db(
                    'SELECT location_id as suggestion_id, name, category, region, locality, image_url, description FROM locations WHERE location_id = %s',
                    (loc_id,), one=True
                )
                if full_loc:
                    verified.append(full_loc)
            else:
                skip_counts['exists_in_trip'] += 1

        print(f"[DEBUG] trip_suggestions summary: raw={len(raw)} linked={skip_counts['linked']} skip={skip_counts}")

        # Manual-mode robustness: if verification/region filtering produced too few items,
        # backfill from existing DB rows in the trip's regions (or localities).
        if planning_mode != 'auto':
            min_ok = 6
            if desired_new is not None:
                min_ok = max(6, min(12, int(desired_new // 2)))

            if len(verified) < min_ok and region_list:
                try:
                    need = min_ok - len(verified)

                    # Build OR filters for region/locality.
                    ors = []
                    params: list = []
                    for r in region_list:
                        rr = (r or '').strip().lower()
                        if not rr:
                            continue
                        like = f"%{rr}%"
                        ors.append('(LOWER(l.region) LIKE %s OR LOWER(l.locality) LIKE %s)')
                        params.extend([like, like])

                    if ors:
                        rows = query_db(
                            f'''SELECT l.location_id, l.name, l.category, l.region, l.locality, l.image_url, l.description
                                FROM locations l
                                WHERE NOT EXISTS (
                                    SELECT 1 FROM trip_locations tl
                                    WHERE tl.trip_id = %s AND tl.location_id = l.location_id
                                )
                                AND ({' OR '.join(ors)})
                                ORDER BY RAND()
                                LIMIT %s''',
                            tuple([trip_id] + params + [need]),
                        ) or []

                        for r in rows:
                            if not r:
                                continue
                            if is_broad_location_row(r):
                                continue
                            execute_db(
                                'INSERT INTO trip_locations (trip_id, location_id, status) VALUES (%s, %s, %s)',
                                (trip_id, r['location_id'], 'suggested'),
                            )
                            verified.append({
                                'suggestion_id': r['location_id'],
                                'name': r.get('name'),
                                'category': r.get('category'),
                                'region': r.get('region'),
                                'locality': r.get('locality'),
                                'image_url': r.get('image_url'),
                                'description': r.get('description'),
                            })
                except Exception as e:
                    print(f'[DEBUG] trip_suggestions manual backfill warning: {e}')

        # Return merged list (existing + new)
        all_suggestions = existing_suggestions + verified
        return jsonify({
            'suggestions': all_suggestions,
            'new_count': len(verified),
            'message': f'{len(verified)} new suggestions added!'
        })

    except Exception as e:
        print(f'[API] trip suggestions error: {e}')
        return jsonify({'suggestions': existing_suggestions, 'message': f'AI error: {str(e)}'})


# ═══════════════════════════════════════════════════════════════════
#  8. ADD LOCATION TO TRIP
#     POST /api/trips/add-location   { trip_id, location_id }
# ═══════════════════════════════════════════════════════════════════
@api_bp.route('/trips/<int:trip_id>/selected-locations')
@login_required
def get_selected_locations(trip_id):
    user_id = _user_id()
    
    # Verify ownership
    trip = get_trip_for_user(trip_id, user_id, full=False)
    if not trip:
        return jsonify({'error': 'Trip not found'}), 404

    return jsonify({'locations': get_selected_locations_service(trip_id)})


@api_bp.route('/trips/add-location', methods=['POST'])
@login_required
def add_location_to_trip():
    user_id = _user_id()
    data = get_json_payload()
    trip_id = data.get('trip_id')
    location_id = data.get('location_id')

    if not trip_id or not location_id:
        return jsonify({'error': 'trip_id and location_id required'}), 400

    # Verify trip ownership
    trip = get_trip_for_user(trip_id, user_id, full=True)
    if not trip:
        return jsonify({'error': 'Trip not found'}), 404

    if (trip.get('trip_status') or 'draft') == 'finalized':
        return jsonify({'error': 'Trip is finalized and cannot be modified'}), 409

    # Safety: prevent broad areas (cities/regions) from being added as single POIs.
    loc_row = query_db(
        'SELECT location_id, name, category, locality, region FROM locations WHERE location_id = %s',
        (location_id,),
        one=True,
    )
    if loc_row and is_broad_location_row(loc_row):
        return jsonify({'error': 'Please select a specific place (attraction), not a whole city/region.'}), 400

    allowed, err = enforce_region_constraint(trip_id=trip_id, location_id=location_id)
    if not allowed:
        return jsonify({'error': err}), 400

    return jsonify(add_location_to_trip_service(trip_id=trip_id, location_id=location_id))


# ═══════════════════════════════════════════════════════════════════
#  8b. SUGGEST LOCATION INTO A TRIP (for Add-to-Trip modal)
#      POST /api/trips/suggest-location   { trip_id, location_id }
#      - inserts/updates trip_locations.status='suggested'
# ═══════════════════════════════════════════════════════════════════
@api_bp.route('/trips/suggest-location', methods=['POST'])
@login_required
def suggest_location_into_trip():
    user_id = _user_id()
    data = get_json_payload()
    trip_id = data.get('trip_id')
    location_id = data.get('location_id')

    if not trip_id or not location_id:
        return jsonify({'error': 'trip_id and location_id required'}), 400

    trip = get_trip_for_user(trip_id, user_id, full=True)
    if not trip:
        return jsonify({'error': 'Trip not found'}), 404
    if (trip.get('trip_status') or 'draft') == 'finalized':
        return jsonify({'error': 'Trip is finalized and cannot be modified'}), 409

    # Safety: prevent broad areas (cities/regions) from being added as single POIs.
    loc_row = query_db(
        'SELECT location_id, name, category, locality, region FROM locations WHERE location_id = %s',
        (location_id,),
        one=True,
    )
    if loc_row and is_broad_location_row(loc_row):
        return jsonify({'error': 'Please select a specific place (attraction), not a whole city/region.'}), 400

    allowed, err = enforce_region_constraint(trip_id=trip_id, location_id=location_id)
    if not allowed:
        return jsonify({'error': err}), 400

    existing = query_db(
        'SELECT trip_location_id, status FROM trip_locations WHERE trip_id = %s AND location_id = %s',
        (trip_id, location_id),
        one=True,
    )
    if existing:
        # If it's already selected/confirmed, don't downgrade it.
        if (existing.get('status') or '').lower() in ('selected', 'confirmed'):
            return jsonify({'success': True, 'message': 'Location already exists in trip'}), 200

        execute_db(
            "UPDATE trip_locations SET status = 'suggested', visit_order = NULL WHERE trip_id = %s AND location_id = %s",
            (trip_id, location_id),
        )
        return jsonify({'success': True, 'message': 'Location added to suggestions'}), 200

    execute_db(
        'INSERT INTO trip_locations (trip_id, location_id, status) VALUES (%s, %s, %s)',
        (trip_id, location_id, 'suggested'),
    )
    return jsonify({'success': True, 'message': 'Location added to suggestions'}), 200


# ═══════════════════════════════════════════════════════════════════
#  8c. QUICK CREATE DRAFT TRIP + SUGGEST LOCATION
#      POST /api/trips/quick-create   { location_id, trip_name? }
# ═══════════════════════════════════════════════════════════════════
@api_bp.route('/trips/quick-create', methods=['POST'])
@login_required
def quick_create_trip_with_location():
    user_id = _user_id()
    data = get_json_payload()
    location_id = data.get('location_id')
    trip_name = (data.get('trip_name') or '').strip()

    if not location_id:
        return jsonify({'error': 'location_id required'}), 400

    loc = query_db(
        'SELECT location_id, name, category, locality, region FROM locations WHERE location_id = %s',
        (location_id,),
        one=True,
    )
    if not loc:
        return jsonify({'error': 'Location not found'}), 404
    if is_broad_location_row(loc):
        return jsonify({'error': 'Please select a specific place (attraction), not a whole city/region.'}), 400

    start_region = (loc.get('locality') or loc.get('region') or '').strip() or 'India'
    main_region = (loc.get('region') or start_region).strip() or start_region

    if not trip_name:
        trip_name = f"Trip to {loc.get('name') or 'New Destination'}"

    # Create a manual draft trip with a sensible default trip_days so AI suggestions are useful.
    trip_id = create_trip(
        user_id=user_id,
        trip_name=trip_name,
        start_region=start_region,
        end_region=None,
        focus_mode='diversity',
        diversity_mode=1,
        pace='balanced',
        companion='couple',
        season='anytime',
        planning_mode='manual',
        trip_days=3,
    )

    insert_trip_regions(trip_id, [main_region])
    session['current_trip_id'] = trip_id

    execute_db(
        'INSERT INTO trip_locations (trip_id, location_id, status) VALUES (%s, %s, %s)',
        (trip_id, location_id, 'suggested'),
    )

    return jsonify({
        'success': True,
        'trip_id': trip_id,
        'message': 'Trip created and location added to suggestions',
        'redirect': f'/draft_trip/{trip_id}',
    })


@api_bp.route('/trips/remove-location', methods=['POST'])
@login_required
def remove_location_from_trip():
    user_id = _user_id()
    data = get_json_payload()
    trip_id = data.get('trip_id')
    location_id = data.get('location_id')

    if not trip_id or not location_id:
        return jsonify({'error': 'trip_id and location_id required'}), 400

    # Verify ownership
    trip = get_trip_for_user(trip_id, user_id, full=True)
    if not trip:
        return jsonify({'error': 'Trip not found'}), 404

    if (trip.get('trip_status') or 'draft') == 'finalized':
        return jsonify({'error': 'Trip is finalized and cannot be modified'}), 409

    return jsonify(remove_location_from_trip_service(trip_id=trip_id, location_id=location_id))


# ═══════════════════════════════════════════════════════════════════
#  9. LOCATION SEARCH — search locations by name/locality/region
#     GET /api/locations/search?q=
# ═══════════════════════════════════════════════════════════════════
@api_bp.route('/locations/search')
def search_locations():
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify({'locations': []})

    rows = [r for r in search_locations_in_db(q, limit=20) if not is_broad_location_row(r)]
    rows = dedupe_location_rows(rows)
    
    # If found in DB, return them (prioritize local data)
    if rows:
        return jsonify({'locations': rows})

    # Try OSM directly first — fast, free, no rate limits
    fallback = search_or_import_location_from_osm(q)
    if fallback:
        return jsonify({'locations': fallback})

    # Only use Gemini normalization as a LAST RESORT (slow, rate-limited)
    normalized = normalize_location_query(q)
    normalized_name = (normalized.get('name') or q).strip() or q
    normalized_region = (normalized.get('region') or '').strip()

    if normalized_name and normalized_name.lower() != q.lower():
        # Try DB with normalized name
        normalized_rows = [
            r for r in search_locations_in_db(normalized_name, limit=20)
            if not is_broad_location_row(r)
        ]
        normalized_rows = dedupe_location_rows(normalized_rows)
        if normalized_rows:
            return jsonify({'locations': normalized_rows})

        # Try OSM with normalized name + region hint
        fallback2 = search_or_import_location_from_osm(normalized_name, region=normalized_region or None)
        if fallback2:
            return jsonify({'locations': fallback2})

    return jsonify({'locations': []})


@api_bp.route('/locations/autocomplete')
def locations_autocomplete():
    q = request.args.get('q', '').strip()
    limit = request.args.get('limit', 10, type=int)

    if not q or len(q) < 2:
        return jsonify({'locations': []})

    limit = max(1, min(limit, 20))
    rows = [r for r in search_locations_in_db(q, limit=limit) if not is_broad_location_row(r)]
    rows = dedupe_location_rows(rows)
    return jsonify({'locations': rows})


# ═══════════════════════════════════════════════════════════════════
#  10. TRIP ITINERARY — grouped by Region → Day → Locations
#      GET /api/trips/<trip_id>/itinerary
# ═══════════════════════════════════════════════════════════════════
@api_bp.route('/trips/<int:trip_id>/itinerary')
@login_required
def trip_itinerary(trip_id):
    user_id = _user_id()

    trip = get_trip_for_user(trip_id, user_id, full=True)
    if not trip:
        return jsonify({'error': 'Trip not found'}), 404
    return jsonify(build_trip_itinerary(trip_id=trip_id, pace=trip.get('pace', 'balanced')))


@api_bp.route('/trips/<int:trip_id>/route-plan')
@login_required
def trip_route_plan(trip_id: int):
    user_id = _user_id()

    trip = get_trip_for_user(trip_id, user_id, full=False)
    if not trip:
        return jsonify({'error': 'Trip not found'}), 404

    plan = get_trip_route_plan(trip_id=trip_id)
    return jsonify({'plan': plan})


# ═══════════════════════════════════════════════════════════════════
#  10b. OPTIMIZE TRIP ROUTE — OSRM table + NN + 2-Opt
#      POST /api/trips/<trip_id>/optimize
# ═══════════════════════════════════════════════════════════════════
@api_bp.route('/trips/<int:trip_id>/optimize', methods=['POST'])
@login_required
def optimize_trip(trip_id: int):
    user_id = _user_id()

    trip = get_trip_for_user(trip_id, user_id, full=True)
    if not trip:
        return jsonify({'success': False, 'message': 'Trip not found'}), 404

    if (trip.get('trip_status') or 'draft') == 'finalized':
        return jsonify({'success': False, 'message': 'Trip is finalized and cannot be optimized'}), 409

    data = get_json_payload()
    start_location_id = data.get('start_location_id')
    end_location_id = data.get('end_location_id')

    try:
        result = optimize_trip_route(
            trip_id=trip_id,
            user_id=user_id,
            start_location_id=start_location_id,
            end_location_id=end_location_id,
        )
        return jsonify({'success': True, **result})
    except LookupError:
        return jsonify({'success': False, 'message': 'Trip not found'}), 404
    except PermissionError as e:
        return jsonify({'success': False, 'message': str(e)}), 409
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except RuntimeError as e:
        # OSRM/network error
        return jsonify({'success': False, 'message': str(e)}), 502
    except Exception as e:
        print(f'[API] optimize-trip error: {e}')
        return jsonify({'success': False, 'message': 'Optimization failed'}), 500


# ═══════════════════════════════════════════════════════════════════
#  11. FINALIZE TRIP — lock trip as finalized
#      POST /api/trips/finalize   { trip_id }
# ═══════════════════════════════════════════════════════════════════
@api_bp.route('/trips/finalize', methods=['POST'])
@login_required
def finalize_trip():
    user_id = _user_id()
    data = get_json_payload()
    trip_id = data.get('trip_id')

    if not trip_id:
        return jsonify({'success': False, 'message': 'trip_id is required'}), 400

    # Verify ownership
    trip = get_trip_for_user(trip_id, user_id, full=False)
    if not trip:
        return jsonify({'success': False, 'message': 'Trip not found'}), 404

    # Best-effort: ensure an optimized snapshot exists for the itinerary page.
    try:
        if get_trip_route_plan(trip_id=trip_id) is None:
            optimize_trip_route(trip_id=trip_id, user_id=user_id)
    except Exception as e:
        print(f'[API] finalize optimize warning: {e}')

    finalize_trip_service(trip_id=trip_id, user_id=user_id)

    return jsonify({'success': True, 'message': 'Trip finalized successfully'})


# ═══════════════════════════════════════════════════════════════════
#  12. DELETE DRAFT TRIPS
#      POST /api/delete-draft-trips   { trip_ids: [1, 2, ...] }
# ═══════════════════════════════════════════════════════════════════
@api_bp.route('/delete-draft-trips', methods=['POST'])
@login_required
def delete_draft_trips():
    user_id = _user_id()
    data = get_json_payload()
    trip_ids = data.get('trip_ids', [])

    if not trip_ids:
        return jsonify({'error': 'No trip IDs provided'}), 400

    return jsonify(delete_draft_trips_service(user_id=user_id, trip_ids=trip_ids))


# ═══════════════════════════════════════════════════════════════════
#  13. AUTH STATUS — check if user is logged in
#      GET /api/auth/status
# ═══════════════════════════════════════════════════════════════════
@api_bp.route('/auth/status')
def auth_status():
    user_id = _user_id()
    if user_id:
        return jsonify({'logged_in': True, 'user_id': user_id})
    return jsonify({'logged_in': False}), 401


@api_bp.route('/admin/migrate-db')
def migrate_db_route():
    try:
        # Check if column exists by trying to add it
        try:
            execute_db("ALTER TABLE locations ADD COLUMN description TEXT")
            return 'Migration Success: Added description column'
        except Exception as e:
            # MySQL error 1060: Duplicate column name
            if '1060' in str(e) or 'Duplicate column' in str(e):
                return 'Migration Info: Column already exists'
            raise e
    except Exception as e:
        return f'Migration Error: {e}'
