"""OpenStreetMap (Nominatim) Service — TripLit
Verifies place names and fetches coordinates using OSM Nominatim API.
Includes fallback search strategies for better match rates.
"""
import requests
import time
from flask import current_app

# Nominatim requires a user-agent and has rate limits (1 req/sec)
NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
USER_AGENT = 'TripLit/1.0 (semester-project)'

# Rate limiting: track last request time
_last_request_time = 0


def _rate_limit():
    """Ensure at least 1 second between Nominatim requests."""
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    _last_request_time = time.time()


def _search_nominatim(query):
    """Perform a single Nominatim search. Returns result dict or None."""
    _rate_limit()

    params = {
        'q': query,
        'format': 'json',
        'limit': 1,
        'addressdetails': 1,
        'extratags': 1,
        'countrycodes': 'in'  # Restrict to India
    }

    headers = {'User-Agent': USER_AGENT}

    try:
        response = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        results = response.json()
        return results[0] if results else None
    except requests.RequestException as e:
        current_app.logger.error(f'OSM API error for "{query}": {e}')
        return None


def verify_place(name, region=None):
    """Verify a place exists using OSM Nominatim and get its coordinates.
    
    Uses multiple search strategies for better match rates:
    1. "Name, Region, India" (most specific)
    2. "Name, India" (without region)
    3. Name only (broadest)

    Args:
        name: place name string (e.g., "Baga Beach")
        region: optional region string to narrow search (e.g., "Goa")

    Returns:
        dict with {lat, lon, locality, display_name, region} if found, else None
    """
    # Build a list of search queries to try (most specific to broadest)
    queries = []
    if region:
        queries.append(f'{name}, {region}, India')
    queries.append(f'{name}, India')
    queries.append(name)

    result = None
    for query in queries:
        result = _search_nominatim(query)
        if result:
            current_app.logger.info(f'OSM: Found "{name}" with query: "{query}"')
            break
    
    if not result:
        current_app.logger.warning(f'OSM: No results for "{name}" (tried {len(queries)} queries)')
        return None

    # Guard: reject broad administrative areas (cities/states/regions)
    # We only want visitable POIs that behave like single "stops" in an itinerary.
    r_class = (result.get('class') or '').strip().lower()
    r_type = (result.get('type') or '').strip().lower()
    r_addresstype = (result.get('addresstype') or '').strip().lower()

    broad_classes = {'boundary', 'place'}
    broad_types = {
        'administrative',
        'city',
        'state',
        'region',
        'country',
        'county',
        'district',
        'municipality',
        'province',
        'subdistrict',
        'borough',
        'suburb',
        'neighbourhood',
        'town',
        'village',
        'hamlet',
    }
    broad_addresstypes = {
        'country',
        'state',
        'region',
        'state_district',
        'district',
        'county',
        'municipality',
        'city',
        'town',
        'village',
        'suburb',
        'neighbourhood',
    }

    if (r_class in broad_classes) or (r_type in broad_types) or (r_addresstype in broad_addresstypes):
        current_app.logger.warning(
            f'OSM: Rejected broad place for "{name}": class={r_class}, type={r_type}, addresstype={r_addresstype}'
        )
        return None

    address = result.get('address', {})

    # Extract locality from address components
    locality = (
        address.get('city') or
        address.get('town') or
        address.get('village') or
        address.get('county') or
        address.get('state_district') or
        ''
    )

    return {
        'lat': float(result['lat']),
        'lon': float(result['lon']),
        'locality': locality,
        'display_name': result.get('display_name', ''),
        'region': address.get('state', ''),
        'osm_class': r_class,
        'osm_type': r_type,
        'addresstype': r_addresstype,
    }
