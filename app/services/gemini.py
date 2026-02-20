"""Gemini AI Service — TripLit
Integrates with Google Gemini API.

This module is intentionally defensive:
- If the google-genai SDK isn't installed, functions return safe defaults
    instead of crashing app startup.
"""
import json
import time
from flask import current_app

try:
        from google import genai
        from google.genai import errors as genai_errors
except Exception:  # pragma: no cover
        genai = None
        genai_errors = None

# Retry settings for rate limiting
MAX_RETRIES = 3
INITIAL_WAIT = 10  # seconds


# Region slug to display name mapping
REGION_DISPLAY_NAMES = {
    'andhrapradesh': 'Andhra Pradesh', 'arunachalpradesh': 'Arunachal Pradesh',
    'assam': 'Assam', 'bihar': 'Bihar', 'chhattisgarh': 'Chhattisgarh',
    'goa': 'Goa', 'gujarat': 'Gujarat', 'haryana': 'Haryana',
    'himachalpradesh': 'Himachal Pradesh', 'jharkhand': 'Jharkhand',
    'karnataka': 'Karnataka', 'kerala': 'Kerala', 'madhyapradesh': 'Madhya Pradesh',
    'maharashtra': 'Maharashtra', 'manipur': 'Manipur', 'meghalaya': 'Meghalaya',
    'mizoram': 'Mizoram', 'nagaland': 'Nagaland', 'odisha': 'Odisha',
    'punjab': 'Punjab', 'rajasthan': 'Rajasthan', 'sikkim': 'Sikkim',
    'tamilnadu': 'Tamil Nadu', 'telangana': 'Telangana', 'tripura': 'Tripura',
    'uttarpradesh': 'Uttar Pradesh', 'uttarakhand': 'Uttarakhand',
    'westbengal': 'West Bengal', 'delhi': 'Delhi', 'chandigarh': 'Chandigarh',
    'jammuandkashmir': 'Jammu and Kashmir', 'ladakh': 'Ladakh',
    'puducherry': 'Puducherry', 'lakshadweep': 'Lakshadweep',
}


def get_display_region(slug: str) -> str:
    """Convert a region slug to its human-readable display name."""
    key = (slug or '').strip().lower().replace(' ', '').replace('-', '').replace('_', '')
    return REGION_DISPLAY_NAMES.get(key, slug)


def _clamp_int(value, default: int, min_value: int, max_value: int) -> int:
    try:
        v = int(value)
    except Exception:
        v = int(default)
    return max(min_value, min(int(v), max_value))


def _pace_key(value: str) -> str:
    k = (value or '').strip().lower()
    return k if k in ('relaxed', 'balanced', 'packed') else 'balanced'


