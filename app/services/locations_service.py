"""Location domain operations.

Includes:
- DB search and (optional) OSM/Wiki fallback behavior used by the API
- lightweight normalization/deduping helpers for display + storage
- a guard to block broad areas (cities/states/regions) from being treated as POIs
"""

from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from typing import Optional

from app.helpers.db import execute_db, query_db
from app.services.osm import verify_place
from app.services.wiki import get_details


def _guard_norm(text: str) -> str:
    text = (text or '').strip().lower()
    # Collapse punctuation/spaces so "NCT of Delhi" and "Delhi" compare safely.
    text = re.sub(r'[^a-z0-9]+', '', text)
    return text


# India-focused project: prevent selecting whole States/UTs as a single POI.
INDIA_STATES_UT = {
    # States
    'andhrapradesh',
    'arunachalpradesh',
    'assam',
    'bihar',
    'chhattisgarh',
    'goa',
    'gujarat',
    'haryana',
    'himachalpradesh',
    'jharkhand',
    'karnataka',
    'kerala',
    'madhyapradesh',
    'maharashtra',
    'manipur',
    'meghalaya',
    'mizoram',
    'nagaland',
    'odisha',
    'punjab',
    'rajasthan',
    'sikkim',
    'tamilnadu',
    'telangana',
    'tripura',
    'uttarpradesh',
    'uttarakhand',
    'westbengal',

    # Union Territories
    'andamanandnicobarislands',
    'chandigarh',
    'dadraandnagarhavelianddamandiu',
    'damananddiu',
    'delhi',
    'nctofdelhi',
    'jammuandkashmir',
    'ladakh',
    'lakshadweep',
    'puducherry',
}


# Common "big city" names likely to be typed as a destination.
MAJOR_CITIES = {
    'mumbai',
    'newdelhi',
    'delhi',
    'bengaluru',
    'bangalore',
    'kolkata',
    'chennai',
    'hyderabad',
    'pune',
    'ahmedabad',
    'jaipur',
    'surat',
    'lucknow',
    'kanpur',
    'nagpur',
    'indore',
    'bhopal',
    'patna',
    'vadodara',
    'visakhapatnam',
    'coimbatore',
    'kochi',
    'agra',
    'varanasi',
}


def is_broad_area_name(name: str) -> bool:
    key = _guard_norm(name)
    if not key:
        return False
    return key in INDIA_STATES_UT or key in MAJOR_CITIES


def is_broad_location_row(row: dict) -> bool:
    if not isinstance(row, dict):
        return False

    name = row.get('name') or ''
    if is_broad_area_name(name):
        return True

    # Some datasets may already tag these.
    category = (row.get('category') or '').strip().lower()
    if category in {'city', 'state', 'region', 'administrative'}:
        return True

    return False


def canonical_place_name(name: str) -> str:
    """Return a canonical display/storage name for a POI.

    Prevents duplicates like "Taj Mahal" vs "Taj Mahal, Agra" when
    locality/region are stored separately.
    """
    s = (name or '').strip()
    if not s:
        return ''

    # Keep only the first segment before comma (most common duplication source).
    s = s.split(',', 1)[0].strip()

    # Remove "India" ONLY when it appears as a trailing standalone word
    # (e.g., "Taj Mahal India" → "Taj Mahal") but NOT when it's part of the
    # place name (e.g., "India Gate" stays as "India Gate").
    s = re.sub(r'\s+india\s*$', '', s, flags=re.IGNORECASE).strip()

    # Collapse whitespace.
    s = re.sub(r'\s+', ' ', s).strip()

    return s


