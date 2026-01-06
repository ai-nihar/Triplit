from dataclasses import dataclass


@dataclass(frozen=True)
class Place:
    name: str
    lat: float | None = None
    lon: float | None = None
    address: str | None = None
