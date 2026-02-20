"""Deduplicate locations in the MySQL database.

Goal
- Merge duplicate/near-duplicate rows in `locations` so they don't silently
  split across trips/wishlists and ruin itinerary logic.

What it does
- Finds duplicates using two strategies:
  1) Exact-ish match: normalized (name, locality, region)
  2) Geo+name match: same approx coordinates and very similar name
- Chooses a canonical location row to keep (prefers richer data).
- Rewrites foreign keys in:
  - wishlist
  - trip_locations
  - trip_route_segments (from/to)
- Clears route caches for affected trips:
  - deletes trip_route_plan and trip_route_segments for impacted trips
- Deletes the duplicate rows from `locations`.

Safety
- Default is DRY RUN. Use --apply to perform changes.
- Take a DB backup before running with --apply.

Usage (PowerShell)
  & "./venv/Scripts/python.exe" scripts/dedupe_locations.py --dry-run
  & "./venv/Scripts/python.exe" scripts/dedupe_locations.py --apply

Env
- Uses .env values: DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
"""

from __future__ import annotations

import argparse
import math
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Tuple

import mysql.connector
from dotenv import load_dotenv


def _norm(text: Optional[str]) -> str:
    s = (text or '').strip().lower()
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'[^a-z0-9 ]+', '', s)
    return s


def _norm_key(text: Optional[str]) -> str:
    return re.sub(r'[^a-z0-9]+', '', _norm(text))


def _base_name(name: Optional[str]) -> str:
    """Canonicalize a location name for dedupe.

    Common duplicates come from storing "Name, City" in `name` while also
    storing City/State in `locality`/`region`.
    """
    s = (name or '').strip()
    if not s:
        return ''
    # Keep only the part before the first comma.
    s = s.split(',', 1)[0].strip()
    # Remove common trailing country tokens.
    s = re.sub(r'\b(india)\b', '', s, flags=re.IGNORECASE).strip()
    return s


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Earth radius
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _row_richness_score(row: Dict[str, Any]) -> int:
    score = 0
    if row.get('image_url'):
        score += 3
    if row.get('description'):
        score += 3
    if row.get('locality'):
        score += 1
    if row.get('region'):
        score += 1
    if row.get('category'):
        score += 1
    if row.get('latitude') is not None and row.get('longitude') is not None:
        score += 2
    return score


def _choose_canonical(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Prefer richer data, then lowest location_id.
    rows_sorted = sorted(
        rows,
        key=lambda r: (-_row_richness_score(r), int(r['location_id'])),
    )
    return rows_sorted[0]


@dataclass
class MergeGroup:
    keep_id: int
    remove_ids: List[int]
    reason: str
    keep_name: str


class UnionFind:
    def __init__(self, ids: Iterable[int]):
        self.parent = {i: i for i in ids}
        self.rank = {i: 0 for i in ids}

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def _connect():
    load_dotenv()
    return mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '3306')),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'triplit'),
    )


def _fetch_locations(cur) -> List[Dict[str, Any]]:
    cur.execute(
        'SELECT location_id, name, locality, region, category, latitude, longitude, image_url, description '
        'FROM locations'
    )
    return list(cur.fetchall())


