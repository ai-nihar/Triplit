"""Wikipedia/Wikimedia Service — TripLit
Fetches images and descriptions from Wikipedia for places.
Uses multiple search strategies for better image match rates.
"""
import requests
from flask import current_app

WIKI_API_URL = 'https://en.wikipedia.org/w/api.php'
HEADERS = {'User-Agent': 'TripLit/1.0 (semester-project; travel planner)'}


def _wiki_get(params: dict, *, timeout: int) -> dict | None:
    try:
        response = requests.get(WIKI_API_URL, params=params, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        current_app.logger.error(f'Wiki API error for params={params}: {e}')
        return None


def _search_titles(search_query: str, *, limit: int, timeout: int) -> list[str]:
    search_params = {
        'action': 'query',
        'list': 'search',
        'srsearch': search_query,
        'srlimit': limit,
        'format': 'json',
    }

    data = _wiki_get(search_params, timeout=timeout)
    if not data:
        return []

    results = data.get('query', {}).get('search', [])
    return [r.get('title', '') for r in results if r.get('title')]


def _get_page_info(page_title: str, *, include_extract: bool, timeout: int) -> dict | None:
    params = {
        'action': 'query',
        'titles': page_title,
        'prop': 'pageimages' + ('|extracts' if include_extract else ''),
        'pithumbsize': 500,
        'format': 'json',
    }

    if include_extract:
        params.update({
            'exintro': True,
            'explaintext': True,
            'exsentences': 2,
        })

    data = _wiki_get(params, timeout=timeout)
    if not data:
        return None

    pages = data.get('query', {}).get('pages', {})
    for _, page_info in pages.items():
        return page_info
    return None


def get_image(place_name):
    """Fetch a Wikipedia image URL for a place.
    
    Tries multiple search queries for better match rates:
    1. Exact place name
    2. Place name + "India"

    Args:
        place_name: name of the place (e.g., "Baga Beach")

    Returns:
        str: image URL, or None if not found
    """
    # Try different search queries
    queries = [
        place_name,
        f'{place_name} India',
    ]

    for query in queries:
        image_url = _try_get_image(query)
        if image_url:
            current_app.logger.info(f'Wiki: Found image for "{place_name}" with query: "{query}"')
            return image_url

    current_app.logger.info(f'Wiki: No image found for "{place_name}"')
    return None


def _try_get_image(search_query):
    """Try to get an image from Wikipedia for a given search query.
    
    Returns image URL or None.
    """
    titles = _search_titles(search_query, limit=3, timeout=10)
    if not titles:
        return None

    for title in titles:
        page_info = _get_page_info(title, include_extract=False, timeout=10)
        if not page_info:
            continue
        thumbnail = page_info.get('thumbnail', {})
        image_url = thumbnail.get('source')
        if image_url:
            return image_url

    return None


def get_details(place_name):
    """Fetch image URL AND description (summary) for a place.
    
    Returns:
        dict: {'image': str|None, 'description': str|None}
    """
    # 1. Try to get image first (reusing existing logic essentially)
    # We want to get the Page ID or Title that worked for the image, to get the extract.
    # But get_image iterates queries.
    
    # Let's write a new logic that gets both.
    queries = [place_name, f'{place_name} India']
    
    for query in queries:
        data = _try_get_details_from_query(query)
        if data and data.get('image'):
             current_app.logger.info(f'Wiki: Found details for "{place_name}" using "{query}"')
             return data
    
    # If no image found, maybe return description only?
    # For now, if no image, we return what we found or None.
    return {'image': None, 'description': None}


def _try_get_details_from_query(search_query):
    """Helper to search and get image + extract."""
    try:
        titles = _search_titles(search_query, limit=1, timeout=5)
        if not titles:
            return None

        page_info = _get_page_info(titles[0], include_extract=True, timeout=5)
        if not page_info:
            return None

        img = page_info.get('thumbnail', {}).get('source')
        desc = page_info.get('extract')
        return {'image': img, 'description': desc}

    except Exception:
        return None
