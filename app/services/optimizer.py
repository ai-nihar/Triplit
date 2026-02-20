"""Route optimizer.

Implements a simple, explainable heuristic pipeline:
- Nearest Neighbor (open path)
- 2-Opt improvement (open path)

We treat the OSRM duration matrix as the primary cost (seconds).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class OptimizeResult:
	order: list[int]  # indices into the original list
	total_cost: float


def _to_cost_matrix(matrix: list[list[float | None]]) -> np.ndarray:
	"""Convert a possibly-None matrix into a float matrix.

	None values become +inf, which will be rejected by validation.
	"""
	arr = np.array(matrix, dtype=float)
	# np.array will turn None -> nan
	arr = np.where(np.isnan(arr), np.inf, arr)
	return arr


def validate_full_matrix(cost: np.ndarray) -> None:
	if cost.ndim != 2 or cost.shape[0] != cost.shape[1]:
		raise ValueError('Cost matrix must be NxN')
	n = cost.shape[0]
	if n == 0:
		return
	if np.isinf(cost).any():
		raise ValueError('Cost matrix contains unreachable pairs (inf).')


def path_cost(cost: np.ndarray, order: list[int]) -> float:
	if len(order) <= 1:
		return 0.0
	total = 0.0
	for a, b in zip(order, order[1:]):
		total += float(cost[a, b])
	return total


def choose_central_start(cost: np.ndarray) -> int:
	"""Pick a stable start: node with minimum sum of costs to others."""
	n = cost.shape[0]
	if n == 0:
		return 0
	row_sums = cost.sum(axis=1)
	return int(np.argmin(row_sums))



def nearest_neighbor_path(cost: np.ndarray, *, start: int = 0, end: int | None = None) -> list[int]:
	"""Nearest-neighbor open path starting at `start`.

	If `end` is provided, that node is kept for last (fixed end).
	"""
	n = cost.shape[0]
	if n == 0:
		return []
	start = max(0, min(int(start), n - 1))

	if end is not None:
		end = max(0, min(int(end), n - 1))
		if end == start:
			end = None

	unvisited = set(range(n))
	unvisited.remove(start)
	order = [start]
	current = start

	while unvisited:
		# If we have a fixed end, keep it until last.
		choices = unvisited
		if end is not None and end in unvisited and len(unvisited) > 1:
			choices = unvisited - {end}

		# Find next with minimum cost
		next_node = min(choices, key=lambda j: float(cost[current, j]))
		unvisited.remove(next_node)
		order.append(next_node)
		current = next_node

	return order


def two_opt_improve(cost: np.ndarray, order: list[int], *, fixed_start: bool = True, max_iter: int = 2000) -> list[int]:
	"""2-Opt for an open path.

	If fixed_start=True, the first element is kept fixed.
	"""
	n = len(order)
	if n <= 3:
		return order

	best = order[:]
	best_cost = path_cost(cost, best)

	# For open paths, 2-opt reverses a segment (i..k)
	# We avoid i=0 when fixed_start.
	start_i = 1 if fixed_start else 0

	improved = True
	iters = 0
	while improved and iters < max_iter:
		improved = False
		iters += 1

		for i in range(start_i, n - 2):
			for k in range(i + 1, n - 1):
				if k - i < 1:
					continue

				candidate = best[:i] + list(reversed(best[i:k + 1])) + best[k + 1:]
				cand_cost = path_cost(cost, candidate)
				if cand_cost + 1e-9 < best_cost:
					best = candidate
					best_cost = cand_cost
					improved = True
					break
			if improved:
				break

	return best


def optimize_order_from_durations(
	durations_s: list[list[float | None]],
	*,
	fixed_start_index: int | None = 0,
	fixed_end_index: int | None = None,
) -> OptimizeResult:
	"""Optimize visit order using durations matrix."""
	cost = _to_cost_matrix(durations_s)
	validate_full_matrix(cost)
	n = cost.shape[0]
	if n <= 1:
		return OptimizeResult(order=list(range(n)), total_cost=0.0)

	end = None
	if fixed_end_index is not None:
		end = max(0, min(int(fixed_end_index), n - 1))

	if fixed_start_index is None:
		# No true start point: pick a stable, "central" start.
		# If an end is fixed, avoid choosing the same node as start.
		fixed_start = False
		if n == 0:
			start = 0
		elif end is None:
			start = choose_central_start(cost)
		else:
			row_sums = cost.sum(axis=1)
			candidates = [i for i in range(n) if i != end]
			start = int(min(candidates, key=lambda i: float(row_sums[i])))
	else:
		start = max(0, min(int(fixed_start_index), n - 1))
		fixed_start = True

	if end is not None and end == start:
		end = None

	nn = nearest_neighbor_path(cost, start=start, end=end)
	improved = two_opt_improve(cost, nn, fixed_start=fixed_start)
	return OptimizeResult(order=improved, total_cost=path_cost(cost, improved))