def _suggestion_capacity(*, pace: str, trip_days: int, region_count: int) -> tuple[int, int]:
    """Return (total_suggestions, approx_per_region).

    Capacity-based so short trips don't get flooded with locations.
    """
    locs_per_day = {'relaxed': 2, 'balanced': 3, 'packed': 5}[pace]
    days = max(1, trip_days)
    total = days * locs_per_day
    total = max(1, min(total, 40))  # hard cap for API cost + usability

    rc = max(1, int(region_count))
    per_region = int((total + rc - 1) // rc)  # ceil
    per_region = max(1, per_region)
    return total, per_region


def _build_prompt(trip, regions, excluded_places, *, total_override: int | None = None):
    """Build the Gemini prompt for place suggestions.

    Args:
        trip: dict with trip details from DB
        regions: list of region name strings
        excluded_places: list of place name strings to avoid

    Returns:
        str: the formatted prompt
    """
    pace = _pace_key(trip.get('pace', 'balanced'))
    trip_days = _clamp_int(trip.get('trip_days', 3), default=3, min_value=1, max_value=30)
    total, per_region = _suggestion_capacity(pace=pace, trip_days=trip_days, region_count=len(regions))
    if total_override is not None:
        total = _clamp_int(total_override, default=total, min_value=1, max_value=40)
        rc = max(1, int(len(regions) or 1))
        per_region = int((total + rc - 1) // rc)
        per_region = max(1, per_region)

    regions_str = ', '.join(regions)
    excluded_str = ', '.join(excluded_places) if excluded_places else 'None'

    start_region = (trip.get('start_region') or '').strip()
    end_region = (trip.get('end_region') or '').strip()

    # Determine interest mode
    diversity = trip.get('diversity_mode')
    # diversity_mode might come as int (1/0) from DB
    if isinstance(diversity, int):
        diversity = bool(diversity)

    if diversity:
        mode_instruction = (
            "- Use DIVERSITY MODE: suggest a wide variety of categories per region.\n"
            "- Include at least 4 different categories per region."
        )
    else:
        focus = trip.get('focus_mode', '')
        if focus:
            categories = focus if isinstance(focus, str) else ', '.join(focus)
            mode_instruction = (
                f"- PRIORITIZE these categories: {categories}\n"
                f"- Focus 60-70% of suggestions on these categories, "
                f"but still include 1-2 other categories per region for variety."
            )
        else:
            mode_instruction = "- Suggest a balanced variety of categories."

    # Pace description
    pace_desc = {
        'relaxed': 'Relaxed (1-2 places per day, plenty of downtime)',
        'balanced': 'Balanced (3-4 places per day, mix of activity and rest)',
        'packed': 'Packed (5+ places per day, maximum sightseeing)'
    }.get(pace, 'Balanced')

    # Companion context
    companion = trip.get('companion_type', '')
    companion_instruction = ''
    if companion == 'family':
        companion_instruction = '- Suggest FAMILY-FRIENDLY places. Avoid nightlife or extreme adventure.'
    elif companion == 'couple':
        companion_instruction = '- Include ROMANTIC spots (scenic viewpoints, serene places, beautiful gardens).'
    elif companion == 'solo':
        companion_instruction = '- Include places good for SOLO travelers (cafes, walking trails, cultural spots).'
    elif companion == 'friends':
        companion_instruction = '- Include FUN group activities (adventure, food tours, entertainment).'

    # Season context
    season = trip.get('season', '')
    season_instruction = ''
    if season and season != 'anytime':
        season_instruction = f'- Consider {season.upper()} season: suggest places best visited during {season}.'

    prompt = f"""You are a travel expert for India. A user is planning a trip with these preferences:

TRIP CONTEXT:
- Start (city/region preference): {start_region or 'not specified'}
- End (city/region preference): {end_region or 'not specified'}
- Regions to explore: {regions_str}
- Trip duration: {trip_days} day(s)
- Travel pace: {pace_desc}
- Companion type: {companion or 'not specified'}
- Season: {season or 'anytime'}

INSTRUCTIONS:
- Suggest exactly {total} real, visitable places across the specified regions.
- Suggestions must be PHYSICAL, MAP-FINDABLE places with a single pin (monuments, temples, forts, parks, museums, beaches, viewpoints).
- Avoid activities/itineraries like "boat ride", "safari", "food tour", "shopping in X" unless it's a specific named place.
- For each place, provide the place name, its category, and a SHORT, INVITING 1-sentence description (max 15 words) that explains why it is worth visiting.
- Categories MUST be one of: heritage, nature, beach, religious, adventure, food, shopping, viewpoint, entertainment, museum, wellness, local-experience
- Distribute places across regions roughly equally (~{per_region} per region).
- The "region" field MUST be EXACTLY one of these region names: {regions_str}.
- Do NOT invent new regions, states, or alternate spellings in the "region" field.
{mode_instruction}
{companion_instruction}
{season_instruction}
- All suggested places MUST be located within the provided "Regions to explore": {regions_str}.
- Even if start/end preferences are provided, do NOT suggest places outside the "Regions to explore". 
- All places must be REAL locations that exist in India.
- Use OFFICIAL, well-known names for places (the kind findable on Google Maps or OpenStreetMap).
- Avoid informal names, night market names, or hyper-local nicknames that wouldn't appear on maps.
- Do NOT suggest any of these already-excluded places: {excluded_str}

RESPOND IN THIS EXACT JSON FORMAT ONLY (no markdown, no explanation, just pure JSON):
{{
  "suggestions": [
    {{"name": "Place Name", "category": "category", "region": "region_name", "description": "Beautiful temple built in..."}},
    ...
  ]
}}"""

    print(f'[GEMINI PROMPT DEBUG] regions={regions}, total={total}, per_region={per_region}, excluded={excluded_str[:100]}')
    print(f'[GEMINI PROMPT DEBUG] start_region={start_region}, end_region={end_region}')
    return prompt


def suggest_places(trip, regions, excluded_places=None, *, total_override: int | None = None):
    """Call Gemini API to get place suggestions for a trip.

    Args:
        trip: dict with trip details
        regions: list of region name strings
        excluded_places: list of place names to exclude (optional)

    Returns:
        list of dicts: [{"name": ..., "category": ..., "region": ...}, ...]
        or empty list on failure
    """
    if excluded_places is None:
        excluded_places = []

    api_key = current_app.config.get('GEMINI_API_KEY', '')
    if not api_key:
        current_app.logger.error('Gemini API key not configured')
        return []

    if genai is None:
        current_app.logger.error('Gemini SDK not installed (missing google-genai)')
        return []

    # Create client with new SDK
    client = genai.Client(api_key=api_key)

    prompt = _build_prompt(trip, regions, excluded_places, total_override=total_override)

    try:
        # Retry loop for rate limiting (429 errors)
        response = None
        for attempt in range(MAX_RETRIES):
            try:
                response = client.models.generate_content(
                    model='gemini-2.5-flash-lite',
                    contents=prompt
                )
                break  # Success — exit retry loop
            except genai_errors.ClientError as e:
                if '429' in str(e) or 'RESOURCE_EXHAUSTED' in str(e):
                    wait_time = INITIAL_WAIT * (2 ** attempt)  # 10s, 20s, 40s
                    current_app.logger.warning(
                        f'Gemini rate limited (attempt {attempt + 1}/{MAX_RETRIES}). '
                        f'Waiting {wait_time}s...'
                    )
                    time.sleep(wait_time)
                else:
                    raise  # Non-rate-limit error, don't retry

        if response is None:
            current_app.logger.error('Gemini: All retry attempts exhausted (rate limited)')
            return []

        text = response.text.strip()

        # Clean up response — remove markdown code fences if present
        if text.startswith('```'):
            lines = text.split('\n')
            text = '\n'.join(lines[1:-1])

        data = json.loads(text)
        suggestions = data.get('suggestions', [])
        print(f'[GEMINI RESPONSE DEBUG] Got {len(suggestions)} raw suggestions')
        for i, s in enumerate(suggestions[:5]):
            print(f'  [{i}] name={s.get("name")}, region={s.get("region")}')

        # Validate each suggestion has required fields
        valid = []
        for s in suggestions:
            if isinstance(s, dict) and 'name' in s and 'category' in s:
                valid.append({
                    'name': s['name'].strip(),
                    'category': s.get('category', 'heritage').strip().lower(),
                    'region': s.get('region', regions[0] if regions else '').strip(),
                    'description': s.get('description', '').strip()
                })

        current_app.logger.info(f'Gemini returned {len(valid)} valid suggestions')
        return valid
    except Exception as e:
        current_app.logger.error(f'Gemini API error: {e}')
        return []


def get_description(place_name):
    """Fetch a short 1-2 sentence description for a specific place using Gemini."""
    api_key = current_app.config.get('GEMINI_API_KEY', '')
    if not api_key:
        return None

    if genai is None:
        current_app.logger.error('Gemini SDK not installed (missing google-genai)')
        return None
    
    try:
        client = genai.Client(api_key=api_key)
        prompt = f"Provide a short, engaging 1-2 sentence description for the travel destination: {place_name} in India. Focus on why a tourist should visit. Do not use quotes."
        
        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=prompt
        )
        text = response.text.strip()
        return text
    except Exception as e:
        current_app.logger.error(f'Gemini Description Error: {e}')
        return None


def normalize_location_query(query: str) -> dict:
    """Normalize a user-entered place query to an official place name.

    Returns:
        dict: {"name": str, "region": str}

    Notes:
        - If GEMINI_API_KEY is missing or SDK unavailable, returns the input.
        - Keeps response format stable for API consumers.
    """
    raw = (query or '').strip()
    if not raw:
        return {'name': '', 'region': ''}

    api_key = current_app.config.get('GEMINI_API_KEY', '')
    if not api_key or genai is None:
        return {'name': raw, 'region': ''}

    prompt = f"""You are helping normalize Indian travel place searches.

USER INPUT: {raw}

TASK:
- Return a best-guess OFFICIAL place name that would be findable on OpenStreetMap / Google Maps.
- Also return an Indian state/UT in the \"region\" field when it is clearly implied, else empty string.
- Remove extra words like \"near\", \"best\", \"famous\", etc.
- IMPORTANT: Do NOT remove words that are part of the actual landmark name, even if they look like country/region names. Examples: \"India Gate\" stays \"India Gate\", \"Gateway of India\" stays \"Gateway of India\".
- If the input already looks like a good official place name, keep it as-is.

RESPOND WITH PURE JSON ONLY (no markdown, no extra text):
{{\"name\": \"...\", \"region\": \"...\"}}
"""

    try:
        client = genai.Client(api_key=api_key)

        response = None
        for attempt in range(MAX_RETRIES):
            try:
                response = client.models.generate_content(
                    model='gemini-2.5-flash-lite',
                    contents=prompt,
                )
                break
            except Exception as e:
                # Keep retry behavior aligned with suggest_places().
                if genai_errors and isinstance(e, genai_errors.ClientError) and (
                    '429' in str(e) or 'RESOURCE_EXHAUSTED' in str(e)
                ):
                    wait_time = INITIAL_WAIT * (2 ** attempt)
                    current_app.logger.warning(
                        f'Gemini normalize rate limited (attempt {attempt + 1}/{MAX_RETRIES}). '
                        f'Waiting {wait_time}s...'
                    )
                    time.sleep(wait_time)
                else:
                    raise

        if response is None:
            return {'name': raw, 'region': ''}

        text = (response.text or '').strip()
        if text.startswith('```'):
            lines = text.split('\n')
            text = '\n'.join(lines[1:-1])

        data = json.loads(text)
        name = (data.get('name') or '').strip() or raw
        region = (data.get('region') or '').strip()

        return {'name': name, 'region': region}

    except Exception as e:
        current_app.logger.error(f'Gemini normalize error: {e}')
        return {'name': raw, 'region': ''}
