"""Wishlist domain operations.

This module contains DB access and business rules for wishlist behavior.
Routes should remain thin and only handle HTTP parsing/serialization.
"""

from __future__ import annotations

from app.helpers.db import execute_db, query_db


def get_wishlist_items(user_id: int) -> list[dict]:
    items = query_db(
        '''SELECT l.location_id, l.name, l.locality, l.region, l.category, l.image_url
           FROM wishlist w
           JOIN locations l ON w.location_id = l.location_id
           WHERE w.user_id = %s
           ORDER BY w.added_at DESC''',
        (user_id,),
    )
    return items or []


def toggle_wishlist_item(user_id: int, location_id: int | str) -> dict:
    """Toggle wishlist item.

    Returns the exact response payload shape currently used by the API.
    """
    existing = query_db(
        'SELECT wishlist_id FROM wishlist WHERE user_id = %s AND location_id = %s',
        (user_id, location_id),
        one=True,
    )

    if existing:
        execute_db(
            'DELETE FROM wishlist WHERE user_id = %s AND location_id = %s',
            (user_id, location_id),
        )
        return {'action': 'removed', 'added': False, 'message': 'Removed from wishlist'}

    execute_db(
        'INSERT INTO wishlist (user_id, location_id) VALUES (%s, %s)',
        (user_id, location_id),
    )
    return {'action': 'added', 'added': True, 'message': 'Added to wishlist'}
