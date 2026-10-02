"""Warm the GSRS active-moiety cache for every UNII in the FDA label index.

The moiety map otherwise only covers UNIIs that appear in the sources' own drug cliques, so
a label carrying a *salt* UNII (gemcitabine hydrochloride) can't be tied back to its parent
drug (gemcitabine). Shares data/drug_groups_cache.json with the build; resumable.

Run:  uv run python -m experiments.label_moieties
"""
from __future__ import annotations

import gzip
import json
from concurrent.futures import ThreadPoolExecutor

from drug_edge_compare.drug_groups import _Cache, _Clients, _Transient

from experiments.audit_sample import GROUP_CACHE
from experiments.label_index import FDA_INDEX


def main() -> None:
    with gzip.open(FDA_INDEX, "rt") as f:
        uniis = sorted(json.load(f))
    clients = _Clients(_Cache(GROUP_CACHE))
    todo = [u for u in uniis if not clients.cache.has(f"gsrs:moiety:{u}")]
    print(f"{len(uniis)} label UNIIs, {len(todo)} need a moiety lookup", flush=True)

    def one(u):
        try:
            clients.gsrs_active_moiety(u)
            return None
        except _Transient:
            return u

    for attempt in range(3):
        with ThreadPoolExecutor(16) as ex:
            todo = [u for u in ex.map(one, todo) if u]
        clients.save()
        print(f"  pass {attempt + 1}: {len(todo)} transient failures left", flush=True)
        if not todo:
            break


if __name__ == "__main__":
    main()