def _find_merge_groups(locations: List[Dict[str, Any]]) -> List[MergeGroup]:
    by_id = {int(r['location_id']): r for r in locations}

    # 1) Exact-ish normalized key group.
    key_map: Dict[Tuple[str, str, str], List[int]] = defaultdict(list)
    for r in locations:
        lid = int(r['location_id'])
        key = (
            _norm_key(_base_name(r.get('name'))),
            _norm_key(r.get('locality')),
            _norm_key(r.get('region')),
        )
        if key[0]:
            key_map[key].append(lid)

    merge_groups: List[MergeGroup] = []
    claimed: set[int] = set()

    for key, ids in key_map.items():
        if len(ids) < 2:
            continue
        rows = [by_id[i] for i in ids]
        keep = _choose_canonical(rows)
        keep_id = int(keep['location_id'])
        remove = sorted([i for i in ids if i != keep_id])
        merge_groups.append(
            MergeGroup(
                keep_id=keep_id,
                remove_ids=remove,
                reason='normalized(name+locality+region)',
                keep_name=str(keep.get('name') or ''),
            )
        )
        claimed.update(ids)

    # 2) Geo + very similar name within buckets.
    geo_rows = [r for r in locations if r.get('latitude') is not None and r.get('longitude') is not None]
    geo_ids = [int(r['location_id']) for r in geo_rows]

    uf = UnionFind(geo_ids)

    buckets: Dict[Tuple[int, int], List[int]] = defaultdict(list)
    for r in geo_rows:
        lid = int(r['location_id'])
        lat = float(r['latitude'])
        lon = float(r['longitude'])
        buckets[(int(lat * 100), int(lon * 100))].append(lid)  # ~0.01 deg

    def neighbor_keys(k: Tuple[int, int]) -> Iterable[Tuple[int, int]]:
        x, y = k
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                yield (x + dx, y + dy)

    for k, ids in list(buckets.items()):
        # compare with neighbors to avoid missing border cases
        candidates: List[int] = []
        for nk in neighbor_keys(k):
            candidates.extend(buckets.get(nk, []))

        # small N typically; O(n^2) inside bucket neighborhood
        for i in range(len(ids)):
            a_id = ids[i]
            a = by_id[a_id]
            a_name = _norm(_base_name(str(a.get('name') or '')))
            a_region = _norm_key(a.get('region'))
            a_loc = _norm_key(a.get('locality'))
            a_lat = float(a['latitude'])
            a_lon = float(a['longitude'])

            for b_id in candidates:
                if b_id <= a_id:
                    continue
                b = by_id[b_id]

                # If both have region/locality, require at least one to match loosely.
                b_region = _norm_key(b.get('region'))
                b_loc = _norm_key(b.get('locality'))
                if a_region and b_region and a_region != b_region:
                    continue
                if a_loc and b_loc and a_loc != b_loc:
                    continue

                b_name = _norm(_base_name(str(b.get('name') or '')))
                sim = _similar(a_name, b_name)
                if sim < 0.92:
                    continue

                dist_km = _haversine_km(a_lat, a_lon, float(b['latitude']), float(b['longitude']))
                if dist_km > 0.30:
                    continue

                uf.union(a_id, b_id)

    # Convert UF sets into merge groups, but avoid duplicating already-claimed exact groups.
    clusters: Dict[int, List[int]] = defaultdict(list)
    for lid in geo_ids:
        clusters[uf.find(lid)].append(lid)

    for _, ids in clusters.items():
        ids = sorted(set(ids))
        if len(ids) < 2:
            continue

        # If this cluster is entirely inside an already-claimed exact group, skip.
        if all(i in claimed for i in ids):
            continue

        rows = [by_id[i] for i in ids]
        keep = _choose_canonical(rows)
        keep_id = int(keep['location_id'])
        remove = [i for i in ids if i != keep_id]

        merge_groups.append(
            MergeGroup(
                keep_id=keep_id,
                remove_ids=sorted(remove),
                reason='geo+name-similarity',
                keep_name=str(keep.get('name') or ''),
            )
        )

    # Final: ensure no keep_id is also in another group's remove_ids.
    # If conflicts exist, prefer earlier groups (exact groups first).
    keep_ids = set(g.keep_id for g in merge_groups)
    pruned: List[MergeGroup] = []
    removed_global: set[int] = set()
    for g in merge_groups:
        # don't remove something we've decided to keep elsewhere
        remove_ids = [rid for rid in g.remove_ids if rid not in keep_ids and rid not in removed_global]
        if not remove_ids:
            continue
        removed_global.update(remove_ids)
        pruned.append(MergeGroup(g.keep_id, remove_ids, g.reason, g.keep_name))

    return pruned


def _affected_trip_ids(cur, ids: List[int]) -> List[int]:
    if not ids:
        return []

    placeholders = ','.join(['%s'] * len(ids))

    trip_ids = set()

    cur.execute(
        f'SELECT DISTINCT trip_id FROM trip_locations WHERE location_id IN ({placeholders})',
        tuple(ids),
    )
    for r in cur.fetchall():
        trip_ids.add(int(r['trip_id']))

    cur.execute(
        f'SELECT DISTINCT trip_id FROM trip_route_segments WHERE from_location_id IN ({placeholders}) '
        f'OR to_location_id IN ({placeholders})',
        tuple(ids) + tuple(ids),
    )
    for r in cur.fetchall():
        trip_ids.add(int(r['trip_id']))

    return sorted(trip_ids)


