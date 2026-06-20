"""Pluggable drug-axis collapse: group distinct drug CURIEs that are "the same drug".

This is an **experiment-layer** concern, deliberately kept out of the core
comparison. The Node Normalizer (correctly) keeps a prodrug separate from its
active moiety, a salt separate from its parent, and a CHEBI record separate from a
UNII record it can't equate — so MEDIC's ``CHEBI:70746`` (dabigatran etexilate) and
DAKP's ``CHEBI:70752`` (dabigatran) never match, even though both are "Pradaxa".

Collapsing those two into one drug is an inference **we** make, not an assertion
either source makes. So this module never rewrites a source's edge: it only assigns
each canonical drug CURIE a ``group_id`` under a chosen authority. The caller decides
what to do with shared group_ids (the comparison treats a same-group match as a
drug-axis *related*, mirroring the disease-axis is-a *related* — see compare.py).

Three interchangeable authorities, so we can compare what each merges before
committing to one (none is obviously right; they trade coverage for aggressiveness):

* ``active_moiety``        -- FDA/GSRS ACTIVE MOIETY. Collapses salts, esters,
                              prodrugs, stereoisomers to the therapeutic moiety.
                              Pivots on UNII (recovered via RxNorm when a clique has
                              none). Most aggressive; authoritative for "same drug
                              therapeutically".
* ``rxnorm_ingredient``    -- RxNorm ingredient (IN). Collapses salts/forms, but NOT
                              prodrug->moiety; cannot group UNII-only cliques
                              (RxNorm has no reverse UNII->RXCUI lookup here).
* ``chebi_functional_parent`` -- ChEBI ``has_functional_parent`` (via EBI OLS).
                              Collapses within ChEBI only; blind to UNII-only drugs.

Every lookup is cached to one JSON file so reruns (and the test suite) are offline.
Negative results are cached too, so dead ends aren't re-fetched.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx

from .nodenorm import Clique

GSRS_BASE = "https://gsrs.ncats.nih.gov/api/v1"
RXNAV_BASE = "https://rxnav.nlm.nih.gov/REST"
OLS_BASE = "https://www.ebi.ac.uk/ols4/api"
_MISS = "__miss__"  # cached sentinel for "looked up, found nothing"


@dataclass
class Grouping:
    """The collapse assignment for one canonical drug CURIE."""

    drug: str            # canonical CURIE (the comparison key the pipeline uses today)
    drug_label: str
    group_id: str        # collapse key; == drug when the drug couldn't be grouped
    group_label: str
    method: str          # "active_moiety" | "ingredient" | "functional_parent" | "self"
    via: str             # the pivot id used to reach the group, for audit

    @property
    def grouped(self) -> bool:
        return self.group_id != self.drug


# --------------------------------------------------------------------------- #
# cached HTTP                                                                  #
# --------------------------------------------------------------------------- #
class _Cache:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._c: dict[str, object] = {}
        if self.path.exists():
            self._c = json.loads(self.path.read_text())

    def get(self, key: str):
        return self._c.get(key, None)

    def has(self, key: str) -> bool:
        return key in self._c

    def put(self, key: str, value) -> None:
        self._c[key] = value if value is not None else _MISS

    def save(self) -> None:
        self.path.write_text(json.dumps(self._c))


def _members(clique: Clique, prefix: str) -> list[str]:
    """Distinct local ids of a given prefix in the clique, preferred-first."""
    seen: list[str] = []
    for cid in [clique.preferred_id, *clique.equivalent_ids]:
        if cid.startswith(prefix + ":"):
            local = cid.split(":", 1)[1]
            if local not in seen:
                seen.append(local)
    return seen


class _Clients:
    """Shared, cached GSRS / RxNav / OLS access. One ``save()`` persists all."""

    def __init__(self, cache: _Cache, *, timeout: float = 30.0):
        self.cache = cache
        self._http = httpx.Client(timeout=timeout, follow_redirects=True,
                                  headers={"Accept": "application/json"})

    def save(self) -> None:
        self.cache.save()

    def _get_json(self, url: str):
        r = self._http.get(url)
        if r.status_code != 200:
            return None
        try:
            return r.json()
        except ValueError:
            return None

    # -- GSRS: UNII -> active-moiety [(UNII, name)] --------------------------
    def gsrs_active_moiety(self, unii: str) -> list[tuple[str, str]]:
        key = f"gsrs:moiety:{unii}"
        if self.cache.has(key):
            v = self.cache.get(key)
            return [] if v == _MISS else [tuple(p) for p in v]
        d = self._get_json(f"{GSRS_BASE}/substances({unii})?view=full")
        out: list[tuple[str, str]] = []
        if d:
            for rel in d.get("relationships", []) or []:
                if (rel.get("type") or "").upper().startswith("ACTIVE MOIETY"):
                    rs = rel.get("relatedSubstance", {}) or {}
                    am = rs.get("approvalID")
                    if am:
                        out.append((am, rs.get("refPname") or am))
        self.cache.put(key, [list(p) for p in out] or None)
        return out

    # -- GSRS: UNII -> molecular formula (for the ion guard) -----------------
    def gsrs_formula(self, unii: str) -> str | None:
        key = f"gsrs:formula:{unii}"
        if self.cache.has(key):
            v = self.cache.get(key)
            return None if v == _MISS else v
        d = self._get_json(f"{GSRS_BASE}/substances({unii})?view=full")
        formula = ((d or {}).get("structure") or {}).get("formula")
        self.cache.put(key, formula)
        return formula

    # -- RxNav: RXCUI -> ingredient (IN) -------------------------------------
    def rxnorm_ingredient(self, rxcui: str) -> tuple[str, str] | None:
        key = f"rxnav:in:{rxcui}"
        if self.cache.has(key):
            v = self.cache.get(key)
            return None if v == _MISS else tuple(v)
        d = self._get_json(f"{RXNAV_BASE}/rxcui/{rxcui}/related.json?tty=IN")
        ing = None
        for grp in (d or {}).get("relatedGroup", {}).get("conceptGroup", []) or []:
            if grp.get("tty") == "IN":
                props = grp.get("conceptProperties") or []
                if len(props) == 1:  # exactly one ingredient; skip combos (MIN)
                    ing = (props[0]["rxcui"], props[0]["name"])
                break
        self.cache.put(key, list(ing) if ing else None)
        return ing

    # -- RxNav: RXCUI -> UNII (to recover a UNII for UNII-less cliques) -------
    def rxnorm_unii(self, rxcui: str) -> str | None:
        key = f"rxnav:unii:{rxcui}"
        if self.cache.has(key):
            v = self.cache.get(key)
            return None if v == _MISS else v
        d = self._get_json(f"{RXNAV_BASE}/rxcui/{rxcui}/allProperties.json?prop=codes")
        unii = None
        for p in (d or {}).get("propConceptGroup", {}).get("propConcept", []) or []:
            if p.get("propName") == "UNII_CODE":
                unii = p.get("propValue")
                break
        self.cache.put(key, unii)
        return unii

    # -- OLS: CHEBI -> has_functional_parent (one hop) -----------------------
    def chebi_functional_parent(self, chebi_local: str) -> str | None:
        key = f"ols:fp:{chebi_local}"
        if self.cache.has(key):
            v = self.cache.get(key)
            return None if v == _MISS else v
        iri = f"http://purl.obolibrary.org/obo/CHEBI_{chebi_local}"
        dbl = quote(quote(iri, safe=""), safe="")
        d = self._get_json(f"{OLS_BASE}/ontologies/chebi/terms/{dbl}/graph")
        parent = None
        for e in (d or {}).get("edges", []) or []:
            if e.get("label") == "has functional parent" and e.get("source", "").endswith(f"CHEBI_{chebi_local}"):
                tgt = e.get("target", "")
                if "CHEBI_" in tgt:
                    parent = "CHEBI:" + tgt.rsplit("CHEBI_", 1)[1]
                    break
        self.cache.put(key, parent)
        return parent


# --------------------------------------------------------------------------- #
# groupers                                                                     #
# --------------------------------------------------------------------------- #
class DrugGrouper(Protocol):
    name: str

    def group(self, clique: Clique) -> Grouping: ...


_FORMULA_TOKEN = __import__("re").compile(r"([A-Z][a-z]?)(\d*)")


def heavy_atoms(formula: str | None) -> int | None:
    """Count non-hydrogen atoms in a molecular formula. None if unparseable.

    The discriminator for bare ions / tiny inorganic moieties (Fe, Zn, K, NO, ...)
    that over-merge therapeutically distinct products: those have <=2 heavy atoms,
    real drug moieties have many.
    """
    if not formula:
        return None
    formula = formula.split(".")[0].split(",")[0].strip()  # take first component of a mixture
    n = 0
    matched = False
    for elem, count in _FORMULA_TOKEN.findall(formula):
        if not elem:
            continue
        matched = True
        if elem == "H":
            continue
        n += int(count) if count else 1
    return n if matched else None


def _self(clique: Clique) -> Grouping:
    return Grouping(clique.preferred_id, clique.preferred_label,
                    clique.preferred_id, clique.preferred_label, "self", "")


class MoietyGrouper:
    """Group by FDA/GSRS active moiety. Pivots on UNII; recovers one from RxNorm
    when the clique carries none (e.g. a CHEBI record with RXCUIs but no UNII)."""

    name = "active_moiety"
    MIN_HEAVY_ATOMS = 3  # reject bare ions / tiny inorganic moieties (Fe, Zn, K, NO, ...)

    def __init__(self, clients: _Clients, *, ion_guard: bool = True):
        self.c = clients
        self.ion_guard = ion_guard

    def _is_ion(self, unii: str) -> bool:
        ha = heavy_atoms(self.c.gsrs_formula(unii))
        return ha is not None and ha < self.MIN_HEAVY_ATOMS

    def _uniis(self, clique: Clique) -> list[str]:
        uniis = _members(clique, "UNII")
        if uniis:
            return uniis
        for rx in _members(clique, "RXCUI"):
            un = self.c.rxnorm_unii(rx)
            if un:
                return [un]
        return []

    def group(self, clique: Clique) -> Grouping:
        uniis = self._uniis(clique)
        if not uniis:
            return _self(clique)
        # each UNII -> its active moiety (UNII, name); a substance with no moiety
        # relationship is its own moiety. Pick the lexically-first for a stable key.
        moieties: dict[str, str] = {}
        for u in uniis:
            am = self.c.gsrs_active_moiety(u)
            for mu, mn in (am or [(u, clique.preferred_label)]):
                moieties[mu] = mn
        if self.ion_guard:
            # drop bare-ion moieties; a drug whose only moiety is an ion (a metal
            # salt) stays its own group rather than merging with every other salt
            # of that ion (ferric citrate vs iron sucrose are different products).
            kept = {mu: mn for mu, mn in moieties.items() if not self._is_ion(mu)}
            moieties = kept
        if not moieties:
            return _self(clique)
        mu = sorted(moieties)[0]
        return Grouping(clique.preferred_id, clique.preferred_label,
                        "UNII:" + mu, moieties[mu], "active_moiety", "UNII:" + uniis[0])


class IngredientGrouper:
    """Group by RxNorm ingredient (IN). Cannot group UNII-only cliques."""

    name = "rxnorm_ingredient"

    def __init__(self, clients: _Clients):
        self.c = clients

    def group(self, clique: Clique) -> Grouping:
        for rx in _members(clique, "RXCUI"):
            ing = self.c.rxnorm_ingredient(rx)
            if ing:
                return Grouping(clique.preferred_id, clique.preferred_label,
                                "RXCUI:" + ing[0], ing[1], "ingredient", "RXCUI:" + rx)
        return _self(clique)


class ChebiFunctionalParentGrouper:
    """Group by ChEBI has_functional_parent, chased to the top (depth-capped).
    Only bridges drugs that both carry a ChEBI id."""

    name = "chebi_functional_parent"
    MAX_HOPS = 5

    def __init__(self, clients: _Clients):
        self.c = clients

    def group(self, clique: Clique) -> Grouping:
        chebis = _members(clique, "CHEBI")
        if not chebis:
            return _self(clique)
        local = chebis[0]
        seen = {local}
        top = local
        for _ in range(self.MAX_HOPS):
            parent = self.c.chebi_functional_parent(top)
            if not parent:
                break
            pl = parent.split(":", 1)[1]
            if pl in seen:
                break
            seen.add(pl)
            top = pl
        if top == local:
            return _self(clique)
        return Grouping(clique.preferred_id, clique.preferred_label,
                        "CHEBI:" + top, "CHEBI:" + top, "functional_parent", "CHEBI:" + local)


def make_groupers(cache_path: str | Path) -> tuple[_Clients, list[DrugGrouper]]:
    clients = _Clients(_Cache(cache_path))
    return clients, [
        MoietyGrouper(clients),
        IngredientGrouper(clients),
        ChebiFunctionalParentGrouper(clients),
    ]


def moiety_grouper(cache_path: str | Path, *, ion_guard: bool = True) -> tuple[_Clients, MoietyGrouper]:
    """The production grouper: active moiety with the bare-ion guard on.

    Returns ``(clients, grouper)``; call ``clients.save()`` after grouping to
    persist any newly-fetched lookups to the cache file.
    """
    clients = _Clients(_Cache(cache_path))
    return clients, MoietyGrouper(clients, ion_guard=ion_guard)
