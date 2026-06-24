"""SRI Node Normalizer client + clique-based reconciliation.

This module is where the feeds are made comparable. MEDIC, DAKP, and dismech were
each normalized differently, so we re-resolve every CURIE through one Node
Normalizer pass (conflation on) so they land in the same identifier space and
collapse to the clique's preferred CURIE. With conflation on, the preferred id is
already MONDO-centric for diseases (MONDO when a MONDO is in the clique), so no
separate de-conflation step is needed.

Responses are cached to a JSON file so repeat builds (and the test suite) don't
re-hit the service.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import httpx

DEFAULT_ENDPOINT = "https://nodenormalization-sri.renci.org/get_normalized_nodes"
BATCH = 500


@dataclass
class Clique:
    """A Node Normalizer clique (or a singleton fallback when unresolved)."""

    queried: str
    preferred_id: str
    preferred_label: str
    equivalent_ids: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    resolved: bool = True


def _singleton(curie: str) -> Clique:
    return Clique(curie, curie, curie, [curie], [], resolved=False)


class NodeNorm:
    """Batched, cached Node Normalizer lookups."""

    def __init__(
        self,
        cache_path: str | Path,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        conflate: bool = True,
        drug_chemical_conflate: bool = True,
        timeout: float = 60.0,
    ):
        self.cache_path = Path(cache_path)
        self.endpoint = endpoint
        self.conflate = conflate
        self.drug_chemical_conflate = drug_chemical_conflate
        self.timeout = timeout
        self._cache: dict[str, dict | None] = {}
        if self.cache_path.exists():
            self._cache = json.loads(self.cache_path.read_text())

    # -- cache I/O -------------------------------------------------------------
    def save(self) -> None:
        self.cache_path.write_text(json.dumps(self._cache))

    # -- network ---------------------------------------------------------------
    def _fetch(self, curies: list[str]) -> None:
        """Populate the cache for any of ``curies`` not already present."""
        missing = [c for c in curies if c not in self._cache]
        if not missing:
            return
        with httpx.Client(timeout=self.timeout) as client:
            for i in range(0, len(missing), BATCH):
                chunk = missing[i : i + BATCH]
                resp = client.post(
                    self.endpoint,
                    json={
                        "curies": chunk,
                        "conflate": self.conflate,
                        "drug_chemical_conflate": self.drug_chemical_conflate,
                        "description": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                for c in chunk:
                    self._cache[c] = data.get(c)  # may be None (unresolved)

    def warm(self, curies: Iterable[str]) -> None:
        """Resolve every CURIE in ``curies`` (network only for cache misses)."""
        self._fetch(sorted(set(curies)))
        self.save()

    # -- resolution ------------------------------------------------------------
    def clique(self, curie: str) -> Clique:
        raw = self._cache.get(curie, "__absent__")
        if raw == "__absent__":
            self._fetch([curie])
            raw = self._cache.get(curie)
        if not raw:
            return _singleton(curie)
        pid = raw["id"]["identifier"]
        plabel = raw["id"].get("label", pid)
        eqs = [e["identifier"] for e in raw.get("equivalent_identifiers", [])]
        return Clique(curie, pid, plabel, eqs, raw.get("type", []), resolved=True)