def _merge_group(cur, group: MergeGroup) -> Tuple[int, int]:
    keep = group.keep_id
    remove_ids = list(group.remove_ids)

    # Affected trips: delete cached plan/segments to avoid stale JSON ids.
    trips = _affected_trip_ids(cur, remove_ids)

    for rid in remove_ids:
        # wishlist: preserve rows, avoid unique conflicts
        cur.execute(
            'INSERT IGNORE INTO wishlist (user_id, location_id, added_at) '
            'SELECT user_id, %s, added_at FROM wishlist WHERE location_id = %s',
            (keep, rid),
        )
        cur.execute('DELETE FROM wishlist WHERE location_id = %s', (rid,))

        # trip_locations: preserve status/order
        cur.execute(
            'INSERT IGNORE INTO trip_locations (trip_id, location_id, status, visit_order, added_at) '
            'SELECT trip_id, %s, status, visit_order, added_at FROM trip_locations WHERE location_id = %s',
            (keep, rid),
        )
        cur.execute('DELETE FROM trip_locations WHERE location_id = %s', (rid,))

        # route segments: rewrite ids
        cur.execute('UPDATE trip_route_segments SET from_location_id = %s WHERE from_location_id = %s', (keep, rid))
        cur.execute('UPDATE trip_route_segments SET to_location_id = %s WHERE to_location_id = %s', (keep, rid))

        # finally delete the location
        cur.execute('DELETE FROM locations WHERE location_id = %s', (rid,))

    if trips:
        placeholders = ','.join(['%s'] * len(trips))
        cur.execute(f'DELETE FROM trip_route_plan WHERE trip_id IN ({placeholders})', tuple(trips))
        cur.execute(f'DELETE FROM trip_route_segments WHERE trip_id IN ({placeholders})', tuple(trips))

    return (keep, len(remove_ids))


def main() -> int:
    parser = argparse.ArgumentParser(description='Deduplicate locations table safely.')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default is dry run).')
    parser.add_argument('--dry-run', action='store_true', help='Force dry-run (default).')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of merge groups to apply (0 = no limit).')

    args = parser.parse_args()
    apply_changes = bool(args.apply) and not bool(args.dry_run)

    db = _connect()
    try:
        cur = db.cursor(dictionary=True)
        locations = _fetch_locations(cur)
        groups = _find_merge_groups(locations)

        if args.limit and args.limit > 0:
            groups = groups[: args.limit]

        total_dups = sum(len(g.remove_ids) for g in groups)
        print(f'[Deduper] Found {len(groups)} merge group(s), {total_dups} duplicate row(s) to remove')

        # Print a preview
        for i, g in enumerate(groups[:25], start=1):
            print(f'  {i:02d}. keep={g.keep_id} ({g.keep_name})  remove={g.remove_ids}  [{g.reason}]')
        if len(groups) > 25:
            print(f'  ... and {len(groups) - 25} more groups')

        if not apply_changes:
            print('[Deduper] DRY RUN: no DB changes applied. Use --apply to perform merges.')
            return 0

        confirm = os.getenv('TRIPLIT_DEDUPE_CONFIRM', '').strip().lower()
        if confirm != 'yes':
            print('[Deduper] Refusing to apply without TRIPLIT_DEDUPE_CONFIRM=yes in environment.')
            print('          Example: $env:TRIPLIT_DEDUPE_CONFIRM="yes"')
            return 2

        print('[Deduper] APPLY: starting transaction...')
        db.start_transaction()

        merged = 0
        removed = 0
        for g in groups:
            keep_id, removed_count = _merge_group(cur, g)
            merged += 1
            removed += removed_count

        db.commit()
        print(f'[Deduper] DONE: merged {merged} group(s), removed {removed} duplicate location row(s).')
        return 0

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print(f'[Deduper] ERROR: {e}')
        return 1

    finally:
        try:
            db.close()
        except Exception:
            pass


if __name__ == '__main__':
    raise SystemExit(main())
