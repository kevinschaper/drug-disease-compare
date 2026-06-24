"""Map a raw edge's CURIEs onto canonical comparison keys.

Both drugs and diseases collapse to the clique-preferred CURIE. Node Normalizer
(with conflation on) already makes MONDO the preferred id whenever a MONDO is in
the clique, so the disease axis is MONDO-centric by construction; terms with no
MONDO equivalent (typically HP) keep their preferred CURIE.
"""
from __future__ import annotations

from dataclasses import dataclass

from .mondo import MondoGraph
from .nodenorm import NodeNorm


def prefix(curie: str) -> str:
    return curie.split(":", 1)[0]


# biolink types that mark a node as a drug/chemical (vs a procedure, gene, disease…)
DRUG_TYPES = {
    "biolink:ChemicalEntity", "biolink:SmallMolecule", "biolink:Drug",
    "biolink:MolecularMixture", "biolink:ChemicalMixture", "biolink:MolecularEntity",
    "biolink:ComplexMolecularMixture", "biolink:NucleicAcidEntity", "biolink:Polypeptide",
}
# prefixes we treat as drug-like when the Node Normalizer can't resolve the CURIE
DRUG_PREFIXES = {
    "CHEBI", "DRUGBANK", "RXCUI", "UNII", "PUBCHEM.COMPOUND",
    "CHEMBL.COMPOUND", "KEGG.COMPOUND", "DrugCentral",
}


@dataclass
class DrugResolution:
    original: str
    canonical: str
    label: str
    unii: str = ""   # FDA UNII from the clique, for precise openFDA label matching


@dataclass
class DiseaseResolution:
    original: str
    canonical: str
    label: str
    canonical_prefix: str       # MONDO | HP | UMLS | ...
    resolved: bool               # Node Normalizer recognised the CURIE


class Reconciler:
    def __init__(self, nn: NodeNorm, mondo: MondoGraph, node_labels: dict[str, str] | None = None):
        self.nn = nn
        self.mondo = mondo
        self.node_labels = node_labels or {}
        self._drug: dict[str, DrugResolution] = {}
        self._disease: dict[str, DiseaseResolution] = {}

    def _label(self, curie: str, clique_label: str) -> str:
        if curie.startswith("MONDO:"):
            lbl = self.mondo.label(curie)
            if lbl and lbl != curie:
                return lbl
        return self.node_labels.get(curie) or clique_label or curie

    def is_drug(self, curie: str) -> bool:
        """True if the CURIE normalizes to a drug/chemical (not a procedure, etc.).

        Used to keep only the drug subset of feeds whose treatment edges mix drugs
        with non-drug modalities (e.g. dismech's MAXO medical actions, NCIT
        procedures). MEDIC/DAKP subjects are all drugs, so this passes them through.
        """
        c = self.nn.clique(curie)
        if c.resolved and c.types:
            return any(t in DRUG_TYPES for t in c.types)
        return prefix(curie) in DRUG_PREFIXES

    def drug(self, curie: str) -> DrugResolution:
        if curie not in self._drug:
            c = self.nn.clique(curie)
            unii = next((e.split(":", 1)[1] for e in [c.preferred_id, *c.equivalent_ids]
                         if e.startswith("UNII:")), "")
            self._drug[curie] = DrugResolution(
                original=curie,
                canonical=c.preferred_id,
                label=self._label(c.preferred_id, c.preferred_label),
                unii=unii,
            )
        return self._drug[curie]

    def disease(self, curie: str) -> DiseaseResolution:
        if curie in self._disease:
            return self._disease[curie]
        c = self.nn.clique(curie)
        # NodeNorm already prefers the clique's MONDO when one exists, so the
        # preferred id is the canonical disease key (MONDO-centric by construction).
        canonical = c.preferred_id
        self._disease[curie] = DiseaseResolution(
            original=curie,
            canonical=canonical,
            label=self._label(canonical, c.preferred_label),
            canonical_prefix=prefix(canonical),
            resolved=c.resolved,
        )
        return self._disease[curie]
