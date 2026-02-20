"""OSRM Distance Matrix (Table) client.

We only use OSRM for the distance/duration matrix ("/table" endpoint).

Default server: https://router.project-osrm.org
You can override via OSRM_BASE_URL env var.

OSRM returns:
- distances: meters (float)
- durations: seconds (float)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable

import requests


DEFAULT_OSRM_BASE_URL = 'https://router.project-osrm.org'


@dataclass(frozen=True)
class OsrmTableResult:
	distances_m: list[list[float | None]]
	durations_s: list[list[float | None]]


def _osrm_base_url() -> str:
	return (os.getenv('OSRM_BASE_URL') or DEFAULT_OSRM_BASE_URL).rstrip('/')


def _format_coords(coords: Iterable[tuple[float, float]]) -> str:
	# OSRM expects "lon,lat;lon,lat".
	parts: list[str] = []
	for lon, lat in coords:
		parts.append(f'{lon:.6f},{lat:.6f}')
	return ';'.join(parts)


def fetch_table_matrix(
	*,
	coordinates: list[tuple[float, float]],
	profile: str = 'driving',
	annotations: str = 'distance,duration',
	timeout_s: float = 20.0,
) -> OsrmTableResult:
	"""Fetch an NxN distance/duration matrix from OSRM Table API.

	Args:
		coordinates: list of (lon, lat)
		profile: OSRM profile, usually "driving"
		annotations: "distance", "duration", or "distance,duration"

	Raises:
		ValueError: on invalid coordinates/count
		RuntimeError: on OSRM/network errors
	"""
	if not coordinates:
		return OsrmTableResult(distances_m=[], durations_s=[])

	if len(coordinates) == 1:
		return OsrmTableResult(distances_m=[[0.0]], durations_s=[[0.0]])

	if len(coordinates) > 100:
		# OSRM public instances commonly cap at 100 coords.
		raise ValueError('Too many coordinates for OSRM table (max 100).')

	coords_str = _format_coords(coordinates)
	url = f"{_osrm_base_url()}/table/v1/{profile}/{coords_str}"
	params = {
		'annotations': annotations,
	}

	try:
		res = requests.get(url, params=params, timeout=timeout_s)
	except requests.RequestException as e:
		raise RuntimeError(f'OSRM request failed: {e}') from e

	if not res.ok:
		raise RuntimeError(f'OSRM error: HTTP {res.status_code}')

	try:
		payload = res.json()
	except ValueError as e:
		raise RuntimeError('OSRM returned non-JSON response') from e

	if payload.get('code') != 'Ok':
		msg = payload.get('message') or payload.get('code') or 'Unknown error'
		raise RuntimeError(f'OSRM error: {msg}')

	distances = payload.get('distances')
	durations = payload.get('durations')
	if distances is None or durations is None:
		raise RuntimeError('OSRM table response missing distances/durations')

	return OsrmTableResult(distances_m=distances, durations_s=durations)