def dedupe_location_rows(rows: list[dict]) -> list[dict]:
    """Remove near-identical rows from a list.

    Uses canonical name + locality + region as the identity key.
    Keeps the first row encountered (API already orders by relevance/limit).
    """
    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []

    for r in rows or []:
        name = canonical_place_name(str(r.get('name') or ''))
        locality = (r.get('locality') or '').strip().lower()
        region = (r.get('region') or '').strip().lower()
        key = (name.lower(), locality, region)
        if key in seen:
            continue
        seen.add(key)

        # Keep original row, but normalize the displayed name to avoid confusing UI.
        if r.get('name') and name and r['name'] != name:
            r = dict(r)
            r['name'] = name
        out.append(r)

    return out


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def _name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or '').strip().lower(), (b or '').strip().lower()).ratio()


def search_locations_in_db(query: str, limit: int = 20) -> list[dict]:
    term = f'%{query}%'
    rows = query_db(
        '''SELECT location_id, name, locality, region, category, image_url, description
           FROM locations
           WHERE name LIKE %s OR locality LIKE %s OR region LIKE %s
           LIMIT %s''',
        (term, term, term, limit),
    )
    return rows or []


def search_or_import_location_from_osm(query: str, region: Optional[str] = None) -> list[dict]:
    """Fallback search via OSM, with DB insertion + Wiki enrichment.

    Returns a list of location dicts matching the API response shape.
    This function preserves existing behavior (including default category).
    """
    # Only if query is specific enough (>3 chars) to avoid bad matches
    if len(query) <= 3:
        return []

    try:
        osm = verify_place(query, region=region)
        if not osm:
            return []

        name = canonical_place_name(osm.get('display_name', '').split(',')[0].strip() or query)

        # Safety: if canonical name is very short but original query was more specific,
        # prefer the original query for wiki lookups (e.g., "India Gate" → "Gate" is wrong)
        wiki_name = name
        if len(name) <= 4 and len(query) > len(name):
            wiki_name = query

        # Near-duplicate guard: if another row is basically the same POI (very close
        # coordinates + very similar name), reuse it instead of inserting.
        try:
            lat = float(osm['lat'])
            lon = float(osm['lon'])
            candidates = query_db(
                '''SELECT location_id, name, locality, region, category, image_url, description, latitude, longitude
                   FROM locations
                   WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                     AND ABS(latitude - %s) < 0.01
                     AND ABS(longitude - %s) < 0.01
                   LIMIT 50''',
                (lat, lon),
            ) or []

            best = None
            for c in candidates:
                c_lat = c.get('latitude')
                c_lon = c.get('longitude')
                if c_lat is None or c_lon is None:
                    continue
                dist = _haversine_km(lat, lon, float(c_lat), float(c_lon))
                if dist > 0.30:
                    continue
                sim = _name_similarity(name, c.get('name') or '')
                if sim < 0.92:
                    continue
                # Prefer the closest candidate.
                if best is None or dist < best[0]:
                    best = (dist, c)

            if best is not None:
                return [best[1]]
        except Exception:
            # Keep behavior safe; do not block import on guard failure.
            pass

        # Double check existence by exact name to avoid race conditions
        existing = query_db('SELECT location_id FROM locations WHERE name = %s', (name,), one=True)
        if existing:
            new_loc = query_db(
                'SELECT location_id, name, locality, region, category, image_url, description FROM locations WHERE location_id = %s',
                (existing['location_id'],),
                one=True,
            )
            return [new_loc] if new_loc else []

        details = get_details(wiki_name)
        img = details.get('image') or ''
        desc = details.get('description') or ''

        loc_id = execute_db(
            '''INSERT INTO locations (name, locality, region, category,
               latitude, longitude, image_url, description)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
            (
                name,
                osm.get('locality', ''),
                osm.get('region', ''),
                'destination',
                osm['lat'],
                osm['lon'],
                img,
                desc,
            ),
        )

        return [{
            'location_id': loc_id,
            'name': name,
            'locality': osm.get('locality', ''),
            'region': osm.get('region', ''),
            'category': 'destination',
            'image_url': img,
            'description': desc,
        }]

    except Exception as e:
        # Preserve existing API logging behavior.
        print(f'[API] Search fallback error: {e}')
        return []
